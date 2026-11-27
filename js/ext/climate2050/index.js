// 2050 dial: pushes the Hot days and Tropical nights lenses from today to 2050 along one of two emissions paths, and
// names each region's "climate twin": the place whose climate today is closest to that region's climate in 2050.
// Appears above the legend for the climate lenses, like the time dial does for the history lenses.
//
// Data: data/climate.json (pipeline/build_climate.py), loaded the first time a climate lens is picked. Values come per
// NUTS 2 region (climate.unit_of maps each NUTS 3 region to one); the dial swaps in a lens object with the same id and
// that year's values. Hover or tap a region to see its twin; an arc on the map joins the two.
// URL: #lens=hot_days&future=2050b (a = if emissions fall, RCP4.5; b = if they don't, RCP8.5).
import { esc } from "../../format.js";

const CSS_HREF = new URL("../../../css/climate.css", import.meta.url).href;
const STEP_MS = 420;
const CLIM = {
  hot_days: { key: "hot", what: "hot days", thr: 30, thrLabel: "30+ hot days a year" },
  tropical_nights: { key: "trop", what: "tropical nights", thr: 20, thrLabel: "20+ tropical nights a year" },
};
const PATHS = [
  { id: "s45", code: "a", label: "If emissions fall", title: "RCP4.5: emissions peak around 2040, then fall" },
  { id: "s85", code: "b", label: "If they don't", title: "RCP8.5: emissions keep rising through the century" },
];

function injectCss() {
  if (document.querySelector(`link[href="${CSS_HREF}"]`)) return;
  const l = document.createElement("link");
  l.rel = "stylesheet";
  l.href = CSS_HREF;
  document.head.appendChild(l);
}

const round = (v) => (v == null ? "–" : v < 9.95 ? v.toFixed(1).replace(/\.0$/, "") : String(Math.round(v)));
const millions = (v) => (v >= 1e6 ? `${(v / 1e6).toFixed(v >= 1e8 ? 0 : 1).replace(/\.0$/, "")}M` : `${Math.round(v / 1000)}k`);

