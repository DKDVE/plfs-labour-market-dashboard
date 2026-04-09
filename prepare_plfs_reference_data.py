"""
Export real PLFS reference tables from the official documentation bundle to CSV.

The folder under data/.../Periodic Labour Force Survey/ contains Excel/PDF documentation
from NSO — not the unit-level microdata files (CHHV1.csv, CPerV1.csv, HHV1.txt, etc.).
Those must be requested separately from microdata.gov.in and placed in data/raw/.

This script extracts everything that *is* in the bundle: geography, sampling strata,
field layouts, and item code books — as analysis-ready CSV files.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("prepare_plfs_reference")


def _project_root() -> Path:
    return Path(__file__).resolve().parent


def _default_bundle_root() -> Path:
    return (
        _project_root()
        / "data"
        / "Periodic Labour Force Survey -20260408T175758Z-3-001"
        / "Periodic Labour Force Survey"
    )


def _safe_sheet_filename(name: str) -> str:
    safe = name.lower().strip().replace(" ", "_").replace(".", "_")
    for ch in "()'\"/\\:*?<>|":
        safe = safe.replace(ch, "")
    return safe or "sheet"


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8")
    logger.info("  wrote %s (%s rows)", path.relative_to(_project_root()), len(df))


def _export_geography(bundle: Path, out: Path, manifest: Dict[str, Any]) -> None:
    sub = out / "geography"
    jan25 = bundle / "Jan 25-Dec25"
    states = pd.read_excel(jan25 / "4. Indian_States_and_UTs_Code  Name.xlsx")
    districts = pd.read_excel(jan25 / "5. Indian_Districts_Code  Name.xlsx")
    _write_csv(states, sub / "indian_states_and_uts.csv")
    _write_csv(districts, sub / "indian_districts.csv")
    manifest["geography"] = {
        "states_source": str(jan25 / "4. Indian_States_and_UTs_Code  Name.xlsx"),
        "districts_source": str(jan25 / "5. Indian_Districts_Code  Name.xlsx"),
        "state_rows": len(states),
        "district_rows": len(districts),
    }

    bstrm_path = jan25 / "3. Bstrm_file.xlsx"
    bstrm = pd.read_excel(bstrm_path, sheet_name="bstrm data", header=0)
    meta = pd.read_excel(bstrm_path, sheet_name="Metadata", header=None)
    _write_csv(bstrm, sub / "basic_stratum_bstrm.csv")
    _write_csv(meta, sub / "bstrm_file_metadata_raw.csv")
    manifest["geography"]["basic_stratum"] = {
        "source": str(bstrm_path),
        "rows": len(bstrm),
    }


def _export_july2023_june2024(bundle: Path, out: Path, manifest: Dict[str, Any]) -> None:
    sub = out / "layouts_july2023_june2024"
    xlsx = bundle / "July 2023-June 2024" / "Data_LayoutPLFS_2023-24.xlsx"
    sheets: List[Tuple[str, str, int]] = [
        ("data_layout_full.csv", "Data Layout", 2),
        ("state_code.csv", "State code", 1),
        ("field_dictionary_hhv1.csv", "hhv1", 0),
        ("field_dictionary_perv1.csv", "perv1", 0),
        ("field_dictionary_hhrv.csv", "hhrv", 0),
        ("field_dictionary_perrv.csv", "perrv", 0),
    ]
    for fname, sheet, header in sheets:
        df = pd.read_excel(xlsx, sheet_name=sheet, header=header)
        _write_csv(df, sub / fname)
    manifest["layouts_july2023_june2024"] = {"source": str(xlsx), "sheets_exported": len(sheets)}


def _export_calendar2024(bundle: Path, out: Path, manifest: Dict[str, Any]) -> None:
    sub = out / "layouts_calendar_year_2024"
    xlsx = bundle / "Jan 24-Dec 24" / "Data_LayoutPLFS_Calendar_2024 (4).xlsx"
    exports: List[Tuple[str, str, int]] = [
        ("data_layout_full.csv", "Data Layout", 2),
        ("state_code.csv", "State code", 1),
        ("field_dictionary_chhv1.csv", "chhv1", 1),
        ("field_dictionary_cperv1.csv", "cperv1", 1),
    ]
    for fname, sheet, header in exports:
        df = pd.read_excel(xlsx, sheet_name=sheet, header=header)
        _write_csv(df, sub / fname)
    manifest["layouts_calendar_year_2024"] = {
        "source": str(xlsx),
        "note": "Use these field names when parsing CHHV1/CPerV1 CSV from NSO (calendar year).",
    }


def _export_item_codes_panel4(bundle: Path, out: Path, manifest: Dict[str, Any]) -> None:
    sub = out / "item_codes_panel4_schedule_10_4"
    xlsx = (
        bundle
        / "Jan 24-Dec 24"
        / "PLFS Panel 4 Sch 10.4 Item Code Description & Codes (1).xlsx"
    )
    xl = pd.ExcelFile(xlsx)
    exported = []
    for sheet in xl.sheet_names:
        df = pd.read_excel(xlsx, sheet_name=sheet, header=1)
        path = sub / f"{_safe_sheet_filename(sheet)}.csv"
        _write_csv(df, path)
        exported.append(sheet)
    manifest["item_codes_panel4"] = {"source": str(xlsx), "sheets": exported}


def _export_fv2025_layout(bundle: Path, out: Path, manifest: Dict[str, Any]) -> None:
    sub = out / "layouts_jan2025_dec2025_fv"
    xlsx = bundle / "Jan 25-Dec25" / "2. FV_Data_LayoutPLFS_2025.xlsx"
    if not xlsx.exists():
        return
    xl = pd.ExcelFile(xlsx)
    for sheet in xl.sheet_names:
        df = pd.read_excel(xlsx, sheet_name=sheet, header=0)
        _write_csv(df, sub / f"{_safe_sheet_filename(sheet)}.csv")
    manifest["layouts_fv_2025"] = {"source": str(xlsx), "sheets": xl.sheet_names}


def _write_notice(out: Path) -> None:
    text = """PLFS reference export — what this is and what it is not
