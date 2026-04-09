PLFS reference export — what this is and what it is not
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
