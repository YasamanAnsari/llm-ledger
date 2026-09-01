"""Tests for the shared confidence policy."""

from __future__ import annotations

from datetime import date

from confidence import Claim, assess, upsert_machine_event

MD = "https://models.dev/api.json"
OR = "https://openrouter.ai/api/v1/models"
OAI = "https://api.openai.com/v1/models"
HF = "https://huggingface.co/org/repo"
WB = "https://web.archive.org/web/2025/https://huggingface.co/org/repo"
TODAY = date(2026, 9, 1)


def _c(day: str, url: str, **kw) -> Claim:
    return Claim(date.fromisoformat(day), url, kw.pop("source_type", "api_metadata"), **kw)


def test_single_aggregator_claim_is_inferred() -> None:
    a = assess([_c("2025-01-20", MD)])
    assert (a.confidence, a.date, a.verified_by) == ("inferred", "2025-01-20", "")


def test_single_first_party_claim_is_verified_by_project() -> None:
    a = assess([_c("2025-01-20", OR, first_party=True)])
    assert (a.confidence, a.verified_by) == ("verified", "llm-ledger")


def test_two_hosts_agreeing_are_verified_and_earliest_wins() -> None:
    a = assess([_c("2025-01-22", OR), _c("2025-01-20", MD)])
    assert (a.confidence, a.date, a.source_url) == ("verified", "2025-01-20", MD)
    assert "corroborated within 2d" in a.notes


def test_first_party_date_wins_over_earlier_aggregator() -> None:
    a = assess([_c("2025-01-18", MD), _c("2025-01-20", OR, first_party=True)])
    assert (a.date, a.source_url, a.confidence) == ("2025-01-20", OR, "verified")


def test_same_host_twice_is_still_one_source() -> None:
    a = assess([_c("2025-01-20", MD), _c("2025-01-21", MD + "?x")])
    assert a.confidence == "inferred"


def test_wide_disagreement_is_disputed_with_all_claims_in_notes() -> None:
    a = assess([_c("2025-01-01", MD), _c("2025-03-15", OR)])
    assert (a.confidence, a.date) == ("disputed", "2025-01-01")
    assert "models.dev 2025-01-01" in a.notes and "openrouter.ai 2025-03-15" in a.notes


def test_middling_gap_stays_inferred() -> None:
    a = assess([_c("2025-01-01", MD), _c("2025-01-15", OR)])
    assert a.confidence == "inferred" and "differ by 14d" in a.notes


def test_human_claim_wins_over_everything() -> None:
    a = assess([_c("2025-01-01", MD), _c("2025-03-01", OR, first_party=True),
                _c("2025-02-10", "https://openai.com/blog/x", source_type="vendor_blog",
                   verified_by="Yasaman Ansari")])
    assert (a.confidence, a.date, a.verified_by) == ("verified", "2025-02-10", "Yasaman Ansari")
    assert "other claims" in a.notes


def test_bounds_use_the_tight_window() -> None:
    hub = _c("2024-07-16", HF, source_type="hf_hub", bound=True)
    capture_far = _c("2024-07-23", WB, source_type="wayback", bound=True)
    assert assess([hub, capture_far]).confidence == "inferred"
    capture_near = _c("2024-07-17", WB, source_type="wayback", bound=True)
    a = assess([hub, capture_near])
    assert (a.confidence, a.date, a.source_type) == ("verified", "2024-07-16", "hf_hub")


def test_registry_timestamp_corroborates_but_does_not_set_the_date() -> None:
    # OpenAI registered gpt-4o-mini two days before launch; models.dev has
    # the launch day. The stated date wins, the bound only corroborates.
    a = assess([_c("2024-07-16", OAI, bound=True), _c("2024-07-18", MD)])
    assert (a.confidence, a.date, a.source_url) == ("verified", "2024-07-18", MD)
    # Registered 16 days early (gpt-5.6 family): stated date kept, not verified.
    a = assess([_c("2026-06-23", OAI, bound=True), _c("2026-07-09", MD)])
    assert (a.confidence, a.date) == ("inferred", "2026-07-09")
    assert assess([_c("2024-07-16", OAI, bound=True)]).confidence == "inferred"


def test_year_placeholder_never_beats_a_day_claim() -> None:
    placeholder = _c("2024-01-01", MD, precision="year")
    hub = _c("2025-04-07", HF, source_type="hf_hub", bound=True)
    a = assess([placeholder, hub])
    assert (a.date, a.precision, a.confidence) == ("2025-04-07", "day", "disputed")
    same_year = _c("2025-01-01", MD, precision="year")
    a = assess([same_year, hub])
    assert (a.date, a.confidence) == ("2025-04-07", "inferred")
    assert assess([placeholder]).precision == "year"


def test_upsert_merges_claims_across_loaders_and_is_idempotent() -> None:
    events, index, claims = [], {}, {}
    ids = iter(("m-weights_released-1",))

    def next_id(*_):
        return next(ids)

    hub = [_c("2025-09-22", HF, source_type="hf_hub", bound=True)]
    md = [_c("2025-09-22", MD)]
    assert upsert_machine_event(events, index, claims, "m", "weights_released", hub, TODAY,
                                next_id=next_id) == "added"
    assert events[0]["confidence"] == "inferred"
    assert upsert_machine_event(events, index, claims, "m", "weights_released", md, TODAY) == "updated"
    assert (events[0]["confidence"], events[0]["source_url"]) == ("verified", MD)
    # Each loader re-running sees the other's claim and changes nothing.
    assert upsert_machine_event(events, index, claims, "m", "weights_released", hub, TODAY) == "unchanged"
    assert upsert_machine_event(events, index, claims, "m", "weights_released", md, TODAY) == "unchanged"
    assert len(claims["m-weights_released-1"]) == 2


def test_upsert_withdraws_claims_before_curated_announcement() -> None:
    events, index, claims = [], {}, {}
    early = [_c("2026-06-13", HF, source_type="hf_hub", bound=True)]
    outcome = upsert_machine_event(events, index, claims, "m", "weights_released", early, TODAY,
                                   not_before=date(2026, 7, 16), next_id=lambda *_: "x")
    assert outcome == "precreated" and not events


def test_upsert_never_touches_curated_rows() -> None:
    curated = {"event_id": "m-api_ga-1", "model_id": "m", "event_type": "api_ga",
               "platform": "", "date": "2025-01-01", "source_type": "vendor_blog"}
    events, index = [curated], {("m", "api_ga", ""): curated}
    assert upsert_machine_event(events, index, {}, "m", "api_ga", [_c("2025-02-01", MD)],
                                TODAY) == "skipped"
    assert curated["date"] == "2025-01-01"
