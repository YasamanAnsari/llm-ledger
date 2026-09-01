"""Validator tests: every rule gets at least one failing fixture."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import validate

TODAY = date(2026, 8, 25)


def _org(**overrides):
    row = {
        "org_id": "acme", "canonical_name": "Acme", "short_name": "Acme",
        "aliases": "", "parent_org_id": "", "country": "US",
        "org_type": "ai_lab", "is_active": "true", "epoch_org_name": "",
        "notes": "",
    }
    row.update(overrides)
    return row


def _model(**overrides):
    row = {
        "model_id": "acme-1", "canonical_name": "Acme 1", "family": "Acme",
        "variant_role": "base", "developer_org_id": "acme",
        "developing_lab": "", "co_developer_org_ids": "", "model_type": "llm",
        "access_type": "api_only", "license": "proprietary",
        "license_family": "proprietary", "license_has_usage_thresholds": "false",
        "license_requires_separate_agreement": "false", "is_derivative": "false",
        "derivative_type": "", "base_model_id": "", "parent_model_id": "",
        "snapshot_of": "", "predecessor_id": "", "successor_id": "",
        "first_public_availability_date": "", "first_availability_via": "",
        "anticipation_days": "", "review_status": "unreviewed",
        "record_created": "2026-01-01T00:00:00+00:00",
        "record_updated": "2026-01-01T00:00:00+00:00", "notes": "",
    }
    row.update(overrides)
    return row


def _event(**overrides):
    row = {
        "event_id": "acme-1-api_ga-1", "model_id": "acme-1",
        "event_type": "api_ga", "date": "2025-01-15", "precision": "day",
        "region": "global", "platform": "", "detail": "",
        "source_url": "https://example.com/blog", "source_type": "vendor_blog",
        "confidence": "inferred", "verified_by": "", "verified_date": "",
        "notes": "",
    }
    row.update(overrides)
    return row


def _tables(orgs=None, models=None, events=None, crosswalk=None, attributes=None,
            claims=None):
    return {
        "organizations": orgs if orgs is not None else [_org()],
        "models": models if models is not None else [_model()],
        "events": events if events is not None else [_event()],
        "claims": claims or [],
        "crosswalk": crosswalk or [],
        "attributes": attributes or [],
    }


def _errors(tables):
    errors, _ = validate.validate_tables(tables, TODAY, check_determinism=False)
    return errors


def test_clean_fixture_passes():
    assert _errors(_tables()) == []


def test_rule1_duplicate_pk():
    tables = _tables(events=[_event(), _event()])
    assert any("duplicate PK" in e for e in _errors(tables))


def test_rule1_unresolved_fk():
    tables = _tables(events=[_event(model_id="ghost", event_id="ghost-api_ga-1")])
    assert any("unknown model_id" in e for e in _errors(tables))


def test_rule2_missing_source_url():
    tables = _tables(events=[_event(source_url="")])
    assert any("rule2" in e and "source_url" in e for e in _errors(tables))


def test_rule3_month_precision_requires_day_one():
    tables = _tables(events=[_event(date="2025-01-15", precision="month")])
    assert any("rule3" in e for e in _errors(tables))
    ok = _tables(events=[_event(date="2025-01-01", precision="month")])
    assert not any("rule3" in e for e in _errors(ok))


def test_rule4_announced_after_api_ga():
    events = [
        _event(event_id="acme-1-announced-1", event_type="announced", date="2025-02-01"),
        _event(event_id="acme-1-api_ga-1", event_type="api_ga", date="2025-01-15"),
    ]
    assert any("rule4" in e for e in _errors(_tables(events=events)))


def test_rule4_future_event_fails_but_future_retired_warns():
    bad = _tables(events=[_event(date="2027-01-01")])
    assert any("rule4" in e and "future" in e for e in _errors(bad))

    retired = _tables(events=[_event(
        event_id="acme-1-retired-1", event_type="retired", date="2027-01-01",
        source_type="deprecation_page")])
    errors, warnings = validate.validate_tables(retired, TODAY, check_determinism=False)
    assert not any("rule4" in e for e in errors)
    assert any("retired" in w for w in warnings)


def test_rule5_disputed_needs_notes_verified_needs_attribution():
    disputed = _tables(events=[_event(confidence="disputed", notes="")])
    assert any("rule5" in e for e in _errors(disputed))
    verified = _tables(events=[_event(confidence="verified")])
    assert sum("rule5" in e for e in _errors(verified)) == 2  # by + date


def test_rule6_model_without_events():
    tables = _tables(models=[_model(), _model(model_id="acme-2")])
    assert any("rule6" in e and "acme-2" in e for e in _errors(tables))


def test_rule7_lineage_cycle():
    models = [
        _model(model_id="a", parent_model_id="b"),
        _model(model_id="b", parent_model_id="a"),
    ]
    events = [
        _event(event_id="a-api_ga-1", model_id="a"),
        _event(event_id="b-api_ga-1", model_id="b"),
    ]
    assert any("rule7" in e for e in _errors(_tables(models=models, events=events)))


def test_rule8_vocab_and_platform_contract():
    bad_vocab = _tables(events=[_event(event_type="launched", event_id="acme-1-launched-1")])
    assert any("rule8" in e for e in _errors(bad_vocab))

    missing_platform = _tables(events=[_event(
        event_id="acme-1-platform_availability-1",
        event_type="platform_availability")])
    assert any("requires platform" in e for e in _errors(missing_platform))

    # A retirement scoped to one platform is legitimate.
    scoped_retirement = _tables(events=[_event(
        event_id="acme-1-retired-1", event_type="retired", platform="aws_bedrock",
        date="2025-06-01")])
    assert not any("rule8" in e for e in _errors(scoped_retirement))


def test_rule4_availability_long_before_announcement_is_an_error() -> None:
    def events(gap_days):
        return [
            _event(event_id="acme-1-announced-1", event_type="announced", date="2025-03-01"),
            _event(event_id="acme-1-weights_released-1", event_type="weights_released",
                   date=(date(2025, 3, 1) - __import__("datetime").timedelta(days=gap_days)).isoformat()),
        ]
    errors, warnings = validate.validate_tables(
        _tables(events=events(45)), TODAY, check_determinism=False)
    assert any("precedes announced" in e for e in errors)
    errors, warnings = validate.validate_tables(
        _tables(events=events(5)), TODAY, check_determinism=False)
    assert not any("precedes announced" in e for e in errors)
    assert any("precedes announced" in w for w in warnings)


def test_rule1_and_rule8_claims_table() -> None:
    orphan = {"event_id": "nope", "source_url": "https://models.dev/api.json",
              "source_type": "api_metadata", "date": "2025-01-15", "precision": "day",
              "label": "", "bound": "false", "first_party": "false"}
    assert any("claims references unknown event_id" in e for e in _errors(_tables(claims=[orphan])))
    bad = dict(orphan, event_id="acme-1-api_ga-1", bound="maybe", date="2025-1-1")
    errs = _errors(_tables(claims=[bad]))
    assert any("bound" in e for e in errs) and any("not ISO" in e for e in errs)


def test_rule8_review_status_required() -> None:
    assert any("review_status" in e for e in _errors(_tables(models=[_model(review_status="")])))


def test_rule8_event_id_format():
    tables = _tables(events=[_event(event_id="wrong-format")])
    assert any("does not follow" in e for e in _errors(tables))


def test_rule10_epoch_columns_blocked():
    errors = validate.check_rule10_no_epoch_columns({})
    assert errors == []  # real schema carries no Epoch-domain columns
