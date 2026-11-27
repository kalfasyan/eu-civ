// Settler advisor: "Where should I live?". The viewer describes a trade, optional pay and home, places to stay near,
// languages and what matters; every NUTS 3 region is scored and the map lights up. All of it runs in the browser
// from data/advisor.json (pipeline/build_advisor.py) plus counties.json and history.json.
//
// Score: hard filters first (travel time to every anchor, a language the viewer speaks or English at work), then each
// part is ranked 0–100 among the regions left and weighted. Money = take-home pay for the trade minus estimated
// rent, in purchasing power. The brief lives in the URL (#advisor=settler&brief=…).
import { esc, el, fin } from "../core/util.js";
import { section, segmented, selectBox, sourcesHtml } from "../core/view.js";
import { frameBox, frameNation } from "../core/frame.js";

const LANGS = [["en", "English"], ["de", "German"], ["fr", "French"], ["es", "Spanish"], ["it", "Italian"], ["nl", "Dutch"],
  ["pt", "Portuguese"], ["pl", "Polish"], ["el", "Greek"], ["ro", "Romanian"], ["sv", "Swedish"], ["da", "Danish"], ["no", "Norwegian"],
  ["fi", "Finnish"], ["cs", "Czech"], ["sk", "Slovak"], ["hu", "Hungarian"], ["bg", "Bulgarian"], ["hr", "Croatian"], ["sr", "Serbian"],
  ["sl", "Slovenian"], ["et", "Estonian"], ["lv", "Latvian"], ["lt", "Lithuanian"], ["tr", "Turkish"], ["ca", "Catalan"]];
const LANG_NAME = Object.fromEntries(LANGS);
const PARTS = [
  { key: "money", label: "Money left", tip: "Take-home pay for your trade minus rent for a 1-bed flat, in purchasing power" },
  { key: "jobs", label: "Jobs in your field", tip: "How common your trade is here compared with the EU" },
  { key: "nature", label: "Nature", tip: "Forest share of the region" },
  { key: "momentum", label: "Momentum", tip: "Growth in jobs and population over the last ten years" },
  { key: "calm", label: "Low unemployment", tip: "Unemployment rate (NUTS 2)" },
  { key: "climate", label: "Mild summers", tip: "Fewer hot days and warm nights. For longer stays it looks ahead: 2035 for 10 years, 2050 for 25 (the middle of the two emissions paths)" },
];
const DEFAULT = { t: "software", pay: null, home: null, anchors: [], langs: ["en"], eng: true, w: { money: 35, jobs: 35, nature: 10, momentum: 15, calm: 0, climate: 10 }, size: "any", years: 10, view: "fit" };
const FIT_RAMP = ["#1d2a3a", "#33405a", "#5b5a6e", "#8f7a4e", "#c9a45c", "#ffe9a8"];
const GAP_RAMP = ["#8c2d3c", "#c4594b", "#e7c6a0", "#c6d8c2", "#5fae9a", "#1f6b6b"];

// --- the brief in the URL ---------------------------------------------------------------------------------------
function encode(b) {
  return [b.t, b.pay || "", b.home || "", b.anchors.map((a) => `${a.id}.${a.h}`).join("_"), b.langs.join("."), b.eng ? 1 : 0,
    PARTS.map((p) => b.w[p.key] ?? 0).join("."), b.size, b.years, b.view].join("~");
}
function decode(s, trades) {
  const b = structuredClone(DEFAULT);
  if (!s) return b;
  const [t, pay, home, anchors, langs, eng, w, size, years, view] = String(s).split("~");
  if (trades.has(t)) b.t = t;
  if (+pay > 0) b.pay = +pay;
  if (home) b.home = home;
  if (anchors) b.anchors = anchors.split("_").map((x) => { const [id, h] = x.split("."); return { id, h: +h || 2 }; }).filter((a) => a.id);
  if (langs) b.langs = langs.split(".").filter((l) => LANG_NAME[l]);
  b.eng = eng !== "0";
  if (w) w.split(".").forEach((v, k) => { if (PARTS[k]) b.w[PARTS[k].key] = Math.max(0, Math.min(100, +v || 0)); }); // older links have fewer weights: the rest keep their defaults
  if (["any", "big", "quiet"].includes(size)) b.size = size;
  if ([2, 10, 25].includes(+years)) b.years = +years;
  if (["fit", "salary"].includes(view)) b.view = view;
  return b;
}

