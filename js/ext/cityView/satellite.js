// City View's Satellite section: the city's latest clear Sentinel-2 true-colour image, read in the browser from the
// public AWS Open Data copies (Element84 Earth Search, no account), with an optional before/after swipe against a
// summer of an earlier year. The same approach as Vresto Lite (github.com/kalfasyan/vresto, web/stac.js and cog.js):
// search the STAC catalogue, then fetch only the bytes of the COG overview that covers the crop.
import { esc } from "../../format.js";
import { icon } from "../../ui/icon.js";
import { vrestoUrl } from "../../app/geo.js";

const STAC = "https://earth-search.aws.element84.com/v1/search";
const COLLECTION = "sentinel-2-c1-l2a";
const GEOTIFF_JS = "https://cdn.jsdelivr.net/npm/geotiff@3.0.5/dist-browser/geotiff.js";
const PX = 512; // canvas size (square)
const SPANS = [15, 30, 60]; // crop widths, km
const FIRST_YEAR = 2017; // the first full year with both Sentinel-2 satellites
const MAX_CLOUD = 15;
const ATTRIBUTION = "Contains modified Copernicus Sentinel data, via Element84 Earth Search (AWS Open Data).";

// --- geometry ------------------------------------------------------------------------------------------------------

// WGS84 -> UTM (transverse Mercator, Krüger series to n^3: well under a metre within a zone and its neighbours).
const WA = 6378137, WF = 1 / 298.257223563, N_ = WF / (2 - WF);
const AA = (WA / (1 + N_)) * (1 + N_ ** 2 / 4 + N_ ** 4 / 64);
const ALPHA = [N_ / 2 - (2 * N_ ** 2) / 3 + (5 * N_ ** 3) / 16, (13 * N_ ** 2) / 48 - (3 * N_ ** 3) / 5, (61 * N_ ** 3) / 240];
const K2 = (2 * Math.sqrt(N_)) / (1 + N_);
export function utmForward(lon, lat, epsg) {
  const zone = epsg % 100, south = Math.floor(epsg / 100) === 327;
  const phi = (lat * Math.PI) / 180, dl = ((lon - (zone * 6 - 183)) * Math.PI) / 180;
  const s = Math.sin(phi);
  const t = Math.sinh(Math.atanh(s) - K2 * Math.atanh(K2 * s));
  const xi = Math.atan(t / Math.cos(dl)), eta = Math.atanh(Math.sin(dl) / Math.sqrt(1 + t * t));
  let E = eta, N = xi;
  ALPHA.forEach((a, j) => {
    const k = 2 * (j + 1);
    E += a * Math.cos(k * xi) * Math.sinh(k * eta);
    N += a * Math.sin(k * xi) * Math.cosh(k * eta);
  });
  return [500000 + 0.9996 * AA * E, (south ? 10000000 : 0) + 0.9996 * AA * N];
}

function inRing(ring, [x, y]) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}
function inGeom(geom, p) {
  const polys = geom?.type === "Polygon" ? [geom.coordinates] : geom?.type === "MultiPolygon" ? geom.coordinates : [];
  return polys.some((rings) => inRing(rings[0], p) && !rings.slice(1).some((h) => inRing(h, p)));
}
// A 5 x 5 lattice over the crop in lon/lat (approximate: the crop is a square in UTM).
function cropPoints([lon, lat], km) {
  const dLat = km / 2 / 111.32, dLon = dLat / Math.cos((lat * Math.PI) / 180);
  const out = [];
  for (let a = -1; a <= 1; a += 0.5) for (let b = -1; b <= 1; b += 0.5) out.push([lon + a * dLon, lat + b * dLat]);
  return out;
}

// --- catalogue -----------------------------------------------------------------------------------------------------

const https = (h) => (typeof h !== "string" ? null : h.startsWith("s3://")
  ? `https://${h.slice(5).split("/")[0]}.s3.amazonaws.com/${h.slice(5).split("/").slice(1).join("/")}` : h.startsWith("https://") ? h : null);

function toScene(item) {
  const p = item.properties || {};
  const href = https(item.assets?.visual?.href);
  const epsg = p["proj:epsg"] ?? Number(String(p["proj:code"] || "").split(":")[1]);
  if (!href || !epsg) return null;
  return {
    id: item.id, date: (p.datetime || "").slice(0, 10), cloud: p["eo:cloud_cover"] ?? 0, epsg, href, geometry: item.geometry,
    platform: p.platform || item.id.slice(0, 3),
  };
}

/**
 * One satellite pass over the crop: the MGRS tiles of the same date and satellite. The crop is often wider than the
 * 10 km overlap between tiles, so a pass is drawn as a mosaic of its tiles. cloud = its cloudiest tile.
 */
