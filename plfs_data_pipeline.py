"""
PLFS Data Pipeline - Production Grade Implementation
====================================================

Author: PLFS Research Team
Date: April 2026
Version: 1.0.0

Description:
    Production-ready data pipeline for PLFS (Periodic Labour Force Survey) analysis.
    Implements industry-standard coding practices with full validation and error handling.

Usage:
    python plfs_data_pipeline.py --config config.yaml
    
Requirements:
    - pandas >= 1.5.0
    - numpy >= 1.23.0
    - pyyaml >= 6.0
    - python >= 3.9
"""

import argparse
import os
import sys
import re
import logging
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
from datetime import datetime

import pandas as pd
import numpy as np
import yaml

# Suppress warnings for cleaner output
warnings.filterwarnings('ignore')

# =============================================================================
# CONFIGURATION & CONSTANTS
# =============================================================================

@dataclass
class PLFSConfig:
    """Configuration dataclass for PLFS pipeline."""
    
    # Data paths
    raw_data_path: Path
    processed_data_path: Path
    output_path: Path
    
    # Data files
    household_file: str = "chhv1.csv"
    person_file: str = "cperv1.csv"
    # Comma for Nesstar CSV exports; use "\t" for tab-separated NSO .txt microdata
    csv_delimiter: str = ","
    # NSO layout CSVs (Field_Name column); when set, raw .txt is read with header=None
    # and columns renamed to pipeline names (see _standardize_nso_*).
    field_dictionary_household: Optional[Path] = None
    field_dictionary_person: Optional[Path] = None
    
    # Validation thresholds
    nso_unemployment_rate: float = 6.7  # NSO official 2023-24
    validation_tolerance: float = 0.5   # percentage points
    validation_sector: Optional[int] = None
    validation_sex: Optional[int] = None
    validation_strict_mode: bool = False
    
    # Processing parameters
    estimate_type: str = "annual"  # 'quarterly' or 'annual'
    quarters: List[int] = None
    # Labour-status definition: 'ups' uses Principal_Status (pas), 'cws' uses acws
    status_measure: str = "ups"
    # Minimum age for headline rates (NSO standard: 15+)
    headline_min_age: int = 15
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        if self.quarters is None:
            self.quarters = [1, 2, 3, 4]
        
        # Create directories if they don't exist
        self.raw_data_path.mkdir(parents=True, exist_ok=True)
        self.processed_data_path.mkdir(parents=True, exist_ok=True)
        self.output_path.mkdir(parents=True, exist_ok=True)


def load_plfs_config_yaml(path: Path) -> PLFSConfig:
    """Build PLFSConfig from config.yaml (paths, files, analysis, validation)."""
    with open(path, encoding="utf-8") as f:
        y = yaml.safe_load(f)
    paths = y.get("paths") or {}
    files = y.get("files") or {}
    analysis = y.get("analysis") or {}
    validation = y.get("validation") or {}
    fd_h = files.get("field_dictionary_household")
    fd_p = files.get("field_dictionary_person")
    return PLFSConfig(
        raw_data_path=Path(paths["raw_data"]).expanduser(),
        processed_data_path=Path(paths["processed_data"]).expanduser(),
        output_path=Path(paths["output"]).expanduser(),
        household_file=files.get("household", "chhv1.csv"),
        person_file=files.get("person", "cperv1.csv"),
        csv_delimiter=str(files.get("delimiter", ",")),
        field_dictionary_household=Path(fd_h).expanduser() if fd_h else None,
        field_dictionary_person=Path(fd_p).expanduser() if fd_p else None,
        estimate_type=analysis.get("estimate_type", "annual"),
        quarters=analysis.get("quarters", [1, 2, 3, 4]),
        status_measure=str(analysis.get("status_measure", "ups")).lower(),
        headline_min_age=int(analysis.get("headline_min_age", 15)),
        nso_unemployment_rate=float(validation.get("nso_unemployment_rate", 6.7)),
        validation_tolerance=float(validation.get("tolerance", 0.5)),
        validation_sector=(
            int(validation["sector"]) if validation.get("sector") is not None else None
        ),
        validation_sex=(
            int(validation["sex"]) if validation.get("sex") is not None else None
        ),
        validation_strict_mode=bool(validation.get("strict_mode", False)),
    )


def _read_field_dictionary_names(path: Path) -> List[str]:
    """Load NSO field names from reference field_dictionary_*.csv (Field_Name column)."""
    meta = pd.read_csv(path, encoding="utf-8")
    if "Field_Name" not in meta.columns:
        raise ValueError(f"Field dictionary missing Field_Name column: {path}")
    return [str(x).strip() for x in meta["Field_Name"].tolist()]


def _qtr_visit_to_numeric(series: pd.Series, prefix: str) -> pd.Series:
    """Map 'Q1'/'V1' style codes to integers."""
    s = series.astype(str).str.strip().str.upper()
    s = s.str.replace(f"^{prefix}", "", regex=True)
    return pd.to_numeric(s, errors="coerce")


def _year_from_sur_date(series: pd.Series) -> pd.Series:
    """Survey date to year; supports DDMMYYYY and YYYYMMDD (both 8 chars)."""
    s = series.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    s = s.str.replace(r"\D", "", regex=True)
    y_last = pd.to_numeric(s.str[-4:], errors="coerce")
    y_first = pd.to_numeric(s.str[:4], errors="coerce")
    first_plausible = y_first.between(1990, 2100, inclusive="both")
    last_plausible = y_last.between(1990, 2100, inclusive="both")
    return y_first.where(first_plausible & ~last_plausible, y_last)


