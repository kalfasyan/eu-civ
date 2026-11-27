// Economy advisor: GDP by industry, metro GDP on the map, leaders, specialisation and growth vs output.
import { esc, fin, ratio, colorScale, robustDomain, RAMPS } from "../core/util.js";
import { money, dollars, pct, int, signedPct, count3, fmtShort } from "../core/fmt.js";
import { barList, rampLegend, sizeLegend } from "../core/charts.js";
import { createTable } from "../core/table.js";
import { createScatter } from "../core/scatter.js";
import { section, tiles, segmented, selectBox, sourcesHtml, frameBtn } from "../core/view.js";
import { rowsHighlight } from "../core/data.js";
import { icon } from "../../../ui/icon.js";
import { hasIcon } from "../../../icons.js";

export const METRO_MIN = 250000;
const short = (s) => String(s || "").replace(/\s*\(.*\)\s*$/, "");
const indIcon = (k) => (hasIcon(`i-${k}`) ? icon(`i-${k}`, "•", { size: 14 }) : k === "government" ? icon("i-public_admin", "🏛", { size: 14 }) : "");

export function mount(ctx) {
  const { app, data, el, link, params } = ctx;
  const nation = app.data.nation;
  const n = nation.nation || {};
  const metros = data.levels.metros;
  const rows = metros.rows;
  const gdpInd = n.gdp_by_industry || {};
  const jobInd = Object.keys(nation.industries || {});

  // --- headline -------------------------------------------------------------------------------------------------
  const topInd = Object.entries(gdpInd).filter(([, v]) => fin(v)).sort((a, b) => b[1] - a[1])[0];
  el.insertAdjacentHTML("beforeend", tiles([
    { label: `GDP ${n.gdp_year || ""}`, value: money(n.gdp), sub: "current euros" },
    { label: "Per person", value: money(ratio(n.gdp, n.population)), sub: "GDP ÷ residents" },
    { label: "Top industry", value: topInd ? short(nation.gdp_industries?.[topInd[0]] || topInd[0]) : "–", sub: topInd ? `${pct(topInd[1] / n.gdp)} of GDP` : "" },
  ]));

  // --- GDP by industry ------------------------------------------------------------------------------------------
  const stRows = data.levels.states.rows;
  const indBody = section(el, { title: "GDP by industry", kicker: "United States", note: "Value added by each industry, where the work is done. Hover an industry to light up the states where it is the biggest share of the economy; click it to rank the metros that specialise in it." });
  const indRows = Object.entries(gdpInd).filter(([, v]) => fin(v)).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({
    key: k, label: short(nation.gdp_industries?.[k] || k), full: nation.gdp_industries?.[k], value: v, text: money(v), sub: pct(v / n.gdp), icon: indIcon(k),
  }));
  const states = app.data.states || [];
  const indBars = barList(indBody, {
    rows: indRows, ariaLabel: "GDP by industry",
    onHover: (r) => {
      if (!r) return link.hover(null);
      const top = states.map((s, i) => ({ i, v: ratio(s.gdp_by_industry?.[r.key], s.gdp) })).filter((x) => fin(x.v)).sort((a, b) => b.v - a.v).slice(0, 8);
      link.hover({ states: new Set(top.map((x) => x.i)), dimOthers: true });
    },
    onClick: (r) => { setIndustry(r.key === "government" ? "public_admin" : r.key); specBody.scrollIntoView({ behavior: "smooth", block: "start" }); },
  });

  // --- map: metro GDP circles -----------------------------------------------------------------------------------
  const mapBody = section(el, { title: "Metro economies on the map", note: "Each circle is a metro area: its area is the metro's GDP, its colour GDP per person. Hover a circle for numbers; click to open the metro." });
  const ppDomain = robustDomain(rows.filter((r) => r.v.population >= 100000).map((r) => r.v.gdp_pc), 0.03, true) || [30000, 120000];
  const ppColor = colorScale({ type: "seq", domain: ppDomain, ramp: RAMPS.gold });
  const gMax = Math.max(...rows.map((r) => r.v.gdp || 0));
  const bubbles = ctx.bubbles("gdp", {
    rMax: 30, minR: 1.5, alpha: 0.6,
    tip: (b) => `<b>${esc(b.row.name)}</b> <span class="sub">${esc(b.row.sub)}</span><br>GDP <b>${money(b.row.v.gdp)}</b> · per person <b>${money(b.row.v.gdp_pc)}</b><br>${count3(b.row.v.population)} people`,
    onHover: (b) => { table.setHot(b ? b.key : null); scatter.setHot(b ? b.key : null); link.hover(b ? rowsHighlight(metros, [b.row]) : null); },
    onClick: (b) => app.selectCity(b.row.ref),
  });
  const bubbleItems = rows.filter((r) => fin(r.v.gdp)).map((r) => ({ key: r.key, x: app.w.grid.cx(r.ref.cell), y: app.w.grid.cy(r.ref.cell), value: r.v.gdp, color: ppColor(r.v.gdp_pc), row: r }));
  bubbles.set(bubbleItems, { vMax: gMax });
  const showBubbles = document.createElement("label");
  showBubbles.className = "adv-check";
  showBubbles.innerHTML = `<input type="checkbox" checked> Show GDP circles`;
  showBubbles.querySelector("input").addEventListener("change", (e) => bubbles.set(e.target.checked ? bubbleItems : [], { vMax: gMax }));
  mapBody.appendChild(showBubbles);
  mapBody.insertAdjacentHTML("beforeend", rampLegend({ ramp: RAMPS.gold, domain: ppDomain, fmt: money, label: "GDP per person" })
    + sizeLegend([1e10, 1e11, 1e12].filter((v) => v <= gMax), (v) => 30 * Math.sqrt(v / gMax) , money, "Circle area = GDP (at the home zoom)"));

  // --- leaders --------------------------------------------------------------------------------------------------
  const lBody = section(el, { title: "Leading metros", note: `GDP per person ranks only metros of ${count3(METRO_MIN)}+ people (small areas with one big plant or mine swing wildly).` });
  const big = rows.filter((r) => (r.v.population || 0) >= METRO_MIN);
  segmented(lBody, {
    label: "Rank by", value: "gdp",
    options: [{ value: "gdp", label: "Largest GDP" }, { value: "gdp_pc", label: "GDP per person" }, { value: "growth", label: "Fastest growing" }],
    onChange: (v) => { table.setRows(v === "gdp" ? rows : big); table.setColumns(cols, { key: v, dir: "desc" }); },
  });
  const cols = [
    { key: "name", label: "Metro", align: "l", value: (r) => r.name, html: (r) => `${esc(r.name)} <span class="sub">${esc(r.sub)}</span>` },
    { key: "gdp", label: "GDP", value: (r) => r.v.gdp, text: (r) => money(r.v.gdp), bar: { max: gMax, color: "rgba(224,181,76,.35)" } },
    { key: "gdp_pc", label: "Per person", value: (r) => r.v.gdp_pc, text: (r) => money(r.v.gdp_pc) },
    { key: "growth", label: "Growth", value: (r) => r.v.growth, text: (r) => signedPct(r.v.growth) },
  ];
  const table = createTable(lBody, {
    caption: "Metros by GDP", columns: cols, rows, sort: { key: "gdp", dir: "desc" }, rank: true, maxHeight: 280,
    search: "Search metros",
    onHover: (r) => { link.hover(r ? rowsHighlight(metros, [r]) : null); bubbles.setHot(r ? r.key : null); scatter.setHot(r ? r.key : null); },
    onClick: (r) => app.selectCity(r.ref),
  });

  // --- specialisation -------------------------------------------------------------------------------------------
  const specBody = section(el, { title: "Who specialises in what", note: `Location quotient: the share of a metro's employed residents in the industry ÷ the U.S. share. ×2 means twice as concentrated as the country. Metros of ${count3(METRO_MIN)}+ people; the 15 most specialised are outlined on the map.` });
  let industry = params.industry && jobInd.includes(params.industry) ? params.industry : "manufacturing";
  const indSel = selectBox(specBody, {
    label: "Industry", value: industry,
    options: jobInd.map((k) => ({ value: k, label: short(nation.industries[k]) })),
    onChange: (v) => setIndustry(v),
  });
  const specInfo = document.createElement("p");
  specInfo.className = "adv-note";
  specBody.appendChild(specInfo);
  const lq = (r, k = industry) => {
    const o = r.ref;
    const us = ratio(n.jobs?.[k], n.employed);
    return us ? ratio(ratio(o.jobs?.[k], o.employed), us) : null;
  };
  const specTable = createTable(specBody, {
    caption: "Most specialised metros", rank: true, maxHeight: 260, rows: [],
    columns: [
      { key: "name", label: "Metro", align: "l", value: (r) => r.name, html: (r) => `${esc(r.name)} <span class="sub">${esc(r.sub)}</span>` },
      { key: "share", label: "Share of jobs", value: (r) => ratio(r.ref.jobs?.[industry], r.ref.employed), text: (r) => pct(ratio(r.ref.jobs?.[industry], r.ref.employed)) },
      { key: "lq", label: "LQ", value: (r) => lq(r), text: (r) => (fin(lq(r)) ? `×${lq(r).toFixed(2)}` : "–"), bar: { max: 1, color: "rgba(74,134,214,.4)" } },
      { key: "workers", label: "Workers", value: (r) => r.ref.jobs?.[industry], text: (r) => count3(r.ref.jobs?.[industry]) },
    ],
    sort: { key: "lq", dir: "desc" },
    onHover: (r) => { link.hover(r ? rowsHighlight(metros, [r]) : null); scatter.setHot(r ? r.key : null); bubbles.setHot(r ? r.key : null); },
    onClick: (r) => app.selectCity(r.ref),
  });

  // --- scatter --------------------------------------------------------------------------------------------------
  const scBody = section(el, { title: "Growth vs output", note: "Each dot is a metro: GDP per person across, population growth up, size = population. Drag a rectangle to select metros and outline them on the map." });
  const scCtl = document.createElement("div");
  scCtl.className = "adv-row";
  scBody.appendChild(scCtl);
  let colorBy = "lq", allMetros = false;
  selectBox(scCtl, {
    label: "Colour", value: colorBy,
    options: [{ value: "lq", label: "Specialisation (chosen industry)" }, { value: "unemployment", label: "Unemployment" }, { value: "median_income", label: "Income" }, { value: "none", label: "None" }],
    onChange: (v) => { colorBy = v; drawScatter(); },
  });
  segmented(scCtl, { label: "Metros", value: "big", options: [{ value: "big", label: `${count3(METRO_MIN)}+` }, { value: "all", label: "All" }], onChange: (v) => { allMetros = v === "all"; drawScatter(); } });
  const legendEl = document.createElement("div");
  const scatter = createScatter(scBody, {
    points: [], height: 300,
    x: { label: "GDP per person", fmt: (v) => money(v), log: true },
    y: { label: "Population growth", fmt: (v) => fmtShort("signed", v) },
    size: { label: "Population", fmt: count3, max: 15, min: 2 },
    refY: [{ v: n.growth ?? 0, label: `U.S. ${signedPct(n.growth)}` }],
    onHover: (p) => { link.hover(p ? rowsHighlight(metros, [p.row]) : null); bubbles.setHot(p ? p.key : null); table.setHot(p ? p.key : null, false); },
    onClick: (p) => app.selectCity(p.row.ref),
    onBrush: (set) => {
      const sel = set ? rows.filter((r) => set.has(r.key)) : [];
      link.base(sel.length ? rowsHighlight(metros, sel, { dim: true }) : specHighlight(), { frame: sel.length > 1 });
      bubbles.setSelected(set);
      brushInfo.innerHTML = sel.length ? brushSummary(sel) : "";
    },
  });
  scBody.appendChild(legendEl);
  const brushInfo = document.createElement("div");
  brushInfo.className = "adv-brushinfo";
  scBody.appendChild(brushInfo);
  function brushSummary(sel) {
    const pop = sel.reduce((a, r) => a + (r.v.population || 0), 0);
    const gdp = sel.reduce((a, r) => a + (r.v.gdp || 0), 0);
    return `<b>${sel.length}</b> metros selected · ${count3(pop)} people · ${money(gdp)} GDP (${pct(gdp / n.gdp)} of U.S.) ${frameBtn()}<button type="button" class="adv-mini" data-clear>Clear</button>`;
  }
  brushInfo.addEventListener("click", (e) => { if (e.target.closest("[data-clear]")) { scatter.setSelected(null); link.base(specHighlight()); bubbles.setSelected(null); brushInfo.innerHTML = ""; } });

  function drawScatter() {
    const list = rows.filter((r) => allMetros || (r.v.population || 0) >= METRO_MIN);
    const cv = (r) => (colorBy === "lq" ? lq(r) : colorBy === "none" ? null : r.v[colorBy]);
    let color = null, legend = "";
    if (colorBy !== "none") {
      const dom = robustDomain(list.map(cv), 0.03, colorBy === "lq") || [0, 1];
      const spec = colorBy === "lq" ? { type: "seq", domain: [Math.max(0.2, dom[0]), Math.max(1.5, dom[1])], log: true, ramp: RAMPS.seq } : { type: "seq", domain: dom, ramp: colorBy === "unemployment" ? RAMPS.heat : RAMPS.gold };
      const cs = colorScale(spec);
      color = (c) => cs(c);
      const f = colorBy === "lq" ? (v) => `×${v.toFixed(1)}` : colorBy === "unemployment" ? (v) => pct(v) : money;
      legend = rampLegend({ ramp: spec.ramp, domain: spec.domain, fmt: f, log: spec.log, label: colorBy === "lq" ? `Specialisation in ${short(nation.industries[industry]).toLowerCase()}` : colorBy === "unemployment" ? "Unemployment" : "Disposable income per person" });
    }
    const labels = [...list].sort((a, b) => (b.v.population || 0) - (a.v.population || 0)).slice(0, 8).map((r) => r.key);
    scatter.update({
      points: list.filter((r) => fin(r.v.gdp_pc) && fin(r.v.growth)).map((r) => ({ key: r.key, x: r.v.gdp_pc, y: r.v.growth, s: r.v.population, c: cv(r), label: r.name, sub: r.sub, row: r })),
      color, labels, colorLabel: colorBy === "none" ? null : colorBy === "lq" ? "LQ" : colorBy === "unemployment" ? "Unemployment" : "Income",
      colorFmt: colorBy === "lq" ? (v) => `×${(+v).toFixed(2)}` : colorBy === "unemployment" ? pct : dollars,
    });
    legendEl.innerHTML = legend;
  }

  let specTop = [];
  const specHighlight = () => (specTop.length ? rowsHighlight(metros, specTop, { ringMax: 15 }) : null);
  function setIndustry(k) {
    industry = k;
    indSel.set(k);
    const list = big.filter((r) => fin(lq(r))).sort((a, b) => lq(b) - lq(a));
    specTop = list.slice(0, 15);
    const maxLq = Math.max(1, ...list.slice(0, 40).map((r) => lq(r)));
    specTable.setColumns([
      { key: "name", label: "Metro", align: "l", value: (r) => r.name, html: (r) => `${esc(r.name)} <span class="sub">${esc(r.sub)}</span>` },
      { key: "share", label: "Share of jobs", value: (r) => ratio(r.ref.jobs?.[industry], r.ref.employed), text: (r) => pct(ratio(r.ref.jobs?.[industry], r.ref.employed)) },
      { key: "lq", label: "LQ", value: (r) => lq(r), text: (r) => (fin(lq(r)) ? `×${lq(r).toFixed(2)}` : "–"), bar: { max: maxLq, color: "rgba(74,134,214,.45)" } },
      { key: "workers", label: "Workers", value: (r) => r.ref.jobs?.[industry], text: (r) => count3(r.ref.jobs?.[industry]) },
    ], { key: "lq", dir: "desc" });
    specTable.setRows(list);
    const us = ratio(n.jobs?.[k], n.employed);
    specInfo.innerHTML = `U.S.: <b>${pct(us)}</b> of employed residents (${count3(n.jobs?.[k])} people) work in ${esc(short(nation.industries[k]).toLowerCase())}.`;
    if (!scatter.selected) link.base(specHighlight());
    indBars.setSelected(k === "public_admin" ? "government" : k);
    drawScatter();
  }
  setIndustry(industry);

  // --- 2050 exposure (data/climate.json, loaded on demand) -------------------------------------------------------
  const exBody = section(el, { title: "2050 exposure", note: "Who sits on the hazards. Heat is days above 30 °C and nights above 20 °C (Copernicus, per NUTS 2 region, ERA5 1991–2020 and the EURO-CORDEX models for 2050). Low land is people living at or below 5 m near the coast: exposure, not a flood forecast, since dykes and dunes are not modelled." });
  exBody.insertAdjacentHTML("beforeend", `<p class="adv-note muted" data-wait>Loading climate data…</p>`);
  app.loadData("climate").then((C) => {
    exBody.querySelector("[data-wait]")?.remove();
    if (!C) { exBody.insertAdjacentHTML("beforeend", `<p class="adv-empty">The climate data file (climate.json) is missing.</p>`); return; }
    const raw = app.w.raw;
    const idx = new Map(raw.counties.map((c, i) => [c.geoid, i]));
    const regPop = new Map(data.levels.counties.rows.map((r) => [r.ref, r.v.population || 0]));
    let path = "s85";
    const Y = C.years.length - 1;
    // a metro's climate: its member regions' values weighted by population; low land: people summed
    const clim = new Map();
    for (const r of rows) {
      let w = 0, h0 = 0, h1 = { s45: 0, s85: 0 }, t1 = { s45: 0, s85: 0 }, low = 0;
      for (const g of r.ref.counties || []) {
        const i = idx.get(g);
        if (i == null) continue;
        low += C.coast[i]?.[2] || 0;
        const u = C.unit_of[i];
        if (u < 0) continue;
        const p = regPop.get(i) || 0;
        w += p; h0 += p * C.base.hot[u];
        for (const k of ["s45", "s85"]) { h1[k] += p * C.path.hot[k].mid[u][Y]; t1[k] += p * C.path.trop[k].mid[u][Y]; }
      }
      clim.set(r.key, w ? { h0: h0 / w, h1: { s45: h1.s45 / w, s85: h1.s85 / w }, t1: { s45: t1.s45 / w, s85: t1.s85 / w }, low } : { low });
    }
    const cv = (r) => clim.get(r.key) || {};
    const S = C.stats;
    const tilesEl = document.createElement("div");
    exBody.appendChild(tilesEl);
    const drawTiles = () => {
      tilesEl.innerHTML = tiles([
        { label: "People with 30+ hot days", value: `${count3(S.pop_hot30_today)} → ${count3(S.pop_hot30_2050[path])}`, sub: "1991–2020 → 2050", color: "#f0b25a" },
        { label: "People on low land", value: count3(S.pop_low_coast), sub: "at or below 5 m", color: "#5fa8d3" },
        { label: "GDP on low land", value: money(S.gdp_low_coast), sub: "estimated from where people live" },
        { label: "Regions that stay mild", value: String(S.mild_2050[path]), sub: "under 5 hot days in 2050" },
      ]);
    };
    segmented(exBody, {
      label: "Emissions path", value: path,
      options: [{ value: "s45", label: "If emissions fall" }, { value: "s85", label: "If they don't" }],
      onChange: (v) => { path = v; drawTiles(); exTable.setRows(rows.filter(inPlay)); refTable.setRows(refuges()); },
    });
    drawTiles();
    const d1 = (v) => (fin(v) ? (v < 9.95 ? v.toFixed(1).replace(/\.0$/, "") : String(Math.round(v))) : "–");
    const inPlay = (r) => (r.v.population || 0) >= METRO_MIN;
    const exTable = createTable(exBody, {
      caption: "Metros by 2050 exposure", rank: true, maxHeight: 280, rows: rows.filter(inPlay), search: "Search metros",
      columns: [
        { key: "name", label: "Metro", align: "l", value: (r) => r.name, html: (r) => `${esc(r.name)} <span class="sub">${esc(r.sub)}</span>` },
        { key: "hot", label: "Hot days 2050", value: (r) => cv(r).h1?.[path], text: (r) => `${d1(cv(r).h0)} → ${d1(cv(r).h1?.[path])}`, bar: { max: 90, color: "rgba(240,178,90,.35)" } },
        { key: "trop", label: "Warm nights", value: (r) => cv(r).t1?.[path], text: (r) => d1(cv(r).t1?.[path]), hideBelow: 420 },
        { key: "low", label: "On low land", value: (r) => cv(r).low, text: (r) => (cv(r).low ? count3(cv(r).low) : "–"), bar: { max: 1.5e6, color: "rgba(95,168,211,.35)" } },
      ],
      sort: { key: "hot", dir: "desc" },
      onHover: (r) => link.hover(r ? rowsHighlight(metros, [r]) : null),
      onClick: (r) => app.selectCity(r.ref),
    });
    const refBody = section(el, { title: "Climate refuges", note: `Metros of ${count3(METRO_MIN)}+ people that stay mild in 2050 (under 5 hot days and 3 warm nights a year), ranked by GDP per person. The Settler advisor weighs the same numbers when you stay 10 or 25 years.` });
    el.insertBefore(refBody.closest("section") || refBody, exBody.closest("section").nextSibling);
    const refuges = () => rows.filter((r) => inPlay(r) && fin(cv(r).h1?.[path]) && cv(r).h1[path] < 5 && cv(r).t1[path] < 3);
    const refTable = createTable(refBody, {
      caption: "Climate refuges", rank: true, maxHeight: 240, rows: refuges(),
      columns: [
        { key: "name", label: "Metro", align: "l", value: (r) => r.name, html: (r) => `${esc(r.name)} <span class="sub">${esc(r.sub)}</span>` },
        { key: "hot", label: "Hot days 2050", value: (r) => cv(r).h1?.[path], text: (r) => d1(cv(r).h1?.[path]) },
        { key: "gdp_pc", label: "Per person", value: (r) => r.v.gdp_pc, text: (r) => money(r.v.gdp_pc) },
        { key: "growth", label: "Growth", value: (r) => r.v.growth, text: (r) => signedPct(r.v.growth), hideBelow: 420 },
      ],
      sort: { key: "gdp_pc", dir: "desc" },
      onHover: (r) => link.hover(r ? rowsHighlight(metros, [r]) : null),
      onClick: (r) => app.selectCity(r.ref),
    });
  }).catch((err) => { console.warn("2050 exposure:", err); exBody.querySelector("[data-wait]")?.remove(); });

  el.insertAdjacentHTML("beforeend", sourcesHtml(data, ["bea_gdp", "acs_1yr", "pep_population", "cbsa_delineation"], [
    "GDP is counted where the work is done (BEA); jobs and specialisation are counted where workers live (ACS), so a commuter suburb's workers count in its own metro.",
    `GDP is ${esc(nation.gdp_vintage || "BEA")} while population is ${esc(nation.vintage || "ACS")}: per-person figures divide numbers a year apart.`,
    "Metro GDP sums the member counties of each metro (OMB 2023 delineation); BEA suppresses some industry figures for small areas, so metro industry GDP is incomplete and not used here.",
  ]));

  return {
    onMapHover(h) {
      const r = h.cell >= 0 ? metros.rowAtCell(h.cell) : null;
      scatter.setHot(r ? r.key : null);
      specTable.setHot(r ? r.key : null);
    },
    onEscape() {
      if (scatter.selected) { scatter.setSelected(null); link.base(specHighlight()); bubbles.setSelected(null); brushInfo.innerHTML = ""; return true; }
      return false;
    },
  };
}
