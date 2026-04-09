/**
 * Binds docs/data/dashboard_data.json to Stitch-based pages (GitHub Pages).
 */
(function () {
  let ruChart = null;

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
      new Chart(chartEl, {
        type: "line",
        data: {
          labels,
          datasets: [
            {
              label: "UR",
              data: rows.map((r) => r.unemployment_rate),
              borderColor: "#ba1a1a",
              backgroundColor: "rgba(186,26,26,0.08)",
              tension: 0.25,
              fill: true,
            },
            {
              label: "LFPR",
              data: rows.map((r) => r.lfpr),
              borderColor: "#0061a5",
              backgroundColor: "rgba(0,97,165,0.06)",
              tension: 0.25,
              fill: true,
            },
            {
              label: "WPR",
              data: rows.map((r) => r.wpr),
              borderColor: "#319795",
              backgroundColor: "rgba(49,151,149,0.06)",
              tension: 0.25,
              fill: true,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: "index", intersect: false },
          plugins: {
            legend: { position: "bottom", labels: { boxWidth: 12, font: { size: 10 } } },
            tooltip: {
              callbacks: {
                label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(2)}%`,
              },
            },
          },
          scales: {
            y: {
              min: 0,
              max: 100,
              ticks: { callback: (v) => `${v}%` },
            },
            x: { ticks: { maxRotation: 45, minRotation: 45, font: { size: 9 } } },
          },
        },
      });
    }

    fillCoverageTable(rows, meta);
    updateInsights(rows, nat);

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
        <td class="px-2 sm:px-4 py-3 text-xs sm:text-sm font-bold tabular-nums align-top">${labelRound(r.round)}</td>
        <td class="px-2 sm:px-4 py-3 text-xs sm:text-sm font-medium tabular-nums break-words">${fmtNum(hh)}</td>
        <td class="px-2 sm:px-4 py-3 text-xs sm:text-sm font-medium tabular-nums break-words">${fmtNum(pr)}</td>
        <td class="px-2 sm:px-4 py-3 text-xs sm:text-sm text-secondary font-bold tabular-nums">${avg}</td>`;
      tb.appendChild(tr);
    });
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
    const nat = data.national_indicators_latest_round || {};
    const allRows = sortTrend(data.multiyear_trend || []);
    const demo = data.demographics_latest_round;

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
    if (nat.unemployment_rate != null) {
      const el = document.getElementById("ru-runtime-ur");
      if (el) el.textContent = fmtPct(nat.unemployment_rate);
    }

    if (!canvas || typeof Chart === "undefined") return;

    function fieldForMetric(m) {
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

    let metric = "ur";

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

    const chartOptions = {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.dataset.label}: ${Number(ctx.parsed.y).toFixed(2)}%`,
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

    function bgForMetric(m) {
      if (m === "ur") return "rgba(186,26,26,0.08)";
      if (m === "lfpr") return "rgba(0,97,165,0.06)";
      return "rgba(49,151,149,0.06)";
    }

    function apply() {
      const yearMode = document.getElementById("year-range")?.value || "all";
      const rows = sliceRows(yearMode);
      const key = fieldForMetric(metric);
      const color = colorForMetric(metric);
      const labels = rows.map((r) => labelRound(r.round));
      const values = rows.map((r) => {
        const v = r[key];
        return v == null || Number.isNaN(Number(v)) ? 0 : Number(v);
      });

      const ds = {
        label: metric.toUpperCase(),
        data: values,
        borderColor: color,
        backgroundColor: bgForMetric(metric),
        tension: 0.25,
        fill: true,
      };

      if (ruChart) {
        ruChart.data.labels = labels;
        const d0 = ruChart.data.datasets[0];
        d0.label = ds.label;
        d0.data = ds.data;
        d0.borderColor = ds.borderColor;
        d0.backgroundColor = ds.backgroundColor;
        ruChart.update();
      } else {
        const stale = typeof Chart !== "undefined" && Chart.getChart ? Chart.getChart(canvas) : null;
        if (stale) stale.destroy();
        ruChart = new Chart(canvas, {
          type: "line",
          data: { labels, datasets: [ds] },
          options: chartOptions,
        });
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
        legend.innerHTML = rows
          .map((r) => {
            const y = labelRound(r.round);
            const v = r[key];
            return `<div class="text-center"><p class="text-[10px] text-slate-400 font-bold uppercase">${y}</p><p class="text-sm font-black text-primary">${Number(v).toFixed(2)}%</p></div>`;
          })
          .join("");
      }
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
