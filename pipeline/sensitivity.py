"""Sensitivity of "the release date" to the choice of event type.

Event studies and staggered difference-in-differences designs anchor on a
single treatment date per model. This analysis uses only the ledger's own
dated events to quantify how much that date moves depending on which
lifecycle event a researcher picks (announced vs api_ga vs weights_released
vs consumer_rollout vs free_tier) - no external microdata, no synthetic
outcomes.

Output: data/generated/sensitivity_report.md
"""

from __future__ import annotations

import statistics
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import schema

PAIRS = (
    ("announced", "api_ga"),
    ("announced", "weights_released"),
    ("announced", "consumer_rollout"),
    ("announced", "free_tier"),
    ("api_ga", "free_tier"),
    ("consumer_rollout", "free_tier"),
)

ANCHOR_TYPES = ("announced", "api_preview", "api_ga", "weights_released",
                "consumer_rollout", "free_tier")


def _first_dates(events: list) -> dict:
    """model_id -> {event_type: (date, precision)} using earliest global events."""
    firsts: dict = defaultdict(dict)
    for e in events:
        if e.get("region", "global") != "global" or e["event_type"] not in ANCHOR_TYPES:
            continue
        try:
            d = date.fromisoformat(e["date"])
        except ValueError:
            continue
        current = firsts[e["model_id"]].get(e["event_type"])
        if current is None or d < current[0]:
            firsts[e["model_id"]][e["event_type"]] = (d, e["precision"])
    return firsts


def _quantiles(values: list) -> str:
    if not values:
        return "-"
    values = sorted(values)
    med = statistics.median(values)
    p25 = values[max(0, int(0.25 * (len(values) - 1)))]
    p75 = values[int(0.75 * (len(values) - 1))]
    return f"median {med:.0f}d (IQR {p25:.0f}-{p75:.0f}d, n={len(values)})"


def _hist(values: list) -> list:
    buckets = (("same day", 0, 0), ("1-7d", 1, 7), ("8-30d", 8, 30),
               ("31-90d", 31, 90), ("91-365d", 91, 365), (">365d", 366, 10 ** 9))
    lines = ["| gap | models |", "|---|---|"]
    for label, lo, hi in buckets:
        lines.append(f"| {label} | {sum(1 for v in values if lo <= v <= hi)} |")
    return lines


def main() -> int:
    events = schema.read_table(schema.EVENTS)
    models = {m["model_id"]: m for m in schema.read_table(schema.MODELS)}
    firsts = _first_dates(events)

    lines = [
        "# Treatment-date sensitivity report",
        "",
        "How far apart are the candidate 'release dates' of the same model?",
        "Computed from the ledger's own dated events (global region, earliest",
        "event per type, day/month precision as recorded). Gaps are in days;",
        "positive means the second event happened after the first.",
        "",
    ]

    for first_type, second_type in PAIRS:
        gaps, per_org = [], defaultdict(list)
        for model_id, types in firsts.items():
            if first_type in types and second_type in types:
                gap = (types[second_type][0] - types[first_type][0]).days
                gaps.append(gap)
                org = models.get(model_id, {}).get("developer_org_id", "?")
                per_org[org].append(gap)
        lines += [f"## {first_type} -> {second_type}", ""]
        if not gaps:
            lines += ["No model has both events yet.", ""]
            continue
        lines += [f"- {_quantiles(gaps)}",
                  f"- range: {min(gaps)}d to {max(gaps)}d", ""]
        lines += _hist([abs(g) for g in gaps])
        lines += ["", "Per-organization medians (n>=3):", ""]
        rows = sorted(
            ((org, statistics.median(v), len(v)) for org, v in per_org.items() if len(v) >= 3),
            key=lambda r: r[1], reverse=True)
        lines += [f"- {org}: {med:.0f}d (n={n})" for org, med, n in rows] or ["- (none with n>=3)"]
        lines.append("")

    # Case study: the ChatGPT anchoring problem, using ledger rows only.
    lines += ["## Case study: which 'ChatGPT date' would you regress on?", ""]
    chatgpt = firsts.get("gpt-3-5", {})
    if chatgpt:
        for event_type in ANCHOR_TYPES:
            if event_type in chatgpt:
                d, precision = chatgpt[event_type]
                lines.append(f"- `{event_type}`: {d.isoformat()} (precision={precision})")
        anchors = sorted(d for d, _ in chatgpt.values())
        if len(anchors) >= 2:
            spread = (anchors[-1] - anchors[0]).days
            lines += ["",
                      f"The candidate treatment dates for the same product span "
                      f"**{spread} days**. A difference-in-differences design with "
                      f"weekly or monthly bins can shift entire pre-periods into the "
                      f"post-period (and vice versa) purely by picking a different "
                      f"row of this table.", ""]
    else:
        lines += ["(gpt-3-5 events not yet loaded)", ""]

    both = sum(1 for t in firsts.values() if "announced" in t and (
        set(t) & {"api_ga", "weights_released", "consumer_rollout", "free_tier"}))
    lines += ["## Coverage", "",
              f"- models with an anchor event: {len(firsts)}",
              f"- models with announced + an availability event: {both}", ""]

    out = schema.GENERATED_DIR / "sensitivity_report.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"sensitivity: -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
