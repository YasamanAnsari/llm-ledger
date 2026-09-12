"""Table surgery for the ledger: merge, rename, delete models and repair
events without breaking a foreign key or a claim.

Pure functions over the dict returned by schema.load_core(); callers write
the tables. Used by the one-time migrations and available to loaders that
must fold a duplicate row into the one that stays.
"""

from __future__ import annotations

from datetime import date

import schema
from confidence import Claim, assess, claim_from_row, claim_to_row, live_claims

MODEL_FK_COLUMNS = ("base_model_id", "parent_model_id", "snapshot_of",
                    "predecessor_id", "successor_id")


def delete_models(tables: dict, model_ids: set) -> int:
    """Remove models with their events, claims, crosswalk and attributes.
    Other models' FK columns pointing at them are blanked."""
    gone_events = {e["event_id"] for e in tables["events"] if e["model_id"] in model_ids}
    before = len(tables["models"])
    tables["models"] = [m for m in tables["models"] if m["model_id"] not in model_ids]
    tables["events"] = [e for e in tables["events"] if e["model_id"] not in model_ids]
    tables["claims"] = [c for c in tables["claims"] if c["event_id"] not in gone_events]
    tables["crosswalk"] = [r for r in tables["crosswalk"] if r["model_id"] not in model_ids]
    tables["attributes"] = [a for a in tables["attributes"] if a["model_id"] not in model_ids]
    for m in tables["models"]:
        for col in MODEL_FK_COLUMNS:
            if m.get(col) in model_ids:
                m[col] = ""
    return before - len(tables["models"])


def rename_model(tables: dict, old: str, new: str) -> None:
    """Give a model a new id; events and claims are re-identified in step."""
    if any(m["model_id"] == new for m in tables["models"]):
        raise ValueError(f"rename target {new} already exists; use merge_models")
    id_map = {}
    for e in tables["events"]:
        if e["model_id"] == old:
            seq = e["event_id"][len(f"{old}-{e['event_type']}-"):]
            id_map[e["event_id"]] = f"{new}-{e['event_type']}-{seq}"
            e["event_id"] = id_map[e["event_id"]]
            e["model_id"] = new
    for c in tables["claims"]:
        c["event_id"] = id_map.get(c["event_id"], c["event_id"])
    for name in ("crosswalk", "attributes"):
        for r in tables[name]:
            if r["model_id"] == old:
                r["model_id"] = new
    for m in tables["models"]:
        if m["model_id"] == old:
            m["model_id"] = new
        for col in MODEL_FK_COLUMNS:
            if m.get(col) == old:
                m[col] = new


def merge_models(tables: dict, keep: str, drop: str) -> None:
    """Fold `drop` into `keep`: crosswalk rows move; attributes move when
    `keep` has none; an event moves when `keep` lacks that (type, platform),
    else it and its claims are dropped; FKs re-point; `drop` is deleted."""
    keep_keys = {(e["event_type"], e["platform"]) for e in tables["events"] if e["model_id"] == keep}
    for e in [e for e in tables["events"] if e["model_id"] == drop]:
        key = (e["event_type"], e["platform"])
        if key in keep_keys:
            continue  # deleted with `drop` below
        new_id = schema.next_event_id(tables["events"], keep, e["event_type"])
        for c in tables["claims"]:
            if c["event_id"] == e["event_id"]:
                c["event_id"] = new_id
        e["event_id"], e["model_id"] = new_id, keep
        keep_keys.add(key)
    existing_xw = {(r["namespace"], r["identifier"])
                   for r in tables["crosswalk"] if r["model_id"] == keep}
    for r in tables["crosswalk"]:
        if r["model_id"] == drop and (r["namespace"], r["identifier"]) not in existing_xw:
            r["model_id"] = keep
    if not any(a["model_id"] == keep for a in tables["attributes"]):
        for a in tables["attributes"]:
            if a["model_id"] == drop:
                a["model_id"] = keep
    for m in tables["models"]:
        for col in MODEL_FK_COLUMNS:
            if m.get(col) == drop:
                m[col] = keep
    delete_models(tables, {drop})


def retag_platform(tables: dict, old: str, new: str) -> int:
    """Rename a platform spelling on every event; returns rows changed."""
    n = 0
    for e in tables["events"]:
        if e["platform"] == old:
            e["platform"] = new
            n += 1
    return n


def detach_crosswalk(tables: dict, model_id: str, namespace: str, identifier: str) -> bool:
    before = len(tables["crosswalk"])
    tables["crosswalk"] = [
        r for r in tables["crosswalk"]
        if (r["model_id"], r["namespace"], r["identifier"]) != (model_id, namespace, identifier)]
    return len(tables["crosswalk"]) < before


def reset_to_hub_claim(tables: dict, event_id: str, today: date) -> bool:
    """Drop every non-hub claim on a weights event and re-assess from the
    repo-creation claim alone (the archive saw a different artifact). With
    no hub claim to fall back to, a capture cannot date anything: the event
    and its claims are removed. Returns True when the event survives."""
    hub = [c for c in tables["claims"] if c["event_id"] == event_id and c["source_type"] == "hf_hub"]
    if not hub:
        tables["events"] = [e for e in tables["events"] if e["event_id"] != event_id]
        tables["claims"] = [c for c in tables["claims"] if c["event_id"] != event_id]
        return False
    tables["claims"] = [c for c in tables["claims"] if c["event_id"] != event_id] + hub
    a = assess([claim_from_row(c) for c in live_claims(hub)])
    for e in tables["events"]:
        if e["event_id"] == event_id:
            e.update({"date": a.date, "precision": a.precision, "confidence": a.confidence,
                      "source_url": a.source_url, "source_type": a.source_type,
                      "verified_by": a.verified_by, "notes": a.notes,
                      "verified_date": today.isoformat() if a.confidence == "verified" else ""})
    return True


def backfill_single_claim(tables: dict, event_id: str, label: str) -> None:
    """Reconstruct the one claim a claimless machine row rests on from the
    row's own fields; the row said 'single source' and now shows it."""
    (e,) = [e for e in tables["events"] if e["event_id"] == event_id]
    claim = Claim(date.fromisoformat(e["date"]), e["source_url"], e["source_type"],
                  precision=e["precision"], label=label)
    tables["claims"].append(claim_to_row(event_id, claim))
    e["notes"] = f"single source: {label} {e['date']}"
