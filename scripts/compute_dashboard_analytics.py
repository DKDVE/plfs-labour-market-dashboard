#!/usr/bin/env python3
"""
Compute descriptive trend statistics for the static dashboard bundle.

Uses only multiyear_trend (national pooled % per round). With ~7 annual points,
this is **not** suitable for serious forecasting or "ML" — we export OLS slopes,
R², and pairwise Pearson correlations with explicit caveats.

Usage:
  python3 scripts/compute_dashboard_analytics.py docs/data/dashboard_data.json
  python3 scripts/compute_dashboard_analytics.py docs/data/dashboard_data.json --in-place
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path


def july_year(round_id: str) -> int | None:
    m = re.search(r"july(\d{4})", str(round_id))
    return int(m.group(1)) if m else None


def ols_slope_intercept_r2(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    """Ordinary least squares y ~ a + b*x; returns (intercept, slope, r_squared)."""
    n = len(xs)
    if n < 2 or len(ys) != n:
        return float("nan"), float("nan"), float("nan")
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return my, 0.0, 0.0
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx
    a = my - b * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    if ss_tot == 0:
        return a, b, 1.0
    preds = [a + b * x for x in xs]
    ss_res = sum((y - p) ** 2 for y, p in zip(ys, preds))
    r2 = max(0.0, min(1.0, 1.0 - ss_res / ss_tot))
    return a, b, r2


def pearson(a: list[float], b: list[float]) -> float | None:
    n = len(a)
    if n < 2 or len(b) != n:
        return None
    ma = sum(a) / n
    mb = sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va == 0 or vb == 0:
        return None
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    return cov / math.sqrt(va * vb)


def build_trend_statistics(trend: list[dict]) -> dict:
    rows = []
    for r in trend:
        y = july_year(r.get("round", ""))
        if y is None:
            continue
        rows.append(
            {
                "round": r["round"],
                "year_july": y,
                "unemployment_rate": float(r["unemployment_rate"]),
                "lfpr": float(r["lfpr"]),
                "wpr": float(r["wpr"]),
            }
        )
    rows.sort(key=lambda x: (x["year_july"], x["round"]))
    n = len(rows)
    if n < 3:
        return {
            "version": 1,
            "n_rounds": n,
            "error": "Need at least 3 rounds with parsable July years for trend statistics.",
        }

    xs = [float(r["year_july"]) for r in rows]
    caveat = (
        "Descriptive only: OLS linear trend vs survey reference year (July start), and Pearson "
        "correlation between national pooled headline series across the same rounds. "
        f"Based on {n} annual pooled estimates — not a forecast, not causal, and not a substitute "
        "for official NSO uncertainty statements. Correlation ≠ causation."
    )

    metrics_cfg = [
        ("unemployment_rate", "UR (%)"),
        ("lfpr", "LFPR (%)"),
        ("wpr", "WPR (%)"),
    ]
    metrics_out: dict = {}
    series: dict[str, list[float]] = {}
    for key, label in metrics_cfg:
        ys = [r[key] for r in rows]
        series[key] = ys
        a, b, r2 = ols_slope_intercept_r2(xs, ys)
        metrics_out[key] = {
            "label": label,
            "slope_pp_per_year": round(b, 4),
            "intercept": round(a, 4),
            "r_squared": round(r2, 4),
            "mean": round(sum(ys) / n, 4),
        }

    ur, lf, wp = series["unemployment_rate"], series["lfpr"], series["wpr"]
    pearsons: dict[str, float | None] = {
        "unemployment_rate__lfpr": pearson(ur, lf),
        "unemployment_rate__wpr": pearson(ur, wp),
        "lfpr__wpr": pearson(lf, wp),
    }
    pearsons_clean = {k: (round(v, 4) if v is not None else None) for k, v in pearsons.items()}

    return {
        "version": 1,
        "n_rounds": n,
        "caveat": caveat,
        "rounds_ordered": [{"round": r["round"], "year_july": r["year_july"]} for r in rows],
        "metrics": metrics_out,
        "pearson_across_rounds": pearsons_clean,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Attach trend_statistics to dashboard JSON.")
    ap.add_argument("json_path", type=Path, help="Path to dashboard_data.json")
    ap.add_argument("--in-place", action="store_true", help="Overwrite file with merged output")
    ap.add_argument("-o", "--output", type=Path, help="Write merged JSON here (default: stdout)")
    args = ap.parse_args()
    path: Path = args.json_path
    if not path.is_file():
        print(f"Missing file: {path}", file=sys.stderr)
        return 1
    data = json.loads(path.read_text(encoding="utf-8"))
    trend = data.get("multiyear_trend")
    if not isinstance(trend, list) or not trend:
        print("multiyear_trend missing or empty", file=sys.stderr)
        return 1
    data["trend_statistics"] = build_trend_statistics(trend)
    out_txt = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if args.in_place:
        path.write_text(out_txt, encoding="utf-8")
        print(f"Wrote {path}", file=sys.stderr)
        return 0
    if args.output:
        args.output.write_text(out_txt, encoding="utf-8")
        print(f"Wrote {args.output}", file=sys.stderr)
        return 0
    sys.stdout.write(out_txt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
