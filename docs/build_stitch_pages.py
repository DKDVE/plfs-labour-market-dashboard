#!/usr/bin/env python3
"""Generate GitHub Pages HTML from Stitch exports + wire navigation."""
from pathlib import Path

ROOT = Path(__file__).parent

CHART_UMD_SCRIPT = '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.min.js" crossorigin="anonymous"></script>\n'

CHART_REPLACEMENT = """<!-- Live Chart.js (data from data/dashboard_data.json) -->
<div class="relative h-64 w-full">
<canvas id="plfs-trend-chart" aria-label="UR, LFPR, and WPR over time"></canvas>
</div>"""


def patch_overview(html: str) -> str:
    # Sidebar + top nav + chrome are already wired in stitch_overview.html

    # Ribbon meta
    html = html.replace(
        '<p class="text-[10px] text-on-surface-variant font-mono opacity-70">Source: data/processed/plfs_processed_data.parquet</p>',
        '<p class="text-[10px] text-on-surface-variant font-mono opacity-70">Latest round: <span data-bind="meta-round">—</span> · Generated: <span data-bind="meta-generated">—</span> · Rounds: <span data-bind="meta-rounds-count">—</span></p>',
    )

    # Last computed
    html = html.replace(
        '<span class="opacity-60 italic">Last computed: 2026-05-20</span>',
        '<span class="opacity-60 italic">Last computed: <span data-bind="meta-generated">—</span></span>',
    )

    # Error banner (after opening dashboard canvas div)
    html = html.replace(
        '<!-- Dashboard Canvas -->\n<div class="p-8 space-y-8 max-w-7xl mx-auto w-full min-w-0">',
        '<!-- Dashboard Canvas -->\n<div class="p-8 space-y-8 max-w-7xl mx-auto w-full min-w-0">\n<div id="plfs-data-error" class="rounded-lg border border-error/30 bg-error-container/20 px-4 py-3 text-sm text-on-error-container" role="alert" hidden></div>',
    )

    # KPI ids + deltas + bars
    html = html.replace(
        '<div class="flex items-center gap-1 text-error font-bold text-xs bg-error-container/20 px-2 py-1 rounded-full">\n<span class="material-symbols-outlined text-[14px]">trending_up</span>\n                            +0.24\n                        </div>',
        '<div class="flex items-center gap-1 text-error font-bold text-xs bg-error-container/20 px-2 py-1 rounded-full">\n<span class="material-symbols-outlined text-[14px]" id="delta-ur-icon">trending_up</span>\n<span id="delta-ur">+0.24</span>\n                        </div>',
    )
    html = html.replace(
        '<h3 class="text-5xl font-black tracking-tighter text-on-surface">4.18%</h3>\n<span class="text-xs text-on-surface-variant font-medium">2023-24</span>',
        '<h3 class="text-5xl font-black tracking-tighter text-on-surface" id="kpi-ur">4.18%</h3>\n<span class="text-xs text-on-surface-variant font-medium" data-bind="kpi-year">2023-24</span>',
        1,
    )
    html = html.replace(
        '<div class="h-full bg-error w-[4.18%] rounded-full"></div>',
        '<div class="h-full bg-error rounded-full transition-all" id="bar-ur" style="width:4.18%"></div>',
        1,
    )

    html = html.replace(
        '<div class="flex items-center gap-1 text-on-tertiary-container font-bold text-xs bg-tertiary-container/10 px-2 py-1 rounded-full">\n<span class="material-symbols-outlined text-[14px]">trending_up</span>\n                            +1.58\n                        </div>',
        '<div class="flex items-center gap-1 text-on-tertiary-container font-bold text-xs bg-tertiary-container/10 px-2 py-1 rounded-full">\n<span class="material-symbols-outlined text-[14px]" id="delta-lfpr-icon">trending_up</span>\n<span id="delta-lfpr">+1.58</span>\n                        </div>',
        1,
    )
    html = html.replace(
        '<h3 class="text-5xl font-black tracking-tighter text-on-surface">54.19%</h3>\n<span class="text-xs text-on-surface-variant font-medium">2023-24</span>',
        '<h3 class="text-5xl font-black tracking-tighter text-on-surface" id="kpi-lfpr">54.19%</h3>\n<span class="text-xs text-on-surface-variant font-medium" data-bind="kpi-year">2023-24</span>',
        1,
    )
    html = html.replace(
        '<div class="h-full bg-secondary w-[54.19%] rounded-full"></div>',
        '<div class="h-full bg-secondary rounded-full transition-all" id="bar-lfpr" style="width:54.19%"></div>',
        1,
    )

    html = html.replace(
        '<div class="flex items-center gap-1 text-on-tertiary-container font-bold text-xs bg-tertiary-container/10 px-2 py-1 rounded-full">\n<span class="material-symbols-outlined text-[14px]">trending_up</span>\n                            +1.40\n                        </div>',
        '<div class="flex items-center gap-1 text-on-tertiary-container font-bold text-xs bg-tertiary-container/10 px-2 py-1 rounded-full">\n<span class="material-symbols-outlined text-[14px]" id="delta-wpr-icon">trending_up</span>\n<span id="delta-wpr">+1.40</span>\n                        </div>',
        1,
    )
    html = html.replace(
        '<h3 class="text-5xl font-black tracking-tighter text-on-surface">51.93%</h3>\n<span class="text-xs text-on-surface-variant font-medium">2023-24</span>',
        '<h3 class="text-5xl font-black tracking-tighter text-on-surface" id="kpi-wpr">51.93%</h3>\n<span class="text-xs text-on-surface-variant font-medium" data-bind="kpi-year">2023-24</span>',
        1,
    )
    html = html.replace(
        '<div class="h-full bg-on-tertiary-container w-[51.93%] rounded-full"></div>',
        '<div class="h-full bg-on-tertiary-container rounded-full transition-all" id="bar-wpr" style="width:51.93%"></div>',
        1,
    )

    # Static trend → Chart.js
    start = "<!-- Simplified Visual Representation of Trend -->"
    end = "<!-- Insights Panel -->"
    i0 = html.find(start)
    i1 = html.find(end)
    if i0 != -1 and i1 != -1:
        html = html[:i0] + CHART_REPLACEMENT + "\n" + html[i1:]

    # Insights
    html = html.replace(
        '<strong class="text-white block mb-1">Unemployment Dynamics</strong>\n                                Unemployment Rate (UR) shows a steady decline from 7.80% (2017-18) to 3.94% (2022-23), with a slight uptick to 4.18% in the latest round.',
        '<strong class="text-white block mb-1">Unemployment Dynamics</strong>\n                                <span id="insight-ur" class="block mt-1">Unemployment Rate (UR) shows a steady decline from 7.80% (2017-18) to 3.94% (2022-23), with a slight uptick to 4.18% in the latest round.</span>',
    )
    html = html.replace(
        '<strong class="text-white block mb-1">Participation Growth</strong>\n                                Labour Force Participation Rate (LFPR) has consistently improved, reaching a multi-year high of 54.19%.',
        '<strong class="text-white block mb-1">Participation Growth</strong>\n                                <span id="insight-lfpr" class="block mt-1">Labour Force Participation Rate (LFPR) has consistently improved, reaching a multi-year high of 54.19%.</span>',
    )
    html = html.replace(
        '<strong class="text-white block mb-1">Worker Ratio Alignment</strong>\n                                Worker Population Ratio (WPR) has tracked closely with LFPR, increasing from 43.40% to 51.93%.',
        '<strong class="text-white block mb-1">Worker Ratio Alignment</strong>\n                                <span id="insight-wpr" class="block mt-1">Worker Population Ratio (WPR) has tracked closely with LFPR, increasing from 43.40% to 51.93%.</span>',
    )

    # Coverage table
    html = html.replace(
        '<table class="w-full table-fixed text-left border-collapse">',
        '<table class="w-full table-fixed text-left border-collapse" id="plfs-coverage-table">',
        1,
    )
    # Remove old static coverage tbody rows
    import re

    html = re.sub(
        r"<tbody class=\"divide-y divide-outline-variant/10\">.*?</tbody>",
        '<tbody class="divide-y divide-outline-variant/10"></tbody>',
        html,
        count=1,
        flags=re.DOTALL,
    )

    # Footer methodology
    html = html.replace(
        '<a class="hover:underline hover:text-[#0061a5] focus:outline-none focus:ring-1 focus:ring-[#0061a5]" href="#">Methodology</a>',
        '<a class="hover:underline hover:text-[#0061a5] focus:outline-none focus:ring-1 focus:ring-[#0061a5]" href="methodology.html">Methodology</a>',
    )

    # Age band table (latest round)
    age_block = """
<!-- Latest round — unemployment by age band -->
<div class="bg-surface-container-lowest p-8 rounded-xl shadow-[0_12px_32px_-4px_rgba(0,32,69,0.08)] border border-outline-variant/10">
<h4 class="text-lg font-bold text-on-surface mb-2">Latest round — unemployment by age band</h4>
<p class="text-xs text-on-surface-variant mb-4">UPS definitions, age 15+ (same extract as pipeline JSON)</p>
<div class="overflow-x-auto rounded-lg border border-outline-variant/10">
<table class="w-full text-left" id="plfs-age-table">
<thead class="bg-surface-container-high">
<tr>
<th class="px-4 py-3 text-[10px] font-black uppercase tracking-widest text-on-surface-variant">Age group</th>
<th class="px-4 py-3 text-[10px] font-black uppercase tracking-widest text-on-surface-variant">UR</th>
</tr>
</thead>
<tbody class="divide-y divide-outline-variant/10"></tbody>
</table>
</div>
</div>
"""
    html = html.replace(
        "<!-- Secondary Panel: Sample Coverage -->",
        age_block + "\n<!-- Secondary Panel: Sample Coverage -->",
    )

    # Scripts before </body>
    scripts = """
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.6/dist/chart.umd.min.js" crossorigin="anonymous"></script>
<script src="assets/js/plfs-dashboard.js" defer></script>
"""
    html = html.replace("</body></html>", scripts + "\n</body></html>")

    return html