function passes(scenes, pts) {
  const by = new Map();
  for (const s of scenes) {
    const k = `${s.date}|${s.platform}`;
    if (!by.has(k)) by.set(k, []);
    by.get(k).push(s);
  }
  const out = [];
  for (const tiles of by.values()) {
    if (!pts.every((p) => tiles.some((t) => inGeom(t.geometry, p)))) continue;
    // Tiles in the crop's own UTM zone first: tiles of a neighbouring zone are only drawn where those left gaps.
    const centre = pts[Math.floor(pts.length / 2)];
    tiles.sort((a, b) => inGeom(b.geometry, centre) - inGeom(a.geometry, centre));
    out.push({ date: tiles[0].date, tiles, cloud: Math.max(...tiles.map((t) => t.cloud)), epsg: tiles[0].epsg });
  }
  return out;
}

const searches = new Map(); // key -> Promise<passes>
/** Passes whose tiles cover a `km` crop around lonlat, newest first (or least cloudy first with byCloud). */
export function findPasses(lonlat, km, from, to, { byCloud = false, signal } = {}) {
  const key = `${lonlat.map((v) => v.toFixed(3))}|${km}|${from}|${to}|${byCloud}`;
  if (!searches.has(key)) {
    const pts = cropPoints(lonlat, km);
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    const bbox = [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)].map((v) => +v.toFixed(5));
    const body = {
      collections: [COLLECTION],
      bbox,
      datetime: `${from}T00:00:00Z/${to}T23:59:59Z`,
      query: { "eo:cloud_cover": { lte: MAX_CLOUD } },
      limit: 200,
      sortby: [{ field: "properties.datetime", direction: "desc" }],
    };
    const p = fetch(STAC, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal })
      .then((r) => { if (!r.ok) throw new Error(`search failed (${r.status})`); return r.json(); })
      .then((page) => {
        const list = passes((page.features || []).map(toScene).filter(Boolean), pts);
        list.sort(byCloud ? (a, b) => a.cloud - b.cloud : (a, b) => b.date.localeCompare(a.date));
        return list;
      });
    p.catch(() => searches.delete(key));
    searches.set(key, p);
  }
  return searches.get(key);
}

// --- imagery -------------------------------------------------------------------------------------------------------

let geotiffLib = null;
function loadGeoTIFF() {
  if (window.GeoTIFF) return Promise.resolve(window.GeoTIFF);
  geotiffLib ??= new Promise((ok, fail) => {
    const s = document.createElement("script");
    s.src = GEOTIFF_JS;
    s.crossOrigin = "anonymous";
    s.onload = () => (window.GeoTIFF ? ok(window.GeoTIFF) : fail(new Error("geotiff.js did not load")));
    s.onerror = () => { geotiffLib = null; fail(new Error("geotiff.js did not load")); };
    document.head.appendChild(s);
  });
  return geotiffLib;
}

const cogs = new Map();
function openCog(href) {
  if (!cogs.has(href)) {
    const p = loadGeoTIFF().then(async (G) => {
      const tiff = await G.fromUrl(href, { allowFullFile: false });
      const n = await tiff.getImageCount();
      const images = await Promise.all([...Array(n).keys()].map((i) => tiff.getImage(i)));
      const base = images[0];
      const [ox, oy] = base.getOrigin();
      const res0 = base.getResolution()[0];
      // Overviews carry no georeferencing of their own: derive their pixel size from the full image.
      const levels = images.map((image) => ({ image, res: (res0 * base.getWidth()) / image.getWidth() })).sort((a, b) => a.res - b.res);
      return { levels, ox, oy };
    });
    p.catch(() => cogs.delete(href));
    cogs.set(href, p);
  }
  return cogs.get(href);
}

/**
 * Draws one tile's part of a `km`-wide square around lonlat onto ctx (PX x PX). The square is laid out in the tile's
 * own UTM zone, so a tile of a neighbouring zone is turned by a degree or two against the others: close enough for
 * the strip it fills.
 */
