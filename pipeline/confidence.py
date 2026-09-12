"""One confidence policy for every machine-dated claim in the ledger.

Loaders collect the claims they have for one (model, event_type) and call
`assess`. The policy:

- a human-checked primary source wins outright (confidence=verified,
  verified_by=the person);
- a single machine claim is `inferred`, unless it is the vendor's or the
  platform's own timestamp for its own event (`first_party`), which is
  `verified` by llm-ledger; a first-party stated date also outranks any
  third-party date (a mirror that differs is noted, never a dispute);
- two or more independent machine claims (distinct source hosts) that agree
  within AGREE_DAYS are `verified` by llm-ledger;
- stated claims that spread over more than DISPUTE_DAYS are `disputed`;
- anything in between stays `inferred`.

The chosen date is the first-party claim when there is one, else the
earliest. Every other claim is written into notes so nothing is lost.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from urllib.parse import urlparse

# Two sources agree when their dates sit this close: it absorbs the UTC vs
# local-day offset of a launch, nothing more. For a bracketing timestamp
# (repo/registry creation, first crawl) a wider gap means the artifact was
# pre-staged and says nothing about the launch day.
AGREE_DAYS = 2
DISPUTE_DAYS = 30
PROJECT_VERIFIER = "llm-ledger"
AGENT_VERIFIER = "llm-ledger-agent"   # rows the LLM agent extracted from a page
PROJECT_VERIFIERS = {PROJECT_VERIFIER, AGENT_VERIFIER}

# Rows with these source types are owned by the loaders and re-assessed on
# every run. Any other source type means a person curated the row: never
# touched by machine code.
MACHINE_SOURCE_TYPES = {"hf_hub", "modelscope", "api_metadata", "lifecycle_table"}


@dataclass(frozen=True)
class Claim:
    date: date
    source_url: str
    source_type: str
    # The source is the vendor/platform reporting its own event
    # (OpenAI `created` for an OpenAI API model, OpenRouter `created` for an
    # OpenRouter listing). Hub `createdAt` is NOT first-party for a public
    # weights release: it measures repo creation, which may be private.
    first_party: bool = False
    # A named person opened a primary source. `verified_by` is required.
    verified_by: str = ""
    # The timestamp brackets the event rather than stating it: repo/model
    # registry creation (at or before release), first public crawl (at or
    # after). Bounds corroborate a stated date but are only chosen as the
    # date when no stated claim exists.
    bound: bool = False
    # "day" or "year" (a catalog Jan-1 placeholder). Year claims never set
    # the day and never dispute a day claim in the same year.
    precision: str = "day"
    label: str = ""  # short source name for notes, e.g. "models.dev"


@dataclass(frozen=True)
class Assessment:
    date: str
    precision: str
    confidence: str
    source_url: str
    source_type: str
    verified_by: str
    notes: str


def _host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def _describe(claims: list) -> str:
    parts = [f"{c.label or _host(c.source_url)} {c.date.isoformat()}"
             for c in sorted(claims, key=lambda c: (c.date, c.source_url))]
    return "; ".join(parts)


# Among bounds, the artifact's own timestamp is the row's date; a twin repo
# elsewhere or a crawl of the page corroborates it (or widens the spread)
# but does not replace it.
SECONDARY_BOUND_SOURCES = {"modelscope", "wayback"}


def _rank(c: Claim) -> tuple:
    """Preference for the row's date: stated day > bracketing day > year
    placeholder; among bounds the artifact's own timestamp beats a twin
    repo or a crawl of it; first-party first; then earliest."""
    return (c.precision != "day", c.bound, c.source_type in SECONDARY_BOUND_SOURCES,
            not c.first_party, c.date)


def assess(claims: list) -> Assessment:
    """Combine claims for one event into a dated, confidence-rated row."""
    if not claims:
        raise ValueError("assess() needs at least one claim")

    human = [c for c in claims if c.verified_by]
    if human:
        best = min(human, key=lambda c: c.date)
        others = [c for c in claims if c is not best]
        notes = f"other claims: {_describe(others)}" if others else ""
        return Assessment(best.date.isoformat(), best.precision, "verified",
                          best.source_url, best.source_type, best.verified_by, notes)

    # One claim per independent host; the earliest from each host counts.
    by_host: dict = {}
    for c in claims:
        host = _host(c.source_url)
        if host not in by_host or c.date < by_host[host].date:
            by_host[host] = c
    independent = list(by_host.values())
    best = min(independent, key=_rank)

    def result(confidence: str, notes: str) -> Assessment:
        verifier = PROJECT_VERIFIER if confidence == "verified" else ""
        return Assessment(best.date.isoformat(), best.precision, confidence,
                          best.source_url, best.source_type, verifier, notes)

    if len(independent) == 1:
        if best.first_party:
            return result("verified", f"first-party: {_describe([best])}")
        return result("inferred", f"single source: {_describe([best])}")

    # Day-precision claims are compared to the day; a year placeholder only
    # disputes when it names a different year. Bounds (repo/registry
    # creation, first crawl) corroborate when close; one that trails the
    # chosen date by more than AGREE_DAYS is lag (a late crawl, a mirror
    # created months later) and says nothing. A bound that LEADS the chosen
    # date stays in: the artifact may have been public there first. Only
    # stated dates dispute.
    comparable = [c for c in independent if c.precision == "day"] or independent
    comparable = [c for c in comparable
                  if not c.bound or (c.date - best.date).days <= AGREE_DAYS]
    spread = (max(c.date for c in comparable) - min(c.date for c in comparable)).days
    stated_day = [c for c in comparable if not c.bound]
    stated_spread = ((max(c.date for c in stated_day) - min(c.date for c in stated_day)).days
                     if len(stated_day) >= 2 else 0)
    year_conflict = any(c.precision == "year" and c.date.year != best.date.year
                        for c in independent)
    # The source reporting its own event (a platform's retirement table, a
    # registry's own listing date) is authoritative for it. A third-party
    # date that differs is a stale or wrong transcription, not a peer
    # opinion: it is noted, never a dispute. Two first-party claims can
    # still dispute each other.
    others = [c for c in independent if c is not best]
    if (best.first_party and not best.bound and best.precision == "day"
            and not any(c.first_party for c in others)):
        agree = [c for c in others if abs((c.date - best.date).days) <= AGREE_DAYS]
        differ = [c for c in others if c not in agree]
        notes = f"first-party: {_describe([best])}"
        notes += f"; agrees: {_describe(agree)}" if agree else ""
        notes += f"; differs: {_describe(differ)}" if differ else ""
        return result("verified", notes)
    if year_conflict or stated_spread > DISPUTE_DAYS:
        return result("disputed", f"sources disagree; kept "
                                  f"{'first-party' if best.first_party else 'best-evidenced'} "
                                  f"claim: {_describe(independent)}")
    if len(comparable) >= 2 and spread <= AGREE_DAYS:
        return result("verified", f"corroborated within {spread}d: {_describe(independent)}")
    if len(comparable) < 2:
        return result("inferred", f"single source, later bounds are lag: {_describe(independent)}")
    return result("inferred", f"claims differ by {spread}d: {_describe(independent)}")


def is_machine_row(row: dict) -> bool:
    return row.get("source_type", "") in MACHINE_SOURCE_TYPES


def curated_model_ids(events: list) -> set:
    """Models with a verified event that was read from a primary page rather
    than produced by a loader. Loaders never rewrite these models' curated
    fields; everything else is machine-owned and re-derived on every run."""
    return {e["model_id"] for e in events
            if e.get("confidence") == "verified" and not is_machine_row(e)}


def claim_to_row(event_id: str, c: Claim) -> dict:
    return {
        "event_id": event_id, "source_url": c.source_url,
        "source_type": c.source_type, "date": c.date.isoformat(),
        "precision": c.precision, "label": c.label,
        "bound": str(c.bound).lower(), "first_party": str(c.first_party).lower(),
    }


def claim_from_row(row: dict) -> Claim:
    return Claim(
        date=date.fromisoformat(row["date"]), source_url=row["source_url"],
        source_type=row["source_type"], first_party=row["first_party"] == "true",
        bound=row["bound"] == "true", precision=row["precision"], label=row["label"],
    )


def index_events(events: list) -> dict:
    """(model_id, event_type, platform) -> event row; the lookup every
    loader hands to upsert_machine_event and keeps in sync through it."""
    return {(e["model_id"], e["event_type"], e.get("platform", "")): e for e in events}


def group_claims(rows: list) -> dict:
    """event_id -> [claim rows]; the in-memory form loaders work with."""
    grouped: dict = {}
    for row in rows:
        grouped.setdefault(row["event_id"], []).append(row)
    return grouped


def flatten_claims(grouped: dict) -> list:
    return [row for rows in grouped.values() for row in rows]


def _remove_event(events: list, index: dict, claims_by_event: dict, row: dict) -> None:
    events.remove(row)
    del index[(row["model_id"], row["event_type"], row.get("platform", ""))]
    claims_by_event.pop(row["event_id"], None)


def withdraw_machine_event(events: list, index: dict, claims_by_event: dict, model_id: str,
                           event_type: str, platform: str = "", only_hosts=None) -> bool:
    """Remove the machine row for (model, type, platform). With `only_hosts`,
    remove it only when every claim label starts with one of those names,
    so a row another source also supports is left alone."""
    row = index.get((model_id, event_type, platform))
    if row is None or not is_machine_row(row):
        return False
    if only_hosts is not None:
        labels = [c["label"].split(" (")[0] for c in claims_by_event.get(row["event_id"], [])]
        if not labels or any(label not in only_hosts for label in labels):
            return False
    _remove_event(events, index, claims_by_event, row)
    return True


def curated_announcement(index: dict, model_id: str):
    """Date of the human-curated `announced` event for a model, else None.

    Machine availability claims (Hub repo creation, vendor model-registry
    `created`, catalog release dates) that fall BEFORE this date describe
    private pre-staging, not a release, and are not loaded.
    """
    row = index.get((model_id, "announced", ""))
    if row is None or is_machine_row(row):
        return None
    return date.fromisoformat(row["date"])


AVAILABILITY_TYPES = {"api_ga", "weights_released", "consumer_rollout",
                      "api_preview", "free_tier", "platform_availability"}


def earliest_availability(index: dict, model_id: str):
    """Earliest availability-class date on record for a model, else None."""
    dates = [date.fromisoformat(row["date"]) for (mid, et, _), row in index.items()
             if mid == model_id and et in AVAILABILITY_TYPES]
    return min(dates, default=None)


def withdraw_machine_announced_after(events: list, index: dict, claims_by_event: dict,
                                     model_id: str, availability: date) -> bool:
    """Drop a machine `announced` row that falls after an availability date.

    Aggregator "publication" dates are the earliest of paper/announcement/
    release; one that trails the release is not an announcement.
    """
    row = index.get((model_id, "announced", ""))
    if row is None or not is_machine_row(row) or date.fromisoformat(row["date"]) <= availability:
        return False
    _remove_event(events, index, claims_by_event, row)
    return True


def upsert_machine_event(events: list, index: dict, claims_by_event: dict,
                         model_id: str, event_type: str, claims: list, today: date,
                         platform: str = "", not_before=None, next_id=None,
                         verifier: str = PROJECT_VERIFIER) -> str:
    """Add or refresh the machine-owned event for (model, type, platform).

    New claims replace stored claims from the same host; claims from other
    hosts (contributed by other loaders) are kept, and the event is
    re-assessed from the full set. `verifier` names who signs a machine
    corroboration (the project, or its agent). Returns "added", "updated",
    "unchanged", "skipped" (curated row), "precreated" (every claim predates
    `not_before` or only a crawl remains; nothing was on record) or
    "withdrawn" (same, and the stale machine row was removed). `index` maps
    (model_id, event_type, platform) -> row; both it and `claims_by_event`
    are kept in sync.
    """
    key = (model_id, event_type, platform)
    existing = index.get(key)
    if existing is not None and not is_machine_row(existing):
        return "skipped"

    merged = list(claims)
    if existing is not None:
        new_hosts = {_host(c.source_url) for c in claims}
        merged += [claim_from_row(r) for r in claims_by_event.get(existing["event_id"], [])
                   if _host(r["source_url"]) not in new_hosts]
    if not_before is not None:
        merged = [c for c in merged if c.date >= not_before]
    if not merged or all(c.source_type == "wayback" for c in merged):
        # Nothing left but a crawl: a capture brackets the release from
        # above and cannot date it on its own. The repo was pre-staged.
        if existing is not None:
            _remove_event(events, index, claims_by_event, existing)
            return "withdrawn"
        return "precreated"
    a = assess(merged)
    verified_by = verifier if a.verified_by == PROJECT_VERIFIER else a.verified_by

    fields = {
        "date": a.date, "precision": a.precision, "confidence": a.confidence,
        "source_url": a.source_url, "source_type": a.source_type,
        "verified_by": verified_by, "notes": a.notes,
    }
    if existing is None:
        row = {
            "event_id": next_id(events, model_id, event_type),
            "model_id": model_id, "event_type": event_type,
            "region": "global", "platform": platform, "detail": "",
            "verified_date": today.isoformat() if a.confidence == "verified" else "",
            **fields,
        }
        events.append(row)
        index[key] = row
        claims_by_event[row["event_id"]] = [claim_to_row(row["event_id"], c) for c in merged]
        return "added"

    claim_rows = sorted((claim_to_row(existing["event_id"], c) for c in merged),
                        key=lambda r: r["source_url"])
    changed = (any(existing.get(k, "") != v for k, v in fields.items())
               or sorted(claims_by_event.get(existing["event_id"], []),
                         key=lambda r: r["source_url"]) != claim_rows)
    claims_by_event[existing["event_id"]] = claim_rows
    if not changed:
        return "unchanged"
    existing.update(fields)
    if a.confidence != "verified":
        existing["verified_date"] = ""
    elif not existing.get("verified_date"):
        existing["verified_date"] = today.isoformat()
    return "updated"