def _round_start_year(path: Path) -> Optional[int]:
    """Extract start year from folder names like '*_july2023_june2024'."""
    m = re.search(r"july(\d{4})_june(\d{4})", str(path).lower())
    if not m:
        return None
    return int(m.group(1))


def _attach_year_from_household(
    person_df: pd.DataFrame, household_df: pd.DataFrame, logger: logging.Logger
) -> pd.DataFrame:
    """Person-level NSO extract has no survey date; copy YEAR from household on ID keys."""
    key = ["ST", "DC", "QTR", "VISIT", "MFSU", "SEG", "SSU"]
    if "SSS" in person_df.columns and "SSS" in household_df.columns:
        key.insert(-1, "SSS")
    lookup = household_df[key + ["YEAR"]].drop_duplicates()
    if lookup.duplicated(subset=key).any():
        logger.warning("Duplicate household keys when attaching YEAR to person rows; keeping first")
        lookup = lookup.drop_duplicates(subset=key, keep="first")
    out = person_df.merge(lookup, on=key, how="left", validate="m:1")
    n_miss = out["YEAR"].isna().sum()
    if n_miss:
        raise ValueError(f"Could not attach YEAR to {n_miss} person rows from household keys")
    return out


# PLFS Status Codes (from NSO documentation)
STATUS_CODES = {
    11: "Self-employed: Own account worker",
    12: "Self-employed: Employer",
    21: "Unpaid family worker",
    31: "Regular salaried/wage employee",
    41: "Casual wage labour: Public works (non-MGNREGA)",
    42: "Casual wage labour: MGNREGA",
    51: "Casual wage labour: Other types",
    81: "Unemployed: Seeking/available for work",
    91: "Attended educational institution",
    92: "Attended domestic duties only",
    93: "Domestic duties + free collection",
    94: "Rentiers/pensioners/remittance recipients",
    95: "Not able to work due to disability",
    97: "Others (begging, prostitution, etc.)"
}

EMPLOYED_CODES = [11, 12, 21, 31, 41, 42, 51]
UNEMPLOYED_CODES = [81]

# NSO headline indicators use population aged 15 years and above (usual status)
PLFS_HEADLINE_MIN_AGE = 15


def _age_ge_min_mask(df: pd.DataFrame, min_age: int = PLFS_HEADLINE_MIN_AGE) -> pd.Series:
    age = pd.to_numeric(df["AGE"], errors="coerce")
    return age >= min_age


def _weighted_ratio(
    num: pd.Series, den: pd.Series, weights: pd.Series
) -> float:
    """ratio = sum(w*num) / sum(w*den); for rates expressed in percent, multiply by 100 outside."""
    n = (weights * num).sum()
    d = (weights * den).sum()
    return float(n / d) if d > 0 else float("nan")


def _status_series(df: pd.DataFrame, status_measure: str) -> pd.Series:
    """Return the selected labour-status code series."""
    sm = status_measure.lower().strip()
    if sm == "ups":
        return pd.to_numeric(df["Principal_Status"], errors="coerce")
    if sm == "cws":
        if "acws" not in df.columns:
            raise ValueError("CWS selected but `acws` column not found in person data.")
        return pd.to_numeric(df["acws"], errors="coerce")
    raise ValueError(f"Invalid status_measure: {status_measure}. Use 'ups' or 'cws'.")


def _status_code_sets(status_measure: str) -> Tuple[set, set]:
    """
    Return (employed_codes, unemployed_codes) for the selected labour-status measure.
    UPS uses principal-status employed set with unemployed=81.
    CWS includes short-duration employed codes and unemployed=81/82.
    """
    sm = status_measure.lower().strip()
    if sm == "ups":
        return set(EMPLOYED_CODES), set(UNEMPLOYED_CODES)
    if sm == "cws":
        employed = {11, 12, 21, 31, 41, 42, 51, 61, 62, 71, 72}
        unemployed = {81, 82}
        return employed, unemployed
    raise ValueError(f"Invalid status_measure: {status_measure}. Use 'ups' or 'cws'.")


# =============================================================================
# LOGGING SETUP
# =============================================================================