async function drawTile(ctx, scene, lonlat, km, signal) {
  const cog = await openCog(scene.href);
  const [E, N] = utmForward(lonlat[0], lonlat[1], scene.epsg);
  const half = (km * 1000) / 2;
  const wanted = (2 * half) / PX;
  let level = cog.levels[0];
  for (const l of cog.levels) if (l.res <= wanted * 1.01) level = l; // the coarsest overview still as sharp as the canvas
  const { image, res } = level;
  const fx0 = (E - half - cog.ox) / res, fy0 = (cog.oy - (N + half)) / res, span = (2 * half) / res;
  const x0 = Math.max(0, Math.floor(fx0)), y0 = Math.max(0, Math.floor(fy0));
  const x1 = Math.min(image.getWidth(), Math.ceil(fx0 + span)), y1 = Math.min(image.getHeight(), Math.ceil(fy0 + span));
  if (x1 <= x0 || y1 <= y0) return;
  const k = PX / span; // canvas px per source px
  const ow = Math.max(1, Math.round((x1 - x0) * k)), oh = Math.max(1, Math.round((y1 - y0) * k));
  const data = await image.readRasters({ window: [x0, y0, x1, y1], width: ow, height: oh, samples: [0, 1, 2], interleave: true, signal });
  if (signal?.aborted) return;
  const rgba = new Uint8ClampedArray(ow * oh * 4);
  for (let i = 0, j = 0; i < ow * oh; i++, j += 3) {
    const r = data[j], g = data[j + 1], b = data[j + 2];
    if (r === 0 && g === 0 && b === 0) continue; // the no-data collar
    rgba[i * 4] = r; rgba[i * 4 + 1] = g; rgba[i * 4 + 2] = b; rgba[i * 4 + 3] = 255;
  }
  const tmp = document.createElement("canvas");
  tmp.width = ow; tmp.height = oh;
  tmp.getContext("2d").putImageData(new ImageData(rgba, ow, oh), 0, 0);
  ctx.drawImage(tmp, Math.round((x0 - fx0) * k), Math.round((y0 - fy0) * k));
}

/** Draws a pass (its tiles mosaicked) onto ctx. Returns the share of the crop that had data. */
export async function drawPass(ctx, pass, lonlat, km, signal) {
  // Fetch all tiles at once, then draw in order (destination-over: earlier tiles win where they overlap).
  const off = pass.tiles.map(() => { const c = document.createElement("canvas"); c.width = c.height = PX; return c; });
  await Promise.all(pass.tiles.map((t, i) => drawTile(off[i].getContext("2d"), t, lonlat, km, signal)));
  if (signal?.aborted) return 0;
  ctx.clearRect(0, 0, PX, PX);
  ctx.save();
  ctx.globalCompositeOperation = "destination-over";
  for (const c of off) ctx.drawImage(c, 0, 0);
  ctx.restore();
  const a = ctx.getImageData(0, 0, PX, PX).data;
  let valid = 0;
  for (let i = 3; i < a.length; i += 4) if (a[i]) valid++;
  return valid / (PX * PX);
}

// --- section -------------------------------------------------------------------------------------------------------

const fmtDate = (d) => new Date(`${d}T12:00:00Z`).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
const isoDay = (d) => d.toISOString().slice(0, 10);

/**
 * Default crop width: 15 km for a metro of one hex, else 30 km. Wider crops are a button away: they need more tiles
 * from one pass, so fewer passes cover them.
 */
export function defaultSpan(m) {
  const b = m.bbox;
  const ext = b ? Math.max(b.x1 - b.x0, b.y1 - b.y0) : 0;
  return ext > 25 ? 30 : 15;
}

export function satelliteHtml(m) {
  if (!m.lonlat) return `<p class="muted cv-note">Satellite view needs the map's projection, which this data build does not carry.</p>`;
  const now = new Date().getUTCFullYear();
  const years = [];
  for (let y = now - 1; y >= FIRST_YEAR; y--) years.push(y);
  const span = defaultSpan(m);
  return `
    <div class="cv-sat-bar">
      <div class="cv-seg" role="group" aria-label="Width of the image">${SPANS.map((s) =>
        `<button type="button" data-span="${s}" aria-pressed="${s === span}">${s} km</button>`).join("")}</div>
      <label class="cv-sat-cmp">Compare with <select data-year aria-label="Compare with a summer of an earlier year">
        <option value="">—</option>${years.map((y) => `<option value="${y}">summer ${y}</option>`).join("")}</select></label>
    </div>
    <div class="cv-sat" data-sat style="--cut:50%">
      <canvas width="${PX}" height="${PX}" data-now aria-label="Latest clear Sentinel-2 image of ${esc(m.city.name)}" role="img"></canvas>
      <canvas width="${PX}" height="${PX}" data-then hidden aria-hidden="true"></canvas>
      <div class="cv-sat-cut" hidden aria-hidden="true"><span data-then-label></span><span data-now-label></span></div>
      <input type="range" min="0" max="100" value="50" data-cut hidden aria-label="Swipe between the two dates">
      <div class="cv-sat-msg" data-msg>Waiting to load…</div>
    </div>
    <div class="cv-sat-meta">
      <button type="button" class="cv-sat-step" data-step="1" aria-label="Older image" title="Older image">‹</button>
      <span data-caption>Sentinel-2</span>
      <button type="button" class="cv-sat-step" data-step="-1" aria-label="Newer image" title="Newer image">›</button>
    </div>
    <p class="cv-note">The newest Sentinel-2 image of the last year with under ${MAX_CLOUD}% cloud over its 110 km tiles (a city can
      still sit under one of those clouds: step back with ‹). Read in your browser from AWS Open Data, nothing is stored.
      ${ATTRIBUTION} <a href="${esc(vrestoUrl(m.lonlat, { zoom: 11 }))}" target="_blank" rel="noopener" data-vresto>Explore in Vresto Lite ›</a></p>`;
}

