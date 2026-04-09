/**
 * Loads dashboard_data.json (same schema as notebook export) and renders KPIs + tables.
 */
async function loadDashboard() {
  const errEl = document.getElementById("error");
  errEl.textContent = "";
  errEl.hidden = true;

  let data;
  try {
    const res = await fetch("data/dashboard_data.json", { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    data = await res.json();
  } catch (e) {
    errEl.textContent =
      "Could not load data/dashboard_data.json. If you opened this file locally, use a local server or deploy to GitHub Pages.";
    errEl.hidden = false;
    console.error(e);
    return;
  }

  const meta = data.metadata || {};
  document.getElementById("meta-line").textContent =
    `Latest survey round: ${meta.latest_round || "—"} · Generated: ${meta.generated_at || "—"} · Rounds: ${meta.total_rounds ?? "—"}`;

  const nat = data.national_indicators_latest_round || {};
  document.getElementById("kpi-ur").textContent = fmtPct(nat.unemployment_rate);
  document.getElementById("kpi-lfpr").textContent = fmtPct(nat.lfpr);
  document.getElementById("kpi-wpr").textContent = fmtPct(nat.wpr);

  const tbody = document.querySelector("#trend-table tbody");
  tbody.innerHTML = "";
  (data.multiyear_trend || []).forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(String(row.round))}</td>
      <td>${fmtPct(row.unemployment_rate)}</td>
      <td>${fmtPct(row.lfpr)}</td>
      <td>${fmtPct(row.wpr)}</td>
    `;
    tbody.appendChild(tr);
  });

  const demo = data.demographics_latest_round || {};
  const g = demo.by_gender || {};
  document.getElementById("demo-gender").innerHTML = `
    <p><strong>Male</strong> — UR ${fmtPct(g.male?.unemployment)} · LFPR ${fmtPct(g.male?.lfpr)}</p>
    <p><strong>Female</strong> — UR ${fmtPct(g.female?.unemployment)} · LFPR ${fmtPct(g.female?.lfpr)}</p>
  `;
  const s = demo.by_sector || {};
  document.getElementById("demo-sector").innerHTML = `
    <p><strong>Rural</strong> — UR ${fmtPct(s.rural?.unemployment)} · LFPR ${fmtPct(s.rural?.lfpr)} · WPR ${fmtPct(s.rural?.wpr)}</p>
    <p><strong>Urban</strong> — UR ${fmtPct(s.urban?.unemployment)} · LFPR ${fmtPct(s.urban?.lfpr)} · WPR ${fmtPct(s.urban?.wpr)}</p>
  `;

  const ageBody = document.querySelector("#age-table tbody");
  ageBody.innerHTML = "";
  (data.age_groups_latest_round || []).forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${escapeHtml(String(row.group))}</td><td>${fmtPct(row.unemployment_rate)}</td>`;
    ageBody.appendChild(tr);
  });
}

function fmtPct(v) {
  if (v === undefined || v === null || Number.isNaN(Number(v))) return "—";
  return `${Number(v).toFixed(2)}%`;
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

document.addEventListener("DOMContentLoaded", loadDashboard);