NAV_RURAL_ACTIVE = (
    '<a class="text-[#181c1e] font-medium hover:text-[#0061a5] transition-colors focus-visible:text-[#0061a5]" href="index.html">Dashboard</a>\n'
    '<a class="text-[#181c1e] font-medium hover:text-[#0061a5] transition-colors focus-visible:text-[#0061a5]" href="demographics.html">Demographics</a>\n'
    '<a class="text-[#0061a5] font-bold border-b-2 border-[#0061a5] pb-1" href="rural-urban.html">Rural vs Urban</a>\n'
    '<a class="text-[#181c1e] font-medium hover:text-[#0061a5] transition-colors focus-visible:text-[#0061a5]" href="methodology.html">Methodology</a>\n'
    '<a class="text-[#181c1e] font-medium hover:text-[#0061a5] transition-colors focus-visible:text-[#0061a5]" href="board-report.html">Board Report</a>'
)

METH_NAV_OLD = """<nav aria-label="Main Navigation" class="hidden md:flex gap-8">
<a class="text-[#181c1e]/60 dark:text-[#ffffff]/60 hover:text-[#0061a5] transition-colors focus-ring" href="#">Dashboard</a>
<a class="text-[#181c1e]/60 dark:text-[#ffffff]/60 hover:text-[#0061a5] transition-colors focus-ring" href="#">Demographics</a>
<a class="text-[#181c1e]/60 dark:text-[#ffffff]/60 hover:text-[#0061a5] transition-colors focus-ring" href="#">Rural vs Urban</a>
<a aria-current="page" class="text-[#002045] dark:text-[#66affe] border-b-2 border-[#0061a5] font-semibold transition-colors focus-ring" href="#">Methodology</a>
<a class="text-[#181c1e]/60 dark:text-[#ffffff]/60 hover:text-[#0061a5] transition-colors focus-ring" href="#">Board Report</a>
</nav>"""