/** Wires the section once it is in the dock. Loads nothing until the section scrolls into view. */
export function mountSatellite(host, m) {
  if (!m.lonlat) return;
  const q = (s) => host.querySelector(s);
  const now = q("[data-now]"), then = q("[data-then]"), msg = q("[data-msg]"), caption = q("[data-caption]");
  const cut = q("[data-cut]"), cutBar = q(".cv-sat-cut"), sat = q("[data-sat]");
  const st = { span: defaultSpan(m), list: [], k: 0, year: "", ctl: null, started: false };

  const say = (t) => { msg.textContent = t; msg.hidden = !t; };
  const nextCtl = () => { st.ctl?.abort(); st.ctl = new AbortController(); return st.ctl.signal; };

  async function drawNow(signal) {
    // Step past scenes whose crop is mostly no-data (the tile's footprint test is approximate at its edges).
    while (st.k < st.list.length) {
      const s = st.list[st.k];
      say("Loading image…");
      const share = await drawPass(now.getContext("2d"), s, m.lonlat, st.span, signal);
      if (signal.aborted) return;
      if (share >= 0.85) {
        caption.textContent = `Sentinel-2 · ${fmtDate(s.date)} · ${Math.round(s.cloud)}% cloud on the tile${s.tiles.length > 1 ? "s" : ""}`;
        q("[data-now-label]").textContent = fmtDate(s.date);
        say("");
        return;
      }
      st.list.splice(st.k, 1);
    }
    now.getContext("2d").clearRect(0, 0, PX, PX);
    caption.textContent = "Sentinel-2";
    say("No clear image found for this view.");
  }

  async function drawThen(signal) {
    const on = !!st.year;
    then.hidden = cut.hidden = cutBar.hidden = !on;
    sat.classList.toggle("comparing", on);
    if (!on) return;
    const list = await findPasses(m.lonlat, st.span, `${st.year}-05-15`, `${st.year}-09-15`, { byCloud: true, signal });
    for (const s of list.slice(0, 4)) {
      const share = await drawPass(then.getContext("2d"), s, m.lonlat, st.span, signal);
      if (signal.aborted) return;
      if (share >= 0.85) { q("[data-then-label]").textContent = fmtDate(s.date); return; }
    }
    then.getContext("2d").clearRect(0, 0, PX, PX);
    q("[data-then-label]").textContent = `no clear image in summer ${st.year}`;
  }

  async function load({ search = true } = {}) {
    const signal = nextCtl();
    try {
      if (search) {
        say("Searching Sentinel-2…");
        const to = new Date(), from = new Date(to.getTime() - 365 * 864e5);
        st.list = (await findPasses(m.lonlat, st.span, isoDay(from), isoDay(to), { signal })).slice();
        st.k = 0;
      }
      if (signal.aborted) return;
      await Promise.all([drawNow(signal), drawThen(signal)]);
    } catch (err) {
      if (signal.aborted || err?.name === "AbortError") return;
      say(`Satellite image not available: ${err.message || err}`);
    }
    updateSteps();
  }

  function updateSteps() {
    host.querySelector('[data-step="1"]').disabled = st.k >= st.list.length - 1;
    host.querySelector('[data-step="-1"]').disabled = st.k <= 0;
  }

  host.querySelectorAll("[data-span]").forEach((b) => (b.onclick = () => {
    st.span = +b.dataset.span;
    host.querySelectorAll("[data-span]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    if (st.started) load();
  }));
  q("[data-year]").onchange = (e) => {
    st.year = e.target.value;
    if (!st.started) return;
    const signal = nextCtl();
    drawThen(signal).catch(() => {});
    drawNow(signal).catch(() => {});
  };
  host.querySelectorAll("[data-step]").forEach((b) => (b.onclick = () => {
    const k = st.k + +b.dataset.step;
    if (k < 0 || k >= st.list.length) return;
    st.k = k;
    const signal = nextCtl();
    drawNow(signal).then(updateSteps, () => {});
  }));
  cut.oninput = () => sat.style.setProperty("--cut", `${cut.value}%`);
  updateSteps();

  const start = () => { if (!st.started) { st.started = true; load(); } };
  if (typeof IntersectionObserver === "function") {
    const io = new IntersectionObserver((es) => {
      if (es.some((e) => e.isIntersecting)) { io.disconnect(); start(); }
    }, { rootMargin: "200px" });
    io.observe(sat);
  } else start();
}

export const SAT_ICON = () => icon("search", "🛰", { size: 15 });
