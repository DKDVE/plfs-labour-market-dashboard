#!/usr/bin/env python3
"""Validate docs/data/dashboard_data.json structure (stdlib only; no jsonschema dep)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "docs" / "data" / "dashboard_data.json"


def err(msg: str) -> None:
    print(f"validate_dashboard_json: {msg}", file=sys.stderr)


def main() -> int:
    data_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_DATA
    if not data_path.is_file():
        err(f"missing {data_path}")
        return 1
    try:
        data = json.loads(data_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        err(f"invalid JSON: {e}")
        return 1

    required_top = (
        "metadata",
        "national_indicators_latest_round",
        "multiyear_trend",
        "demographics_latest_round",
        "age_groups_latest_round",
    )
    for k in required_top:
        if k not in data:
            err(f"missing top-level key {k!r}")
            return 1

    meta = data["metadata"]
    for mk in ("generated_at", "latest_round"):
        if mk not in meta:
            err(f"metadata missing {mk!r}")
            return 1

    nat = data["national_indicators_latest_round"]
    for nk in ("unemployment_rate", "lfpr", "wpr"):
        if nk not in nat:
            err(f"national_indicators_latest_round missing {nk!r}")
            return 1

    trend = data["multiyear_trend"]
    if not isinstance(trend, list) or len(trend) == 0:
        err("multiyear_trend must be a non-empty array")
        return 1
    for i, row in enumerate(trend):
        if not isinstance(row, dict):
            err(f"multiyear_trend[{i}] must be an object")
            return 1
        for rk in ("round", "unemployment_rate", "lfpr", "wpr"):
            if rk not in row:
                err(f"multiyear_trend[{i}] missing {rk!r}")
                return 1

    ages = data["age_groups_latest_round"]
    if not isinstance(ages, list):
        err("age_groups_latest_round must be an array")
        return 1
    for i, row in enumerate(ages):
        if not isinstance(row, dict) or "group" not in row or "unemployment_rate" not in row:
            err(f"age_groups_latest_round[{i}] must have group and unemployment_rate")
            return 1

    if len(trend) >= 3:
        if "trend_statistics" not in data:
            err(
                "trend_statistics missing (required when multiyear_trend has 3+ rounds); "
                "run: python3 scripts/compute_dashboard_analytics.py docs/data/dashboard_data.json --in-place"
            )
            return 1
        ts = data["trend_statistics"]
        if not isinstance(ts, dict):
            err("trend_statistics must be an object")
            return 1
        if ts.get("error"):
            pass
        else:
            for mk in ("metrics", "pearson_across_rounds"):
                if mk not in ts:
                    err(f"trend_statistics missing {mk!r}")
                    return 1
            metrics = ts["metrics"]
            for ind in ("unemployment_rate", "lfpr", "wpr"):
                if ind not in metrics:
                    err(f"trend_statistics.metrics missing {ind!r}")
                    return 1

    print(f"OK: {data_path} ({len(trend)} trend rows, {len(ages)} age bands)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
