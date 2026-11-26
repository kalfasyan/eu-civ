// Time dial: replays a lens year by year (2000 to the latest year) with a turn counter, a play button, a level /
// change-since-start switch and "story beats" that name the biggest movers. Appears above the legend whenever the active
// lens has history (Population, GDP vs EU average, Unemployment, Farm jobs, Factory jobs).
//
// Data: data/history.json (pipeline/build_history.py), loaded the first time a timed lens is picked. Hex values come
// from each hex's NUTS 3 region (world.county); the dial swaps in a lens object with the same id and that year's values,
// so the legend, tooltip, minimap and URL all keep working. URL: #lens=gdp_index&year=2008 (or year=2008c for change).
import { esc } from "../../format.js";

const CSS_HREF = new URL("../../../css/timedial.css", import.meta.url).href;
const STEP_MS = 650;

// lens id -> how to build its yearly values
const TIMED = {
  density: { key: "pop", src: "Eurostat demo_r_pjanaggr3 · UK: ONS", kind: "density", change: { rel: true, label: "population change", fmt: "pct", dom: [-0.3, 0.3], good: "neutral" } },
  gdp_index: { key: "gdp_idx", src: "Eurostat nama_10r_3gdp, NUTS 3", kind: "value", change: { rel: false, label: "change in points of the EU average", fmt: "int", dom: [-60, 60], good: "good" } },
  unemployment: { key: "unemp", src: "Eurostat LFS, NUTS 2", kind: "value", change: { rel: false, label: "change in percentage points", fmt: "pct", dom: [-0.12, 0.12], good: "bad" } },
  farm_jobs: { key: "farm", src: "Eurostat nama_10r_3empers, NUTS 3", kind: "value", change: { rel: false, label: "change in share of jobs, points", fmt: "pct", dom: [-0.1, 0.1], good: "neutral" } },
  factory_jobs: { key: "factory", src: "Eurostat nama_10r_3empers, NUTS 3", kind: "value", change: { rel: false, label: "change in share of jobs, points", fmt: "pct", dom: [-0.08, 0.08], good: "neutral" } },
};
const DIVERGE = ["#8c2d3c", "#c4594b", "#e7c6a0", "#c6d8c2", "#5fae9a", "#1f6b6b"];

function injectCss() {
  if (document.querySelector(`link[href="${CSS_HREF}"]`)) return;
  const l = document.createElement("link");
  l.rel = "stylesheet";
  l.href = CSS_HREF;
  document.head.appendChild(l);
}