============================================================

IN THIS FOLDER
  CSV files extracted from the official NSO documentation Excel workbooks shipped with
  the survey: state/district codes, basic stratum (BSTRM), field dictionaries for
  HHV1/PerV1/HHRV/PerRV (July–June panel) and CHHV1/CPerV1 (calendar year), and item
  code lists for Schedule 10.4. These are real reference tables for coding and parsing.

NOT IN THE DOCUMENTATION BUNDLE (must be obtained separately)
  Unit-level microdata: household and person CSV/TXT files (e.g. chhv1.csv, cperv1.csv
  for calendar year, or HHV1/PerV1 for July–June) from NSO / microdata.gov.in.
  After download, place them under data/raw/ (see config.yaml) and run plfs_data_pipeline.py.

The sample_data/ CSVs under the survey folder (if present) are synthetic demos only —
they are not NSO microdata.
"""
    p = out / "README_REFERENCE_EXPORT.txt"
    p.write_text(text, encoding="utf-8")
    logger.info("  wrote %s", p.relative_to(_project_root()))


def prepare_reference_data(
    bundle_root: Path | None = None,
    output_dir: Path | None = None,
) -> Path:
    bundle = bundle_root or _default_bundle_root()
    out = output_dir or (_project_root() / "data" / "processed" / "plfs_reference")

    if not bundle.is_dir():
        raise FileNotFoundError(f"Bundle folder not found: {bundle}")

    manifest: Dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "bundle_root": str(bundle.resolve()),
        "output_dir": str(out.resolve()),
    }

    logger.info("Source bundle: %s", bundle)
    logger.info("Output:        %s", out)

    out.mkdir(parents=True, exist_ok=True)

    _export_geography(bundle, out, manifest)
    _export_july2023_june2024(bundle, out, manifest)
    _export_calendar2024(bundle, out, manifest)
    _export_item_codes_panel4(bundle, out, manifest)
    _export_fv2025_layout(bundle, out, manifest)
    _write_notice(out)

    manifest["microdata"] = {
        "status": "not_included_in_documentation_bundle",
        "expected_raw_paths": "data/raw/chhv1.csv, data/raw/cperv1.csv (names configurable in config.yaml)",
    }

    manifest_path = out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    logger.info("Wrote %s", manifest_path.relative_to(_project_root()))

    return out


if __name__ == "__main__":
    prepare_reference_data()
