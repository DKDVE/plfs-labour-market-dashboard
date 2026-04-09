/**
 * Binds docs/data/dashboard_data.json to Stitch-based pages (GitHub Pages).
 */
(function () {
  let ruChart = null;
  let ruChartIsDual = false;
  let overviewChart = null;

  const scriptSrc =
    document.currentScript?.src ||
    document.querySelector('script[src$="plfs-dashboard.js"]')?.getAttribute("src");
  const DATA_URL = scriptSrc
    ? new URL("../../data/dashboard_data.json", scriptSrc).href
    : new URL("data/dashboard_data.json", window.location.href).href;

  function fmtPct(x, d) {
    if (x == null || Number.isNaN(Number(x))) return "—";
    return `${Number(x).toFixed(d ?? 2)}%`;
  }

  function fmtNum(x) {
    if (x == null || Number.isNaN(Number(x))) return "—";
    return Number(x).toLocaleString("en-IN");
  }

  function roundYear(r) {
    return parseInt(String(r.round).match(/july(\d{4})/)?.[1] || "0", 10);
  }

  function sortTrend(rows) {
    return [...rows].sort((a, b) => roundYear(a) - roundYear(b));
  }

  function labelRound(r) {
    if (r == null || r === "") return "—";
    const m = String(r).match(/(\d{3})_july(\d{4})_june(\d{4})/);
    if (!m) return String(r);
    return `${m[2].slice(2)}-${m[3].slice(2)}`;
  }

  function initMobileNav() {
    const toggle = document.getElementById("plfs-nav-toggle");
    const sidebar = document.getElementById("plfs-sidebar");
    const backdrop = document.getElementById("plfs-nav-backdrop");
    if (!toggle || !sidebar) return;
    const close = () => {
      sidebar.classList.remove("plfs-sidebar-open");
      backdrop?.classList.remove("plfs-backdrop-visible");
      toggle.setAttribute("aria-expanded", "false");
    };
    const open = () => {
      sidebar.classList.add("plfs-sidebar-open");
      backdrop?.classList.add("plfs-backdrop-visible");
      toggle.setAttribute("aria-expanded", "true");
    };
    toggle.addEventListener("click", () => {
      if (sidebar.classList.contains("plfs-sidebar-open")) close();
      else open();
    });
    backdrop?.addEventListener("click", close);
    try {
      window.matchMedia("(min-width: 1024px)").addEventListener("change", close);
    } catch (_) {
      /* ignore */
    }
  }

  function drawSparklines(rows) {
    if (typeof Chart === "undefined" || !rows.length) return;
    const spec = [
      { id: "spark-ur", key: "unemployment_rate", color: "#ba1a1a" },
      { id: "spark-lfpr", key: "lfpr", color: "#0061a5" },
      { id: "spark-wpr", key: "wpr", color: "#319795" },
    ];
    spec.forEach(({ id, key, color }) => {
      const c = document.getElementById(id);
      if (!c) return;
      const values = rows.map((r) => r[key]).filter((v) => v != null && !Number.isNaN(Number(v)));
      if (!values.length) return;
      const stale = Chart.getChart ? Chart.getChart(c) : null;
      if (stale) stale.destroy();
      new Chart(c.getContext("2d"), {
        type: "line",
        data: {
          labels: values.map((_, i) => i),
          datasets: [
            {
              data: values,
              borderColor: color,
              borderWidth: 1.5,
              fill: false,
              tension: 0.25,
              pointRadius: 0,
            },
          ],
        },
        options: {
          responsive: false,
          maintainAspectRatio: false,
          animation: false,
          plugins: { legend: { display: false }, tooltip: { enabled: false } },
          scales: { x: { display: false }, y: { display: false } },
        },
      });
    });
  }

  async function load() {
    let data;
    try {
      const res = await fetch(DATA_URL, { cache: "no-store" });
      if (!res.ok) throw new Error(String(res.status));
      data = await res.json();
    } catch (e) {
      console.error(e);
      const banner = document.getElementById("plfs-data-error") || document.getElementById("error");
      if (banner) {
        banner.removeAttribute("hidden");
        banner.classList.remove("hidden");
        banner.textContent =
          "Could not load dashboard_data.json. If testing locally, serve docs/ over HTTP (or deploy to GitHub Pages).";
      }
      return;
    }

    const meta = data.metadata || {};
    document.querySelectorAll("[data-bind='meta-generated']").forEach((el) => {
      el.textContent = meta.generated_at || "—";
    });
    document.querySelectorAll("[data-bind='meta-round']").forEach((el) => {
      el.textContent = meta.latest_round || "—";
    });
    document.querySelectorAll("[data-bind='meta-rounds-count']").forEach((el) => {
      el.textContent = meta.total_rounds != null ? String(meta.total_rounds) : "—";
    });
    document.querySelectorAll("[data-bind='meta-source-parquet']").forEach((el) => {
      el.textContent = meta.source_parquet || meta.data_source || "—";
    });

    const chipRoot = document.getElementById("plfs-methodology-chips");
    if (chipRoot && Array.isArray(meta.methodology_chips) && meta.methodology_chips.length) {
      const label = chipRoot.firstElementChild;
      chipRoot.replaceChildren(label);
      meta.methodology_chips.forEach((text) => {
        const s = document.createElement("span");
        s.className =
          "bg-surface-container-high text-on-surface text-[10px] font-bold px-2.5 py-1 rounded-full whitespace-nowrap uppercase tracking-wider";
        s.textContent = text;
        chipRoot.appendChild(s);
      });
    }

    initMobileNav();

    const nat = data.national_indicators_latest_round || {};
    const ur = document.getElementById("kpi-ur");
    const lfpr = document.getElementById("kpi-lfpr");
    const wpr = document.getElementById("kpi-wpr");
    if (ur) ur.textContent = fmtPct(nat.unemployment_rate);
    if (lfpr) lfpr.textContent = fmtPct(nat.lfpr);
    if (wpr) wpr.textContent = fmtPct(nat.wpr);
    document.querySelectorAll("[data-bind='kpi-year']").forEach((el) => {
      el.textContent = labelRound(meta.latest_round || "");
    });

    const rows = sortTrend(data.multiyear_trend || []);
    const deltas = computeDeltas(rows);
    bindDelta("delta-ur", deltas.ur, "delta-ur-icon");
    bindDelta("delta-lfpr", deltas.lfpr, "delta-lfpr-icon");
    bindDelta("delta-wpr", deltas.wpr, "delta-wpr-icon");

    updateProgressBars(nat);

    const chartEl = document.getElementById("plfs-trend-chart");
    if (chartEl && typeof Chart !== "undefined") {
      const labels = rows.map((r) => labelRound(r.round));
      const national = {
        ur: rows.map((r) => r.unemployment_rate),
        lfpr: rows.map((r) => r.lfpr),
        wpr: rows.map((r) => r.wpr),
      };

      function indexedSeries(arr) {
        const base = arr.find((v) => v != null && !Number.isNaN(Number(v)) && Number(v) !== 0);
        if (base == null) return arr.map(() => null);
        const b = Number(base);
        return arr.map((v) =>
          v == null || Number.isNaN(Number(v)) ? null : (Number(v) / b) * 100
        );
      }

      function datasetsForScale(scale) {
        let urD = national.ur;
        let lfD = national.lfpr;
        let wpD = national.wpr;
        if (scale === "indexed") {
          urD = indexedSeries(national.ur);
          lfD = indexedSeries(national.lfpr);
          wpD = indexedSeries(national.wpr);
        }
        const suf = scale === "indexed" ? " (index)" : "";
        return [
          {
            label: `UR${suf}`,
            data: urD,
            borderColor: "#ba1a1a",
            backgroundColor: "rgba(186,26,26,0.08)",
            tension: 0.25,
            fill: true,
          },
          {
            label: `LFPR${suf}`,
            data: lfD,
            borderColor: "#0061a5",
            backgroundColor: "rgba(0,97,165,0.06)",
            tension: 0.25,
            fill: true,
          },
          {
            label: `WPR${suf}`,
            data: wpD,
            borderColor: "#319795",
            backgroundColor: "rgba(49,151,149,0.06)",
            tension: 0.25,
            fill: true,
          },
        ];
      }

      function yAxisForScale(scale) {
        if (scale === "indexed") {
          return { ticks: { callback: (v) => Number(v).toFixed(0) } };
        }
        return { min: 0, max: 100, ticks: { callback: (v) => `${v}%` } };
      }

      function tooltipCb(scale) {
        return (ctx) => {
          const y = ctx.parsed.y;
          if (y == null || Number.isNaN(y)) return `${ctx.dataset.label}: —`;
          if (scale === "indexed") return `${ctx.dataset.label}: ${y.toFixed(1)}`;
          return `${ctx.dataset.label}: ${y.toFixed(2)}%`;
        };
      }

      function rebuildOverviewChart(scale) {
        const ds = datasetsForScale(scale);
        const yAxis = yAxisForScale(scale);
        if (overviewChart) {
          overviewChart.data.datasets = ds;
          overviewChart.options.scales.y = yAxis;
          overviewChart.options.plugins.tooltip.callbacks.label = tooltipCb(scale);
          overviewChart.update();
          return;
        }
        const stale = Chart.getChart ? Chart.getChart(chartEl) : null;
        if (stale) stale.destroy();
        overviewChart = new Chart(chartEl, {
          type: "line",
          data: { labels, datasets: ds },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: "index", intersect: false },
            plugins: {
              legend: { position: "bottom", labels: { boxWidth: 12, font: { size: 10 } } },
              tooltip: { callbacks: { label: tooltipCb(scale) } },
            },
            scales: {
              y: yAxisForScale(scale),
              x: { ticks: { maxRotation: 45, minRotation: 45, font: { size: 9 } } },
            },
          },
        });
      }

      rebuildOverviewChart("absolute");

      const toolbar = document.getElementById("plfs-chart-scale-toolbar");
      if (toolbar) {
        toolbar.querySelectorAll(".plfs-scale-btn").forEach((btn) => {
          btn.addEventListener("click", () => {
            const sc = btn.getAttribute("data-scale") || "absolute";
            rebuildOverviewChart(sc);
            toolbar.querySelectorAll(".plfs-scale-btn").forEach((b) => {
              const on = b.getAttribute("data-scale") === sc;
              b.classList.toggle("bg-white", on);
              b.classList.toggle("shadow-sm", on);
              b.classList.toggle("text-primary", on);
              b.classList.toggle("text-slate-600", !on);
            });
          });
        });
      }
    }

    drawSparklines(rows);

    fillCoverageTable(rows, meta);
    updateInsights(rows, nat);
    bindTrendStatistics(data.trend_statistics);

    bindDemographics(data.demographics_latest_round);
    bindAgeGroups(data.age_groups_latest_round);
    bindBoardReport(nat, rows, deltas, meta, data.demographics_latest_round);
    bindRuralUrban(data);
  }

  function fyLabel(roundId) {
    const m = String(roundId).match(/july(\d{4})_june(\d{4})/);
    if (!m) return String(roundId);
    return `${m[1].slice(2)}-${m[2].slice(2)}`;
  }

  function bindBoardReport(nat, rows, deltas, meta, demo) {
    if (!document.getElementById("board-kpi-ur")) return;
    setText("board-kpi-ur", fmtPct(nat.unemployment_rate));
    setText("board-kpi-lfpr", fmtPct(nat.lfpr));
    setText("board-kpi-wpr", fmtPct(nat.wpr));
    const fmtPP = (d) => {
      if (d == null || Number.isNaN(d)) return "—";
      const s = d >= 0 ? "+" : "";
      return `${s}${d.toFixed(2)} pp`;
    };
    setText("board-delta-ur", fmtPP(deltas.ur));
    setText("board-delta-lfpr", fmtPP(deltas.lfpr));
    setText("board-delta-wpr", fmtPP(deltas.wpr));
    if (demo) {
      const g = demo.by_gender || {};
      const m = g.male || {};
      const f = g.female || {};
      setText("board-demo-m-ur", fmtPct(m.unemployment));
      setText("board-demo-f-ur", fmtPct(f.unemployment));
      const s = demo.by_sector || {};
      const ru = s.rural || {};
      const uu = s.urban || {};
      setText("board-demo-r-ur", fmtPct(ru.unemployment));
      setText("board-demo-u-ur", fmtPct(uu.unemployment));
      setText("board-demo-r-lfpr", fmtPct(ru.lfpr));
      setText("board-demo-u-lfpr", fmtPct(uu.lfpr));
    }
    const tb = document.getElementById("board-trend-tbody");
    if (!tb || !rows.length) return;
    const latest = meta.latest_round;
    tb.innerHTML = "";
    rows.forEach((r) => {
      const isLatest = latest && r.round === latest;
      const tr = document.createElement("tr");
      tr.className = isLatest
        ? "bg-primary/5 font-bold"
        : "hover:bg-surface-container-low transition-colors";
      const y = fyLabel(r.round);
      const tdCls = isLatest ? "text-primary" : "text-on-surface";
      const numCls = isLatest ? "text-primary" : "text-slate-600";
      tr.innerHTML = `
        <td class="px-6 py-3 font-medium ${tdCls}">${y}</td>
        <td class="px-6 py-3 text-right font-mono ${numCls}">${Number(r.unemployment_rate).toFixed(2)}</td>
        <td class="px-6 py-3 text-right font-mono ${numCls}">${Number(r.lfpr).toFixed(2)}</td>
        <td class="px-6 py-3 text-right font-mono ${numCls}">${Number(r.wpr).toFixed(2)}</td>`;
      tb.appendChild(tr);
    });
  }

  function computeDeltas(rows) {
    if (rows.length < 2) return { ur: null, lfpr: null, wpr: null };
    const latest = rows[rows.length - 1];
    const prev = rows[rows.length - 2];
    return {
      ur: latest.unemployment_rate - prev.unemployment_rate,
      lfpr: latest.lfpr - prev.lfpr,
      wpr: latest.wpr - prev.wpr,
    };
  }

  function bindDelta(id, delta, iconId) {
    const el = document.getElementById(id);
    if (!el || delta == null || Number.isNaN(delta)) return;
    const up = delta >= 0;
    el.textContent = `${up ? "+" : ""}${delta.toFixed(2)}`;
    const icon = iconId ? document.getElementById(iconId) : null;
    if (icon) icon.textContent = up ? "trending_up" : "trending_down";
  }

  function updateProgressBars(nat) {
    const ur = nat.unemployment_rate;
    const lf = nat.lfpr;
    const wp = nat.wpr;
    setBarWidth("bar-ur", ur);
    setBarWidth("bar-lfpr", lf);
    setBarWidth("bar-wpr", wp);
  }

  function setBarWidth(id, pct) {
    const el = document.getElementById(id);
    if (el) el.style.width = `${Math.min(100, Math.max(0, pct))}%`;
  }

  function fillCoverageTable(rows, meta) {
    const tb = document.querySelector("#plfs-coverage-table tbody");
    if (!tb) return;
    tb.innerHTML = "";
    const sorted = [...rows].sort((a, b) => roundYear(b) - roundYear(a));
    sorted.slice(0, 8).forEach((r) => {
      const hh = r.households ?? meta.total_households_latest_round;
      const pr = r.records;
      const avg = hh && pr ? (pr / hh).toFixed(2) : "—";
      const tr = document.createElement("tr");
      tr.className = "hover:bg-surface-container-highest transition-colors";
      tr.innerHTML = `
        <td class="whitespace-nowrap px-4 py-3 text-sm font-bold tabular-nums">${labelRound(r.round)}</td>
        <td class="whitespace-nowrap px-4 py-3 text-sm font-medium tabular-nums text-right">${fmtNum(hh)}</td>
        <td class="whitespace-nowrap px-4 py-3 text-sm font-medium tabular-nums text-right">${fmtNum(pr)}</td>
        <td class="whitespace-nowrap px-4 py-3 text-sm text-secondary font-bold tabular-nums text-right">${avg}</td>`;
      tb.appendChild(tr);
    });
  }

  function bindTrendStatistics(ts) {
    const card = document.getElementById("plfs-trend-stats-card");
    if (!card) return;
    if (!ts || typeof ts !== "object") {
      card.hidden = true;
      return;
    }
    const caveatEl = document.getElementById("plfs-trend-stats-caveat");
    if (ts.error) {
      if (caveatEl) caveatEl.textContent = String(ts.error);
      card.hidden = false;
      return;
    }
    if (!ts.metrics || !ts.pearson_across_rounds) {
      card.hidden = true;
      return;
    }
    if (caveatEl) caveatEl.textContent = ts.caveat || "";

    const pairLabels = {
      unemployment_rate__lfpr: "UR · LFPR",
      unemployment_rate__wpr: "UR · WPR",
      lfpr__wpr: "LFPR · WPR",
    };

    const slopeTb = document.querySelector("#plfs-trend-stats-slopes tbody");
    if (slopeTb) {
      slopeTb.innerHTML = "";
      ["unemployment_rate", "lfpr", "wpr"].forEach((k) => {
        const m = ts.metrics[k];
        if (!m) return;
        const tr = document.createElement("tr");
        tr.className = "hover:bg-surface-container-highest transition-colors";
        const slope = Number(m.slope_pp_per_year);
        const sStr = Number.isNaN(slope) ? "—" : `${slope >= 0 ? "+" : ""}${slope.toFixed(2)}`;
        const r2 = Number(m.r_squared);
        const rStr = Number.isNaN(r2) ? "—" : r2.toFixed(3);
        const td1 = document.createElement("td");
        td1.className = "px-4 py-2 font-medium";
        td1.textContent = m.label || k;
        const td2 = document.createElement("td");
        td2.className = "px-4 py-2 text-right font-mono tabular-nums text-sm";
        td2.textContent = `${sStr} pp/yr`;
        const td3 = document.createElement("td");
        td3.className = "px-4 py-2 text-right font-mono tabular-nums text-sm";
        td3.textContent = rStr;
        tr.append(td1, td2, td3);
        slopeTb.appendChild(tr);
      });
    }

    const corrTb = document.querySelector("#plfs-trend-stats-corr tbody");
    if (corrTb) {
      corrTb.innerHTML = "";
      Object.keys(ts.pearson_across_rounds).forEach((k) => {
        const v = ts.pearson_across_rounds[k];
        const tr = document.createElement("tr");
        tr.className = "hover:bg-surface-container-highest transition-colors";
        const td1 = document.createElement("td");
        td1.className = "px-4 py-2 text-sm";
        td1.textContent = pairLabels[k] || k.replace(/__/g, " · ");
        const td2 = document.createElement("td");
        td2.className = "px-4 py-2 text-right font-mono tabular-nums text-sm font-semibold";
        td2.textContent = v == null ? "—" : Number(v).toFixed(4);
        tr.append(td1, td2);
        corrTb.appendChild(tr);
      });
    }

    card.hidden = false;
  }

  function updateInsights(rows, nat) {
    if (!rows.length) return;
    const urMin = Math.min(...rows.map((r) => r.unemployment_rate));
    const urMax = Math.max(...rows.map((r) => r.unemployment_rate));
    const el1 = document.getElementById("insight-ur");
    if (el1) {
      el1.innerHTML = `UR ranges from <strong class="text-white">${fmtPct(urMin)}</strong> to <strong class="text-white">${fmtPct(
        urMax
      )}</strong> across rounds in this extract. Latest headline UR is <strong class="text-white">${fmtPct(
        nat.unemployment_rate
      )}</strong>.`;
    }
    const el2 = document.getElementById("insight-lfpr");
    if (el2) {
      el2.innerHTML = `LFPR in the latest round is <strong class="text-white">${fmtPct(
        nat.lfpr
      )}</strong>, compared across ${rows.length} pooled annual rounds.`;
    }
    const el3 = document.getElementById("insight-wpr");
    if (el3) {
      el3.innerHTML = `WPR in the latest round is <strong class="text-white">${fmtPct(
        nat.wpr
      )}</strong>, moving with LFPR as expected under UPS definitions.`;
    }
  }

  function bindDemographics(demo) {
    if (!demo) return;
    const g = demo.by_gender || {};
    const m = g.male || {};
    const f = g.female || {};
    setText("demo-male-ur", fmtPct(m.unemployment));
    setText("demo-male-lfpr", fmtPct(m.lfpr));
    setText("demo-female-ur", fmtPct(f.unemployment));
    setText("demo-female-lfpr", fmtPct(f.lfpr));

    const s = demo.by_sector || {};
    const r = s.rural || {};
    const u = s.urban || {};
    setText("demo-rural-ur", fmtPct(r.unemployment));
    setText("demo-rural-lfpr", fmtPct(r.lfpr));
    setText("demo-rural-wpr", fmtPct(r.wpr));
    setText("demo-urban-ur", fmtPct(u.unemployment));
    setText("demo-urban-lfpr", fmtPct(u.lfpr));
    setText("demo-urban-wpr", fmtPct(u.wpr));
  }

  function bindAgeGroups(ages) {
    if (!ages || !ages.length) return;
    const tb = document.querySelector("#plfs-age-table tbody");
    if (!tb) return;
    tb.innerHTML = "";
    ages.forEach((row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td class="px-4 py-2 text-sm">${row.group}</td><td class="px-4 py-2 text-sm font-semibold">${fmtPct(
        row.unemployment_rate
      )}</td>`;
      tb.appendChild(tr);
    });
  }

  function setText(id, t) {
    const el = document.getElementById(id);
    if (el) el.textContent = t;
  }

  function bindRuralUrban(data) {
    const canvas = document.getElementById("ru-trend-chart");
    const meta = data.metadata || {};
    const nat = data.national_indicators_latest_round || {};
    const allRows = sortTrend(data.multiyear_trend || []);
    const demo = data.demographics_latest_round;
    const ruPage = data.rural_urban_page || {};
    const bySectorTrend = data.multiyear_trend_by_sector;
    const factors = meta.sector_scale_factors;

    const noteElPre = document.getElementById("ru-sector-composition-note");
    if (noteElPre && ruPage.sector_composition_note != null) {
      noteElPre.textContent = ruPage.sector_composition_note;
    }

    const sectorRows = ruPage.sector_rows;
    if (Array.isArray(sectorRows)) {
      sectorRows.forEach((row, i) => {
        if (i > 2) return;
        setText(`ru-sector-title-${i}`, row.title || "—");
        setText(`ru-sector-cap-${i}`, row.context != null ? String(row.context) : "—");
        const mp = Number(row.male_pct);
        const fp = Number(row.female_pct);
        if (!Number.isNaN(mp) && !Number.isNaN(fp)) {
          setBarWidth(`ru-sector-bar-m-${i}`, mp);
          setBarWidth(`ru-sector-bar-f-${i}`, fp);
        }
      });
    }

    const et = ruPage.employment_type_pct;
    if (et && typeof et === "object") {
      const self = Number(et.self_employed);
      const wage = Number(et.regular_wage);
      const cas = Number(et.casual_labor);
      if (!Number.isNaN(self)) {
        setBarWidth("ru-emp-bar-self", self);
        setText("ru-emp-pct-self", `${self.toFixed(1)}%`);
      }
      if (!Number.isNaN(wage)) {
        setBarWidth("ru-emp-bar-wage", wage);
        setText("ru-emp-pct-wage", `${wage.toFixed(1)}%`);
      }
      if (!Number.isNaN(cas)) {
        setBarWidth("ru-emp-bar-casual", cas);
        setText("ru-emp-pct-casual", `${cas.toFixed(1)}%`);
      }
    }

    if (demo?.by_sector) {
      const r = demo.by_sector.rural || {};
      const u = demo.by_sector.urban || {};
      setText("ru-rural-ur", fmtPct(r.unemployment));
      setText("ru-urban-ur", fmtPct(u.unemployment));
      setText("ru-rural-lfpr", fmtPct(r.lfpr));
      setText("ru-urban-lfpr", fmtPct(u.lfpr));
      setText("ru-rural-wpr", fmtPct(r.wpr));
      setText("ru-urban-wpr", fmtPct(u.wpr));
      const urGap = Number(u.unemployment) - Number(r.unemployment);
      setText("ru-gap-ur", `${urGap >= 0 ? "+" : ""}${urGap.toFixed(2)} pp`);
      const lfGap = Number(u.lfpr) - Number(r.lfpr);
      setText("ru-gap-lfpr", `${lfGap >= 0 ? "+" : ""}${lfGap.toFixed(2)} pp`);
    }

    if (ruPage.executive_lfpr_gap_pp != null && String(ruPage.executive_lfpr_gap_pp).trim() !== "") {
      const raw = String(ruPage.executive_lfpr_gap_pp).replace(/pp/gi, "").trim();
      const g = Number(raw);
      if (!Number.isNaN(g)) {
        setText("ru-gap-lfpr", `${g >= 0 ? "+" : ""}${g.toFixed(2)} pp`);
      } else {
        setText("ru-gap-lfpr", String(ruPage.executive_lfpr_gap_pp));
      }
    }

    if (nat.unemployment_rate != null) {
      setText("ru-runtime-ur", fmtPct(nat.unemployment_rate));
    }

    if (!canvas || typeof Chart === "undefined") return;

    function fieldKey(m) {
      if (m === "ur") return "unemployment_rate";
      if (m === "lfpr") return "lfpr";
      return "wpr";
    }

    function colorForMetric(m) {
      if (m === "ur") return "#ba1a1a";
      if (m === "lfpr") return "#0061a5";
      return "#319795";
    }

    function sliceRows(yearMode) {
      let rows = [...allRows].sort((a, b) => roundYear(a) - roundYear(b));
      if (yearMode === "3") rows = rows.slice(-3);
      else if (yearMode === "5") rows = rows.slice(-5);
      return rows;
    }

    function rowMap(list) {
      const m = new Map();
      (list || []).forEach((r) => m.set(r.round, r));
      return m;
    }

    function dualSeriesFromPipeline(rows, key) {
      const rural = bySectorTrend?.rural;
      const urban = bySectorTrend?.urban;
      if (!rural?.length || !urban?.length) return null;
      const mr = rowMap(rural);
      const mu = rowMap(urban);
      const ruralData = [];
      const urbanData = [];
      for (const nr of rows) {
        const rr = mr.get(nr.round);
        const uu = mu.get(nr.round);
        const rv = rr?.[key];
        const uv = uu?.[key];
        ruralData.push(rv == null || Number.isNaN(Number(rv)) ? null : Number(rv));
        urbanData.push(uv == null || Number.isNaN(Number(uv)) ? null : Number(uv));
      }
      if (ruralData.every((v) => v == null) && urbanData.every((v) => v == null)) return null;
      return { ruralData, urbanData, fromPipeline: true };
    }

    function dualSeriesScaled(rows, key) {
      if (!factors?.rural || !factors?.urban) return null;
      const fr = factors.rural[key];
      const fu = factors.urban[key];
      if (fr == null || fu == null) return null;
      const ruralData = rows.map((r) => {
        const v = r[key];
        return v == null || Number.isNaN(Number(v)) ? null : Number(v) * Number(fr);
      });
      const urbanData = rows.map((r) => {
        const v = r[key];
        return v == null || Number.isNaN(Number(v)) ? null : Number(v) * Number(fu);
      });
      return { ruralData, urbanData, fromPipeline: false };
    }

    let metric = "ur";
    const params = new URLSearchParams(window.location.search);
    const pm = params.get("metric");
    if (pm === "ur" || pm === "lfpr" || pm === "wpr") metric = pm;
    const py = params.get("years");
    const yrSel = document.getElementById("year-range");
    if (yrSel && py && (py === "all" || py === "3" || py === "5")) yrSel.value = py;

    function syncRuralUrl() {
      const y = document.getElementById("year-range")?.value || "all";
      try {
        const u = new URL(window.location.href);
        u.searchParams.set("metric", metric);
        u.searchParams.set("years", y);
        history.replaceState(null, "", `${u.pathname}${u.search}`);
      } catch (_) {
        /* ignore */
      }
    }

    function styleMetricButtons() {
      document.querySelectorAll(".ru-metric-btn").forEach((b) => {
        const m = b.getAttribute("data-metric");
        const on = m === metric;
        b.classList.toggle("bg-white", on);
        b.classList.toggle("shadow-sm", on);
        b.classList.toggle("text-primary", on);
        b.classList.toggle("text-slate-500", !on);
      });
    }

    function styleSexButtons(activeSex) {
      document.querySelectorAll(".ru-sex-btn").forEach((b) => {
        const s = b.getAttribute("data-sex");
        const on = s === activeSex;
        b.classList.toggle("border-2", on);
        b.classList.toggle("border-primary", on);
        b.classList.toggle("text-primary", on);
        b.classList.toggle("bg-primary-fixed", on);
        b.classList.toggle("border", !on);
        b.classList.toggle("border-slate-300", !on);
      });
    }

    function updateScopeNote(sexSel) {
      const note = document.getElementById("ru-filter-scope-note");
      if (!note) return;
      const st = document.getElementById("state-filter")?.value ?? "IN";
      const ag = document.getElementById("age-band")?.value ?? "15p";
      const nonDefault = sexSel !== "all" || st !== "IN" || ag !== "15p";
      note.hidden = !nonDefault;
    }

    function bgForMetricTone(color) {
      if (color === "#ba1a1a") return "rgba(186,26,26,0.08)";
      if (color === "#0061a5") return "rgba(0,97,165,0.06)";
      return "rgba(49,151,149,0.06)";
    }

    function apply() {
      const yearMode = document.getElementById("year-range")?.value || "all";
      const rows = sliceRows(yearMode);
      const key = fieldKey(metric);
      const color = colorForMetric(metric);
      const labels = rows.map((r) => labelRound(r.round));

      const fromPipe = dualSeriesFromPipeline(rows, key);
      const scaled = !fromPipe ? dualSeriesScaled(rows, key) : null;
      const dual = fromPipe || scaled;
      const isDual = dual != null;

      const noteEl = document.getElementById("ru-trend-note");
      if (noteEl) {
        if (isDual && fromPipe) {
          noteEl.textContent =
            "Rural and urban series from multiyear_trend_by_sector in dashboard_data.json (per round).";
        } else if (isDual) {
          noteEl.textContent = meta.sector_scale_note || "";
        } else {
          noteEl.textContent =
            "National pooled series only—rural/urban multi-year paths appear when sector split is published (see JSON schema).";
        }
      }

      if (ruChart && ruChartIsDual !== isDual) {
        ruChart.destroy();
        ruChart = null;
      }
      ruChartIsDual = isDual;

      const chartOptions = {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: {
            display: isDual,
            position: "bottom",
            labels: { boxWidth: 12, font: { size: 10 } },
          },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const y = ctx.parsed.y;
                const lab = ctx.dataset.label || "";
                if (y == null || Number.isNaN(y)) return `${lab}: —`;
                return `${lab}: ${Number(y).toFixed(2)}%`;
              },
            },
          },
        },
        scales: {
          y: {
            min: 0,
            max: 100,
            ticks: { callback: (v) => `${v}%` },
          },
          x: { ticks: { maxRotation: 45, minRotation: 0, font: { size: 9 } } },
        },
      };

      if (isDual) {
        const ruralColor = "#2d6a4f";
        const urbanColor = color;
        const rLab = fromPipe ? "Rural" : "Rural (est.)";
        const uLab = fromPipe ? "Urban" : "Urban (est.)";
        const datasets = [
          {
            label: rLab,
            data: dual.ruralData,
            borderColor: ruralColor,
            backgroundColor: "rgba(45,106,79,0.08)",
            tension: 0.25,
            fill: true,
          },
          {
            label: uLab,
            data: dual.urbanData,
            borderColor: urbanColor,
            backgroundColor: bgForMetricTone(urbanColor),
            tension: 0.25,
            fill: true,
          },
        ];
        const stale = Chart.getChart ? Chart.getChart(canvas) : null;
        if (stale && !ruChart) stale.destroy();
        if (ruChart) {
          ruChart.data.labels = labels;
          ruChart.data.datasets = datasets;
          ruChart.options.plugins.legend.display = true;
          ruChart.update();
        } else {
          if (stale) stale.destroy();
          ruChart = new Chart(canvas, {
            type: "line",
            data: { labels, datasets },
            options: chartOptions,
          });
        }
      } else {
        const values = rows.map((r) => {
          const v = r[key];
          return v == null || Number.isNaN(Number(v)) ? 0 : Number(v);
        });
        const ds = {
          label: metric.toUpperCase(),
          data: values,
          borderColor: color,
          backgroundColor: bgForMetricTone(color),
          tension: 0.25,
          fill: true,
        };
        const stale = Chart.getChart ? Chart.getChart(canvas) : null;
        if (stale && !ruChart) stale.destroy();
        if (ruChart) {
          ruChart.data.labels = labels;
          ruChart.data.datasets = [ds];
          ruChart.options.plugins.legend.display = false;
          ruChart.update();
        } else {
          if (stale) stale.destroy();
          ruChart = new Chart(canvas, {
            type: "line",
            data: { labels, datasets: [ds] },
            options: chartOptions,
          });
        }
      }

      const legend = document.getElementById("ru-year-cells");
      if (legend) {
        legend.className =
          "grid gap-4 pt-4 border-t border-slate-100 " +
          (rows.length <= 3
            ? "grid-cols-3"
            : rows.length <= 5
              ? "grid-cols-5"
              : "grid-cols-2 sm:grid-cols-4 lg:grid-cols-7");
        if (isDual) {
          legend.innerHTML = rows
            .map((r, i) => {
              const y = labelRound(r.round);
              const rv = dual.ruralData[i];
              const uv = dual.urbanData[i];
              const rs = rv == null ? "—" : `${Number(rv).toFixed(2)}%`;
              const us = uv == null ? "—" : `${Number(uv).toFixed(2)}%`;
              return `<div class="text-center"><p class="text-[10px] text-slate-400 font-bold uppercase">${y}</p><p class="text-[10px] font-bold text-[#2d6a4f]">${rs}</p><p class="text-[10px] font-bold text-primary">${us}</p></div>`;
            })
            .join("");
        } else {
          legend.innerHTML = rows
            .map((r) => {
              const y = labelRound(r.round);
              const v = r[key];
              return `<div class="text-center"><p class="text-[10px] text-slate-400 font-bold uppercase">${y}</p><p class="text-sm font-black text-primary">${Number(v).toFixed(2)}%</p></div>`;
            })
            .join("");
        }
      }

      syncRuralUrl();
    }

    const metricGroup = document.getElementById("ru-metric-toggles");
    if (metricGroup) {
      metricGroup.addEventListener("click", (e) => {
        const btn = e.target.closest(".ru-metric-btn");
        if (!btn) return;
        e.preventDefault();
        e.stopPropagation();
        metric = btn.getAttribute("data-metric") || "ur";
        styleMetricButtons();
        apply();
      });
    }

    let sexSel = "all";
    document.querySelectorAll(".ru-sex-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        sexSel = btn.getAttribute("data-sex") || "all";
        styleSexButtons(sexSel);
        updateScopeNote(sexSel);
      });
    });

    ["state-filter", "age-band"].forEach((id) => {
      const el = document.getElementById(id);
      if (el)
        el.addEventListener("change", () => {
          updateScopeNote(sexSel);
        });
    });

    const yr = document.getElementById("year-range");
    if (yr) yr.addEventListener("change", () => apply());

    const form = document.getElementById("ru-filter-form");
    if (form) {
      form.addEventListener("submit", (e) => {
        e.preventDefault();
        apply();
      });
    }

    styleMetricButtons();
    styleSexButtons("all");
    updateScopeNote("all");
    apply();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", load);
  } else {
    load();
  }
})();
