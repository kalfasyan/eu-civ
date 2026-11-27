// The Almanac: what every number means and exactly where it comes from.
import { resolveTables } from "../terrain.js";
import { esc } from "../format.js";
import { parseHex, luminance } from "../color.js";
import { icon, glyph } from "./icon.js";

const COVER_ICON = { forest_deciduous: "l-forest", forest_evergreen: "l-forest", forest_mixed: "l-forest", cropland: "l-farmland", pasture: "l-farmland", urban: "l-developed" };
// Glyph colour that reads on a resource medallion (dark on light faces such as nuclear yellow or silver).
const inkOn = (hex) => {
  try { return /^#[0-9a-f]{6}$/i.test(hex || "") && luminance(parseHex(hex)) > 0.4 ? "#1c1710" : "#f8f0d8"; } catch { return "#f8f0d8"; }
};
const CATEGORY = { energy: "Energy", mineral: "Minerals", agri: "Agriculture" };

export function initPedia(data) {
  const modal = document.getElementById("pedia");
  const card = modal.querySelector(".modal-card");
  const nav = document.getElementById("pedia-nav");
  const body = document.getElementById("pedia-body");
  const srcName = (id) => data.sources?.find((s) => s.id === id)?.title || id || "";
  let restoreFocus = null;

  const h2 = (ic, fb, text) => `<h2>${icon(ic, fb, { size: 24 })}<span>${esc(text)}</span></h2>`;

  const pages = {
    "About this map": () => `
      ${h2("pedia", "📖", "About this map")}
      <p>This is the real Europe, drawn like a strategy game. Nothing is invented: every tile, city and
      number comes from public data (mostly Eurostat; the ONS for the UK), listed under <i>Sources</i>.</p>
      <h4>How it's built</h4>
      <p>The 27 EU member states, plus every other country Eurostat maps by region (the United Kingdom, Switzerland, Norway, Iceland,
      Liechtenstein, Türkiye, Serbia, North Macedonia, Montenegro and Albania), are projected (ETRS89 Lambert azimuthal equal-area, EPSG:3035) and cut into ${data.world.grid.cols}×${data.world.grid.rows}
      hexes, each ${data.world.grid.radius * 2} km corner to corner. Each hex belongs to the country and NUTS 3 region that most of its sample points
      (one every 4 km) fall in. Terrain comes from elevation and ESA WorldCover land-cover samples inside each hex. The outermost regions
      (Canary Islands, Azores, Madeira, the French overseas departments), Ceuta and Melilla, and Svalbard and Jan Mayen are left off, like the original left off Alaska and Hawaii.</p>
      <p><b>Cities</b> are Eurostat's metropolitan regions (agglomerations of 250,000+ people built from NUTS 3 regions), placed at their principal city.
      Their numbers cover the whole metro region, not just the city proper. Where Eurostat defines no metro regions (Türkiye, the Western Balkans, Iceland,
      Liechtenstein), a city is placed at each place of 250,000+ people and at the capital. Leuven and Edessa are added as towns. These single-place
      cities show the municipality's own population (jobs and GDP are their region's, scaled by population share), except in Türkiye,
      where a metropolitan municipality covers its whole province.
      <b>Regions</b> are the ${data.world.counties.length.toLocaleString("en")} NUTS 3 regions (the map's "counties"); the UK's are its NUTS 2021 (ITL 2021) regions.</p>
      <h4>Time, climate and the future</h4>
      <p>Lenses with history (Population, GDP vs EU average, Unemployment, Farm and Factory jobs) have a <b>time dial</b> that
      replays Eurostat's yearly series from 2000 to the latest year, on today's borders. The <b>Climate</b> lenses (Hot days,
      Tropical nights) show the 1991–2020 ERA5 average per NUTS 2 region and have a <b>2050 dial</b>. The dial uses the
      EURO-CORDEX ensemble median for RCP4.5 ("if emissions fall") or RCP8.5 ("if they don't"), as 21-year means shifted
      onto ERA5, with the 17th to 83rd percentile of the models as the range (Copernicus European Climate Data Explorer
      v2.0). A <b>climate twin</b> is the region whose 1991–2020 climate is closest to a region's 2050 climate, at least
      300 km away. <b>Low-lying land</b> is land at or below 5 m near the sea. Dykes and storm surges are not modelled,
      so it shows exposure, not a flood forecast.</p>
      <p>For sources and versions, resolution, uncertainty, known gaps, licences, citing and rebuilding the data, see the
      <a href="https://github.com/kalfasyan/eu-civ/blob/main/docs/FAQ.md" target="_blank" rel="noopener">researcher FAQ</a>.</p>
      <h4>Credits</h4>
      <p>The map engine, art and interface are from Andrej Karpathy's <a href="https://karpathy.ai/usaciv/" target="_blank" rel="noopener">usaciv</a>
      (MIT licence, via the poro/usaciv fork). This European edition swaps in a new data pipeline built from European sources.</p>
      <h4>Controls</h4>
      <p>Drag or arrow keys / WASD to pan · scroll, +/– or double-click to zoom · click a city or a country to open it ·
      / or ⌘K to search · L to cycle lenses · R to show or hide resources · ? for all shortcuts · Esc to close.</p>
      <p>The address bar always holds a link to what you're looking at (lens, selection and view); use <i>Share</i> to copy it
      or to download a picture.</p>`,
    Yields: () => `
      ${h2("y-production", "⚙️", "Yields")}
      <p>Civilization's yields mapped onto real measures. Job-based yields count people <i>employed</i> in an industry group,
      where they work (Eurostat regional accounts; BRES for the UK; estimated from value added where a country publishes no regional jobs). <b>Gold is GDP</b>: output per year in euros, counted where the work is done.</p>
      <table>${data.nation.yields.map((y) => `<tr><td class="ic" style="color:${esc(y.color)}">${glyph(y, 26)}</td><td><b style="color:${esc(y.color)}">${esc(y.label)}${y.key === "gold" ? " (GDP)" : ""}</b><br>${esc(y.description)}</td></tr>`).join("")}</table>
      <h4>Amenities</h4>
      <p>Unemployment is the Labour Force Survey rate for ages 15–74; income is net disposable household income per person. Both are
      published for NUTS 2 regions and weighted by population for metros.</p>`,
    States: () => `
      ${h2("terrain", "🗺️", "Countries")}
      <p>Click any land hex without a city to open its country. A country's numbers are the sums of its NUTS 3 regions on the map
      (${esc(data.nation.vintage)}${data.nation.gdp_vintage ? `; GDP from ${esc(data.nation.gdp_vintage)}` : ""}),
      not the sum of its cities, so rural areas count too.</p>
      <p><b>Ranks</b> ("#3 of ${data.world.states.length}") compare all ${data.world.states.length} countries on the map; 1 is the largest.</p>`,
    Terrain: () => {
      const t = data.w?.tables || resolveTables(data.world.tables);
      const hasCover = Array.isArray(data.world.cover);
      const row = (x) => `<tr><td class="nm">${x.color ? `<span class="swatch" style="background:${esc(x.color)}"></span>` : ""}${
        COVER_ICON[x.key] ? icon(COVER_ICON[x.key], "", { size: 15 }) + " " : ""}<b>${esc(x.name)}</b></td><td>${esc(x.rule || "")}</td></tr>`;
      return `
      ${h2("terrain", "🗺️", "Terrain")}
      <p>Each hex averages the elevation samples inside it (AWS Terrain Tiles, zoom 7). Relief comes from the mean elevation and roughness
      (standard deviation) of those samples; shading comes from elevation differences with neighbouring hexes, lit from the
      north-west.</p>
      <h4>${icon("l-forest", "🌲", { size: 16 })} Land cover</h4>
      ${hasCover
        ? `<p>The base colour of each hex is its dominant land-cover group: the largest group among the land samples inside it.
           Small symbols show the mix: trees scale with the forest share, and fields, reeds, shrubs and grass tufts mark farmland,
           wetland, scrub and grassland.</p>
           <table>${t.cover.filter((x) => x.id > 0).map(row).join("")}</table>`
        : `<p class="muted">This data build has no land-cover layer yet; land is coloured by elevation.</p>`}
      <h4>Relief</h4>
      <table>${t.relief.map(row).join("")}</table>
      <h4>${icon("r-hydro", "💧", { size: 16 })} Water</h4>
      <table>${t.water.filter((x) => x.id > 0).map(row).join("")}</table>
      <h4>Beyond the borders</h4>
      <p class="muted">Land outside the map's countries is drawn for context only and not mapped in detail.</p>`;
    },
    Lenses: () => `
      ${h2("layers", "▤", "Lenses")}
      <p>Lenses recolour the map by one measure (${esc(data.lenses.vintage)}). Each hex is sampled every 4 km. Most lenses
      take a mean over the NUTS 3 regions those samples fall in, weighted by sample count and population density, so a hex
      shared by a city and farmland leans towards the city. Indicators published for NUTS 2 regions (unemployment, income,
      life expectancy, R&amp;D and others) give the same value to every NUTS 3 region inside them. The Climate lenses are
      per NUTS 2 region: each hex shows the value of its own NUTS 3 region's NUTS 2 unit, with no blending across borders.</p>
      <p>The legend shows how many hexes fall at each value. Hover or drag on it to show only that range on the map.</p>
      ${(data.lenses.groups || [{ id: null, name: "" }]).map((g) => {
        const ls = data.lenses.lenses.filter((l) => !g.id || l.group === g.id);
        if (!ls.length) return "";
        return `${g.name ? `<h3 class="grp">${icon(`g-${g.id}`, "", { size: 16 })} ${esc(g.name)}</h3>` : ""}${ls.map((l) => `
          <div class="lens-entry"><div class="le-ic">${glyph(l, 26)}</div><div>
          <h4>${esc(l.name)}</h4><p>${esc(l.description)}<br>
          <i class="le-ramp" style="background:linear-gradient(90deg, ${(l.ramp || []).map(esc).join(",")})"></i>
          <span class="muted">Scale: ${esc(l.scale)}, ${l.domain[0].toLocaleString()}–${l.domain[1].toLocaleString()} ${esc(l.unit)}${
            l.higher_is === "good" ? " · higher is better" : l.higher_is === "bad" ? " · higher is worse" : ""}${l.source ? " · " + esc(srcName(l.source)) : ""}</span></p></div></div>`).join("")}`;
      }).join("")}`,
    Resources: () => {
      const r = data.resources;
      if (!r?.types?.length) return `${h2("resources", "⛏️", "Resources")}<p class="muted">This data build has no resources layer.</p>`;
      const count = new Map();
      for (const it of r.items || []) count.set(it.type, (count.get(it.type) || 0) + 1);
      const cats = [...new Set(r.types.map((t) => t.category || "other"))];
      return `
      ${h2("resources", "⛏️", "Resources")}
      <p>Resources mark the country's biggest power plants, mines and oil &amp; gas fields on the tiles where they are.
      Only meaningful sites are shown: each type's threshold is in its description. When zoomed out, a hex shows its
      highest-ranked resource; zoom in to see more. Press <b>R</b> to show or hide them.</p>
      ${cats.map((c) => `<h4>${esc(CATEGORY[c] || c)}</h4><table class="res-table">
        <tr><th></th><th>Type</th><th>What counts</th><th>Sites</th></tr>
        ${r.types.filter((t) => (t.category || "other") === c).map((t) => `<tr>
          <td class="ic"><span class="res-ic" style="background:${esc(t.color || "#24384f")};color:${inkOn(t.color)}">${glyph(t, 20)}</span></td>
          <td class="nm"><b>${esc(t.name)}</b>${t.unit ? `<br><span class="muted">value in ${esc(t.unit)}</span>` : ""}</td>
          <td>${esc(t.description || "")}<br><span class="muted">Source: ${esc(srcName(t.source))}</span></td>
          <td class="num">${count.get(t.id) || 0}</td></tr>`).join("")}</table>`).join("")}`;
    },
    Sources: () => `
      ${h2("pedia", "📖", "Sources")}
      ${data.sources.map((s) => `
        <h4>${esc(s.title)}</h4>
        <p>${esc(s.description)}<br>
        <span class="muted">${esc(s.publisher)} · ${esc(s.license)}${s.vintage ? " · " + esc(s.vintage) : ""} ·
        <a href="${esc(s.homepage)}" target="_blank" rel="noopener">homepage</a></span></p>
        <table>${(s.files || []).map((f) => `<tr><td><code>${esc(f.url)}</code></td><td class="muted" style="white-space:nowrap">${esc((f.retrieved || "").slice(0, 10))}<br>${((f.bytes || 0) / 1e6).toFixed(1)} MB</td></tr>`).join("")}</table>`).join("")}`,
  };

  const show = (name) => {
    if (!pages[name]) name = "About this map";
    body.innerHTML = pages[name]();
    body.scrollTop = 0;
    nav.querySelectorAll("button").forEach((b) => {
      const on = b.dataset.page === name;
      b.classList.toggle("active", on);
      b.setAttribute("aria-current", on ? "page" : "false");
    });
  };
  nav.innerHTML = `<div class="hd">Almanac</div>` + Object.keys(pages).map((p) => `<button data-page="${esc(p)}">${esc(p)}</button>`).join("");
  nav.onclick = (e) => {
    const b = e.target.closest("button[data-page]");
    if (b) show(b.dataset.page);
  };
  const close = () => {
    if (modal.hidden) return;
    modal.hidden = true;
    if (restoreFocus && document.contains(restoreFocus)) restoreFocus.focus();
    restoreFocus = null;
  };
  modal.onclick = (e) => {
    if (e.target === modal || e.target.closest("[data-close]")) close();
  };
  // Keep Tab inside the dialog.
  modal.addEventListener("keydown", (e) => {
    if (e.key !== "Tab") return;
    const f = [...card.querySelectorAll("button, a[href], [tabindex]:not([tabindex='-1'])")].filter((x) => x.offsetParent);
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });

  return {
    open(page = "About this map") {
      if (modal.hidden) restoreFocus = document.activeElement;
      show(page);
      modal.hidden = false;
      (nav.querySelector("button.active") || card.querySelector("[data-close]"))?.focus();
    },
    close,
    get isOpen() {
      return !modal.hidden;
    },
  };
}
