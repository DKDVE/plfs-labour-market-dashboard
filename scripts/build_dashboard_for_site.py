#!/usr/bin/env python3
"""
Headless build of data/output artifacts for GitHub Pages / static frontends.

Mirrors the multi-round flow and exports in PLFS_Analysis_Notebook.ipynb (sections 3–8).
Run from repo root:  python scripts/build_dashboard_for_site.py

Environment:
  MPLBACKEND=Agg  (set automatically below for headless chart export)
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Headless matplotlib before pyplot import
os.environ.setdefault("MPLBACKEND", "Agg")

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import yaml

# Repo root = parent of scripts/
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from plfs_data_pipeline import (
    PLFSAnalytics,
    PLFSConfig,
    PLFSDataProcessor,
    DataExporter,
    setup_logging,
)


def pick_round_files(round_entry: dict) -> tuple[str | None, str | None]:
    hh = round_entry.get("household_v1") or round_entry.get("household_fv") or round_entry.get("household")
    pp = round_entry.get("person_v1") or round_entry.get("person_fv") or round_entry.get("person")
    return hh, pp


def main() -> int:
    cfg_path = REPO_ROOT / "config.yaml"
    if not cfg_path.is_file():
        print("ERROR: config.yaml not found at repo root.", file=sys.stderr)
        return 1

    cfg_yaml = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    paths_cfg = cfg_yaml["paths"]
    files_cfg = cfg_yaml["files"]
    analysis_cfg = cfg_yaml.get("analysis", {})
    validation_cfg = cfg_yaml.get("validation", {})
    rounds_cfg = cfg_yaml["plfs_extracted"]["rounds"]

    base_extracted_path = Path(paths_cfg["plfs_extracted"])
    if not base_extracted_path.is_dir():
        print(f"ERROR: plfs_extracted path not found: {base_extracted_path}", file=sys.stderr)
        return 1

    base_config = PLFSConfig(
        raw_data_path=Path(paths_cfg["raw_data"]),
        processed_data_path=Path(paths_cfg["processed_data"]),
        output_path=Path(paths_cfg["output"]),
        household_file=files_cfg["household"],
        person_file=files_cfg["person"],
        csv_delimiter=files_cfg.get("delimiter", "\t"),
        field_dictionary_household=Path(files_cfg["field_dictionary_household"])
        if files_cfg.get("field_dictionary_household")
        else None,
        field_dictionary_person=Path(files_cfg["field_dictionary_person"])
        if files_cfg.get("field_dictionary_person")
        else None,
        estimate_type=analysis_cfg.get("estimate_type", "annual"),
        quarters=analysis_cfg.get("quarters", [1, 2, 3, 4]),
        status_measure=analysis_cfg.get("status_measure", "ups"),
        headline_min_age=analysis_cfg.get("headline_min_age", 15),
        nso_unemployment_rate=validation_cfg.get("nso_unemployment_rate", 6.7),
        validation_tolerance=validation_cfg.get("tolerance", 0.5),
        validation_sector=validation_cfg.get("sector"),
        validation_sex=validation_cfg.get("sex"),
        validation_strict_mode=validation_cfg.get("strict_mode", False),
    )

    base_config.output_path.mkdir(parents=True, exist_ok=True)
    log_file = base_config.output_path / f"plfs_ci_build_{datetime.now():%Y%m%d_%H%M%S}.log"
    logger = setup_logging(log_file)

    round_outputs: dict[str, pd.DataFrame] = {}
    trend_rows: list[dict] = []
    analytics = PLFSAnalytics(logger, headline_min_age=base_config.headline_min_age)

    for round_name in sorted(rounds_cfg.keys()):
        round_entry = rounds_cfg[round_name]
        hh_file, person_file = pick_round_files(round_entry)
        if not hh_file or not person_file:
            logger.warning("Skipping %s: missing household/person mapping", round_name)
            continue

        round_dir = base_extracted_path / round_name
        if not round_dir.is_dir():
            logger.warning("Skipping %s: folder not found %s", round_name, round_dir)
            continue

        round_config = PLFSConfig(
            raw_data_path=round_dir,
            processed_data_path=base_config.processed_data_path,
            output_path=base_config.output_path,
            household_file=hh_file,
            person_file=person_file,
            csv_delimiter=base_config.csv_delimiter,
            field_dictionary_household=base_config.field_dictionary_household,
            field_dictionary_person=base_config.field_dictionary_person,
            estimate_type=base_config.estimate_type,
            quarters=base_config.quarters,
            status_measure=base_config.status_measure,
            headline_min_age=base_config.headline_min_age,
            nso_unemployment_rate=base_config.nso_unemployment_rate,
            validation_tolerance=base_config.validation_tolerance,
            validation_sector=base_config.validation_sector,
            validation_sex=base_config.validation_sex,
            validation_strict_mode=base_config.validation_strict_mode,
        )

        processor = PLFSDataProcessor(round_config, logger)
        round_df = processor.process_data()
        round_outputs[round_name] = round_df

        trend_rows.append(
            {
                "round": round_name,
                "records": len(round_df),
                "households": int(round_df["HHID"].nunique()),
                "unemployment_rate": float(analytics.calculate_unemployment_rate(round_df)),
                "lfpr": float(analytics.calculate_lfpr(round_df)),
                "wpr": float(analytics.calculate_wpr(round_df)),
            }
        )
        logger.info("Processed %s: %s records", round_name, f"{len(round_df):,}")

    if not round_outputs:
        print(
            "ERROR: No rounds processed. Ensure data/raw/plfs_extracted/<round>/ microdata is present.",
            file=sys.stderr,
        )
        return 1

    latest_round = sorted(round_outputs.keys())[-1]
    processed_df = round_outputs[latest_round]
    multiyear_stats = pd.DataFrame(trend_rows).sort_values("round").reset_index(drop=True)

    summary_stats = analytics.generate_summary_statistics(processed_df)

    processed_df = processed_df.copy()
    processed_df["age_group"] = pd.cut(
        processed_df["AGE"],
        bins=[0, 14, 24, 34, 44, 54, 64, 120],
        labels=["0-14", "15-24", "25-34", "35-44", "45-54", "55-64", "65+"],
    )
    age_group_unemp = analytics.calculate_unemployment_rate(processed_df, by="age_group")

    sns.set_style("whitegrid")
    plt.rcParams["figure.figsize"] = (12, 6)

    def create_unemployment_charts(df: pd.DataFrame, stats: dict, trend_df: pd.DataFrame):
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle("PLFS Labor Market Indicators", fontsize=16, fontweight="bold")

        ax1 = axes[0, 0]
        t = trend_df.copy()
        ax1.plot(t["round"], t["unemployment_rate"], marker="o", color="#e74c3c", label="UR")
        ax1.plot(t["round"], t["lfpr"], marker="o", color="#3498db", label="LFPR")
        ax1.plot(t["round"], t["wpr"], marker="o", color="#2ecc71", label="WPR")
        ax1.set_ylabel("Percentage (%)")
        ax1.set_title("All-Year Trend (National)")
        ax1.tick_params(axis="x", rotation=45)
        ax1.legend()

        ax2 = axes[0, 1]
        gender_unemp = stats["by_gender"]["unemployment"]
        ax2.bar(["Male", "Female"], gender_unemp.values, color=["#3498db", "#e74c3c"])
        ax2.set_ylabel("Unemployment Rate (%)")
        ax2.set_title("Latest Round: Unemployment by Gender")
        for i, v in enumerate(gender_unemp.values):
            ax2.text(i, v + 0.3, f"{v:.1f}%", ha="center", fontweight="bold")

        ax3 = axes[1, 0]
        sector_unemp = stats["by_sector"]["unemployment"]
        ax3.bar(["Rural", "Urban"], sector_unemp.values, color=["#27ae60", "#f39c12"])
        ax3.set_ylabel("Unemployment Rate (%)")
        ax3.set_title("Latest Round: Unemployment by Sector")
        for i, v in enumerate(sector_unemp.values):
            ax3.text(i, v + 0.3, f"{v:.1f}%", ha="center", fontweight="bold")

        ax4 = axes[1, 1]
        if "by_state" in stats:
            state_unemp = stats["by_state"]["unemployment"].sort_values(ascending=False).head(10)
            ax4.barh(range(len(state_unemp)), state_unemp.values, color="#9b59b6")
            ax4.set_yticks(range(len(state_unemp)))
            ax4.set_yticklabels([f"State {s}" for s in state_unemp.index])
            ax4.set_xlabel("Unemployment Rate (%)")
            ax4.set_title("Latest Round: Top 10 States by Unemployment")
            ax4.invert_yaxis()

        plt.tight_layout()
        out = base_config.output_path / "unemployment_dashboard.png"
        plt.savefig(out, dpi=300, bbox_inches="tight")
        plt.close(fig)
        logger.info("Saved visualization: %s", out)

    create_unemployment_charts(processed_df, summary_stats, multiyear_stats)

    plt.figure(figsize=(12, 6))
    age_group_unemp.sort_index().plot(kind="bar", color="steelblue")
    plt.title("Latest Round: Unemployment Rate by Age Group", fontsize=14, fontweight="bold")
    plt.xlabel("Age Group")
    plt.ylabel("Unemployment Rate (%)")
    plt.xticks(rotation=45)
    plt.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(base_config.output_path / "unemployment_by_age.png", dpi=300)
    plt.close()

    if "EDUCATION_LEVEL" in processed_df.columns:
        edu_unemp = analytics.calculate_unemployment_rate(processed_df, by="EDUCATION_LEVEL")
        plt.figure(figsize=(12, 6))
        edu_unemp.sort_values().plot(kind="barh", color="coral")
        plt.title("Latest Round: Unemployment by Education Level", fontsize=14, fontweight="bold")
        plt.xlabel("Unemployment Rate (%)")
        plt.ylabel("Education Level")
        plt.grid(axis="x", alpha=0.3)
        plt.tight_layout()
        plt.savefig(base_config.output_path / "unemployment_by_education.png", dpi=300)
        plt.close()

    exporter = DataExporter(base_config.output_path, logger)
    exporter.export_to_parquet(processed_df, "plfs_processed_full.parquet")
    exporter.export_to_csv(multiyear_stats, "plfs_multiyear_trends.csv")
    exporter.export_summary_to_json(summary_stats, "summary_statistics.json")

    if "by_state" in summary_stats:
        state_df = pd.DataFrame(
            {
                "state_code": summary_stats["by_state"]["unemployment"].index,
                "unemployment_rate": summary_stats["by_state"]["unemployment"].values,
            }
        )
        exporter.export_to_csv(state_df, "state_unemployment.csv")

    age_group_df = pd.DataFrame(
        {"age_group": age_group_unemp.index, "unemployment_rate": age_group_unemp.values}
    )
    exporter.export_to_csv(age_group_df, "age_group_unemployment.csv")

    dashboard_data = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "data_source": "PLFS multi-year",
            "total_rounds": int(len(multiyear_stats)),
            "latest_round": latest_round,
            "total_records_latest_round": int(len(processed_df)),
            "total_households_latest_round": int(processed_df["HHID"].nunique()),
        },
        "national_indicators_latest_round": {
            "unemployment_rate": round(summary_stats["national"]["unemployment_rate"], 2),
            "lfpr": round(summary_stats["national"]["lfpr"], 2),
            "wpr": round(summary_stats["national"]["wpr"], 2),
        },
        "multiyear_trend": multiyear_stats.to_dict(orient="records"),
        "demographics_latest_round": {
            "by_gender": {
                "male": {
                    "unemployment": round(summary_stats["by_gender"]["unemployment"][1], 2),
                    "lfpr": round(summary_stats["by_gender"]["lfpr"][1], 2),
                },
                "female": {
                    "unemployment": round(summary_stats["by_gender"]["unemployment"][2], 2),
                    "lfpr": round(summary_stats["by_gender"]["lfpr"][2], 2),
                },
            },
            "by_sector": {
                "rural": {"unemployment": round(summary_stats["by_sector"]["unemployment"][1], 2)},
                "urban": {"unemployment": round(summary_stats["by_sector"]["unemployment"][2], 2)},
            },
        },
        "age_groups_latest_round": [
            {"group": str(group), "unemployment_rate": round(rate, 2)}
            for group, rate in age_group_unemp.items()
        ],
    }

    dashboard_file = base_config.output_path / "dashboard_data.json"
    with open(dashboard_file, "w", encoding="utf-8") as f:
        json.dump(dashboard_data, f, indent=2)

    logger.info("Dashboard data written to %s", dashboard_file)
    print(f"OK: {dashboard_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
