// Prosperity advisor (EU): output vs household income, poverty and unemployment.
import { esc, fin, colorScale, RAMPS } from "../core/util.js";
import { money, dollars, pct, int, count3, fmtShort } from "../core/fmt.js";
import { barList, histogram, rampLegend } from "../core/charts.js";
import { createTable } from "../core/table.js";
import { createScatter } from "../core/scatter.js";
import { section, tiles, segmented, lensButton, sourcesHtml, topBy, frameBtn } from "../core/view.js";
import { rowsHighlight } from "../core/data.js";

const METRO_MIN = 250000;
const BIG_METRO = 500000;

export function mount(ctx) {
  const { app, data, el, link } = ctx;
  const n = data.nat;
  const { states, metros, counties } = data.levels;

  el.insertAdjacentHTML("beforeend", tiles([
    { label: "Disposable income", value: dollars(n.median_income), sub: "per person, EU27" },
    { label: "GDP per person", value: dollars(n.gdp / n.population), sub: "EU27" },
    { label: "Unemployment", value: pct(n.unemployment), sub: data.vintage },
  ]));

  // --- income vs home value -------------------------------------------------------------------------------------
  const aBody = section(el, { title: "Output and household income", note: "GDP per person (what is produced in a place) against net disposable household income per person (what residents have to spend). The dashed lines mark income at 30%, 50% and 80% of GDP: commuter hubs and capitals sit far below them, regions that live on transfers or commuting above. Drag a rectangle to select places; hover the map to find one here." });
  const aCtl = document.createElement("div");
  aCtl.className = "adv-row";
  aBody.appendChild(aCtl);
  let level = counties ? "counties" : "metros";
  segmented(aCtl, { label: "Places", value: level, options: [...(counties ? [{ value: "counties", label: "Regions" }] : []), { value: "metros", label: "Metros" }], onChange: (v) => { level = v; drawAfford(); } });
  for (const [id, label] of [["income", "Income lens"], ["gdp_pc", "GDP lens"]]) {
    const b = lensButton(app, id, label);
    if (b) aCtl.appendChild(b);
  }
  const ratioDomain = [0.3, 0.9];
  const ratioColor = colorScale({ type: "seq", domain: ratioDomain, ramp: RAMPS.heat });
  const lv = () => data.levels[level];
  const inc = (r) => (level === "counties" ? r.v.income : r.v.median_income);
  const gdpOf = (r) => (level === "counties" ? r.v.gdp_per_capita : r.v.gdp_pc);
  const ratioOf = (r) => (fin(gdpOf(r)) && fin(inc(r)) && gdpOf(r) > 0 ? inc(r) / gdpOf(r) : null);
  const scatter = createScatter(aBody, {
    height: 310, points: [],
    x: { label: "GDP per person", fmt: money, log: true },
    y: { label: "Disposable income per person", fmt: money, log: true },
    size: { label: "Population", fmt: count3, max: 14, min: 1.4 },
    refLines: [{ k: 0.3, label: "30%" }, { k: 0.5, label: "50%" }, { k: 0.8, label: "80%" }],
    color: (c) => ratioColor(c), colorLabel: "Income ÷ GDP", colorFmt: (v) => `${Math.round(v * 100)}%`,
    onHover: (p) => { link.hover(p ? rowsHighlight(lv(), [p.row]) : null); affTable.setHot(p ? p.key : null, false); },
    onClick: (p) => lv().focus(p.row),
    onBrush: (set) => {
      const sel = set ? lv().rows.filter((r) => set.has(r.key)) : [];
      link.base(sel.length ? rowsHighlight(lv(), sel, { dim: true }) : null, { frame: sel.length > 1 });
      affTable.setSelected(set);
      selInfo.innerHTML = sel.length ? `<b>${int(sel.length)}</b> ${level} selected · ${count3(sel.reduce((a, r) => a + (r.v.population || 0), 0))} people ${frameBtn()}<button type="button" class="adv-mini" data-clear>Clear</button>` : "";
    },
  });
  aBody.insertAdjacentHTML("beforeend", rampLegend({ ramp: RAMPS.heat, domain: ratioDomain, fmt: (v) => `${Math.round(v * 100)}%`, label: "Household income ÷ GDP" }));
  const selInfo = document.createElement("div");
  selInfo.className = "adv-brushinfo";
  aBody.appendChild(selInfo);
  const clearSel = () => { scatter.setSelected(null); affTable.setSelected(null); link.base(null); selInfo.innerHTML = ""; };
  selInfo.addEventListener("click", (e) => { if (e.target.closest("[data-clear]")) clearSel(); });
  aBody.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">Output and income table</h4>`);
  const affTable = createTable(aBody, {
    caption: "Income to GDP", rank: true, maxHeight: 260, rows: [], search: "Search places",
    columns: [
      { key: "name", label: "Place", align: "l", value: (r) => r.name, html: (r) => `${esc(r.name)} <span class="sub">${esc(r.sub)}</span>` },
      { key: "gdp", label: "GDP/p", value: gdpOf, text: (r) => money(gdpOf(r)) },
      { key: "inc", label: "Income/p", value: inc, text: (r) => money(inc(r)) },
      { key: "ratio", label: "Ratio", value: (r) => ratioOf(r), html: (r) => fin(ratioOf(r)) ? `<span class="dot" style="background:${ratioColor(ratioOf(r))}"></span>${Math.round(ratioOf(r) * 100)}%` : "–" },
    ],
    sort: { key: "ratio", dir: "desc" },
    onHover: (r) => { link.hover(r ? rowsHighlight(lv(), [r]) : null); scatter.setHot(r ? r.key : null); },
    onClick: (r) => lv().focus(r),
  });
  function drawAfford() {
    clearSel();
    const rows = lv().rows.filter((r) => fin(ratioOf(r)));
    scatter.update({
      points: rows.map((r) => ({ key: r.key, x: gdpOf(r), y: inc(r), s: r.v.population, c: ratioOf(r), label: r.name, sub: r.sub, row: r })),
      labels: topBy(rows, (r) => r.v.population, { n: 6 }).map((x) => x.r.key),
    });
    affTable.setRows(rows);
  }
  drawAfford();

  // --- poverty --------------------------------------------------------------------------------------------------
  let povHist = null;
  if (counties) {
    const pBody = section(el, { title: "Poverty", note: "Regions by the share of people at risk of poverty or social exclusion (EU-SILC, published for NUTS 2 regions). Hover a bar to outline those regions; the table lists them all." });
    const pCtl = document.createElement("div");
    pCtl.className = "adv-row";
    pBody.appendChild(pCtl);
    const lb = lensButton(app, "poverty", "Poverty lens");
    if (lb) pCtl.appendChild(lb);
    const pHost = document.createElement("div");
    pBody.appendChild(pHost);
    const usPov = (() => {
      let a = 0, w = 0;
      for (const r of counties.rows) if (fin(r.v.poverty) && fin(r.v.population)) { a += r.v.poverty * r.v.population; w += r.v.population; }
      return w ? a / w : null;
    })();
    povHist = histogram(pHost, {
      values: counties.rows.map((r) => ({ key: r.key, v: r.v.poverty, w: r.v.population })), bins: 30, domain: [0, 0.45], height: 120,
      fmt: (v) => fmtShort("pct", v), unitLabel: "counties", label: "Histogram of county poverty rates",
      colorOf: (_, t) => colorScale({ type: "seq", domain: [0, 1], ramp: RAMPS.heat })(t),
      markers: fin(usPov) ? [{ v: usPov, label: `EU ${pct(usPov)}` }] : [],
      onHover: (bin) => link.hover(bin ? rowsHighlight(counties, bin.keys.map((k) => counties.byKey.get(k)), { dim: true }) : null),
    });
    const povTable = createTable(pBody, {
      caption: "County poverty rates", rank: true, maxHeight: 240, rows: counties.rows.filter((r) => fin(r.v.poverty)), search: "Search counties",
      columns: [
        { key: "name", label: "County", align: "l", value: (r) => r.name, html: (r) => `${esc(r.name)} <span class="sub">${esc(r.sub)}</span>` },
        { key: "population", label: "People", value: (r) => r.v.population, text: (r) => count3(r.v.population) },
        { key: "poverty", label: "Poverty", value: (r) => r.v.poverty, text: (r) => pct(r.v.poverty), bar: { max: 0.5, color: "rgba(232,119,74,.4)" } },
        { key: "income", label: "Income", value: (r) => r.v.income, text: (r) => money(r.v.income) },
      ],
      sort: { key: "poverty", dir: "desc" },
      onHover: (r) => link.hover(r ? rowsHighlight(counties, [r]) : null),
      onClick: (r) => counties.focus(r),
    });
    ctx.cleanup(() => povTable.destroy());
  }

  // --- unemployment ---------------------------------------------------------------------------------------------
  const uBody = section(el, { title: "Unemployment", note: `Labour Force Survey unemployment rate, ages 15–74 (NUTS 2 regions, population-weighted for metros). Metros of ${count3(BIG_METRO)}+ people.` });
  const uHost = document.createElement("div");
  let uLevel = "states";
  segmented(uBody, { label: "Areas", value: uLevel, options: [{ value: "states", label: "States" }, { value: "metros", label: "Large metros" }], onChange: (v) => { uLevel = v; drawU(); } });
  uBody.appendChild(uHost);
  function drawU() {
    uHost.innerHTML = "";
    const lvU = uLevel === "states" ? states : metros;
    const min = uLevel === "states" ? 0 : BIG_METRO;
    const high = topBy(lvU.rows, (r) => r.v.unemployment, { n: 8, min });
    const low = topBy(lvU.rows, (r) => r.v.unemployment, { n: 8, min, asc: true });
    const max = Math.max(...high.map((x) => x.v));
    const mk = (list) => list.map((x) => ({ key: x.r.key, label: x.r.name, sub: uLevel === "metros" ? x.r.sub : "", value: x.v, text: pct(x.v), tone: x.v > n.unemployment * 1.03 ? "bad" : x.v < n.unemployment * 0.97 ? "good" : null, row: x.r }));
    const o = { max, onHover: (r) => link.hover(r ? rowsHighlight(lvU, [r.row]) : null), onClick: (r) => lvU.focus(r.row) };
    uHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">Highest</h4>`);
    barList(uHost, { ...o, rows: mk(high) });
    uHost.insertAdjacentHTML("beforeend", `<h4 class="adv-h4">Lowest</h4>`);
    barList(uHost, { ...o, rows: mk(low) });
  }
  drawU();

  el.insertAdjacentHTML("beforeend", sourcesHtml(data, ["eurostat_gdp", "eurostat_hhinc", "eurostat_silc", "eurostat_lfs"], [
    "Income, poverty and unemployment are published for NUTS 2 regions: every NUTS 3 region inside one shares its value.",
    "GDP is counted where people work and income where they live, so the ratio swings in commuter belts and capitals.",
    "Money is in current euros, not adjusted for price levels (see the PPS lenses for that).",
  ]));

  return {
    onMapHover(h) {
      const l = lv();
      const r = h.cell >= 0 ? l.rowAtCell(h.cell) : null;
      scatter.setHot(r ? r.key : null);
      affTable.setHot(r ? r.key : null);
      if (povHist && counties) {
        const c = h.cell >= 0 ? counties.rowAtCell(h.cell) : null;
        povHist.setHot(c ? povHist.binOf(c.v.poverty)?.i ?? null : null);
      }
    },
    onEscape() {
      if (scatter.selected) { clearSel(); return true; }
      return false;
    },
  };
}