// Net annual pay from gross on a country's curve (piecewise linear; the top segment's marginal rate beyond it).
function netOf(curve, g) {
  if (!curve || !fin(g)) return null;
  if (g <= curve[0][0]) return g * (curve[0][1] / curve[0][0]);
  for (let k = 1; k < curve.length; k++) {
    const [g0, n0] = curve[k - 1], [g1, n1] = curve[k];
    if (g <= g1) return n0 + ((g - g0) / (g1 - g0)) * (n1 - n0);
  }
  const [g0, n0] = curve.at(-2), [g1, n1] = curve.at(-1);
  return n1 + (g - g1) * ((n1 - n0) / (g1 - g0));
}
// The gross that gives a target net (bisection on the monotone curve).
function grossFor(curve, net) {
  if (!curve || !fin(net)) return null;
  let lo = 0, hi = 2e6;
  for (let k = 0; k < 50; k++) { const m = (lo + hi) / 2; if (netOf(curve, m) < net) lo = m; else hi = m; }
  return (lo + hi) / 2;
}

const euro = (v) => (fin(v) ? `€${Math.round(v).toLocaleString("en-GB")}` : "–");
const euroK = (v) => (fin(v) ? `€${(v / 1000).toFixed(v >= 1e5 ? 0 : 1)}k` : "–");

