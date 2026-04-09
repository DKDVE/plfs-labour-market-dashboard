/**
 * Binds docs/data/dashboard_data.json to Stitch-based pages (GitHub Pages).
 */
(function () {
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
        <td class="px-6 py-4 text-sm font-bold">${labelRound(r.round)}</td>
        <td class="px-6 py-4 text-sm font-medium">${fmtNum(hh)}</td>
        <td class="px-6 py-4 text-sm font-medium">${fmtNum(pr)}</td>
        <td class="px-6 py-4 text-sm text-secondary font-bold">${avg}</td>`;
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

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", load);
  } else {
    load();
  }
})();
