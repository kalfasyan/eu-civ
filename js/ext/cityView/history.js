// "Since 2000" cards for the City View, from data/history.json (the time dial's yearly series).
// A metro's value in a year is built from its member NUTS 3 regions: GDP vs EU average is their population-weighted
// mean, jobs and population are sums. A year counts only when every member region has a figure, so a redrawn region
// never makes the line jump.
import { esc } from "../../format.js";

function metroSeries(H, members, key, how) {
  const NY = H.years.length;
  const idx = members.map((g) => H.regions.indexOf(g)).filter((i) => i >= 0);
  if (!idx.length || idx.length < members.length) return [];
  const [a, b] = H.range[key] || [H.years[0], H.years.at(-1)];
  const at = (k, i, y) => H.series[k][i * NY + (y - H.years[0])];
  const out = [];
  for (let y = a; y <= b; y++) {
    let num = 0, den = 0, ok = true;
    for (const i of idx) {
      const v = at(key, i, y);
      if (v == null) { ok = false; break; }
      if (how === "sum") num += v;
      else {
        const p = at("pop", i, y) ?? at("pop", i, Math.min(b, H.range.pop[1]));
        if (p == null) { ok = false; break; }
        num += v * p; den += p;
      }
    }
    if (ok) out.push({ year: y, value: how === "sum" ? num : num / den });
  }
  return out;
}

let uid = 0;
// Year-scaled line: x follows the calendar, so a gap in the data shows as a dashed stretch instead of being squeezed out.
function yearSpark(series, { fmt, title, color = "#ecd08e" }) {
  const W = 400, H = 96, padL = 8, padR = 8, padT = 22, padB = 20;
  const y0 = series[0].year, y1 = series.at(-1).year;
  const vals = series.map((p) => p.value);
  let lo = Math.min(...vals), hi = Math.max(...vals);
  const sp = hi - lo || hi * 0.01 || 1;
  lo -= sp * 0.12; hi += sp * 0.12;
  const X = (y) => padL + ((y - y0) / Math.max(1, y1 - y0)) * (W - padL - padR);
  const Y = (v) => padT + (1 - (v - lo) / (hi - lo)) * (H - padT - padB);
  const up = series.at(-1).value >= series[0].value;
  const col = up ? color : "#f08a6a";
  let solid = "", dashed = "";
  series.forEach((p, k) => {
    const pt = `${X(p.year).toFixed(1)} ${Y(p.value).toFixed(1)}`;
    if (k === 0) { solid += `M${pt}`; return; }
    const prev = series[k - 1];
    if (p.year - prev.year > 1) { dashed += `M${X(prev.year).toFixed(1)} ${Y(prev.value).toFixed(1)}L${pt}`; solid += `M${pt}`; }
    else solid += `L${pt}`;
  });
  const id = `cvh${++uid}`;
  const area = series.length ? `M${X(y0)} ${H - padB}` + series.map((p) => `L${X(p.year).toFixed(1)} ${Y(p.value).toFixed(1)}`).join("") + `L${X(y1)} ${H - padB}Z` : "";
  const ticks = [];
  for (let y = y0; y <= y1; y++) {
    if (y !== y0 && y !== y1 && (y % 5 || y - y0 < 3 || y1 - y < 3)) continue;
    ticks.push(`<text x="${X(y).toFixed(1)}" y="${H - 5}" text-anchor="${y === y0 ? "start" : y === y1 ? "end" : "middle"}" class="cv-ax">${y}</text>`);
  }
  const grid = [0.25, 0.5, 0.75].map((f) => `<line x1="${padL}" x2="${W - padR}" y1="${(padT + f * (H - padT - padB)).toFixed(1)}" y2="${(padT + f * (H - padT - padB)).toFixed(1)}" class="cv-grid"/>`).join("");
  const dot = (p, end) => `<circle cx="${X(p.year).toFixed(1)}" cy="${Y(p.value).toFixed(1)}" r="${end ? 4 : 2.8}" fill="${end ? col : "#16212d"}" stroke="${col}" stroke-width="1.6"><title>${p.year}: ${esc(fmt(p.value))}</title></circle>`;
  const hit = series.map((p) => `<circle cx="${X(p.year).toFixed(1)}" cy="${Y(p.value).toFixed(1)}" r="6" fill="transparent"><title>${p.year}: ${esc(fmt(p.value))}</title></circle>`).join("");
  const lbl = (p, anchor) => `<text x="${X(p.year).toFixed(1)}" y="${(Y(p.value) - 8).toFixed(1)}" text-anchor="${anchor}" class="cv-lab">${esc(fmt(p.value))}</text>`;
  return `<svg class="cv-spark" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(title)}">
    <defs><linearGradient id="${id}" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="${col}" stop-opacity=".35"/><stop offset="1" stop-color="${col}" stop-opacity="0"/></linearGradient></defs>
    ${grid}<path d="${area}" fill="url(#${id})"/>
    <path d="${solid}" fill="none" stroke="${col}" stroke-width="2" stroke-linejoin="round"/>
    ${dashed ? `<path d="${dashed}" fill="none" stroke="${col}" stroke-width="1.5" stroke-dasharray="3 4" opacity=".7"><title>No data for these years</title></path>` : ""}
    ${hit}${dot(series[0], false)}${dot(series.at(-1), true)}${lbl(series[0], "start")}${lbl(series.at(-1), "end")}${ticks.join("")}
  </svg>`;
}

const signedPts = (d) => `${d >= 0 ? "+" : "−"}${Math.abs(Math.round(d))} pts`;
const signedPct = (d) => `${d >= 0 ? "+" : "−"}${Math.abs(d * 100).toFixed(0)}%`;
const short = (v) => (v >= 1e6 ? (v / 1e6).toFixed(2) + "M" : Math.round(v / 1000) + "k");

function card(title, series, change, fmt, note, aria) {
  if (series.length < 2) return "";
  const ch = change(series[0].value, series.at(-1).value);
  return `<div class="cv-card">
    <div class="cv-card-h"><span>${esc(title)} ${series[0].year}–${series.at(-1).year}</span><span class="${ch.good ? "good" : "bad"}">${ch.text}</span></div>
    ${yearSpark(series, { fmt, title: aria })}
    <p class="cv-note">${note}</p>
  </div>`;
}

export function historyHtml(m, H) {
  if (!H) return `<p class="muted cv-note">Yearly series not available.</p>`;
  const members = m.city.counties || [];
  const gdp = metroSeries(H, members, "gdp_idx", "mean");
  const jobs = metroSeries(H, members, "jobs", "sum");
  const html =
    card("GDP per person vs EU average", gdp, (a, b) => ({ text: signedPts(b - a), good: b >= a }), (v) => String(Math.round(v)),
      "Purchasing power standards, EU27 = 100 in each year (Eurostat nama_10r_3gdp). Open the <b>GDP vs EU average</b> lens and press play to see every region move.",
      `GDP per person of ${m.city.name} relative to the EU average, by year`) +
    card("Jobs", jobs, (a, b) => ({ text: signedPct(b / a - 1), good: b >= a }), short,
      "Employed persons by place of work (Eurostat nama_10r_3empers).", `Jobs in ${m.city.name} by year`);
  return html || `<p class="muted cv-note">Eurostat has no complete yearly series for this metro's regions.</p>`;
}

export { yearSpark };

// Population 2000 onwards, to replace the shorter series in cities.json when it reaches further back.
export function populationSeries(m, H) {
  return H ? metroSeries(H, m.city.counties || [], "pop", "sum") : [];
}