export async function mount(ctx) {
  const { app, data, el: host, link } = ctx;
  const [A, H, C] = await Promise.all([app.loadData("advisor"), app.loadData("history").catch(() => null), app.loadData("climate").catch(() => null)]);
  if (!A) {
    host.insertAdjacentHTML("beforeend", `<p class="adv-empty pad">The advisor's data file (advisor.json) is missing.</p>`);
    return {};
  }
  const counties = data.levels.counties;
  const w = app.w, grid = w.grid, raw = w.raw;
  const N = raw.counties.length;
  const trades = new Map(A.trades.map((t) => [t.id, t]));
  const rowByIdx = new Map(counties.rows.map((r) => [r.ref, r]));
  const idxByGeo = new Map(raw.counties.map((c, i) => [c.geoid, i]));
  const F = Object.fromEntries(A.regionFields.map((k, j) => [k, j]));
  const reg = (i, k) => A.regions[i][F[k]];
  const ctry = (i) => raw.counties[i].geoid.slice(0, 2);
  // region centroids (km) and cells
  const cx = new Float64Array(N), cy = new Float64Array(N), cn = new Int32Array(N);
  const cellsOf = Array.from({ length: N }, () => []);
  raw.county.forEach((r, c) => { if (r >= 0) { cx[r] += grid.cx(c); cy[r] += grid.cy(c); cn[r]++; cellsOf[r].push(c); } });
  for (let i = 0; i < N; i++) {
    if (cn[i]) { cx[i] /= cn[i]; cy[i] /= cn[i]; }
    else { const cell = rowByIdx.get(i)?.v.cell; if (Number.isInteger(cell)) { cx[i] = grid.cx(cell); cy[i] = grid.cy(cell); cellsOf[i].push(cell); } }
  }
  const allCities = app.data.cities || [];
  const cityById = new Map(allCities.map((c) => [c.id, c]));
  const homeRegionOf = (city) => {
    const ids = (city?.counties || []).map((g) => idxByGeo.get(g)).filter((i) => i != null);
    return ids.sort((a, b) => (rowByIdx.get(b)?.v.population || 0) - (rowByIdx.get(a)?.v.population || 0))[0] ?? null;
  };
  // Straight line to drive/train time: a detour factor and an average speed, plus getting going.
  const hoursTo = (i, city) => 0.25 + (Math.hypot(cx[i] - city.x, cy[i] - city.y) * 1.3) / 90;

  let B = decode(app.advisors?.brief?.take() ?? ctx.params?.brief, trades);

  // --- controls ---------------------------------------------------------------------------------------------------
  const form = section(host, { title: "Your settler brief", note: "Tell the advisor who you are. Every region on the map is scored for you, and the best ones are listed below. Nothing you type leaves your browser." });
  const tradeOpts = A.trades.map((t) => ({ value: t.id, label: t.label, group: t.group }));
  const r1 = el("div", "adv-row st-row");
  form.appendChild(r1);
  const tradeSel = selectBox(r1, { label: "Trade", options: tradeOpts, value: B.t, onChange: (v) => { B.t = v; update(); } });
  tradeSel.el.classList.add("st-trade");

  const r2 = el("div", "st-pay");
  r2.innerHTML = `<label class="st-f"><span>Pay today, gross per year <i class="muted">(optional)</i></span><input type="number" inputmode="numeric" min="0" step="1000" placeholder="e.g. 72000" id="st-pay"></label>
    <label class="st-f"><span>Where you live now</span><input list="st-cities" placeholder="City" id="st-home" autocomplete="off"></label>
    <datalist id="st-cities">${allCities.slice().sort((a, b) => a.name.localeCompare(b.name)).map((c) => `<option value="${esc(c.name)}">${esc((c.states || []).join("/"))}</option>`).join("")}</datalist>`;
  form.appendChild(r2);
  const payIn = r2.querySelector("#st-pay"), homeIn = r2.querySelector("#st-home");
  const cityByName = (s) => allCities.find((c) => c.name.toLowerCase() === String(s || "").trim().toLowerCase()) || null;
  payIn.value = B.pay || "";
  homeIn.value = B.home ? cityById.get(B.home)?.name || "" : "";
  payIn.addEventListener("change", () => { B.pay = +payIn.value > 0 ? +payIn.value : null; update(); });
  homeIn.addEventListener("change", () => { const c = cityByName(homeIn.value); B.home = c ? c.id : null; if (!c) homeIn.value = ""; update(); });

  const anchorBox = el("div", "st-anchors");
  form.appendChild(anchorBox);
  function renderAnchors() {
    anchorBox.innerHTML = `<span class="st-k">Stay near</span>${B.anchors.map((a, k) => {
      const c = cityById.get(a.id);
      return c ? `<span class="st-anchor">${esc(c.name)} · within <select data-k="${k}" aria-label="Hours to ${esc(c.name)}">${[1, 2, 3, 5].map((h) => `<option value="${h}"${h === a.h ? " selected" : ""}>${h}h</option>`).join("")}</select><button type="button" class="st-x" data-del="${k}" aria-label="Remove ${esc(c.name)}">✕</button></span>` : "";
    }).join("")}<input list="st-cities" class="st-add" placeholder="+ add a city" aria-label="Add a city to stay near" autocomplete="off">`;
  }
  renderAnchors();
  anchorBox.addEventListener("change", (e) => {
    if (e.target.matches("select[data-k]")) { B.anchors[+e.target.dataset.k].h = +e.target.value; update(); }
    else if (e.target.matches(".st-add")) {
      const c = cityByName(e.target.value);
      if (c && !B.anchors.some((a) => a.id === c.id)) { B.anchors.push({ id: c.id, h: 2 }); renderAnchors(); update(); }
      else e.target.value = "";
    }
  });
  anchorBox.addEventListener("click", (e) => {
    const d = e.target.closest("[data-del]");
    if (d) { B.anchors.splice(+d.dataset.del, 1); renderAnchors(); update(); }
  });

  const langBox = el("div", "st-langs");
  form.appendChild(langBox);
  function renderLangs() {
    langBox.innerHTML = `<span class="st-k">Languages you speak</span>${B.langs.map((l) => `<button type="button" class="st-lang" data-lang="${l}" aria-label="Remove ${esc(LANG_NAME[l])}">${esc(LANG_NAME[l])} ✕</button>`).join("")}
      <select class="st-addlang" aria-label="Add a language"><option value="">+ add</option>${LANGS.filter(([c]) => !B.langs.includes(c)).map(([c, n]) => `<option value="${c}">${esc(n)}</option>`).join("")}</select>
      <label class="st-eng"><input type="checkbox" ${B.eng ? "checked" : ""}> English is enough at work</label>`;
  }
  renderLangs();
  langBox.addEventListener("click", (e) => {
    const b = e.target.closest("[data-lang]");
    if (b) { B.langs = B.langs.filter((l) => l !== b.dataset.lang); renderLangs(); update(); }
  });
  langBox.addEventListener("change", (e) => {
    if (e.target.matches(".st-addlang") && e.target.value) { B.langs.push(e.target.value); renderLangs(); update(); }
    if (e.target.matches(".st-eng input")) { B.eng = e.target.checked; update(); }
  });

  const wBox = el("div", "st-weights");
  form.appendChild(wBox);
  wBox.innerHTML = `<span class="st-k">What matters</span>${PARTS.map((p) => `<label class="st-w" title="${esc(p.tip)}"><span>${esc(p.label)}</span><input type="range" min="0" max="100" step="5" data-w="${p.key}" value="${B.w[p.key]}"><b>${B.w[p.key]}</b></label>`).join("")}`;
  wBox.addEventListener("input", (e) => {
    const r = e.target.closest("[data-w]");
    if (!r) return;
    B.w[r.dataset.w] = +r.value;
    r.nextElementSibling.textContent = r.value;
    update();
  });
  const r3 = el("div", "adv-row st-row");
  form.appendChild(r3);
  r3.insertAdjacentHTML("beforeend", `<span class="st-k">City life</span>`);
  segmented(r3, { label: "City life", value: B.size, options: [{ value: "big", label: "Big city" }, { value: "any", label: "Any" }, { value: "quiet", label: "Quiet" }], onChange: (v) => { B.size = v; update(); } });
  r3.insertAdjacentHTML("beforeend", `<span class="st-k">Staying</span>`);
  segmented(r3, { label: "How long you will stay", value: B.years, options: [{ value: 2, label: "2 yrs" }, { value: 10, label: "10 yrs" }, { value: 25, label: "25 yrs" }], onChange: (v) => { B.years = +v; update(); } });

  // --- results ----------------------------------------------------------------------------------------------------
  const res = section(host, { title: "Your shortlist", note: "" });
  const viewRow = el("div", "adv-row st-row");
  res.appendChild(viewRow);
  viewRow.insertAdjacentHTML("beforeend", `<span class="st-k">Map</span>`);
  const viewSeg = segmented(viewRow, { label: "Map colour", value: B.view, options: [{ value: "fit", label: "Fit for you" }, { value: "salary", label: "Your salary here" }], onChange: (v) => { B.view = v; update(); } });
  const shareBtn = el("button", "adv-mini st-share", "Copy link to this brief");
  shareBtn.type = "button";
  viewRow.appendChild(shareBtn);
  shareBtn.addEventListener("click", async () => {
    app.hash.flush();
    try { await navigator.clipboard.writeText(location.href); shareBtn.textContent = "Link copied"; }
    catch { shareBtn.textContent = "Copy the address bar"; }
    setTimeout(() => (shareBtn.textContent = "Copy link to this brief"), 2000);
  });
  const summary = el("p", "adv-note st-summary");
  res.appendChild(summary);
  const list = el("ol", "st-list");
  res.appendChild(list);
  const card = el("div", "st-card");
  res.appendChild(card);
  const surprise = el("div", "st-surprise");
  res.appendChild(surprise);

  host.insertAdjacentHTML("beforeend", sourcesHtml(data, ["eurostat_gdp", "eurostat_emp", "eurostat_census", "eurostat_lfs", "worldcover", "copernicus_ecde"], [
    "Pay is estimated: the national average for your occupation group in your sector (Structure of Earnings Survey 2022, firms with 10+ staff), scaled by the region's overall pay level. Your own pay, if you enter it, rescales every region by the same factor.",
    "Take-home pay uses each country's tax and social contributions for a single person without children (earn_nt_net). Bonuses, local taxes and your own situation will differ.",
    "Rent is the roughest number. Eurostat's only rent for every country is a 1-bed flat in the capital (and a few cities with EU sites), from a survey used to set EU staff pay. Every other region is estimated from it by household income and density, shown with a hollow dot.",
    "\"English is enough at work\" keeps every region in play; where you don't speak the local language the card says so, with the share of adults who speak their best foreign language well (Adult Education Survey, edat_aes_l31), usually English.",
    "Travel time is a straight line with a detour factor at about 90 km/h, not a timetable.",
    "Mild summers counts hot days (30 °C) and warm nights (20 °C) per NUTS 2 region. A 2-year stay uses today's climate; 10 and 25 years use the models' path to 2035 and 2050, halfway between the two emissions paths (Copernicus ECDE).",
    "The UK and Türkiye have no comparable pay data, and a few Balkan countries no occupation census, so they are left out of the money and jobs parts.",
  ]));

  // --- the engine -------------------------------------------------------------------------------------------------
  const val = (k, i) => rowByIdx.get(i)?.v?.[k];
  let last = null;

  function compute() {
    const t = B.t;
    const pay = A.pay[t], jobs = A.jobs[t];
    const homeCity = B.home ? cityById.get(B.home) : null;
    const homeIdx = homeCity ? homeRegionOf(homeCity) : null;
    const k = B.pay && homeIdx != null && pay[homeIdx] ? B.pay / (pay[homeIdx] * 12) : 1;
    const anchors = B.anchors.map((a) => ({ ...a, city: cityById.get(a.id) })).filter((a) => a.city);
    const langs = new Set(B.langs);
    const R = [];
    for (let i = 0; i < N; i++) {
      const c = ctry(i);
      const r = { i, ok: true, why: null };
      // hard filters
      for (const a of anchors) {
        const h = hoursTo(i, a.city);
        if (h > a.h) { r.ok = false; r.why = `more than ${a.h}h from ${a.city.name}`; break; }
      }
      const rl = String(reg(i, "langs") || "").split("+").filter(Boolean);
      const speaks = rl.some((l) => langs.has(l));
      const eng = A.english[c];
      if (r.ok && !speaks && !B.eng) { r.ok = false; r.why = `you don't speak ${rl.map((l) => LANG_NAME[l] || l).join(" or ")}`; }
      r.engShare = eng;
      const gross = fin(pay[i]) ? pay[i] * 12 * k : null;
      const net = netOf(A.net[c], gross);
      const rent = reg(i, "rent1");
      const pli = A.pli[c] || 100;
      r.gross = gross; r.net = net; r.rent = rent;
      r.left = fin(net) && fin(rent) ? net / 12 - rent : null;
      r.leftPPS = fin(r.left) ? r.left / (pli / 100) : null;
      r.jobs = jobs[i];
      r.nature = val("forest", i);
      const jg = reg(i, "jobsGrowth10y"), pg = reg(i, "popGrowth10y");
      r.momentum = fin(jg) || fin(pg) ? 0.6 * (jg ?? pg) + 0.4 * (pg ?? jg) : null;
      r.unemp = val("unemployment", i);
      r.calm = fin(r.unemp) ? -r.unemp : null;
      // climate: hot days + warm nights in the year the stay is heading for (a 2-year stay: today, 1991–2020 + trend)
      const u = C ? C.unit_of[i] : -1;
      if (u >= 0) {
        const yi = Math.min(C.years.length - 1, (B.years === 2 ? 2026 : B.years === 10 ? 2035 : 2050) - C.years[0]);
        const at = (k) => (C.path[k].s45.mid[u][yi] + C.path[k].s85.mid[u][yi]) / 2;
        r.hot = at("hot"); r.trop = at("trop"); r.hotNow = C.base.hot[u];
        r.climate = -(r.hot + r.trop);
      } else r.climate = null;
      r.density = val("density", i);
      r.anchorH = anchors.map((a) => hoursTo(i, a.city));
      r.engOnly = !speaks;
      if (r.ok && !fin(r.leftPPS) && B.w.money > 0) { r.ok = false; r.why = "no comparable pay data"; }
      R.push(r);
    }
    // weights (momentum counts only for longer stays)
    const W = { ...B.w };
    W.momentum *= B.years === 2 ? 0 : B.years === 25 ? 1.5 : 1;
    const parts = PARTS.map((p) => p.key).filter((p) => W[p] > 0);
    if (B.size !== "any") { parts.push("city"); W.city = 20; }
    for (const r of R) r.city = fin(r.density) ? (B.size === "big" ? Math.log(r.density) : -Math.log(r.density)) : null;
    const keyOf = { money: "leftPPS", jobs: "jobs", nature: "nature", momentum: "momentum", calm: "calm", climate: "climate", city: "city" };
    const ok = R.filter((r) => r.ok);
    // rank 0–100 within the regions still in play
    for (const p of parts) {
      const kf = keyOf[p];
      const vals = ok.map((r) => r[kf]).filter(fin).sort((a, b) => a - b);
      for (const r of ok) {
        const v = r[kf];
        if (!fin(v) || !vals.length) { r["p_" + p] = null; continue; }
        let lo = 0, hi = vals.length;
        while (lo < hi) { const m = (lo + hi) >> 1; vals[m] < v ? (lo = m + 1) : (hi = m); }
        r["p_" + p] = Math.round((100 * lo) / Math.max(1, vals.length - 1));
      }
    }
    for (const r of ok) {
      let s = 0, ws = 0;
      for (const p of parts) if (fin(r["p_" + p])) { s += r["p_" + p] * W[p]; ws += W[p]; }
      r.score = ws ? s / ws : null;
    }
    // "your salary here": the gross you'd need to keep today's money left (in purchasing power)
    let target = null;
    if (homeIdx != null && B.pay) target = R[homeIdx].leftPPS;
    for (const r of R) {
      if (!fin(target)) { r.need = null; r.gap = null; continue; }
      const c = ctry(r.i);
      const needNet = (target * ((A.pli[c] || 100) / 100) + (r.rent ?? 0)) * 12;
      r.need = fin(r.rent) ? grossFor(A.net[c], needNet) : null;
      r.gap = fin(r.need) && fin(r.gross) ? r.gross / r.need - 1 : null;
    }
    const ranked = ok.filter((r) => fin(r.score)).sort((a, b) => b.score - a.score);
    return { R, ranked, parts, homeIdx, k, target, anchors };
  }

  // --- drawing ------------------------------------------------------------------------------------------------------
  const markers = { id: "settler-marks", z: 60, space: "screen", top: [], draw(cctx) {
    const cam = app.cam;
    cctx.font = "600 12px Palatino, Georgia, serif";
    cctx.textAlign = "center"; cctx.textBaseline = "middle";
    markers.top.forEach((i, k) => {
      const [x, y] = cam.toScreen(cx[i], cy[i]);
      if (x < -20 || y < -20 || x > cam.w + 20 || y > cam.h + 20) return;
      const r = k === 0 ? 12 : 10;
      cctx.beginPath(); cctx.arc(x, y, r + 2, 0, 7); cctx.fillStyle = "rgba(10,8,4,.75)"; cctx.fill();
      cctx.beginPath(); cctx.arc(x, y, r, 0, 7); cctx.fillStyle = k === 0 ? "#ecd08e" : "#1b2838"; cctx.fill();
      cctx.lineWidth = 2; cctx.strokeStyle = "#ecd08e"; cctx.stroke();
      cctx.fillStyle = k === 0 ? "#1b2838" : "#ecd08e"; cctx.fillText(String(k + 1), x, y + 0.5);
    });
  } };
  ctx.cleanup(app.registerOverlay(markers));

  function lensFor(out) {
    const values = new Array(grid.size).fill(null);
    if (B.view === "salary" && fin(out.target)) {
      for (let c = 0; c < grid.size; c++) { const r = raw.county[c]; if (r >= 0 && out.R[r].ok) values[c] = out.R[r].gap; }
      return { id: "settler", group: "settler", name: "Your salary here", icon: "l-income", emoji: "💶", unit: "what your trade pays here vs what you'd need", format: "pct", scale: "linear", domain: [-0.4, 0.4], ramp: GAP_RAMP, higher_is: "good", source: "", description: "Teal: your trade pays more here than you'd need to keep today's money left after rent. Red: less. Regions filtered out by your brief show no data.", values };
    }
    for (let c = 0; c < grid.size; c++) { const r = raw.county[c]; if (r >= 0 && out.R[r].ok && fin(out.R[r].score)) values[c] = out.R[r].score; }
    return { id: "settler", group: "settler", name: `Fit: ${trades.get(B.t).label}`, icon: "l-amenities", emoji: "🏕️", unit: "fit for your brief, 0–100", format: "int", scale: "linear", domain: [0, 100], ramp: FIT_RAMP, higher_is: "good", source: "", description: "How well each region fits your brief, ranked against every other region that passes your filters. Grey regions are filtered out (too far, language, or no pay data).", values };
  }

  const name = (i) => { const r = rowByIdx.get(i); return r ? `${r.name}` : raw.counties[i].name; };
  const stayYear = () => (B.years === 2 ? "2026" : B.years === 10 ? "2035" : "2050");
  const sub = (i) => { const r = rowByIdx.get(i); return [r?.v.metro && r.v.metro !== r.name ? r.v.metro : null, ctry(i)].filter(Boolean).join(", "); };
  const dot = (q) => `<i class="st-dot ${q}" title="${q === "m" ? "measured" : q === "d" ? "derived from official data" : "estimated"}"></i>`;

  function why(r, out) {
    const parts = out.parts.filter((p) => fin(r["p_" + p])).map((p) => ({ p, v: r["p_" + p] })).sort((a, b) => b.v - a.v);
    if (!parts.length) return "";
    const say = {
      money: (r) => `${euro(r.left)} a month left after rent`,
      jobs: (r) => `your trade is ${r.jobs >= 1 ? `${r.jobs.toFixed(1)}× as common as` : `less common than`} the EU average`,
      nature: (r) => `${Math.round((r.nature || 0) * 100)}% of the land is forest`,
      momentum: (r) => `jobs and people grew ${r.momentum >= 0 ? "+" : ""}${(r.momentum * 100).toFixed(0)}% in ten years`,
      calm: (r) => `unemployment is ${(r.unemp * 100).toFixed(1)}%`,
      climate: (r) => `summers stay mild (${Math.round(r.hot)} hot days a year by ${stayYear()})`,
      city: (r) => (B.size === "big" ? "it's a dense, busy place" : "it's quiet and open"),
    };
    const best = parts.slice(0, 2).filter((x) => x.v >= 60).map((x) => say[x.p](r));
    const worst = parts.at(-1);
    let s = best.length ? `Strong because ${best.join(" and ")}.` : `A balanced pick with no standout.`;
    if (worst && worst.v < 40 && parts.length > 1) s += ` Weaker on ${PARTS.find((p) => p.key === worst.p)?.label.toLowerCase() || "city life"}${worst.p === "money" ? ` (${euro(r.left)} left)` : ""}.`;
    if (r.engOnly) s += ` You'd rely on English${fin(r.engShare) && r.engShare < 100 ? ` (${Math.round(r.engShare)}% of adults here speak a foreign language well)` : ""}.`;
    return s;
  }

  function cardHtml(r, rank, out) {
    const t = trades.get(B.t);
    const c = ctry(r.i);
    const surveyed = reg(r.i, "rentSurvey");
    const payQ = A.payQuality[t.id]?.[c] === "trade" ? "d" : "e";
    const bars = out.parts.map((p) => {
      const v = r["p_" + p];
      const lbl = PARTS.find((x) => x.key === p)?.label || (B.size === "big" ? "Big city" : "Quiet");
      return `<div class="st-bar"><span>${esc(lbl)}</span><span class="b"><i style="width:${fin(v) ? v : 0}%"></i></span><b>${fin(v) ? v : "–"}</b></div>`;
    }).join("");
    const anchorsTxt = out.anchors.map((a, k) => `${a.city.name} ≈ ${r.anchorH[k].toFixed(1)}h`).join(" · ");
    return `<div class="st-card-h"><span class="st-rank">${rank ? `#${rank}` : ""}</span><div><b>${esc(name(r.i))}</b><span class="muted"> ${esc(sub(r.i))}</span></div><span class="st-score">${fin(r.score) ? Math.round(r.score) : "–"}</span></div>
      <p class="st-why">${esc(why(r, out))}</p>
      <div class="st-kv">
        <span>${dot(payQ)}${esc(t.label)}, gross</span><b>${euro(r.gross / 12)} / mo</b>
        <span>${dot("d")}After tax</span><b>${euro(r.net / 12)} / mo</b>
        <span>${dot(surveyed ? "d" : "e")}Rent, 1-bed${surveyed ? "" : " (estimate)"}</span><b>−${euro(r.rent)}</b>
        <span><strong>Left each month</strong></span><b class="st-left">${euro(r.left)}</b>
        <span>${dot("m")}Your trade vs EU</span><b>${fin(r.jobs) ? `${r.jobs.toFixed(1)}×` : "–"}</b>
        ${fin(r.hot) ? `<span>${dot("e")}Hot days a year, 1991–2020 → ${stayYear()}</span><b>${Math.round(r.hotNow)} → ${Math.round(r.hot)}</b>` : ""}
        <span>${dot("m")}Jobs and people, 10 yrs</span><b>${fin(r.momentum) ? `${r.momentum >= 0 ? "+" : "−"}${Math.abs(r.momentum * 100).toFixed(0)}%` : "–"}</b>
        ${fin(r.need) ? `<span>${dot("d")}You'd need to earn</span><b>${euroK(r.need)} / yr</b>` : ""}
      </div>
      ${anchorsTxt ? `<p class="muted st-anch">${esc(anchorsTxt)}</p>` : ""}
      <div class="st-bars">${bars}</div>
      <p class="st-legend muted">${dot("m")}measured ${dot("d")}derived ${dot("e")}estimated</p>`;
  }

  let selected = null;
  function render(out) {
    const top = out.ranked.slice(0, 10);
    markers.top = top.map((r) => r.i);
    const nOk = out.R.filter((r) => r.ok).length;
    const t = trades.get(B.t);
    summary.innerHTML = `${nOk.toLocaleString("en-GB")} of ${N.toLocaleString("en-GB")} regions pass your filters.${
      out.homeIdx != null && B.pay ? ` Your pay is ${Math.round(out.k * 100)}% of the estimated average for ${esc(t.label)} in ${esc(name(out.homeIdx))}; every region is scaled by that.` : " Add your pay and home city to scale pay to you and to see what you'd need to earn elsewhere."}`;
    list.innerHTML = top.length ? top.map((r, k) => `<li><button type="button" data-i="${r.i}" class="st-item${selected === r.i ? " on" : ""}">
        <span class="n">${k + 1}</span><span class="nm"><b>${esc(name(r.i))}</b><span class="muted">${esc(sub(r.i))}</span></span>
        <span class="m">${euro(r.left)}<small>left / mo</small></span><span class="s">${Math.round(r.score)}</span></button></li>`).join("")
      : `<li class="adv-empty">No region passes every filter. Allow more travel time or another language.</li>`;
    const pick = out.R[selected] && out.R[selected].ok ? out.R[selected] : top[0];
    card.innerHTML = pick ? cardHtml(pick, top.indexOf(pick) + 1, out) : "";
    card.hidden = !pick;
    // a surprise: the best region outside the top 10 that isn't part of a big metro
    const metroPop = (i) => { const m = rowByIdx.get(i)?.v.cbsa; return m ? cityById.get(m)?.population || 0 : 0; };
    const s = out.ranked.slice(10).find((r) => metroPop(r.i) < 400000 && (rowByIdx.get(r.i)?.v.population || 0) < 400000);
    surprise.innerHTML = s ? `<span class="st-k">Off the beaten path</span><button type="button" data-i="${s.i}" class="st-item"><span class="n">★</span><span class="nm"><b>${esc(name(s.i))}</b><span class="muted">${esc(sub(s.i))}</span></span><span class="m">${euro(s.left)}<small>left / mo</small></span><span class="s">${Math.round(s.score)}</span></button>` : "";
    viewSeg.el.querySelector('[data-v="salary"]').disabled = !fin(out.target);
    viewSeg.el.querySelector('[data-v="salary"]').title = fin(out.target) ? "" : "Add your pay and home city first";
  }

  const hl = (i) => (i == null ? null : { cells: new Set(cellsOf[i]), label: name(i) });
  res.addEventListener("click", (e) => {
    const b = e.target.closest("[data-i]");
    if (!b) return;
    selected = +b.dataset.i;
    render(last);
    const r = rowByIdx.get(selected);
    if (r) counties.focus(r);
  });
  res.addEventListener("mouseover", (e) => { const b = e.target.closest("[data-i]"); link.hover(b ? hl(+b.dataset.i) : null); });
  res.addEventListener("mouseleave", () => link.hover(null));

  // Frame the map on the regions still in play whenever the filters change what passes.
  let framedSig = null;
  function frame(out) {
    const sig = `${B.anchors.map((a) => a.id + a.h).join()}|${B.langs.join()}|${B.eng}`;
    if (sig === framedSig) return;
    const first = framedSig === null;
    framedSig = sig;
    const ok = out.R.filter((r) => r.ok && cn[r.i]);
    if (!ok.length || ok.length > N * 0.6) { if (!first) frameNation(app); return; }
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const r of ok) { x0 = Math.min(x0, cx[r.i]); x1 = Math.max(x1, cx[r.i]); y0 = Math.min(y0, cy[r.i]); y1 = Math.max(y1, cy[r.i]); }
    const m = grid.R * 3;
    frameBox(app, { x0: x0 - m, y0: y0 - m, x1: x1 + m, y1: y1 + m }, { maxScale: 2 });
  }

  let queued = 0;
  function update() {
    if (queued) return;
    queued = requestAnimationFrame(() => {
      queued = 0;
      if (B.view === "salary" && !(B.pay && B.home)) { B.view = "fit"; viewSeg.set("fit"); }
      last = compute();
      render(last);
      frame(last);
      ctx.setLens(lensFor(last));
      app.invalidate();
      app.hash.update();
    });
  }

  ctx.cleanup(app.advisors.brief.hook({
    get: () => (app.mode === "advisor" && app.advisors?.current === "settler" ? encode(B) : null),
    set(v) {
      if (!v) return;
      app.advisors.brief.take();
      B = decode(v, trades);
      tradeSel.set(B.t);
      payIn.value = B.pay || "";
      homeIn.value = B.home ? cityById.get(B.home)?.name || "" : "";
      renderAnchors(); renderLangs();
      wBox.querySelectorAll("[data-w]").forEach((r) => { r.value = B.w[r.dataset.w]; r.nextElementSibling.textContent = r.value; });
      viewSeg.set(B.view);
      update();
    },
  }));
  update();

  return {
    onMapClick(ev) {
      const cell = ev.cell ?? app.cellAt?.(ev.x, ev.y);
      const r = cell >= 0 ? raw.county[cell] : -1;
      if (r < 0 || !last?.R[r]) return false;
      selected = r;
      render(last);
      card.scrollIntoView({ block: "nearest", behavior: "smooth" });
      return true;
    },
    onMapHover(h) {
      const r = h.cell >= 0 ? raw.county[h.cell] : -1;
      list.querySelectorAll(".st-item").forEach((b) => b.classList.toggle("hot", +b.dataset.i === r));
    },
    destroy() { markers.top = []; },
  };
}