def setup_logging(log_file: Optional[Path] = None) -> logging.Logger:
    """
    Configure logging with both file and console handlers.
    
    Args:
        log_file: Path to log file. If None, logs only to console.
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger('PLFS_Pipeline')
    logger.setLevel(logging.INFO)
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Create formatters
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler (if specified)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


# =============================================================================
# DATA VALIDATION
# =============================================================================

class DataValidator:
    """Validate PLFS data quality and structure."""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    def validate_household_data(self, df: pd.DataFrame) -> Tuple[bool, List[str]]:
        """
        Validate household-level data structure and quality.
        
        Args:
            df: Household dataframe
            
        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []
        
        # Required columns check
        required_cols = ['STATE', 'DISTRICT', 'HHID', 'MLTS']
        missing_cols = [col for col in required_cols if col not in df.columns]
        
        if missing_cols:
            issues.append(f"Missing required columns: {missing_cols}")
        
        # Duplicate household IDs
        if 'HHID' in df.columns:
            duplicates = df['HHID'].duplicated().sum()
            if duplicates > 0:
                issues.append(f"Found {duplicates} duplicate household IDs")
        
        # Multiplier validation
        if 'MLTS' in df.columns:
            null_mlts = df['MLTS'].isnull().sum()
            if null_mlts > 0:
                issues.append(f"Found {null_mlts} null multiplier values")
            
            # Raw sub-sample multipliers can be very large (e.g. 1e8) in NSO extracts
            if df['MLTS'].max() > 10_000_000_000:
                issues.append("Suspiciously high multiplier values detected")
        
        is_valid = len(issues) == 0
        
        if is_valid:
            self.logger.info("✓ Household data validation passed")
        else:
            self.logger.warning(f"✗ Household data validation failed: {issues}")
        
        return is_valid, issues
    
    def validate_person_data(self, df: pd.DataFrame) -> Tuple[bool, List[str]]:
        """
        Validate person-level data structure and quality.
        
        Args:
            df: Person dataframe
            
        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []
        
        # Required columns
        required_cols = ['HHID', 'PERSON_SERIAL_NO', 'AGE', 'SEX']
        missing_cols = [col for col in required_cols if col not in df.columns]
        
        if missing_cols:
            issues.append(f"Missing required columns: {missing_cols}")
        
        # Age validation
        if 'AGE' in df.columns:
            invalid_age = ((df['AGE'] < 0) | (df['AGE'] > 120)).sum()
            if invalid_age > 0:
                issues.append(f"Found {invalid_age} invalid age values")
        
        # Sex validation
        if 'SEX' in df.columns:
            valid_sex = df['SEX'].isin([1, 2, 3])
            if not valid_sex.all():
                issues.append(f"Found {(~valid_sex).sum()} invalid sex codes")
        
        is_valid = len(issues) == 0
        
        if is_valid:
            self.logger.info("✓ Person data validation passed")
        else:
            self.logger.warning(f"✗ Person data validation failed: {issues}")
        
        return is_valid, issues
    
    def validate_merge(
        self, 
        df_before: pd.DataFrame, 
        df_after: pd.DataFrame,
        merge_key: str
    ) -> Tuple[bool, Dict[str, int]]:
        """
        Validate that merge did not create duplicates or lose data.
        
        Args:
            df_before: DataFrame before merge
            df_after: DataFrame after merge
            merge_key: Key used for merging
            
        Returns:
            Tuple of (is_valid, diagnostics_dict)
        """
        diagnostics = {
            'rows_before': len(df_before),
            'rows_after': len(df_after),
            'unique_keys_before': df_before[merge_key].nunique(),
            'unique_keys_after': df_after[merge_key].nunique(),
        }
        
        # Check for row explosion (cartesian product)
        is_valid = diagnostics['rows_after'] == diagnostics['rows_before']
        
        if is_valid:
            self.logger.info("✓ Merge validation passed - no duplicates created")
        else:
            self.logger.error(
                f"✗ Merge validation failed - "
                f"rows increased from {diagnostics['rows_before']} "
                f"to {diagnostics['rows_after']}"
            )
        
        return is_valid, diagnostics


# =============================================================================
# DATA LOADER
# =============================================================================

class PLFSDataLoader:
    """Load and prepare PLFS data files."""
    
    def __init__(self, config: PLFSConfig, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.validator = DataValidator(logger)
        self.round_start_year = _round_start_year(config.raw_data_path)
    
    def _load_raw_table(self, filepath: Path, field_dict: Optional[Path]) -> pd.DataFrame:
        """Read tabular file; if field_dict is set, use NSO Field_Name list as column names."""
        df = pd.read_csv(
            filepath,
            sep=self.config.csv_delimiter,
            header=None,
            low_memory=False,
            dtype=str,
        )
        if field_dict is not None:
            if not field_dict.exists():
                raise FileNotFoundError(f"Field dictionary not found: {field_dict}")
            names = _read_field_dictionary_names(field_dict)
            if len(names) != len(df.columns):
                self.logger.warning(
                    "Column count mismatch for %s (data=%s, layout=%s). "
                    "Falling back to positional parsing for this round.",
                    filepath,
                    len(df.columns),
                    len(names),
                )
                return df
            df.columns = names
        return df
    
    def _standardize_nso_household(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map NSO field_dictionary names (lowercase) to pipeline columns."""
        out = df.copy()
        if "st" in out.columns:
            out["ST"] = pd.to_numeric(out["st"], errors="coerce")
            out["DC"] = pd.to_numeric(out["dc"], errors="coerce")
            out["QTR"] = _qtr_visit_to_numeric(out["qtr"], "Q")
            out["VISIT"] = _qtr_visit_to_numeric(out["visit"], "V")
            out["MFSU"] = pd.to_numeric(out["mfsu"], errors="coerce")
            out["SEG"] = pd.to_numeric(out["seg"], errors="coerce")
            if "sss" in out.columns:
                out["SSS"] = pd.to_numeric(out["sss"], errors="coerce")
            if "ss" in out.columns:
                out["SS"] = pd.to_numeric(out["ss"], errors="coerce")
            out["SSU"] = pd.to_numeric(out["ssu"], errors="coerce")
            if "sur_date" in out.columns:
                out["YEAR"] = _year_from_sur_date(out["sur_date"])
            out["MLTS"] = pd.to_numeric(out["mult"], errors="coerce")
            out["STATE"] = out["ST"]
            out["DISTRICT"] = out["DC"]
            if "hh_size" in out.columns:
                out["HH_SIZE"] = pd.to_numeric(out["hh_size"], errors="coerce")
            if "hhtype" in out.columns:
                out["HH_TYPE"] = pd.to_numeric(out["hhtype"], errors="coerce")
            if "relg" in out.columns:
                out["RELIGION"] = pd.to_numeric(out["relg"], errors="coerce")
            if "sg" in out.columns:
                out["SOCIAL_GROUP"] = pd.to_numeric(out["sg"], errors="coerce")
            if "hce_tot" in out.columns:
                out["MONTHLY_CONSUMER_EXPENDITURE"] = pd.to_numeric(out["hce_tot"], errors="coerce")
            if "sec" in out.columns:
                out["SECTOR"] = pd.to_numeric(out["sec"], errors="coerce")
        else:
            # Positional fallback for older rounds with different layouts
            out["ST"] = pd.to_numeric(out.iloc[:, 5], errors="coerce")
            out["DC"] = pd.to_numeric(out.iloc[:, 6], errors="coerce")
            out["QTR"] = _qtr_visit_to_numeric(out.iloc[:, 2], "Q")
            out["VISIT"] = _qtr_visit_to_numeric(out.iloc[:, 3], "V")
            out["SECTOR"] = pd.to_numeric(out.iloc[:, 4], errors="coerce")
            out["MFSU"] = pd.to_numeric(out.iloc[:, 12], errors="coerce")
            out["SEG"] = pd.to_numeric(out.iloc[:, 13], errors="coerce")
            out["SSS"] = pd.to_numeric(out.iloc[:, 14], errors="coerce")
            out["SS"] = pd.to_numeric(out.iloc[:, 10], errors="coerce")
            out["SSU"] = pd.to_numeric(out.iloc[:, 15], errors="coerce")
            out["HH_SIZE"] = pd.to_numeric(out.iloc[:, 20], errors="coerce")
            out["HH_TYPE"] = pd.to_numeric(out.iloc[:, 21], errors="coerce")
            out["RELIGION"] = pd.to_numeric(out.iloc[:, 22], errors="coerce")
            out["SOCIAL_GROUP"] = pd.to_numeric(out.iloc[:, 23], errors="coerce")
            out["MONTHLY_CONSUMER_EXPENDITURE"] = pd.to_numeric(out.iloc[:, 24], errors="coerce")
            out["MLTS"] = pd.to_numeric(out.iloc[:, -2], errors="coerce")
            out["YEAR"] = (
                _year_from_sur_date(out.iloc[:, 26]) if out.shape[1] >= 27 else pd.Series(np.nan, index=out.index)
            )
            out["STATE"] = out["ST"]
            out["DISTRICT"] = out["DC"]
        if "YEAR" not in out.columns or out["YEAR"].isna().all():
            out["YEAR"] = self.round_start_year
        return out
    
    def _standardize_nso_person(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map NSO person extract columns; YEAR comes from household merge when missing."""
        out = df.copy()
        if "st" in out.columns:
            out["ST"] = pd.to_numeric(out["st"], errors="coerce")
            out["DC"] = pd.to_numeric(out["dc"], errors="coerce")
            out["QTR"] = _qtr_visit_to_numeric(out["qtr"], "Q")
            out["VISIT"] = _qtr_visit_to_numeric(out["visit"], "V")
            out["MFSU"] = pd.to_numeric(out["mfsu"], errors="coerce")
            out["SEG"] = pd.to_numeric(out["seg"], errors="coerce")
            if "sss" in out.columns:
                out["SSS"] = pd.to_numeric(out["sss"], errors="coerce")
            if "ss" in out.columns:
                out["SS"] = pd.to_numeric(out["ss"], errors="coerce")
            out["SSU"] = pd.to_numeric(out["ssu"], errors="coerce")
            out["PERSON_SERIAL_NO"] = pd.to_numeric(out["srl"], errors="coerce")
            out["AGE"] = pd.to_numeric(out["age"], errors="coerce")
            out["SEX"] = pd.to_numeric(out["sex"], errors="coerce")
            out["Principal_Status"] = pd.to_numeric(out["pas"], errors="coerce")
            if "sec" in out.columns:
                out["SECTOR"] = pd.to_numeric(out["sec"], errors="coerce")
            if "acws" in out.columns:
                out["acws"] = pd.to_numeric(out["acws"], errors="coerce")
        else:
            # Positional fallback (stable core identifiers across rounds)
            out["ST"] = pd.to_numeric(out.iloc[:, 5], errors="coerce")
            out["DC"] = pd.to_numeric(out.iloc[:, 6], errors="coerce")
            out["QTR"] = _qtr_visit_to_numeric(out.iloc[:, 2], "Q")
            out["VISIT"] = _qtr_visit_to_numeric(out.iloc[:, 3], "V")
            out["SECTOR"] = pd.to_numeric(out.iloc[:, 4], errors="coerce")
            out["MFSU"] = pd.to_numeric(out.iloc[:, 12], errors="coerce")
            out["SEG"] = pd.to_numeric(out.iloc[:, 13], errors="coerce")
            out["SSS"] = pd.to_numeric(out.iloc[:, 14], errors="coerce")
            out["SS"] = pd.to_numeric(out.iloc[:, 10], errors="coerce")
            out["SSU"] = pd.to_numeric(out.iloc[:, 15], errors="coerce")
            out["PERSON_SERIAL_NO"] = pd.to_numeric(out.iloc[:, 16], errors="coerce")
            out["SEX"] = pd.to_numeric(out.iloc[:, 18], errors="coerce")
            out["AGE"] = pd.to_numeric(out.iloc[:, 19], errors="coerce")
            out["Principal_Status"] = pd.to_numeric(out.iloc[:, 31], errors="coerce")
            if out.shape[1] > 130:
                out["acws"] = pd.to_numeric(out.iloc[:, 130], errors="coerce")
        return out
    
    def create_household_id(self, df: pd.DataFrame) -> pd.Series:
        """
        Create unique household identifier from component fields.
        
        Args:
            df: DataFrame with household component fields
            
        Returns:
            Series with unique household IDs
        """
        required_fields = ['ST', 'DC', 'QTR', 'VISIT', 'MFSU', 'SEG', 'SSU', 'YEAR']
        
        # Validate all required fields exist
        missing = [f for f in required_fields if f not in df.columns]
        if missing:
            raise ValueError(f"Missing required fields for HHID: {missing}")
        
        def _norm(x: pd.Series, width: int) -> pd.Series:
            s = x.astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
            return s.str.zfill(width)

        hhid = (
            _norm(df['ST'], 2) +
            _norm(df['DC'], 3) +
            _norm(df['QTR'], 1) +
            _norm(df['VISIT'], 1) +
            (_norm(df['SS'], 1) if 'SS' in df.columns else "") +
            _norm(df['MFSU'], 5) +
            _norm(df['SEG'], 1)
        )
        # Second-stage stratum (NSO raw microdata); omitted for older CSV exports without `SSS`
        if 'SSS' in df.columns:
            hhid = hhid + _norm(df['SSS'], 1)
        hhid = hhid + (
            _norm(df['SSU'], 2) +
            _norm(df['YEAR'], 4)
        )
        
        self.logger.info(f"Created {hhid.nunique():,} unique household IDs")
        
        return hhid
    
    def load_household_data(self, filepath: Path) -> pd.DataFrame:
        """
        Load household-level data with validation.
        
        Args:
            filepath: Path to household CSV file
            
        Returns:
            Validated household DataFrame
        """
        self.logger.info(f"Loading household data from {filepath}")
        
        try:
            if self.config.field_dictionary_household:
                df = self._load_raw_table(filepath, self.config.field_dictionary_household)
                df = self._standardize_nso_household(df)
            else:
                df = pd.read_csv(
                    filepath,
                    sep=self.config.csv_delimiter,
                    low_memory=False,
                )
                if "st" in df.columns and "ST" not in df.columns:
                    df = self._standardize_nso_household(df)
            self.logger.info(f"Loaded {len(df):,} household records")
            
            # Create HHID if not exists
            if 'HHID' not in df.columns:
                df['HHID'] = self.create_household_id(df)
            # Some older rounds include repeated household records for the same key;
            # keep one row so person->household merge remains many-to-one.
            dup_hh = df['HHID'].duplicated().sum()
            if dup_hh > 0:
                self.logger.warning(
                    "Found %s duplicate household rows by HHID; keeping first record per HHID.",
                    dup_hh,
                )
                df = df.drop_duplicates(subset=['HHID'], keep='first').copy()
            
            # Validate
            is_valid, issues = self.validator.validate_household_data(df)
            if not is_valid:
                raise ValueError(f"Household data validation failed: {issues}")
            
            return df
            
        except Exception as e:
            self.logger.error(f"Failed to load household data: {str(e)}")
            raise
    
    def load_person_data(
        self, filepath: Path, household_df: Optional[pd.DataFrame] = None
    ) -> pd.DataFrame:
        """
        Load person-level data with validation.
        
        Args:
            filepath: Path to person CSV file
            household_df: Required for NSO .txt extracts (no survey date on person) to attach YEAR.
            
        Returns:
            Validated person DataFrame
        """
        self.logger.info(f"Loading person data from {filepath}")
        
        try:
            if self.config.field_dictionary_person:
                df = self._load_raw_table(filepath, self.config.field_dictionary_person)
                df = self._standardize_nso_person(df)
                if "YEAR" not in df.columns:
                    if self.round_start_year is not None:
                        df["YEAR"] = self.round_start_year
                    elif household_df is None:
                        raise ValueError(
                            "Person file has no YEAR; pass household_df from the same round "
                            "or add survey year to the extract."
                        )
                    else:
                        df = _attach_year_from_household(df, household_df, self.logger)
            else:
                df = pd.read_csv(
                    filepath,
                    sep=self.config.csv_delimiter,
                    low_memory=False,
                )
                if "st" in df.columns and "ST" not in df.columns:
                    df = self._standardize_nso_person(df)
                    if "YEAR" not in df.columns:
                        if self.round_start_year is not None:
                            df["YEAR"] = self.round_start_year
                        elif household_df is not None:
                            df = _attach_year_from_household(df, household_df, self.logger)
            self.logger.info(f"Loaded {len(df):,} person records")
            
            # Create HHID if not exists
            if 'HHID' not in df.columns:
                df['HHID'] = self.create_household_id(df)
            
            # Validate
            is_valid, issues = self.validator.validate_person_data(df)
            if not is_valid:
                raise ValueError(f"Person data validation failed: {issues}")
            
            return df
            
        except Exception as e:
            self.logger.error(f"Failed to load person data: {str(e)}")
            raise


# =============================================================================
# MULTIPLIER HANDLER
# =============================================================================

class MultiplierHandler:
    """Handle survey multiplier weights according to NSO methodology."""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    def apply_weights(
        self, 
        df: pd.DataFrame,
        estimate_type: str = 'annual',
        num_quarters: int = 4
    ) -> pd.DataFrame:
        """
        Apply survey weights according to estimate type.
        
        Args:
            df: DataFrame with MLTS column
            estimate_type: 'quarterly', 'annual', or 'combined'
            num_quarters: Number of quarters (for annual estimates)
            
        Returns:
            DataFrame with WEIGHT column added
        """
        if 'MLTS' not in df.columns:
            raise ValueError("MLTS column not found in DataFrame")
        
        df = df.copy()
        
        if estimate_type == 'quarterly':
            # Single quarter, single sub-sample
            df['WEIGHT'] = df['MLTS'] / 100
            self.logger.info("Applied quarterly weights (MLTS / 100)")
            
        elif estimate_type == 'annual':
            # Annual estimate across multiple quarters
            df['WEIGHT'] = df['MLTS'] / (100 * num_quarters)
            self.logger.info(f"Applied annual weights (MLTS / {100 * num_quarters})")
            
        elif estimate_type == 'combined':
            # Combined sub-samples (simplified approach)
            df['WEIGHT'] = df['MLTS'] / 200
            self.logger.info("Applied combined sub-sample weights (MLTS / 200)")
            
        else:
            raise ValueError(f"Invalid estimate_type: {estimate_type}")
        
        # Log weight statistics
        self.logger.info(
            f"Weight statistics - Mean: {df['WEIGHT'].mean():.2f}, "
            f"Min: {df['WEIGHT'].min():.2f}, Max: {df['WEIGHT'].max():.2f}"
        )
        
        return df
    
    def validate_weights(
        self, 
        df: pd.DataFrame,
        nso_unemployment: float,
        tolerance: float = 0.5,
        status_measure: str = "ups",
        headline_min_age: int = PLFS_HEADLINE_MIN_AGE,
        sector: Optional[int] = None,
        sex: Optional[int] = None,
        strict_mode: bool = False,
    ) -> Tuple[bool, Dict[str, float]]:
        """
        Validate weights by comparing unemployment estimate to NSO official.
        
        Args:
            df: DataFrame with weights and employment status
            nso_unemployment: NSO official unemployment rate (%)
            tolerance: Acceptable difference in percentage points
            status_measure: UPS or CWS definition used for unemployment status
            headline_min_age: minimum age for headline rates
            sector: optional sector filter (1=rural, 2=urban)
            sex: optional sex filter (1=male, 2=female)
            strict_mode: if True, validation mismatch is logged as error
            
        Returns:
            Tuple of (is_valid, diagnostics_dict)
        """
        if 'WEIGHT' not in df.columns:
            raise ValueError("WEIGHT column not found. Apply weights first.")
        
        # Unemployment rate: unemployed / labour force among filtered headline population.
        sub = df.loc[_age_ge_min_mask(df, headline_min_age)].copy()
        if sector is not None:
            sub = sub[sub["SECTOR"] == sector]
        if sex is not None:
            sub = sub[sub["SEX"] == sex]
        w = sub["WEIGHT"]
        status = (
            sub["status_code"]
            if "status_code" in sub.columns
            else _status_series(sub, status_measure)
        )
        employed_codes, unemployed_codes = _status_code_sets(status_measure)
        unemp = status.isin(unemployed_codes).astype(int)
        ilf = status.isin(employed_codes | unemployed_codes).astype(int)
        weighted_unemployment = _weighted_ratio(unemp, ilf, w) * 100
        
        difference = abs(weighted_unemployment - nso_unemployment)
        is_valid = difference <= tolerance
        
        diagnostics = {
            'estimated_unemployment': weighted_unemployment,
            'nso_unemployment': nso_unemployment,
            'difference': difference,
            'tolerance': tolerance,
            'status_measure': status_measure,
            'headline_min_age': headline_min_age,
            'sector': sector,
            'sex': sex,
            'strict_mode': strict_mode,
            'is_valid': is_valid
        }
        
        if is_valid:
            self.logger.info(
                f"✓ Weight validation PASSED - "
                f"Estimated: {weighted_unemployment:.2f}%, "
                f"NSO: {nso_unemployment:.2f}%, "
                f"Diff: {difference:.2f}pp"
            )
        else:
            log_fn = self.logger.error if strict_mode else self.logger.warning
            log_fn(
                f"✗ Weight validation FAILED - "
                f"Estimated: {weighted_unemployment:.2f}%, "
                f"NSO: {nso_unemployment:.2f}%, "
                f"Diff: {difference:.2f}pp (tolerance: {tolerance}pp)"
            )
        
        return is_valid, diagnostics


# =============================================================================
# DATA PROCESSOR
# =============================================================================

class PLFSDataProcessor:
    """Process and merge PLFS household and person data."""
    
    def __init__(
        self, 
        config: PLFSConfig, 
        logger: logging.Logger
    ):
        self.config = config
        self.logger = logger
        self.loader = PLFSDataLoader(config, logger)
        self.validator = DataValidator(logger)
        self.multiplier_handler = MultiplierHandler(logger)
    
    def merge_household_person(
        self,
        household_df: pd.DataFrame,
        person_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Safely merge household and person data.
        
        Args:
            household_df: Household-level DataFrame
            person_df: Person-level DataFrame
            
        Returns:
            Merged DataFrame
        """
        self.logger.info("Merging household and person data...")
        
        # Select household columns to merge (avoid duplicates)
        hh_cols_to_merge = [
            'HHID', 'MLTS', 'HH_SIZE', 'HH_TYPE', 'RELIGION', 
            'SOCIAL_GROUP', 'MONTHLY_CONSUMER_EXPENDITURE'
        ]
        
        # Keep only existing columns
        hh_cols_to_merge = [col for col in hh_cols_to_merge if col in household_df.columns]
        
        # Ensure HHID is unique in household data
        assert household_df['HHID'].is_unique, "Duplicate HHIDs in household data!"
        
        # Perform merge
        merged = person_df.merge(
            household_df[hh_cols_to_merge],
            on='HHID',
            how='left',
            validate='m:1'  # Many persons to one household
        )
        
        # Validate merge
        is_valid, diagnostics = self.validator.validate_merge(
            person_df, 
            merged, 
            'HHID'
        )
        
        if not is_valid:
            raise ValueError(f"Merge validation failed: {diagnostics}")
        
        self.logger.info(
            f"Merge complete - {len(merged):,} person records with household data"
        )
        
        return merged
    
    def add_derived_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add commonly used derived features.
        
        Args:
            df: Input DataFrame
            
        Returns:
            DataFrame with derived features added
        """
        self.logger.info("Adding derived features...")
        
        df = df.copy()
        
        # Employment status indicators from chosen definition (UPS/CWS)
        status = _status_series(df, self.config.status_measure)
        employed_codes, unemployed_codes = _status_code_sets(self.config.status_measure)
        df["status_code"] = status
        df['employed'] = status.isin(employed_codes).astype(int)
        df['unemployed'] = status.isin(unemployed_codes).astype(int)
        df['in_labor_force'] = (df['employed'] + df['unemployed']).clip(0, 1)
        
        # Demographics
        if 'SEX' in df.columns:
            df['female'] = (df['SEX'] == 2).astype(int)
            df['male'] = (df['SEX'] == 1).astype(int)
        
        if 'AGE' in df.columns:
            df['youth'] = ((df['AGE'] >= 15) & (df['AGE'] <= 29)).astype(int)
            df['working_age'] = ((df['AGE'] >= 15) & (df['AGE'] <= 64)).astype(int)
        
        # Urban/Rural
        if 'SECTOR' in df.columns:
            df['urban'] = (df['SECTOR'] == 2).astype(int)
            df['rural'] = (df['SECTOR'] == 1).astype(int)
        
        self.logger.info("Derived features added successfully")
        
        return df
    
    def process_data(self) -> pd.DataFrame:
        """
        Execute full data processing pipeline.
        
        Returns:
            Processed and validated DataFrame
        """
        self.logger.info("="*80)
        self.logger.info("Starting PLFS data processing pipeline")
        self.logger.info("="*80)
        
        # Step 1: Load data
        household_path = self.config.raw_data_path / self.config.household_file
        person_path = self.config.raw_data_path / self.config.person_file
        
        household_df = self.loader.load_household_data(household_path)
        person_df = self.loader.load_person_data(person_path, household_df=household_df)
        
        # Step 2: Merge
        merged_df = self.merge_household_person(household_df, person_df)
        
        # Step 3: Add derived features
        processed_df = self.add_derived_features(merged_df)
        
        # Step 4: Apply weights
        processed_df = self.multiplier_handler.apply_weights(
            processed_df,
            estimate_type=self.config.estimate_type,
            num_quarters=len(self.config.quarters)
        )
        
        # Step 5: Validate weights
        self.logger.info(
            "Validating unemployment benchmark using %s definition, age >= %s, sector=%s, sex=%s",
            self.config.status_measure.upper(),
            self.config.headline_min_age,
            self.config.validation_sector,
            self.config.validation_sex,
        )
        is_valid, diagnostics = self.multiplier_handler.validate_weights(
            processed_df,
            self.config.nso_unemployment_rate,
            self.config.validation_tolerance,
            status_measure=self.config.status_measure,
            headline_min_age=self.config.headline_min_age,
            sector=self.config.validation_sector,
            sex=self.config.validation_sex,
            strict_mode=bool(getattr(self.config, "validation_strict_mode", False)),
        )
        
        if not is_valid:
            self.logger.warning(
                "Weight validation failed - estimates may not match NSO official figures"
            )
        
        # Step 6: Save processed data
        output_file = self.config.processed_data_path / "plfs_processed_data.parquet"
        processed_df.to_parquet(output_file, index=False, compression='snappy')
        self.logger.info(f"Processed data saved to {output_file}")
        
        self.logger.info("="*80)
        self.logger.info("Pipeline complete!")
        self.logger.info("="*80)
        
        return processed_df


# =============================================================================
# ANALYTICS ENGINE
# =============================================================================

class PLFSAnalytics:
    """Calculate PLFS labor market indicators with proper weighting."""
    
    def __init__(self, logger: logging.Logger, headline_min_age: int = PLFS_HEADLINE_MIN_AGE):
        self.logger = logger
        self.headline_min_age = headline_min_age
    
    def calculate_unemployment_rate(
        self, 
        df: pd.DataFrame,
        by: Optional[Union[str, List[str]]] = None
    ) -> Union[float, pd.Series]:
        """
        Calculate unemployment rate with survey weights.
        
        NSO definition: unemployed / labour force among persons aged 15+ (usual principal status).
        
        Args:
            df: DataFrame with employment data and weights
            by: Column(s) to group by. If None, returns overall rate.
            
        Returns:
            Unemployment rate (%) or Series of rates by group
        """
        df = df.loc[_age_ge_min_mask(df, self.headline_min_age)]

        def ur_one(g: pd.DataFrame) -> float:
            return _weighted_ratio(g["unemployed"], g["in_labor_force"], g["WEIGHT"]) * 100

        if by is None:
            return ur_one(df)
        return df.groupby(by).apply(lambda g: ur_one(g))
    
    def calculate_lfpr(
        self,
        df: pd.DataFrame,
        by: Optional[Union[str, List[str]]] = None
    ) -> Union[float, pd.Series]:
        """
        Calculate Labor Force Participation Rate with survey weights.
        
        NSO definition: labour force / population aged 15+.
        
        Args:
            df: DataFrame with labor force data and weights
            by: Column(s) to group by. If None, returns overall rate.
            
        Returns:
            LFPR (%) or Series of rates by group
        """
        df = df.loc[_age_ge_min_mask(df, self.headline_min_age)]

        def lfpr_one(g: pd.DataFrame) -> float:
            ws = g["WEIGHT"].sum()
            return float(100.0 * (g["WEIGHT"] * g["in_labor_force"]).sum() / ws) if ws > 0 else float("nan")

        if by is None:
            return lfpr_one(df)
        return df.groupby(by).apply(lambda g: lfpr_one(g))
    
    def calculate_wpr(
        self,
        df: pd.DataFrame,
        by: Optional[Union[str, List[str]]] = None
    ) -> Union[float, pd.Series]:
        """
        Calculate Worker Population Ratio with survey weights.
        
        NSO definition: employed / population aged 15+.
        
        Args:
            df: DataFrame with employment data and weights
            by: Column(s) to group by. If None, returns overall rate.
            
        Returns:
            WPR (%) or Series of rates by group
        """
        df = df.loc[_age_ge_min_mask(df, self.headline_min_age)]

        def wpr_one(g: pd.DataFrame) -> float:
            ws = g["WEIGHT"].sum()
            return float(100.0 * (g["WEIGHT"] * g["employed"]).sum() / ws) if ws > 0 else float("nan")

        if by is None:
            return wpr_one(df)
        return df.groupby(by).apply(lambda g: wpr_one(g))
    
    def generate_summary_statistics(
        self, 
        df: pd.DataFrame
    ) -> Dict[str, Union[float, pd.DataFrame]]:
        """
        Generate comprehensive summary statistics.
        
        Args:
            df: Processed PLFS DataFrame
            
        Returns:
            Dictionary of summary statistics
        """
        self.logger.info("Generating summary statistics...")
        
        stats = {
            'national': {
                'unemployment_rate': self.calculate_unemployment_rate(df),
                'lfpr': self.calculate_lfpr(df),
                'wpr': self.calculate_wpr(df)
            },
            'by_gender': {
                'unemployment': self.calculate_unemployment_rate(df, by='SEX'),
                'lfpr': self.calculate_lfpr(df, by='SEX'),
                'wpr': self.calculate_wpr(df, by='SEX')
            },
            'by_sector': {
                'unemployment': self.calculate_unemployment_rate(df, by='SECTOR'),
                'lfpr': self.calculate_lfpr(df, by='SECTOR'),
                'wpr': self.calculate_wpr(df, by='SECTOR')
            }
        }
        
        # State-level
        if 'STATE' in df.columns:
            stats['by_state'] = {
                'unemployment': self.calculate_unemployment_rate(df, by='STATE')
            }
        
        self.logger.info("Summary statistics generated successfully")
        
        return stats


# =============================================================================
# EXPORT UTILITIES
# =============================================================================

class DataExporter:
    """Export processed data and results in various formats."""
    
    def __init__(self, output_path: Path, logger: logging.Logger):
        self.output_path = output_path
        self.logger = logger
    
    def export_to_csv(self, df: pd.DataFrame, filename: str) -> Path:
        """Export DataFrame to CSV."""
        filepath = self.output_path / filename
        df.to_csv(filepath, index=False)
        self.logger.info(f"Exported to CSV: {filepath}")
        return filepath
    
    def export_to_parquet(self, df: pd.DataFrame, filename: str) -> Path:
        """Export DataFrame to Parquet (more efficient)."""
        filepath = self.output_path / filename
        df.to_parquet(filepath, index=False, compression='snappy')
        self.logger.info(f"Exported to Parquet: {filepath}")
        return filepath
    
    def export_summary_to_json(
        self, 
        stats: Dict, 
        filename: str = "summary_statistics.json"
    ) -> Path:
        """Export summary statistics to JSON for web API."""
        import json
        
        # Convert pandas Series to dict
        def convert_to_serializable(obj):
            if isinstance(obj, pd.Series):
                return obj.to_dict()
            elif isinstance(obj, pd.DataFrame):
                return obj.to_dict(orient='records')
            elif isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj)
            elif isinstance(obj, dict):
                return {k: convert_to_serializable(v) for k, v in obj.items()}
            else:
                return obj
        
        serializable_stats = convert_to_serializable(stats)
        
        filepath = self.output_path / filename
        with open(filepath, 'w') as f:
            json.dump(serializable_stats, f, indent=2)
        
        self.logger.info(f"Exported summary to JSON: {filepath}")
        return filepath


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(description="PLFS data processing pipeline")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="YAML config path (default: ./config.yaml)",
    )
    args = parser.parse_args()

    if args.config.is_file():
        config = load_plfs_config_yaml(args.config)
    else:
        config = PLFSConfig(
            raw_data_path=Path("./data/raw"),
            processed_data_path=Path("./data/processed"),
            output_path=Path("./data/output"),
            household_file="chhv1.csv",
            person_file="cperv1.csv",
            estimate_type="annual",
            quarters=[1, 2, 3, 4],
            nso_unemployment_rate=6.7,
            validation_tolerance=0.5,
        )
    
    # Setup logging
    log_file = config.output_path / f"plfs_pipeline_{datetime.now():%Y%m%d_%H%M%S}.log"
    logger = setup_logging(log_file)
    
    try:
        # Initialize processor
        processor = PLFSDataProcessor(config, logger)
        
        # Process data
        processed_df = processor.process_data()
        
        # Generate analytics
        analytics = PLFSAnalytics(logger, headline_min_age=config.headline_min_age)
        summary_stats = analytics.generate_summary_statistics(processed_df)
        
        # Export results
        exporter = DataExporter(config.output_path, logger)
        
        # Export processed data
        exporter.export_to_parquet(
            processed_df,
            "plfs_processed_data.parquet"
        )
        
        # Export summary statistics
        exporter.export_summary_to_json(
            summary_stats,
            "summary_statistics.json"
        )
        
        # Print key results
        logger.info("\n" + "="*80)
        logger.info("KEY RESULTS")
        logger.info("="*80)
        logger.info(f"National Unemployment Rate: {summary_stats['national']['unemployment_rate']:.2f}%")
        logger.info(f"Labor Force Participation Rate: {summary_stats['national']['lfpr']:.2f}%")
        logger.info(f"Worker Population Ratio: {summary_stats['national']['wpr']:.2f}%")
        logger.info("="*80)
        
        logger.info("\nPipeline completed successfully! ✓")
        
    except Exception as e:
        logger.error(f"Pipeline failed: {str(e)}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
