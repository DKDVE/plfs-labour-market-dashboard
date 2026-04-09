#!/usr/bin/env python3
"""
Batch-download PLFS public-use microdata from microdata.gov.in (NADA).

Two supported methods (use one):

1) Official API (optional; often returns 403)
   The portal’s Swagger documents /api/datasets/{id}/fileslist with X-API-KEY, but MoSPI
   frequently responds with ACCESS-DENIED for normal user keys (admin-style ACL on NADA).
   Put the key in .env as X-API-KEY=... or MICRODATA_API_KEY=... — do not commit .env.

2) Cookie + Get Microdata (reliable batch ZIP download)
   Export Netscape cookies.txt after you log in, then either:
     MICRODATA_COOKIES=microdata_cookies.txt
     or:  python download_plfs_microdata.py --cookies microdata_cookies.txt
   If the API returns 403, the script automatically uses this cookie method when set.

   API docs (reference): https://microdata.gov.in/NADA/api-documentation/catalog/

Never paste API keys or cookies into chat or commit them to git.

Respect MoSPI/NADA terms of use; use only your own account.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://microdata.gov.in/NADA/index.php"
USER_AGENT = (
    "Mozilla/5.0 (compatible; PLFS-batch-download/1.0; +https://microdata.gov.in)"
)


def load_dotenv_file(path: Path) -> None:
    """
    Minimal KEY=value loader (no python-dotenv dependency).
    Does not override variables already set in the environment.
    """
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if (val.startswith('"') and val.endswith('"')) or (
            val.startswith("'") and val.endswith("'")
        ):
            val = val[1:-1]
        if key and key not in os.environ:
            os.environ[key] = val


def load_project_dotenv() -> None:
    """Load .env from script directory and current working directory."""
    here = Path(__file__).resolve().parent
    load_dotenv_file(here / ".env")
    load_dotenv_file(Path.cwd() / ".env")


def resolve_cookies_path(cookies_cli: Optional[Path]) -> Optional[Path]:
    """CLI --cookies or env MICRODATA_COOKIES (path to Netscape cookies.txt)."""
    if cookies_cli is not None:
        return cookies_cli
    p = os.environ.get("MICRODATA_COOKIES", "").strip()
    return Path(p) if p else None

# July–June panel unit-level style rounds (matches Nesstar hhv1/perv1/hhrv/perrv family).
DEFAULT_PANEL_ZIPS = [
    (204, "july2017_june2018"),
    (216, "july2018_june2019"),
    (217, "july2019_june2020"),
    (206, "july2020_june2021"),
    (214, "july2021_june2022"),
    (210, "july2022_june2023"),
    (213, "july2023_june2024"),
]

# Optional: calendar-year studies (different file naming — often chhv1/cperv1 in docs).
OPTIONAL_CALENDAR = [
    (209, "calendar_2021_jan21_dec21"),
    (211, "calendar_2022_jan22_dec22"),
    (208, "calendar_2023_jan23_dec23"),
]


def load_cookie_jar(path: Path) -> requests.cookies.RequestsCookieJar:
    jar = requests.cookies.RequestsCookieJar()
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _, path_s, secure, expires, name, value = parts[:7]
        if "microdata.gov.in" not in domain:
            continue
        jar.set(name, value, domain=domain.lstrip("."), path=path_s or "/")
    return jar


def discover_plfs_catalog_rows() -> List[dict]:
    """Public search API — no login required."""
    url = f"{BASE}/api/catalog"
    r = requests.get(
        url,
        params={"sk": "PLFS", "limit": 50, "offset": 0},
        headers={"User-Agent": USER_AGENT},
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    rows = data.get("result", {}).get("rows", [])
    return rows


def get_microdata_html(session: requests.Session, catalog_id: int) -> str:
    url = f"{BASE}/catalog/{catalog_id}/get-microdata"
    r = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=120)
    r.raise_for_status()
    return r.text


def find_download_targets(html: str, page_url: str) -> Tuple[List[Tuple[str, str]], List[str]]:
    """
    Returns:
      zip_targets: list of (absolute_url, suggested_label)
      other_notes: human-readable lines (e.g. Nesstar only)
    """
    soup = BeautifulSoup(html, "html.parser")
    zip_targets: List[Tuple[str, str]] = []
    notes: List[str] = []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = " ".join(a.get_text().split())
        full = urljoin(page_url, href)
        low = text.lower()
        hlow = href.lower()
        if "login" in low and "access" in html.lower():
            continue
        if "zip" in low or hlow.endswith(".zip") or "zip" in hlow:
            label = re.sub(r"[^\w\.\-\s\[\],]+", "", text)[:80] or "download.zip"
            zip_targets.append((full, label))
        elif "nesstar" in low or hlow.endswith(".nesstar"):
            notes.append(f"Nesstar link (manual / Windows Explorer): {full}")

    # De-duplicate zip URLs preserving order
    seen = set()
    deduped: List[Tuple[str, str]] = []
    for u, lbl in zip_targets:
        if u not in seen:
            seen.add(u)
            deduped.append((u, lbl))
    return deduped, notes


def _api_headers(api_key: str) -> dict:
    return {"User-Agent": USER_AGENT, "X-API-KEY": api_key.strip()}


def extract_files_from_payload(data: Any) -> List[dict]:
    """Normalize fileslist JSON into a list of dict-like file entries."""
    if not isinstance(data, dict):
        return []
    candidates: List[Any] = []
    if isinstance(data.get("files"), list):
        candidates = data["files"]
    elif isinstance(data.get("result"), list):
        candidates = data["result"]
    elif isinstance(data.get("result"), dict):
        inner = data["result"]
        if isinstance(inner.get("files"), list):
            candidates = inner["files"]
        elif isinstance(inner.get("rows"), list):
            candidates = inner["rows"]
    out: List[dict] = []
    for item in candidates:
        if isinstance(item, dict):
            out.append(item)
        elif isinstance(item, str):
            out.append({"filename": item})
    return out


def file_download_token(entry: Dict[str, Any]) -> Optional[str]:
    """Return path token for /fileslist/download/... (usually base64 from API)."""
    for k in ("base64", "file_base64", "FileNo", "encoded_name", "file_no"):
        v = entry.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    fn = entry.get("filename") or entry.get("file_name") or entry.get("name")
    if fn:
        return base64.b64encode(str(fn).encode("utf-8")).decode("ascii")
    return None


def suggested_disk_name(entry: Dict[str, Any], catalog_id: int, slug: str) -> str:
    fn = entry.get("filename") or entry.get("file_name") or entry.get("name")
    if fn:
        safe = re.sub(r"[^\w\.\-]+", "_", str(fn))
        return f"{catalog_id}_{slug}_{safe}"
    return f"{catalog_id}_{slug}_download.bin"


def download_file(
    session: requests.Session,
    url: str,
    dest: Path,
    delay_sec: float,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    time.sleep(delay_sec)
    with session.get(
        url, headers={"User-Agent": USER_AGENT}, stream=True, timeout=300
    ) as r:
        r.raise_for_status()
        # Heuristic: small HTML usually means error or login redirect
        ctype = r.headers.get("Content-Type", "")
        clen = r.headers.get("Content-Length")
        if "text/html" in ctype and (clen is None or int(clen) < 50000):
            chunk = next(r.iter_content(chunk_size=8192), b"")
            if b"Login" in chunk or b"login" in chunk.lower():
                raise RuntimeError(
                    f"Server returned HTML (likely not logged in). First bytes: {chunk[:200]!r}"
                )
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)


def _api_denied(r: requests.Response, data: Any) -> bool:
    if r.status_code in (401, 403):
        return True
    if not isinstance(data, dict):
        return False
    if data.get("message") == "ACCESS-DENIED":
        return True
    if data.get("status") == "failed" and "ACCESS" in str(data.get("message", "")).upper():
        return True
    return False


def download_study_via_cookie_session(
    session: requests.Session,
    sid: int,
    slug: str,
    output_dir: Path,
    delay: float,
    dry_run: bool,
    manifest: dict,
) -> None:
    """One study: Get Microdata HTML → find ZIP links → download."""
    page_url = f"{BASE}/catalog/{sid}/get-microdata"
    print(f"  (cookie mode) opening Get Microdata for {sid}…")
    try:
        html = get_microdata_html(session, sid)
    except requests.RequestException as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        manifest["studies"].append({"catalog_id": sid, "slug": slug, "error": str(e)})
        return

    if "Login to access data" in html or "user must be logged in" in html.lower():
        print("  ERROR: not logged in (cookies missing or expired).", file=sys.stderr)
        manifest["studies"].append({"catalog_id": sid, "slug": slug, "error": "login_required"})
        return

    zips, notes = find_download_targets(html, page_url)
    for n in notes:
        print(f"  note: {n}")
    if not zips:
        hint = output_dir / f"{sid}_{slug}_no_zip_found.txt"
        hint.write_text(
            "No ZIP link parsed from Get Microdata page.\n"
            f"URL: {page_url}\n",
            encoding="utf-8",
        )
        print(f"  WARNING: no ZIP link; wrote {hint}")
        manifest["studies"].append(
            {"catalog_id": sid, "slug": slug, "hint_file": str(hint), "mode": "cookie"}
        )
        return

    for url, label in zips:
        parsed = urlparse(url)
        fname = Path(parsed.path).name
        if not fname or fname == "get-microdata":
            safe = re.sub(r"[^\w\.\-]+", "_", label)[:60]
            fname = f"{sid}_{slug}_{safe}.zip"
        else:
            fname = f"{sid}_{slug}_{fname}"
        dest = output_dir / fname
        if not dest.suffix:
            dest = dest.with_suffix(".zip")
        print(f"  ZIP: {url}\n       -> {dest}")
        if dry_run:
            manifest["studies"].append(
                {"catalog_id": sid, "slug": slug, "url": url, "mode": "cookie"}
            )
            continue
        try:
            download_file(session, url, dest, delay_sec=delay)
            print(f"       saved ({dest.stat().st_size // 1024 // 1024} MiB)")
            manifest["studies"].append(
                {
                    "catalog_id": sid,
                    "slug": slug,
                    "file": str(dest),
                    "url": url,
                    "mode": "cookie",
                }
            )
        except Exception as e:
            print(f"       ERROR: {e}", file=sys.stderr)
            manifest["studies"].append(
                {"catalog_id": sid, "slug": slug, "url": url, "error": str(e), "mode": "cookie"}
            )


def run_api(
    api_key: str,
    output_dir: Path,
    studies: List[Tuple[int, str]],
    delay: float,
    dry_run: bool,
    zip_only: bool,
    dump_fileslist: bool,
    cookies_path: Optional[Path],
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict = {
        "mode": "x_api_key_with_optional_cookie_fallback",
        "studies": [],
    }
    session = requests.Session()
    if cookies_path is not None and cookies_path.is_file():
        session.cookies.update(load_cookie_jar(cookies_path))
        print(
            "Using browser cookies together with X-API-KEY (helps if the server checks both)."
        )

    for idx, (sid, slug) in enumerate(studies):
        print(f"\n=== API catalog {sid} ({slug}) ===")
        try:
            r = session.get(
                f"{BASE}/api/datasets/{sid}/fileslist",
                headers=_api_headers(api_key),
                timeout=120,
            )
            data: Any = None
            try:
                data = r.json()
            except Exception:
                data = None

            if r.status_code != 200 or _api_denied(r, data):
                msg = ""
                if isinstance(data, dict):
                    msg = str(data.get("message", ""))
                print(
                    f"  fileslist not available (HTTP {r.status_code} {msg}). "
                    "MoSPI often restricts this endpoint; falling back to cookie/HTML download if possible.",
                    file=sys.stderr,
                )
                if cookies_path is not None and cookies_path.is_file():
                    cs = requests.Session()
                    cs.cookies.update(load_cookie_jar(cookies_path))
                    download_study_via_cookie_session(
                        cs, sid, slug, output_dir, delay, dry_run, manifest
                    )
                else:
                    print(
                        "  Add Netscape cookies: export MICRODATA_COOKIES=path/to/cookies.txt\n"
                        "  or run without X-API-KEY in .env and use:  --cookies cookies.txt",
                        file=sys.stderr,
                    )
                    manifest["studies"].append(
                        {
                            "catalog_id": sid,
                            "slug": slug,
                            "error": "api_fileslist_denied_no_cookie_fallback",
                        }
                    )
                continue

            if isinstance(data, dict) and data.get("status") == "failed" and not _api_denied(
                r, data
            ):
                msg = data.get("message", data)
                print(f"  ERROR fileslist: {msg}", file=sys.stderr)
                manifest["studies"].append({"catalog_id": sid, "slug": slug, "error": str(msg)})
                continue
        except Exception as e:
            print(f"  ERROR fileslist: {e}", file=sys.stderr)
            manifest["studies"].append({"catalog_id": sid, "slug": slug, "error": str(e)})
            continue

        if data is None:
            continue

        if dump_fileslist and idx == 0:
            sample = output_dir / "_debug_fileslist_sample.json"
            sample.write_text(json.dumps(data, indent=2)[:12000], encoding="utf-8")
            print(f"  [debug] wrote first fileslist response (truncated) to {sample}")

        files = extract_files_from_payload(data)
        if not files:
            print("  WARNING: empty files list; check _debug_fileslist_sample.json if --dump-fileslist", file=sys.stderr)
            manifest["studies"].append({"catalog_id": sid, "slug": slug, "error": "no_files"})
            continue

        downloaded_any = False
        for entry in files:
            name_hint = str(
                entry.get("filename") or entry.get("file_name") or entry.get("name") or ""
            )
            if zip_only and name_hint and not name_hint.lower().endswith(".zip"):
                continue

            token = file_download_token(entry)
            if not token:
                continue

            path_token = quote(token, safe="")
            url = f"{BASE}/api/fileslist/download/{sid}/{path_token}"
            dest = output_dir / suggested_disk_name(entry, sid, slug)
            print(f"  file: {name_hint or '(unknown name)'}\n       -> {dest}")
            if dry_run:
                downloaded_any = True
                continue

            time.sleep(delay)
            try:
                with session.get(
                    url, headers=_api_headers(api_key), stream=True, timeout=600
                ) as dr:
                    dr.raise_for_status()
                    ctype = dr.headers.get("Content-Type", "")
                    if "application/json" in ctype:
                        body = dr.content[:500]
                        raise RuntimeError(f"unexpected JSON response: {body!r}")
                    with open(dest, "wb") as out_f:
                        for chunk in dr.iter_content(chunk_size=1024 * 256):
                            if chunk:
                                out_f.write(chunk)
                sz = dest.stat().st_size
                print(f"       saved ({sz // 1024 // 1024} MiB)")
                manifest["studies"].append(
                    {"catalog_id": sid, "slug": slug, "file": str(dest), "url": url}
                )
                downloaded_any = True
            except Exception as e:
                print(f"       ERROR: {e}", file=sys.stderr)
                manifest["studies"].append(
                    {"catalog_id": sid, "slug": slug, "url": url, "error": str(e)}
                )

        if not downloaded_any and not dry_run:
            manifest["studies"].append(
                {"catalog_id": sid, "slug": slug, "error": "no_matching_files"}
            )

    mf = output_dir / "download_manifest.json"
    if not dry_run:
        mf.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"\nWrote manifest: {mf}")
    return 0


def run(
    cookies_path: Path,
    output_dir: Path,
    studies: List[Tuple[int, str]],
    delay: float,
    dry_run: bool,
) -> int:
    jar = load_cookie_jar(cookies_path)
    session = requests.Session()
    session.cookies.update(jar)

    manifest: dict = {"studies": []}
    for sid, slug in studies:
        page_url = f"{BASE}/catalog/{sid}/get-microdata"
        print(f"\n=== Catalog {sid} ({slug}) ===")
        try:
            html = get_microdata_html(session, sid)
        except requests.RequestException as e:
            print(f"  ERROR fetching page: {e}", file=sys.stderr)
            manifest["studies"].append(
                {"catalog_id": sid, "slug": slug, "error": str(e)}
            )
            continue

        if "Login to access data" in html or "user must be logged in" in html.lower():
            print(
                "  Not authenticated: page asks for login. Check cookies file.",
                file=sys.stderr,
            )
            manifest["studies"].append(
                {
                    "catalog_id": sid,
                    "slug": slug,
                    "error": "login_required",
                }
            )
            continue

        zips, notes = find_download_targets(html, page_url)
        for n in notes:
            print(f"  note: {n}")
        if not zips:
            hint = output_dir / f"{sid}_{slug}_no_zip_found.txt"
            hint.write_text(
                "No ZIP link parsed from Get Microdata page.\n"
                "Open the page in a browser and download manually, or inspect HTML for changes.\n"
                f"URL: {page_url}\n",
                encoding="utf-8",
            )
            print(f"  WARNING: no ZIP link found; wrote {hint}")
            manifest["studies"].append(
                {
                    "catalog_id": sid,
                    "slug": slug,
                    "zip_urls": [],
                    "hint_file": str(hint),
                }
            )
            continue

        for url, label in zips:
            parsed = urlparse(url)
            fname = Path(parsed.path).name
            if not fname or fname == "get-microdata":
                safe = re.sub(r"[^\w\.\-]+", "_", label)[:60]
                fname = f"{sid}_{slug}_{safe}.zip"
            else:
                fname = f"{sid}_{slug}_{fname}"
            dest = output_dir / fname
            if not dest.suffix:
                dest = dest.with_suffix(".zip")
            print(f"  ZIP: {url}\n       -> {dest}")
            if dry_run:
                continue
            try:
                download_file(session, url, dest, delay_sec=delay)
                print(f"       saved ({dest.stat().st_size // 1024 // 1024} MiB)")
            except Exception as e:
                print(f"       ERROR: {e}", file=sys.stderr)
                manifest["studies"].append(
                    {
                        "catalog_id": sid,
                        "slug": slug,
                        "url": url,
                        "error": str(e),
                    }
                )
                continue
            manifest["studies"].append(
                {
                    "catalog_id": sid,
                    "slug": slug,
                    "file": str(dest),
                    "url": url,
                }
            )

    mf = output_dir / "download_manifest.json"
    if not dry_run:
        mf.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"\nWrote manifest: {mf}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Batch PLFS ZIP download (microdata.gov.in)")
    p.add_argument(
        "--api-key-file",
        type=Path,
        default=None,
        help="Path to a one-line file containing your X-API-KEY (safer than shell history)",
    )
    p.add_argument(
        "--all-files",
        action="store_true",
        help="With API mode: download every file from fileslist, not only .zip",
    )
    p.add_argument(
        "--dump-fileslist",
        action="store_true",
        help="With API mode: save first fileslist JSON sample for debugging",
    )
    p.add_argument(
        "--cookies",
        type=Path,
        help="Netscape cookies.txt for microdata.gov.in (after you log in)",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/raw/plfs_zips"),
        help="Directory for downloaded ZIPs",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Seconds between requests (be polite to the server)",
    )
    p.add_argument(
        "--include-calendars",
        action="store_true",
        help="Also download calendar-year PLFS studies (209, 211, 208)",
    )
    p.add_argument(
        "--catalog-ids",
        type=str,
        default="",
        help="Comma-separated NADA numeric IDs (overrides default list), e.g. 204,213",
    )
    p.add_argument(
        "--discover-plfs",
        action="store_true",
        help="Print PLFS studies from public API and exit",
    )
    p.add_argument("--dry-run", action="store_true", help="List URLs only; do not download")
    args = p.parse_args()

    if args.discover_plfs:
        rows = discover_plfs_catalog_rows()
        for row in rows:
            print(
                f"id={row['id']:>3}  idno={row.get('idno','')[:40]:40}  {row.get('title','')[:70]}"
            )
        print(f"\nTotal: {len(rows)}")
        return 0

    load_project_dotenv()

    api_key = (
        os.environ.get("MICRODATA_API_KEY") or os.environ.get("X-API-KEY") or ""
    ).strip()
    if args.api_key_file is not None:
        if not args.api_key_file.is_file():
            print(
                f"Error: --api-key-file not found: {args.api_key_file}",
                file=sys.stderr,
            )
            return 2
        api_key = args.api_key_file.read_text(encoding="utf-8").strip()

    if args.catalog_ids.strip():
        ids = []
        for part in args.catalog_ids.split(","):
            part = part.strip()
            if not part:
                continue
            ids.append((int(part), f"catalog_{part}"))
        studies = ids
    else:
        studies = list(DEFAULT_PANEL_ZIPS)
        if args.include_calendars:
            studies.extend(OPTIONAL_CALENDAR)

    cookies_path = resolve_cookies_path(args.cookies)
    cookie_file: Optional[Path] = None
    if cookies_path is not None:
        if cookies_path.is_file():
            cookie_file = cookies_path
        else:
            print(
                f"Warning: cookies path not found: {cookies_path.resolve()} — "
                "API fallback to HTML download will not work until this file exists.",
                file=sys.stderr,
            )

    if api_key:
        return run_api(
            api_key=api_key,
            output_dir=args.output_dir,
            studies=studies,
            delay=args.delay,
            dry_run=args.dry_run,
            zip_only=not args.all_files,
            dump_fileslist=args.dump_fileslist,
            cookies_path=cookie_file,
        )

    if not cookie_file:
        print(
            "Error: need either X-API-KEY / MICRODATA_API_KEY in .env, or a Netscape cookies file.\n"
            "  Cookies: export after login, save as microdata_cookies.txt and set MICRODATA_COOKIES=... or --cookies\n"
            "  Note: /api/.../fileslist often returns 403 for normal accounts; cookies + Get Microdata is reliable.\n"
            "  Do not paste secrets into chat or commit .env.",
            file=sys.stderr,
        )
        return 2

    return run(
        cookies_path=cookie_file,
        output_dir=args.output_dir,
        studies=studies,
        delay=args.delay,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