METH_NAV_NEW = """<nav aria-label="Main Navigation" class="hidden md:flex gap-8">
<a class="text-[#181c1e]/60 dark:text-[#ffffff]/60 hover:text-[#0061a5] transition-colors focus-ring" href="index.html">Dashboard</a>
<a class="text-[#181c1e]/60 dark:text-[#ffffff]/60 hover:text-[#0061a5] transition-colors focus-ring" href="demographics.html">Demographics</a>
<a class="text-[#181c1e]/60 dark:text-[#ffffff]/60 hover:text-[#0061a5] transition-colors focus-ring" href="rural-urban.html">Rural vs Urban</a>
<a aria-current="page" class="text-[#002045] dark:text-[#66affe] border-b-2 border-[#0061a5] font-semibold transition-colors focus-ring" href="methodology.html">Methodology</a>
<a class="text-[#181c1e]/60 dark:text-[#ffffff]/60 hover:text-[#0061a5] transition-colors focus-ring" href="board-report.html">Board Report</a>
</nav>"""


def patch_demographics(html: str) -> str:
    html = html.replace(
        '<div class="text-4xl font-black text-on-surface tracking-tighter mb-1">3.83%</div>',
        '<div class="text-4xl font-black text-on-surface tracking-tighter mb-1" id="demo-male-ur">3.83%</div>',
        1,
    )
    html = html.replace(
        '<div class="text-4xl font-black text-on-surface tracking-tighter mb-1">4.88%</div>',
        '<div class="text-4xl font-black text-on-surface tracking-tighter mb-1" id="demo-female-ur">4.88%</div>',
        1,
    )
    html = html.replace(
        '<span class="hover:text-primary cursor-pointer">Home</span>',
        '<a class="hover:text-primary" href="index.html">Home</a>',
        1,
    )
    html = html.replace(
        '<a class="text-slate-500 hover:text-blue-600 text-xs transition-colors focus:ring-2 focus:ring-primary outline-none px-1 rounded" href="#">Methodology Notes</a>',
        '<a class="text-slate-500 hover:text-blue-600 text-xs transition-colors focus:ring-2 focus:ring-primary outline-none px-1 rounded" href="methodology.html">Methodology Notes</a>',
        1,
    )
    return html


