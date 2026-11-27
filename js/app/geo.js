// Map km <-> lon/lat. The map is ETRS89 Lambert azimuthal equal-area (EPSG:3035), shifted so its top-left corner is
// (0, 0) with y down (pipeline/common.py Proj). world.json carries that shift in `projection`; builds from before it
// did fall back to the shift of the shipped grid when the grid matches.

// The shipped grid (pipeline/build_world.py: NUTS 2024 + UK NUTS 2021 bounds, margin 150 km, 145 x 146 hexes of 20 km).
const SHIPPED = { min_x: 2637.848, max_y: 5411.124, margin: 150, grid: [20, 145, 146] };

// GRS80 and the EPSG:3035 parameters.
const A = 6378137, F = 1 / 298.257222101, E2 = F * (2 - F), E = Math.sqrt(E2);
const LAT0 = (52 * Math.PI) / 180, LON0 = 10, FE = 4321000, FN = 3210000;
const qOf = (s) => (1 - E2) * (s / (1 - E2 * s * s) - (1 / (2 * E)) * Math.log((1 - E * s) / (1 + E * s)));
const QP = qOf(1), Q0 = qOf(Math.sin(LAT0));
const B0 = Math.asin(Q0 / QP), RQ = A * Math.sqrt(QP / 2);
const D = (A * Math.cos(LAT0)) / Math.sqrt(1 - E2 * Math.sin(LAT0) ** 2) / (RQ * Math.cos(B0));
const E4 = E2 * E2, E6 = E4 * E2;

/** EPSG:3035 metres -> [lon, lat] in degrees (EPSG guidance note 7-2, method 9820). */
export function laeaInverse(X, Y) {
  const dx = X - FE, dy = Y - FN;
  const rho = Math.hypot(dx / D, D * dy);
  if (rho < 1e-9) return [LON0, (LAT0 * 180) / Math.PI];
  const C = 2 * Math.asin(rho / (2 * RQ));
  const beta = Math.asin(Math.cos(C) * Math.sin(B0) + (D * dy * Math.sin(C) * Math.cos(B0)) / rho);
  const lon = LON0 + (Math.atan2(dx * Math.sin(C), D * rho * Math.cos(B0) * Math.cos(C) - D * D * dy * Math.sin(B0) * Math.sin(C)) * 180) / Math.PI;
  const lat = beta
    + (E2 / 3 + (31 * E4) / 180 + (517 * E6) / 5040) * Math.sin(2 * beta)
    + ((23 * E4) / 360 + (251 * E6) / 3780) * Math.sin(4 * beta)
    + ((761 * E6) / 45360) * Math.sin(6 * beta);
  return [lon, (lat * 180) / Math.PI];
}

/** The world's projection shift {min_x, max_y, margin} (km), or null when it is not known. */
export function projectionOf(w) {
  const raw = w?.raw || w;
  if (raw?.projection && Number.isFinite(raw.projection.min_x)) return raw.projection;
  const g = raw?.grid;
  const [r, c, n] = SHIPPED.grid;
  return g && raw.margin === SHIPPED.margin && g.radius === r && g.cols === c && g.rows === n ? SHIPPED : null;
}

/** Map km (x right, y down) -> [lon, lat], or null when the world's projection is unknown. */
export function toLonLat(w, x, y) {
  const p = projectionOf(w);
  if (!p) return null;
  return laeaInverse((x + p.min_x - p.margin) * 1000, (p.max_y + p.margin - y) * 1000);
}

// Vresto Lite: Sentinel-2 search and true-colour streaming in the browser (github.com/kalfasyan/vresto, web/).
export const VRESTO_LITE = "https://vresto-yannis20.vercel.app/";

/** A Vresto Lite link that opens at lon/lat with the last `days` of imagery (its ?ll=lat,lon&z=&from=&to= state). */
export function vrestoUrl([lon, lat], { zoom = 11, days = 60, cloud = 20 } = {}) {
  const day = (d) => d.toISOString().slice(0, 10);
  const now = new Date();
  const q = new URLSearchParams({
    ll: `${lat.toFixed(4)},${lon.toFixed(4)}`, z: String(zoom),
    from: day(new Date(now.getTime() - days * 864e5)), to: day(now), cloud: String(cloud),
  });
  return `${VRESTO_LITE}?${String(q).replace(/%2C/g, ",")}`;
}