export function install(app) {
  injectCss();
  const raw = app.w.raw;
  const grid = app.w.grid;
  const nCells = grid.size;
  const regionCells = new Map(); // region index -> cell list (for beats: fly there)
  raw.county.forEach((r, i) => {
    if (r < 0) return;
    if (!regionCells.has(r)) regionCells.set(r, []);
    regionCells.get(r).push(i);
  });
  let landKm2 = null; // region index -> land area, from counties.json (density)

  let H = null; // history.json
  let regionIndex = null; // geoid -> index into H.regions
  let loading = null;
  const st = { open: false, year: null, mode: "level", base: null, playing: 0, own: false };

  // --- DOM ------------------------------------------------------------------------------------------------------
  const el = document.createElement("div");
  el.id = "time-dial";
  el.className = "panel time-dial";
  el.hidden = true;
  el.setAttribute("role", "group");
  el.setAttribute("aria-label", "Time dial");
  const area = document.getElementById("lens-area");
  area.insertBefore(el, document.getElementById("legend"));

  const pill = document.createElement("button");
  pill.type = "button";
  pill.className = "td-pill";
  pill.hidden = true;
  pill.title = "Replay this lens year by year";
  area.insertBefore(pill, el);
  pill.addEventListener("click", () => openDial());

  el.innerHTML = `
    <div class="td-beat" aria-live="polite"></div>
    <div class="td-row">
      <button type="button" class="td-play" aria-label="Play">▶</button>
      <div class="td-turn"><b></b> AD</div>
      <div class="td-track">
        <input type="range" class="td-range" role="slider" aria-label="Year" step="1">
        <div class="td-ticks"></div>
      </div>
      <button type="button" class="icon-btn td-close" aria-label="Close the time dial" title="Back to the latest data">✕</button>
    </div>
    <div class="td-row td-row2">
      <div class="td-seg" role="group" aria-label="Colour by">
        <button type="button" data-mode="level" aria-pressed="true">Level</button>
        <button type="button" data-mode="change" aria-pressed="false">Change since <span class="td-y0"></span></button>
      </div>
      <span class="td-src muted"></span>
    </div>`;
  const $ = (s) => el.querySelector(s);
  const range = $(".td-range"), playBtn = $(".td-play"), turnEl = $(".td-turn b"), beatEl = $(".td-beat");

  // --- data -----------------------------------------------------------------------------------------------------
  function load() {
    if (H) return Promise.resolve(H);
    if (!loading) {
      loading = Promise.all([app.loadData("history"), app.data.counties ? app.data.counties : app.loadCounties()]).then(([h, c]) => {
        if (!h) throw new Error("history.json missing");
        H = h;
        regionIndex = new Map(h.regions.map((g, i) => [g, i]));
        const cols = c?.columns || [];
        const ka = cols.indexOf("land_km2");
        landKm2 = (c?.rows || []).map((r) => (ka >= 0 ? r[ka] : null));
        return H;
      });
    }
    return loading;
  }

  const spec = () => TIMED[st.base?.id];
  const span = () => H.range[spec().key];
  const NY = () => H.years.length;
  const val = (key, r, y) => (y < H.years[0] || y > H.years.at(-1) ? null : H.series[key][r * NY() + (y - H.years[0])]);
  // A region's value in year y; density = population / land area.
  function regionVal(r, y) {
    const s = spec();
    const v = val(s.key, r, y);
    if (v == null) return null;
    if (s.kind === "density") return landKm2[r] ? v / landKm2[r] : null;
    return v;
  }
  // The first year in range with data for this region (the "change since" base).
  function firstYear(r) {
    const [a, b] = span();
    for (let y = a; y <= b; y++) if (val(spec().key, r, y) != null) return y;
    return null;
  }

  function buildLens() {
    const s = spec(), base = st.base, y = st.year;
    const values = new Array(nCells).fill(null);
    if (st.mode === "level") {
      // Population keeps the base lens's hex detail: scale each hex by its region's population in y vs the latest year.
      const latestY = span()[1];
      for (let i = 0; i < nCells; i++) {
        const r = raw.county[i];
        if (r < 0) continue;
        if (s.kind === "density") {
          const p1 = val(s.key, r, y), pL = val(s.key, r, latestY);
          values[i] = p1 == null ? null : base.values[i] != null && pL ? base.values[i] * (p1 / pL) : regionVal(r, y);
        } else values[i] = regionVal(r, y);
      }
      return { ...base, name: `${base.name} · ${y}`, note: null, values, timeDial: { year: y, mode: "level" } };
    }
    const y0 = span()[0];
    for (let i = 0; i < nCells; i++) {
      const r = raw.county[i];
      if (r < 0) continue;
      const fy = firstYear(r);
      if (fy == null || fy > y) continue;
      const a = val(s.key, r, fy), b = val(s.key, r, y);
      if (a == null || b == null) continue;
      values[i] = s.change.rel ? (a ? b / a - 1 : null) : b - a;
    }
    const ramp = s.change.good === "bad" ? [...DIVERGE].reverse() : [...DIVERGE]; // teal = the good direction
    return {
      ...base, name: `${base.name}: change ${y0}–${y}`, values, format: s.change.fmt, scale: "linear", domain: s.change.dom, ramp,
      unit: s.change.label, higher_is: s.change.good, note: null,
      description: `Change from ${y0} (or a region's first year with data) to ${y}. ${base.description || ""}`,
      timeDial: { year: y, mode: "change" },
    };
  }

  // --- apply ----------------------------------------------------------------------------------------------------
  function apply() {
    if (!st.open || !H || !spec()) return;
    const lens = buildLens();
    st.own = true;
    try {
      app.setLens(lens);
    } finally {
      st.own = false;
    }
    app.invalidate(); // same lens id, new colours: drop the cached map
    turnEl.textContent = st.year;
    range.value = st.year;
    range.setAttribute("aria-valuetext", String(st.year));
    renderBeat();
    app.hash.update();
  }

  function setYear(y) {
    const [a, b] = span();
    st.year = Math.max(a, Math.min(b, y));
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
    const [a, b] = span();
    if (st.year >= b) setYear(a);
    playBtn.textContent = "❚❚";
    playBtn.setAttribute("aria-label", "Pause");
    st.playing = setInterval(() => {
      if (st.year >= span()[1]) return stop();
      setYear(st.year + 1);
    }, STEP_MS);
  }

  function renderChrome() {
    const [a, b] = span();
    range.min = a;
    range.max = b;
    $(".td-y0").textContent = a;
    const ticks = [];
    for (let y = a; y <= b; y++) if (y === a || y === b || y % 5 === 0) ticks.push(`<span style="left:${((y - a) / Math.max(1, b - a)) * 100}%">${y}</span>`);
    $(".td-ticks").innerHTML = ticks.join("");
    el.querySelectorAll(".td-seg button").forEach((bt) => bt.setAttribute("aria-pressed", String(bt.dataset.mode === st.mode)));
    $(".td-src").textContent = spec().src;
  }

  function regionName(g) {
    const r = raw.counties[regionIndex.get(g)];
    const c = r ? raw.states[raw.owner[regionCells.get(regionIndex.get(g))?.[0]]] : null;
    return r ? `${r.name}${c ? ` (${c.fips || ""})` : ""}`.replace(" ()", "") : g;
  }
  function fmt(v) {
    const s = spec();
    if (v == null) return "–";
    if (s.key === "pop") return v >= 1e6 ? (v / 1e6).toFixed(2) + "M" : Math.round(v / 1000) + "k";
    if (s.key === "gdp_idx") return String(Math.round(v));
    return (v * 100).toFixed(1) + "%";
  }
  function delta(a, b) {
    const s = spec();
    if (s.key === "pop") { const d = (b / a - 1) * 100; return (d >= 0 ? "+" : "−") + Math.abs(d).toFixed(0) + "%"; }
    if (s.key === "gdp_idx") { const d = b - a; return (d >= 0 ? "+" : "−") + Math.abs(Math.round(d)) + " pts"; }
    const d = (b - a) * 100;
    return (d >= 0 ? "+" : "−") + Math.abs(d).toFixed(1) + " pts";
  }

  function renderBeat() {
    const s = spec();
    const [a] = span();
    const note = (H.notes || []).find((n) => n.series === s.key && n.year === st.year);
    const mv = H.beats?.[s.key]?.[String(st.year)];
    let html = "";
    if (note) {
      html += `<p class="td-note">${note.geo ? `<button type="button" class="td-geo" data-geo="${esc(note.geo)}">${esc(regionName(note.geo))}</button> · ` : ""}${esc(note.text)}</p>`;
    }
    if (st.year === a) {
      html += `<p class="muted">Turn one. Press play to watch every region move, or switch to <i>Change</i> to colour by how far each one moved.</p>`;
    } else if (mv) {
      const [up, down] = mv;
      const line = (lbl, m) => `<div class="td-mv"><span class="muted">${lbl}</span> <button type="button" class="td-geo" data-geo="${esc(m[0])}">${esc(regionName(m[0]))}</button> <span class="td-num">${fmt(m[1])} → ${fmt(m[2])}</span> <b>${delta(m[1], m[2])}</b></div>`;
      html += line(`Biggest rise since ${a}`, up) + line(`Biggest fall`, down);
    }
    beatEl.innerHTML = html;
    beatEl.hidden = !html;
  }

  function flyToRegion(g) {
    const r = regionIndex.get(g);
    const cells = regionCells.get(r);
    if (!cells) return;
    const h = { cells: new Set(cells), color: "#ecd08e" };
    app.setHighlight(h);
    const b = app.highlightBounds(h);
    if (b) app.fitBounds(b.x0 - 120, b.y0 - 120, b.x1 + 120, b.y1 + 120, { maxScale: 3 });
  }
  beatEl.addEventListener("click", (e) => {
    const b = e.target.closest(".td-geo");
    if (b) flyToRegion(b.dataset.geo);
  });

  // --- open / close ---------------------------------------------------------------------------------------------
  async function openDial({ year = null, mode = null } = {}) {
    const base = st.base || (app.state.lens && TIMED[app.state.lens.id] ? app.lensById.get(app.state.lens.id) : null);
    if (!base) return;
    st.base = base;
    try {
      await load();
    } catch (err) {
      console.warn("time dial:", err);
      pill.hidden = true;
      return;
    }
    if (!st.base) return;
    st.open = true;
    if (mode) st.mode = mode;
    const [a, b] = span();
    st.year = year != null ? Math.max(a, Math.min(b, year)) : b;
    el.hidden = false;
    pill.hidden = true;
    renderChrome();
    apply();
  }

  function closeDial({ restore = true } = {}) {
    stop();
    const base = st.base;
    st.open = false;
    el.hidden = true;
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
    const ok = !!(lens && TIMED[lens.id]);
    st.base = ok ? app.lensById.get(lens.id) : null;
    pill.hidden = !ok || st.open;
    if (ok) pill.innerHTML = `<span aria-hidden="true">⏳</span> Replay ${esc(st.base.name)} <span class="muted">2000–today</span>`;
  }

  app.on("lens", (lens) => {
    if (st.own) return;
    // A lens picked by the user: keep the dial running on the new lens if it has history, else close it.
    if (st.open) {
      if (lens && TIMED[lens.id]) {
        st.base = app.lensById.get(lens.id);
        stop();
        renderChrome();
        setYear(st.year);
        return;
      }
      closeDial({ restore: false });
    }
    updatePill();
  });

  playBtn.addEventListener("click", play);
  range.addEventListener("input", () => { stop(); setYear(+range.value); });
  $(".td-close").addEventListener("click", () => closeDial());
  el.querySelectorAll(".td-seg button").forEach((bt) => bt.addEventListener("click", () => {
    st.mode = bt.dataset.mode;
    if (st.mode === "change" && st.year === span()[0]) st.year = span()[1];
    renderChrome();
    apply();
  }));
  el.addEventListener("keydown", (e) => {
    if (e.key === " " && e.target === el) { e.preventDefault(); play(); }
  });

  app.hash.register("year", {
    get: () => (st.open && st.year ? `${st.year}${st.mode === "change" ? "c" : ""}` : null),
    set(v) {
      if (!v) { if (st.open) closeDial(); return; }
      const m = /^(\d{4})(c?)$/.exec(v);
      if (!m) return;
      updatePill();
      openDial({ year: +m[1], mode: m[2] ? "change" : "level" });
    },
  });

  updatePill();
  app.timeDial = { open: openDial, close: closeDial, play, setYear, state: st, timed: Object.keys(TIMED) };
}