export function install(app) {
  injectCss();
  const raw = app.w.raw;
  const grid = app.w.grid;
  const nCells = grid.size;
  const nReg = raw.counties.length;
  const cellsOf = Array.from({ length: nReg }, () => []);
  raw.county.forEach((r, i) => { if (r >= 0) cellsOf[r].push(i); });
  const cxOf = new Float64Array(nReg), cyOf = new Float64Array(nReg);
  cellsOf.forEach((cs, r) => {
    if (!cs.length) return;
    let x = 0, y = 0;
    for (const c of cs) { x += grid.cx(c); y += grid.cy(c); }
    cxOf[r] = x / cs.length; cyOf[r] = y / cs.length;
  });
  // A region's everyday name: the city it belongs to, else the region.
  const cityOfRegion = new Map();
  for (const c of [...(app.data.cities || [])].sort((a, b) => a.population - b.population)) {
    for (const g of c.counties || []) cityOfRegion.set(g, c);
  }
  const regionLabel = (r) => cityOfRegion.get(raw.counties[r].geoid)?.name || raw.counties[r].name;

  let C = null, pop = null, unitRegions = null, unitRep = null, loading = null;
  const st = { open: false, year: 2050, path: "s85", base: null, playing: 0, own: false, focus: null, pinned: false };

  // --- DOM ------------------------------------------------------------------------------------------------------
  const el = document.createElement("div");
  el.id = "climate-dial";
  el.className = "panel time-dial cd-dial";
  el.hidden = true;
  el.setAttribute("role", "group");
  el.setAttribute("aria-label", "2050 dial");
  const area = document.getElementById("lens-area");
  area.insertBefore(el, document.getElementById("legend"));

  const pill = document.createElement("button");
  pill.type = "button";
  pill.className = "td-pill cd-pill";
  pill.hidden = true;
  pill.title = "Push this lens forward to 2050";
  area.insertBefore(pill, el);
  pill.addEventListener("click", () => openDial());

  el.innerHTML = `
    <div class="cd-twin" aria-live="polite"></div>
    <div class="td-row">
      <button type="button" class="td-play" aria-label="Play">▶</button>
      <div class="td-turn"><b></b> AD</div>
      <div class="td-track cd-track">
        <input type="range" class="td-range" role="slider" aria-label="Year" min="2025" max="2050" step="1">
        <div class="td-ticks"><span style="left:0%">2025</span><span style="left:20%">2030</span><span style="left:60%">2040</span><span style="left:100%">2050</span></div>
      </div>
      <button type="button" class="icon-btn td-close" aria-label="Close the 2050 dial" title="Back to today's climate (1991–2020)">✕</button>
    </div>
    <div class="td-row td-row2">
      <div class="td-seg" role="group" aria-label="Emissions path">
        ${PATHS.map((p) => `<button type="button" data-path="${p.id}" title="${esc(p.title)}" aria-pressed="false">${esc(p.label)}</button>`).join("")}
      </div>
      <span class="td-src muted">Copernicus ECDE · EURO-CORDEX models</span>
    </div>
    <p class="cd-stat"></p>`;
  const $ = (s) => el.querySelector(s);
  const range = $(".td-range"), playBtn = $(".td-play"), turnEl = $(".td-turn b"), twinEl = $(".cd-twin"), statEl = $(".cd-stat");

  // --- data -----------------------------------------------------------------------------------------------------
  function load() {
    if (C) return Promise.resolve(C);
    if (!loading) {
      loading = Promise.all([app.loadData("climate"), app.data.counties ? app.data.counties : app.loadCounties()]).then(([c, cnt]) => {
        if (!c) throw new Error("climate.json missing");
        C = c;
        const cols = cnt?.columns || [];
        const kp = cols.indexOf("population"), kc = cols.indexOf("cell");
        pop = (cnt?.rows || []).map((r) => (kp >= 0 ? r[kp] || 0 : 0));
        // regions smaller than a hex own no cell: place them at their listed cell
        (cnt?.rows || []).forEach((row, r) => {
          const c = kc >= 0 ? row[kc] : null;
          if (!cellsOf[r].length && Number.isInteger(c) && c >= 0) { cellsOf[r].push(c); cxOf[r] = grid.cx(c); cyOf[r] = grid.cy(c); }
        });
        unitRegions = C.units.map(() => []);
        C.unit_of.forEach((u, r) => { if (u >= 0) unitRegions[u].push(r); });
        // each unit is drawn at its most populous region
        unitRep = unitRegions.map((rs) => rs.slice().sort((a, b) => pop[b] - pop[a])[0] ?? null);
        return C;
      });
    }
    return loading;
  }

  const spec = () => CLIM[st.base?.id];
  const yi = () => st.year - C.years[0];
  const valU = (key, u, q = "mid", path = st.path, y = st.year) => C.path[key][path][q][u]?.[y - C.years[0]] ?? null;

  function buildLens() {
    const s = spec(), base = st.base;
    const values = new Array(nCells).fill(null);
    for (let i = 0; i < nCells; i++) {
      const r = raw.county[i];
      if (r < 0) continue;
      const u = C.unit_of[r];
      if (u >= 0) values[i] = valU(s.key, u);
    }
    const p = PATHS.find((x) => x.id === st.path);
    return {
      ...base, name: `${base.name} · ${st.year}`, note: null, values,
      unit: `${base.unit}, ${st.year} (${p.label.toLowerCase()})`,
      description: `${C.notes.path} ${p.title}.`,
      climateDial: { year: st.year, path: st.path },
    };
  }

  // --- twin card and arc ----------------------------------------------------------------------------------------
  function defaultFocus() {
    const sel = app.state.selectedCity;
    const g = sel?.counties?.[0];
    const r = g ? raw.counties.findIndex((c) => c.geoid === g) : raw.counties.findIndex((c) => c.geoid === "FR101");
    return r >= 0 ? r : 0;
  }

  function renderTwin() {
    const r = st.focus;
    const u = r != null ? C.unit_of[r] : -1;
    if (u < 0) { twinEl.innerHTML = `<p class="muted">No climate data for this region.</p>`; arc.twin = null; return; }
    const tw = C.twin[st.path][u];
    const k = spec().key, other = k === "hot" ? "trop" : "hot";
    const otherWhat = other === "hot" ? "hot days" : "tropical nights";
    const now = C.base[k][u], then = valU(k, u, "mid", st.path, 2050), lo = valU(k, u, "lo", st.path, 2050), hi = valU(k, u, "hi", st.path, 2050);
    const oNow = C.base[other][u], oThen = valU(other, u, "mid", st.path, 2050);
    const tj0 = C.base.tjja[u], tj1 = C.f2050[st.path].tjja[u];
    const name = regionLabel(r);
    let head;
    if (tw) {
      const [tu, d] = tw;
      const tr = unitRep[tu];
      const tname = C.unit_name[tu] || (tr != null ? regionLabel(tr) : C.units[tu]);
      head = d > 0.8
        ? `<b>${esc(name)}</b> in 2050 has no close match in Europe today. The nearest is <button type="button" class="td-geo" data-r="${tr}">${esc(tname)}</button>.`
        : `<b>${esc(name)}</b> in 2050 feels like <button type="button" class="td-geo" data-r="${tr}">${esc(tname)}</button> today.`;
      arc.from = r; arc.twin = tr; arc.twinName = tname;
    } else {
      head = `<b>${esc(name)}</b>`;
      arc.twin = null;
    }
    const ratio = (a, b) => (a >= 1 && b / a >= 1.5 ? ` <span class="cd-x">×${(b / a).toFixed(1)}</span>` : "");
    twinEl.innerHTML = `<p class="cd-head">${head}</p>
      <p class="cd-nums"><span>${esc(spec().what[0].toUpperCase() + spec().what.slice(1))} <b>${round(now)} → ${round(then)}</b>${ratio(now, then)} <span class="muted">(${round(lo)}–${round(hi)})</span></span>
      <span>${otherWhat[0].toUpperCase() + otherWhat.slice(1)} <b>${round(oNow)} → ${round(oThen)}</b></span>
      <span>Summer <b>${tj0.toFixed(1)} → ${tj1.toFixed(1)} °C</b></span></p>
      <p class="muted cd-hint">1991–2020 → 2050, ${esc(PATHS.find((p) => p.id === st.path).label.toLowerCase())}. ${st.pinned ? "Tap another region to compare." : "Hover or tap a region to see its twin."}</p>`;
  }

  function renderStat() {
    const s = spec();
    let a = 0, b = 0, tot = 0;
    for (let r = 0; r < nReg; r++) {
      const u = C.unit_of[r];
      if (u < 0) continue;
      tot += pop[r];
      if (C.base[s.key][u] >= s.thr) a += pop[r];
      if (valU(s.key, u) >= s.thr) b += pop[r];
    }
    statEl.innerHTML = `People in places with ${esc(s.thrLabel)}: <b>${millions(a)}</b> in 1991–2020, <b>${millions(b)}</b> in ${st.year} <span class="muted">(of ${millions(tot)})</span>`;
  }

  const arc = { id: "climate-twin", z: 55, space: "screen", from: null, twin: null, draw(ctx) {
    if (!st.open || arc.twin == null || arc.from == null) return;
    const cam = app.cam;
    const [x0, y0] = cam.toScreen(cxOf[arc.from], cyOf[arc.from]);
    const [x1, y1] = cam.toScreen(cxOf[arc.twin], cyOf[arc.twin]);
    const mx = (x0 + x1) / 2, my = (y0 + y1) / 2, dx = x1 - x0, dy = y1 - y0;
    const len = Math.hypot(dx, dy) || 1;
    const bend = Math.min(160, len * 0.3);
    const s = dx >= 0 ? -1 : 1; // bend the arc upwards
    const qx = mx - (dy / len) * bend * s, qy = my + (dx / len) * bend * s;
    ctx.save();
    ctx.lineCap = "round";
    ctx.setLineDash([6, 6]);
    ctx.lineWidth = 4; ctx.strokeStyle = "rgba(10,8,4,.6)";
    ctx.beginPath(); ctx.moveTo(x0, y0); ctx.quadraticCurveTo(qx, qy, x1, y1); ctx.stroke();
    ctx.lineWidth = 2; ctx.strokeStyle = "#f0b25a";
    ctx.beginPath(); ctx.moveTo(x0, y0); ctx.quadraticCurveTo(qx, qy, x1, y1); ctx.stroke();
    ctx.setLineDash([]);
    for (const [x, y, fill] of [[x0, y0, "#1b2838"], [x1, y1, "#f0b25a"]]) {
      ctx.beginPath(); ctx.arc(x, y, 7, 0, 7); ctx.fillStyle = "rgba(10,8,4,.7)"; ctx.fill();
      ctx.beginPath(); ctx.arc(x, y, 5, 0, 7); ctx.fillStyle = fill; ctx.fill();
      ctx.lineWidth = 2; ctx.strokeStyle = "#f0b25a"; ctx.stroke();
    }
    ctx.font = "600 12px Palatino, Georgia, serif";
    ctx.textBaseline = "middle";
    const lbl = (x, y, t) => {
      const w = ctx.measureText(t).width;
      const left = x + 12 + w > cam.w - 8;
      const tx = left ? x - 12 - w : x + 12;
      ctx.fillStyle = "rgba(10,8,4,.75)"; ctx.fillRect(tx - 4, y - 9, w + 8, 18);
      ctx.fillStyle = "#f3e3bd"; ctx.fillText(t, tx, y + 0.5);
    };
    lbl(x0, y0, `${regionLabel(arc.from)}, 2050`);
    lbl(x1, y1, `${arc.twinName || regionLabel(arc.twin)}, today`);
    ctx.restore();
  } };
  app.registerOverlay(arc);

  // --- apply ----------------------------------------------------------------------------------------------------
  function apply() {
    if (!st.open || !C || !spec()) return;
    const lens = buildLens();
    st.own = true;
    try { app.setLens(lens); } finally { st.own = false; }
    app.invalidate();
    turnEl.textContent = st.year;
    range.value = st.year;
    range.setAttribute("aria-valuetext", `${st.year}, ${PATHS.find((p) => p.id === st.path).label}`);
    el.querySelectorAll(".td-seg button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.path === st.path)));
    renderTwin();
    renderStat();
    app.hash.update();
  }

  function setYear(y) {
    st.year = Math.max(C.years[0], Math.min(C.years.at(-1), y));
    apply();
  }
  function stop() {
    clearInterval(st.playing);
    st.playing = 0;
    playBtn.textContent = "▶";
    playBtn.setAttribute("aria-label", "Play");
  }
  function play() {
    if (st.playing) return stop();
    if (st.year >= C.years.at(-1)) setYear(C.years[0]);
    playBtn.textContent = "❚❚";
    playBtn.setAttribute("aria-label", "Pause");
    st.playing = setInterval(() => {
      if (st.year >= C.years.at(-1)) return stop();
      setYear(st.year + 1);
    }, STEP_MS);
  }

  function flyTo(r) {
    const cells = cellsOf[r];
    if (!cells?.length) return;
    const h = { cells: new Set(cells), color: "#f0b25a" };
    app.setHighlight(h);
    const b = app.highlightBounds(h);
    if (b) app.fitBounds(b.x0 - 160, b.y0 - 160, b.x1 + 160, b.y1 + 160, { maxScale: 2.5 });
  }
  twinEl.addEventListener("click", (e) => {
    const b = e.target.closest(".td-geo");
    if (b) flyTo(+b.dataset.r);
  });

  // --- open / close ---------------------------------------------------------------------------------------------
  async function openDial({ year = null, path = null } = {}) {
    const base = st.base || (app.state.lens && CLIM[app.state.lens.id] ? app.lensById.get(app.state.lens.id) : null);
    if (!base) return;
    st.base = base;
    try { await load(); } catch (err) {
      console.warn("2050 dial:", err);
      pill.hidden = true;
      return;
    }
    if (!st.base) return;
    st.open = true;
    if (path) st.path = path;
    st.year = year != null ? Math.max(C.years[0], Math.min(C.years.at(-1), year)) : C.years.at(-1);
    if (st.focus == null) st.focus = defaultFocus();
    el.hidden = false;
    pill.hidden = true;
    apply();
  }

  function closeDial({ restore = true } = {}) {
    stop();
    const base = st.base;
    st.open = false;
    el.hidden = true;
    arc.twin = null;
    app.setHighlight(null);
    if (restore && base) {
      st.own = true;
      try { app.setLens(base); } finally { st.own = false; }
      app.invalidate();
    }
    updatePill();
    app.hash.update();
  }

  function updatePill() {
    const lens = app.state.lens;
    const ok = !!(lens && CLIM[lens.id]);
    st.base = ok ? app.lensById.get(lens.id) : null;
    pill.hidden = !ok || st.open;
    if (ok) pill.innerHTML = `<span aria-hidden="true">🔭</span> Push ${esc(st.base.name)} to 2050 <span class="muted">and find your climate twin</span>`;
  }

  app.on("lens", (lens) => {
    if (st.own) return;
    if (st.open) {
      if (lens && CLIM[lens.id]) {
        st.base = app.lensById.get(lens.id);
        stop();
        apply();
        return;
      }
      closeDial({ restore: false });
    }
    updatePill();
  });
  app.on("hover", (h) => {
    if (!st.open || st.pinned || !C || h.cell == null || h.cell < 0) return;
    const r = raw.county[h.cell];
    if (r < 0 || r === st.focus) return;
    st.focus = r;
    renderTwin();
    app.requestDraw();
  });
  app.on("mapclick", (ev) => {
    if (!st.open || !C) return false;
    const r = ev.cell >= 0 ? raw.county[ev.cell] : -1;
    if (r < 0) return false;
    st.focus = r;
    st.pinned = true;
    renderTwin();
    app.requestDraw();
    return false; // let the map select the place as usual
  });

  playBtn.addEventListener("click", play);
  range.addEventListener("input", () => { stop(); setYear(+range.value); });
  $(".td-close").addEventListener("click", () => closeDial());
  el.querySelectorAll(".td-seg button").forEach((b) => b.addEventListener("click", () => { st.path = b.dataset.path; apply(); }));

  app.hash.register("future", {
    get: () => (st.open ? `${st.year}${PATHS.find((p) => p.id === st.path).code}` : null),
    set(v) {
      if (!v) { if (st.open) closeDial(); return; }
      const m = /^(\d{4})([ab]?)$/.exec(v);
      if (!m) return;
      updatePill();
      openDial({ year: +m[1], path: m[2] === "a" ? "s45" : m[2] === "b" ? "s85" : null });
    },
  });

  updatePill();
  app.climate2050 = { open: openDial, close: closeDial, play, setYear, state: st, load, twinOf: (r) => (C ? C.twin[st.path][C.unit_of[r]] : null) };
}
