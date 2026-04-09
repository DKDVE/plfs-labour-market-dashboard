# PLFS Labour Market Dashboard

Production-style pipeline and a **static dashboard** for Periodic Labour Force Survey (PLFS) indicators. The public site reads `docs/data/dashboard_data.json` (same schema as `PLFS_Analysis_Notebook.ipynb` exports).

## Website (GitHub Pages)

After deployment, enable Pages once: **Settings → Pages → Build and deployment → Source: GitHub Actions**.

The workflow **Deploy GitHub Pages** publishes the `docs/` folder. Your site URL will be:

`https://<user>.github.io/<repo>/`

## Repository contents

- `plfs_data_pipeline.py` — NSO-weighted UR / LFPR / WPR and extracts
- `config.yaml` — rounds, paths, validation
- `PLFS_Analysis_Notebook.ipynb` — multi-year analysis
- `scripts/build_dashboard_for_site.py` — headless export for CI
- `docs/` — static frontend (HTML/CSS/JS) + bundled JSON for Pages

**Not committed** (see `.gitignore`): virtualenvs, secrets, raw microdata under `data/raw/`, large parquet outputs, logs.

To run the full pipeline locally, place extracted PLFS text files under `data/raw/plfs_extracted/<round_id>/` and run the notebook or `python scripts/build_dashboard_for_site.py`, then copy `data/output/dashboard_data.json` to `docs/data/dashboard_data.json` before pushing.

## Periodic data refresh

Workflow **Refresh dashboard data** (weekly + manual) runs the headless build **only if** raw extracts are present in the runner (e.g. committed or downloaded in a future workflow step). Without raw data, rely on local exports and commit updates to `docs/data/dashboard_data.json`.

## API (optional)

`api.py` is a FastAPI app for local or separate hosting; GitHub Pages does not run it.

## License

Use subject to NSO data terms for PLFS microdata.