def patch_rural_urban(html: str) -> str:
    old = """<nav class="hidden md:flex gap-8"><a class="text-[#181c1e] font-medium hover:text-[#0061a5] transition-colors focus-visible:text-[#0061a5]" href="#">Dashboard</a>
<a class="text-[#181c1e] font-medium hover:text-[#0061a5] transition-colors focus-visible:text-[#0061a5]" href="#">Demographics</a>
<a class="text-[#0061a5] font-bold border-b-2 border-[#0061a5] pb-1" href="#">Rural vs Urban</a>
<a class="text-[#181c1e] font-medium hover:text-[#0061a5] transition-colors focus-visible:text-[#0061a5]" href="#">Methodology</a>
<a class="text-[#181c1e] font-medium hover:text-[#0061a5] transition-colors focus-visible:text-[#0061a5]" href="#">Board Report</a></nav>"""
    if old in html:
        html = html.replace(old, f"<nav class=\"hidden md:flex gap-8\">{NAV_RURAL_ACTIVE}</nav>")
    html = html.replace('<a class="hover:text-primary" href="#">Home</a>', '<a class="hover:text-primary" href="index.html">Home</a>', 1)
    html = html.replace(
        '<a class="hover:text-[#002045] transition-colors focus-visible:text-primary" href="#">Methodology Notes</a>',
        '<a class="hover:text-[#002045] transition-colors focus-visible:text-primary" href="methodology.html">Methodology Notes</a>',
        1,
    )
    return html


def patch_methodology(html: str) -> str:
    if METH_NAV_OLD in html:
        html = html.replace(METH_NAV_OLD, METH_NAV_NEW)
    return html


def patch_board_report(html: str) -> str:
    return html


def main():
    overview = (ROOT / "stitch_overview.html").read_text(encoding="utf-8")
    (ROOT / "index.html").write_text(patch_overview(overview), encoding="utf-8")

    d = (ROOT / "stitch_demographics.html").read_text(encoding="utf-8")
    d = patch_demographics(d)
    d = d.replace("</body>", '<script src="assets/js/plfs-dashboard.js" defer></script>\n</body>', 1)
    (ROOT / "demographics.html").write_text(d, encoding="utf-8")

    r = (ROOT / "stitch_rural_urban.html").read_text(encoding="utf-8")
    r = patch_rural_urban(r)
    r = r.replace(
        "</body>",
        CHART_UMD_SCRIPT + '<script src="assets/js/plfs-dashboard.js" defer></script>\n</body>',
        1,
    )
    (ROOT / "rural-urban.html").write_text(r, encoding="utf-8")

    m = (ROOT / "stitch_methodology.html").read_text(encoding="utf-8")
    m = patch_methodology(m)
    m = m.replace("</body>", '<script src="assets/js/plfs-dashboard.js" defer></script>\n</body>', 1)
    (ROOT / "methodology.html").write_text(m, encoding="utf-8")

    b = (ROOT / "stitch_board_report.html").read_text(encoding="utf-8")
    b = patch_board_report(b)
    b = b.replace("</body>", '<script src="assets/js/plfs-dashboard.js" defer></script>\n</body>', 1)
    (ROOT / "board-report.html").write_text(b, encoding="utf-8")

    print("Wrote index.html, demographics.html, rural-urban.html, methodology.html, board-report.html")


if __name__ == "__main__":
    main()
