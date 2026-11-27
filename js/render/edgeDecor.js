// Edge decor: the "here be monsters" margin of the map. Hand-drawn clouds drift through the sea mist beyond the
// world's edges, and a few sea creatures (serpents, a kraken, a whale) surface in the open ocean near the edges, in
// the spirit of an old engraved chart.
//
// It draws on its own transparent canvas over the map (createEdgeDecor), so animating it never re-renders or
// re-blits the map: each tick clears the rectangles it drew last time and blits a handful of cached sprites.
// It only ticks while something is on screen, the tab is visible and the user has not asked for reduced motion,
// and the tick rate follows how fast things move on screen at the current zoom (slow drift → few frames).
//
// Placement is deterministic (hashed), in world km, so the creatures stay put between visits.
import { WATER_LAKE } from "./art/water.js";

const TAU = Math.PI * 2;
const INK = "rgba(28,34,44,0.78)";

// ---- tiny helpers ------------------------------------------------------------------------------------------------

/** Deterministic 0..1 hash of two integers. */
function hash01(a, b) {
  let h = Math.imul(a | 0, 374761393) ^ Math.imul(b | 0, 668265263);
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

function rng(seed) {
  let a = (seed | 0) + 0x6d2b79f5;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function newCanvas(w, h) {
  const cv = document.createElement("canvas");
  cv.width = Math.max(1, Math.ceil(w));
  cv.height = Math.max(1, Math.ceil(h));
  return cv;
}

// ---- sprites -----------------------------------------------------------------------------------------------------
// Each sprite is painted at a base size in css px (BASE_*) times a power-of-two device scale, and blitted scaled down
// to its on-screen size. Painted once per (kind, variant, bucket).

const BASE = { cloud: [220, 104], serpent: [180, 96], kraken: [150, 100], whale: [170, 100] };
const WATERLINE = { serpent: 0.78, kraken: 0.8, whale: 0.74 }; // share of the sprite height where the sea is
const sprites = new Map();

function sprite(kind, variant, devPerCss) {
  const bucket = 2 ** Math.max(-1, Math.min(2, Math.ceil(Math.log2(devPerCss)))); // 0.5 .. 4 device px per css px
  const key = `${kind}|${variant}|${bucket}`;
  let sp = sprites.get(key);
  if (sp) return sp;
  const [bw, bh] = BASE[kind];
  const cv = newCanvas(bw * bucket, bh * bucket);
  const g = cv.getContext("2d");
  g.scale(bucket, bucket);
  g.lineCap = "round";
  g.lineJoin = "round";
  PAINT[kind](g, bw, bh, variant);
  sp = { canvas: cv, w: bw, h: bh };
  sprites.set(key, sp);
  return sp;
}

// A cloud in the engraved-chart manner: a flat-bottomed bank of round puffs with an ink outline, a cream body
// shading to a cool grey underside, a few inner curl lines, and a faint shadow on the mist below.
function paintCloud(g, W, H, variant) {
  const r = rng(1000 + variant * 77);
  const base = H * 0.74;
  const puffs = [];
  const n = 5 + Math.floor(r() * 3);
  for (let k = 0; k < n; k++) {
    const t = n === 1 ? 0.5 : k / (n - 1);
    const mid = 1 - Math.abs(t - 0.5) * 2; // 0 at the ends, 1 in the middle
    const rad = H * (0.17 + 0.2 * mid + 0.08 * r());
    const x = W * (0.13 + 0.74 * t) + (r() - 0.5) * W * 0.04;
    const y = base - rad * (0.55 + 0.35 * r());
    puffs.push([x, y, rad]);
  }
  // a second, higher row of puffs over the middle
  const m = 1 + Math.floor(r() * 2);
  for (let k = 0; k < m; k++) {
    const x = W * (0.36 + 0.28 * (m === 1 ? 0.5 : k / (m - 1))) + (r() - 0.5) * W * 0.06;
    const rad = H * (0.22 + 0.06 * r());
    puffs.push([x, base - H * 0.42 - rad * 0.2, rad]);
  }
  const x0 = Math.min(...puffs.map(([x, , rr]) => x - rr)), x1 = Math.max(...puffs.map(([x, , rr]) => x + rr));
  const shape = () => {
    g.beginPath();
    for (const [x, y, rr] of puffs) {
      g.moveTo(x + rr, y);
      g.arc(x, y, rr, 0, TAU);
    }
  };
  const clipAbove = (pad = 0) => {
    g.beginPath();
    g.rect(0, 0, W, base + pad);
    g.clip();
  };
  // shadow on the sea: a few nested flat ellipses, darkest in the middle (no blur filter: Safari has none)
  const scx = (x0 + x1) / 2 + W * 0.03, scy = base + H * 0.12, srx = (x1 - x0) * 0.5, sry = H * 0.09;
  for (let k = 0; k < 4; k++) {
    g.beginPath();
    g.ellipse(scx, scy, srx * (1 - k * 0.13), sry * (1 - k * 0.18), 0, 0, TAU);
    g.fillStyle = "rgba(4,14,28,0.07)";
    g.fill();
  }
  // ink outline (stroked wide, then the body covers its inner half), flat underside included
  g.save();
  clipAbove(1.2);
  shape();
  g.lineWidth = 3;
  g.strokeStyle = INK;
  g.stroke();
  g.restore();
  g.beginPath();
  g.moveTo(x0 + H * 0.06, base + 0.4);
  g.lineTo(x1 - H * 0.06, base + 0.4);
  g.lineWidth = 1.6;
  g.strokeStyle = INK;
  g.stroke();
  // body
  g.save();
  clipAbove();
  shape();
  g.clip();
  shape();
  const top = Math.min(...puffs.map(([, y, rr]) => y - rr));
  const grad = g.createLinearGradient(0, top, 0, base);
  grad.addColorStop(0, "#fbf5e4");
  grad.addColorStop(0.55, "#ece4cf");
  grad.addColorStop(1, "#b9c2c6");
  g.fillStyle = grad;
  g.fill();
  // inner curls: a short arc inside some puffs, upper left, like an engraver's contour line
  g.lineWidth = 1.1;
  g.strokeStyle = "rgba(92,98,104,0.45)";
  for (let k = 0; k < puffs.length; k++) {
    if (k % 2 && k !== puffs.length - 1) continue;
    const [x, y, rr] = puffs[k];
    g.beginPath();
    g.arc(x + rr * 0.12, y + rr * 0.12, rr * 0.72, Math.PI * 1.05, Math.PI * 1.55);
    g.stroke();
  }
  // soft underside band
  g.fillStyle = "rgba(120,134,146,0.22)";
  g.fillRect(0, base - H * 0.1, W, H * 0.1);
  g.restore();
}

// Shared bits for the creatures.
function inkStroke(g, path, width, colour) {
  g.lineWidth = width + 2.6;
  g.strokeStyle = INK;
  g.stroke(path);
  g.lineWidth = width;
  g.strokeStyle = colour;
  g.stroke(path);
}

function eye(g, x, y, r) {
  g.beginPath();
  g.arc(x, y, r, 0, TAU);
  g.fillStyle = "#fff8e0";
  g.fill();
  g.lineWidth = 1;
  g.strokeStyle = INK;
  g.stroke();
  g.beginPath();
  g.arc(x + r * 0.25, y, r * 0.5, 0, TAU);
  g.fillStyle = "#14161c";
  g.fill();
}

const SERPENTS = [
  { body: "#3f8f7a", belly: "#cfe3b4", stripe: "rgba(20,60,52,0.55)", fin: "#c0504a" }, // sea-green, red frills
  { body: "#a5523c", belly: "#f0d29a", stripe: "rgba(70,24,16,0.5)", fin: "#3e7f8f" }, // rust, teal frills
];

// A sea serpent: two coils arching out of the water and a neck rising to a frilled, horned head, facing right.
function paintSerpent(g, W, H, variant) {
  const c = SERPENTS[variant % SERPENTS.length];
  const wl = H * WATERLINE.serpent;
  const th = H * 0.13; // body thickness
  // coils (each an arch from the water and back)
  const coils = [[W * 0.16, W * 0.2, H * 0.34], [W * 0.43, W * 0.22, H * 0.42]];
  for (const [x, w, h] of coils) {
    const P = new Path2D();
    P.moveTo(x - w / 2, wl + th * 0.3);
    P.bezierCurveTo(x - w / 2, wl - h * 1.25, x + w / 2, wl - h * 1.25, x + w / 2, wl + th * 0.3);
    inkStroke(g, P, th, c.body);
    // belly highlight on the inner side of the arch, stripes across the back
    const B = new Path2D();
    B.moveTo(x - w / 2 + th * 0.3, wl);
    B.bezierCurveTo(x - w / 2 + th * 0.3, wl - h * 1.02, x + w / 2 - th * 0.3, wl - h * 1.02, x + w / 2 - th * 0.3, wl);
    g.lineWidth = th * 0.28;
    g.strokeStyle = c.belly;
    g.stroke(B);
    g.lineWidth = 1.4;
    g.strokeStyle = c.stripe;
    for (let k = 1; k < 5; k++) {
      const t = k / 5, u = 1 - t;
      const px = u * u * u * (x - w / 2) + 3 * u * u * t * (x - w / 2) + 3 * u * t * t * (x + w / 2) + t * t * t * (x + w / 2);
      const py = u * u * u * wl + 3 * u * u * t * (wl - h * 1.25) + 3 * u * t * t * (wl - h * 1.25) + t * t * t * wl;
      g.beginPath();
      g.moveTo(px - th * 0.12, py - th * 0.42);
      g.lineTo(px + th * 0.12, py + th * 0.1);
      g.stroke();
    }
    // dorsal spikes along the top of the arch
    g.fillStyle = c.fin;
    g.strokeStyle = INK;
    g.lineWidth = 1;
    for (let k = 1; k < 4; k++) {
      const t = 0.22 + k * 0.14, u = 1 - t;
      const px = u * u * u * (x - w / 2) + 3 * u * u * t * (x - w / 2) + 3 * u * t * t * (x + w / 2) + t * t * t * (x + w / 2);
      const py = u * u * u * wl + 3 * u * u * t * (wl - h * 1.25) + 3 * u * t * t * (wl - h * 1.25) + t * t * t * wl;
      g.beginPath();
      g.moveTo(px - th * 0.32, py - th * 0.42);
      g.lineTo(px + th * 0.05, py - th * 1.25);
      g.lineTo(px + th * 0.34, py - th * 0.4);
      g.closePath();
      g.fill();
      g.stroke();
    }
  }
  // tail tip flicking out of the water, left of the first coil
  const T = new Path2D();
  T.moveTo(W * 0.02, wl - H * 0.02);
  T.quadraticCurveTo(W * 0.0, wl - H * 0.2, W * 0.06, wl - H * 0.26);
  g.lineWidth = 1.2;
  inkStroke(g, T, th * 0.45, c.body);
  g.beginPath();
  g.moveTo(W * 0.06, wl - H * 0.26);
  g.lineTo(W * 0.015, wl - H * 0.37);
  g.lineTo(W * 0.075, wl - H * 0.33);
  g.lineTo(W * 0.11, wl - H * 0.4);
  g.closePath();
  g.fillStyle = c.fin;
  g.fill();
  g.lineWidth = 1;
  g.strokeStyle = INK;
  g.stroke();
  // neck: from the water up to the head
  const hx = W * 0.8, hy = H * 0.2;
  const N = new Path2D();
  N.moveTo(W * 0.64, wl + th * 0.3);
  N.bezierCurveTo(W * 0.66, wl - H * 0.3, W * 0.84, wl - H * 0.18, hx - W * 0.03, hy + H * 0.08);
  inkStroke(g, N, th * 1.05, c.body);
  const NB = new Path2D();
  NB.moveTo(W * 0.655 + th * 0.35, wl);
  NB.bezierCurveTo(W * 0.68 + th * 0.3, wl - H * 0.26, W * 0.82, wl - H * 0.16, hx - W * 0.04, hy + H * 0.14);
  g.lineWidth = th * 0.3;
  g.strokeStyle = c.belly;
  g.stroke(NB);
  // frill behind the head
  g.beginPath();
  g.moveTo(hx - W * 0.06, hy + H * 0.12);
  g.lineTo(hx - W * 0.13, hy - H * 0.02);
  g.lineTo(hx - W * 0.075, hy + H * 0.0);
  g.lineTo(hx - W * 0.1, hy - H * 0.13);
  g.lineTo(hx - W * 0.035, hy - H * 0.06);
  g.lineTo(hx - W * 0.03, hy - H * 0.16);
  g.lineTo(hx + W * 0.01, hy - H * 0.04);
  g.closePath();
  g.fillStyle = c.fin;
  g.fill();
  g.lineWidth = 1.1;
  g.strokeStyle = INK;
  g.stroke();
  // head: a long snout with an open jaw and a curled horn
  const Hd = new Path2D();
  Hd.moveTo(hx - W * 0.04, hy - H * 0.06);
  Hd.quadraticCurveTo(hx + W * 0.05, hy - H * 0.12, hx + W * 0.17, hy - H * 0.02); // brow to snout tip
  Hd.lineTo(hx + W * 0.09, hy + H * 0.035); // upper jaw back to the corner of the mouth
  Hd.lineTo(hx + W * 0.15, hy + H * 0.1); // lower jaw tip
  Hd.quadraticCurveTo(hx + W * 0.04, hy + H * 0.15, hx - W * 0.03, hy + H * 0.12);
  Hd.closePath();
  g.fillStyle = c.body;
  g.fill(Hd);
  g.lineWidth = 1.5;
  g.strokeStyle = INK;
  g.stroke(Hd);
  // mouth inside, a tooth, the nostril
  g.beginPath();
  g.moveTo(hx + W * 0.16, hy - H * 0.012);
  g.lineTo(hx + W * 0.09, hy + H * 0.035);
  g.lineTo(hx + W * 0.14, hy + H * 0.088);
  g.closePath();
  g.fillStyle = "#7a2228";
  g.fill();
  g.beginPath();
  g.moveTo(hx + W * 0.125, hy + H * 0.0);
  g.lineTo(hx + W * 0.13, hy + H * 0.03);
  g.lineTo(hx + W * 0.137, hy + H * 0.002);
  g.fillStyle = "#fff8e0";
  g.fill();
  g.beginPath();
  g.arc(hx + W * 0.145, hy - H * 0.045, 1.1, 0, TAU);
  g.fillStyle = INK;
  g.fill();
  const Hn = new Path2D();
  Hn.moveTo(hx + W * 0.0, hy - H * 0.09);
  Hn.quadraticCurveTo(hx - W * 0.01, hy - H * 0.25, hx + W * 0.05, hy - H * 0.24);
  g.lineWidth = 1;
  inkStroke(g, Hn, 2.4, "#efe2bf");
  eye(g, hx + W * 0.045, hy - H * 0.05, H * 0.035);
}

// A kraken: four tentacles curling out of the sea, suckers on their inner sides, and the top of its head.
function paintKraken(g, W, H) {
  const wl = H * WATERLINE.kraken;
  const body = "#8a3d63", light = "#e7b6c4";
  // the mantle, just breaking the surface
  const M = new Path2D();
  M.moveTo(W * 0.36, wl + 2);
  M.bezierCurveTo(W * 0.37, wl - H * 0.3, W * 0.63, wl - H * 0.3, W * 0.64, wl + 2);
  M.closePath();
  g.fillStyle = body;
  g.fill(M);
  g.lineWidth = 1.6;
  g.strokeStyle = INK;
  g.stroke(M);
  g.fillStyle = "rgba(255,220,235,0.25)";
  g.beginPath();
  g.ellipse(W * 0.46, wl - H * 0.15, W * 0.05, H * 0.04, -0.4, 0, TAU);
  g.fill();
  eye(g, W * 0.43, wl - H * 0.06, H * 0.035);
  eye(g, W * 0.57, wl - H * 0.06, H * 0.035);
  // tentacles: [base x, top x, top y, curl direction]
  const T = [[0.16, 0.05, 0.12, 1], [0.3, 0.26, 0.04, -1], [0.72, 0.76, 0.02, 1], [0.86, 0.95, 0.16, -1]];
  for (const [bx, tx, ty, dir] of T) {
    const x0 = W * bx, x1 = W * tx, y1 = H * ty;
    const P = [];
    // a tapered curve from the water to a curl at the top
    const N = 18;
    for (let k = 0; k <= N; k++) {
      const t = k / N;
      const x = x0 + (x1 - x0) * t + Math.sin(t * Math.PI) * W * 0.05 * dir;
      const y = wl + (y1 - wl) * t;
      P.push([x, y, (1 - t) * H * 0.075 + H * 0.012]);
    }
    // the curl: a shrinking circle past the tip
    const [ex, ey] = P[P.length - 1];
    const cr = H * 0.05;
    for (let k = 1; k <= 10; k++) {
      const a = Math.PI + (dir > 0 ? 1 : -1) * k * 0.55;
      const rr = cr * (1 - k * 0.07);
      P.push([ex + dir * cr + Math.cos(a) * rr * dir, ey + Math.sin(a) * rr, H * 0.012 * (1 - k * 0.06)]);
    }
    const outline = (pad) => {
      g.beginPath();
      for (let k = 0; k < P.length; k++) {
        const [x, y, r] = P[k];
        g.moveTo(x + r + pad, y);
        g.arc(x, y, r + pad, 0, TAU);
      }
    };
    outline(1.3);
    g.fillStyle = INK;
    g.fill();
    outline(0);
    g.fillStyle = body;
    g.fill();
    // suckers
    g.fillStyle = light;
    for (let k = 2; k < P.length - 8; k += 2) {
      const [x, y, r] = P[k];
      g.beginPath();
      g.arc(x - dir * r * 0.45, y, Math.max(0.9, r * 0.32), 0, TAU);
      g.fill();
    }
  }
}

// A whale rolling at the surface: its back, a raised tail fluke and a spout.
function paintWhale(g, W, H) {
  const wl = H * WATERLINE.whale;
  const body = "#4d6475", belly = "#c9d3d6";
  const B = new Path2D();
  B.moveTo(W * 0.08, wl + 2);
  B.bezierCurveTo(W * 0.12, wl - H * 0.36, W * 0.52, wl - H * 0.42, W * 0.66, wl + 2);
  B.closePath();
  g.fillStyle = body;
  g.fill(B);
  g.lineWidth = 1.6;
  g.strokeStyle = INK;
  g.stroke(B);
  // grooves along the back
  g.lineWidth = 1;
  g.strokeStyle = "rgba(220,235,240,0.35)";
  for (let k = 0; k < 3; k++) {
    g.beginPath();
    g.moveTo(W * (0.2 + k * 0.03), wl - H * (0.06 + k * 0.05));
    g.quadraticCurveTo(W * 0.36, wl - H * (0.2 + k * 0.05), W * (0.5 - k * 0.02), wl - H * (0.06 + k * 0.04));
    g.stroke();
  }
  eye(g, W * 0.17, wl - H * 0.08, H * 0.028);
  // tail stock and fluke
  const F = new Path2D();
  F.moveTo(W * 0.72, wl + 2);
  F.quadraticCurveTo(W * 0.78, wl - H * 0.2, W * 0.83, wl - H * 0.36);
  F.quadraticCurveTo(W * 0.74, wl - H * 0.46, W * 0.7, wl - H * 0.6);
  F.quadraticCurveTo(W * 0.8, wl - H * 0.52, W * 0.85, wl - H * 0.42);
  F.quadraticCurveTo(W * 0.9, wl - H * 0.56, W * 0.99, wl - H * 0.58);
  F.quadraticCurveTo(W * 0.92, wl - H * 0.44, W * 0.87, wl - H * 0.34);
  F.quadraticCurveTo(W * 0.84, wl - H * 0.18, W * 0.8, wl + 2);
  F.closePath();
  g.fillStyle = body;
  g.fill(F);
  g.lineWidth = 1.5;
  g.strokeStyle = INK;
  g.stroke(F);
  // the spout from the blowhole: a fan of droplet arcs
  g.lineWidth = 1.6;
  g.strokeStyle = "rgba(225,242,250,0.85)";
  const bx = W * 0.26, by = wl - H * 0.3;
  for (const [dx, h] of [[-0.09, 0.2], [-0.04, 0.27], [0.02, 0.29], [0.07, 0.24], [0.11, 0.17]]) {
    g.beginPath();
    g.moveTo(bx, by);
    g.quadraticCurveTo(bx + W * dx * 0.4, by - H * h * 1.1, bx + W * dx, by - H * h * 0.7);
    g.stroke();
  }
  g.fillStyle = "rgba(225,242,250,0.85)";
  for (const [dx, dy] of [[-0.1, 0.12], [0.12, 0.1], [-0.05, 0.2], [0.08, 0.19], [0.0, 0.27]]) {
    g.beginPath();
    g.arc(bx + W * dx, by - H * dy, 1.3, 0, TAU);
    g.fill();
  }
  g.fillStyle = belly;
  g.beginPath();
  g.moveTo(W * 0.74, wl - H * 0.56);
  g.quadraticCurveTo(W * 0.8, wl - H * 0.5, W * 0.84, wl - H * 0.43);
  g.quadraticCurveTo(W * 0.79, wl - H * 0.47, W * 0.74, wl - H * 0.56);
  g.fill();
}

const PAINT = { cloud: paintCloud, serpent: paintSerpent, kraken: paintKraken, whale: paintWhale };

// ---- placement ---------------------------------------------------------------------------------------------------

const RING = 1500; // km beyond the world rectangle that clouds fill
const CLOUD_STEP = 430; // km between cloud candidates
const CREATURE_GAP = 650; // km between creatures
const EDGE_REACH = 520; // creatures live within this many km of the world's edge

/** Clouds and creatures for a world, cached on it ({clouds, creatures, W, H}, positions in km). */
const layouts = new WeakMap();
export function layout(w) {
  let L = layouts.get(w);
  if (L) return L;
  const W = w.raw.width, H = w.raw.height;
  const clouds = [];
  let id = 0;
  for (let gy = -RING; gy <= H + RING; gy += CLOUD_STEP) {
    for (let gx = -RING; gx <= W + RING; gx += CLOUD_STEP) {
      id++;
      if (hash01(id, 3) < 0.6) continue;
      const x = gx + (hash01(id, 5) - 0.5) * CLOUD_STEP * 0.8;
      const y = gy + (hash01(id, 7) - 0.5) * CLOUD_STEP * 0.8;
      // outside the rectangle, by a little more than half a cloud: they never cover the map itself
      const out = Math.max(-x, x - W, -y, y - H);
      if (out < 90) continue;
      // top and bottom bands drift east, the side bands drift north; the period of each lane is its length
      const side = x < 0 || x > W ? (y > -60 && y < H + 60) : false;
      clouds.push({
        x, y, side, variant: Math.floor(hash01(id, 11) * 4), size: 0.75 + hash01(id, 13) * 0.55,
        speed: 5 + hash01(id, 17) * 6, phase: hash01(id, 19) * TAU, flip: hash01(id, 23) < 0.5,
      });
    }
  }
  // creatures: open sea (not a lake, 4+ hexes from land) near the world's edge, best-hashed first, spaced out
  const { grid, water } = w;
  const n = grid.size;
  const dist = new Uint8Array(n);
  let front = [];
  for (let i = 0; i < n; i++) {
    if (water[i]) continue;
    dist[i] = 1;
    front.push(i);
  }
  for (let step = 2; step <= 5 && front.length; step++) {
    const next = [];
    for (const i of front) {
      for (let d = 0; d < 6; d++) {
        const j = grid.neighbour(i, d);
        if (j >= 0 && !dist[j]) { dist[j] = step; next.push(j); }
      }
    }
    front = next;
  }
  const cand = [];
  for (let i = 0; i < n; i++) {
    if (!water[i] || water[i] === WATER_LAKE || dist[i]) continue; // dist 0: 5+ hexes from land
    const x = grid.cx(i), y = grid.cy(i);
    const edge = Math.min(x, y, W - x, H - y);
    if (edge > EDGE_REACH || edge < grid.R * 2) continue;
    cand.push([hash01(i, 29), i, x, y]);
  }
  cand.sort((a, b) => a[0] - b[0]);
  const creatures = [];
  const kinds = ["serpent", "kraken", "serpent", "whale", "serpent", "whale", "kraken"];
  for (const [, i, x, y] of cand) {
    if (creatures.some((c) => (c.x - x) ** 2 + (c.y - y) ** 2 < CREATURE_GAP ** 2)) continue;
    const k = creatures.length;
    creatures.push({
      x, y, kind: kinds[k % kinds.length], variant: k % 2, flip: x > W / 2, phase: hash01(i, 31) * TAU,
      period: 3.2 + hash01(i, 37) * 1.6,
    });
    if (creatures.length >= 9) break;
  }
  L = { clouds, creatures, W, H };
  layouts.set(w, L);
  return L;
}

// ---- drawing -----------------------------------------------------------------------------------------------------

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const cloudCss = (s) => clamp(320 * s, 84, 330); // cloud width in css px at scale s (px per km)
const creatureCss = (s) => clamp(190 * s, 58, 210);
const wrap = (v, lo, hi) => lo + ((((v - lo) % (hi - lo)) + (hi - lo)) % (hi - lo));

/**
 * Draw the decor for camera `cam` at time `t` (seconds) into ctx (css px transform already set). `avoid` is a list
 * of screen rects {x, y, w, h} (the city banners) that creatures stay out of. Returns {rects, speed}: the screen
 * rects drawn (css px, for clearing next time) and the fastest on-screen motion in css px per second.
 */
export function drawEdgeDecor(ctx, cam, w, t, { dpr = 1, avoid = null, still = false } = {}) {
  const L = layout(w);
  const s = cam.scale;
  const rects = [];
  let speed = 0;
  const vw = cam.w, vh = cam.h;
  // clouds
  const cw0 = cloudCss(s);
  const spanX = [-RING, L.W + RING], spanY = [-RING, L.H + RING];
  for (const c of L.clouds) {
    const cw = cw0 * c.size, chh = (cw * BASE.cloud[1]) / BASE.cloud[0];
    const v = still ? 0 : c.speed; // km/s
    let x = c.x, y = c.y;
    if (c.side) y = wrap(c.y - v * t, spanY[0], spanY[1]);
    else x = wrap(c.x + v * t, spanX[0], spanX[1]);
    // keep a lane's clouds out of the map rectangle while they wrap through a corner
    const [sx, sy] = cam.toScreen(x, y);
    const bob = still ? 0 : Math.sin(t * 0.35 + c.phase) * Math.min(4, cw * 0.02);
    const rx = sx - cw / 2, ry = sy - chh / 2 + bob;
    if (rx > vw || ry > vh || rx + cw < 0 || ry + chh < 0) continue;
    const inside = Math.max(-x, x - L.W, -y, y - L.H);
    if (inside < 60) continue; // wrapped into a corner of the map: skip until it is out again
    const sp = sprite("cloud", c.variant, (cw / BASE.cloud[0]) * dpr);
    if (c.flip) {
      ctx.save();
      ctx.translate(rx + cw, ry);
      ctx.scale(-1, 1);
      ctx.drawImage(sp.canvas, 0, 0, cw, chh);
      ctx.restore();
    } else ctx.drawImage(sp.canvas, rx, ry, cw, chh);
    rects.push([rx, ry, cw, chh]);
    speed = Math.max(speed, v * s);
  }
  // creatures: bob up and down through the waterline, with ripples where they break the surface
  const sz = creatureCss(s);
  for (const c of L.creatures) {
    const [bw, bh] = BASE[c.kind];
    const cw = sz * (bw / 170), chh = (cw * bh) / bw;
    const [sx, sy] = cam.toScreen(c.x, c.y);
    const rx = sx - cw / 2, ry = sy - chh * WATERLINE[c.kind];
    if (rx > vw || ry > vh || rx + cw < 0 || ry + chh < 0) continue;
    if (avoid && avoid.some((b) => rx < b.x + b.w && b.x < rx + cw && ry < b.y + b.h && b.y < ry + chh)) continue;
    const ph = still ? 0.5 : (t / c.period) * TAU + c.phase;
    const lift = (0.5 + 0.5 * Math.sin(ph)) * 0.14; // share of the height sunk below the waterline
    const sp = sprite(c.kind, c.variant, (cw / bw) * dpr);
    const wl = chh * WATERLINE[c.kind];
    const sink = chh * lift;
    // the part above the (moving) waterline only: source rows 0 .. waterline - sink
    const srcH = (sp.canvas.height * (wl - sink)) / chh;
    ctx.save();
    if (c.flip) {
      ctx.translate(rx + cw, 0);
      ctx.scale(-1, 1);
      ctx.drawImage(sp.canvas, 0, 0, sp.canvas.width, srcH, 0, ry + sink, cw, wl - sink);
    } else ctx.drawImage(sp.canvas, 0, 0, sp.canvas.width, srcH, rx, ry + sink, cw, wl - sink);
    ctx.restore();
    // ripples at the waterline
    const wy = ry + wl;
    ctx.lineWidth = Math.max(1, cw * 0.008);
    ctx.strokeStyle = "rgba(230,246,250,0.7)";
    const rip = 0.5 + 0.5 * Math.sin(ph * 2 + 1);
    ctx.beginPath();
    for (const fx of RIPPLES[c.kind]) {
      const x = c.flip ? rx + cw * (1 - fx[0]) : rx + cw * fx[0];
      const r = cw * fx[1] * (0.85 + 0.3 * rip);
      ctx.moveTo(x - r, wy);
      ctx.ellipse(x, wy, r, r * 0.22, 0, Math.PI, TAU, true);
    }
    ctx.stroke();
    rects.push([rx - 2, ry - 2, cw + 4, chh + 4]);
    speed = Math.max(speed, (chh * 0.14 * TAU) / c.period / 2); // peak bob speed, css px/s
  }
  return { rects, speed };
}

// where each creature breaks the surface: [x as a share of the width, ripple radius as a share of the width]
const RIPPLES = {
  serpent: [[0.08, 0.1], [0.27, 0.07], [0.33, 0.07], [0.53, 0.07], [0.57, 0.07], [0.69, 0.07]],
  kraken: [[0.15, 0.08], [0.31, 0.07], [0.5, 0.17], [0.72, 0.07], [0.86, 0.08]],
  whale: [[0.37, 0.3], [0.76, 0.07]],
};

/**
 * The decor on its own canvas over the map. `canvas` is a transparent canvas laid over the map canvas (same size,
 * no pointer events). Call render() whenever the map is drawn (with the banner rects to avoid); between map draws it
 * animates itself at the rate its motion needs. setEnabled(false) clears it and stops.
 */
export function createEdgeDecor(canvas, w, cam) {
  const ctx = canvas.getContext("2d");
  const reduce = typeof matchMedia === "function" ? matchMedia("(prefers-reduced-motion: reduce)") : null;
  let dpr = 1, last = [], avoid = null, timer = 0, enabled = true;
  const t0 = performance.now();

  function paint(full) {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (full) ctx.clearRect(0, 0, canvas.width / dpr, canvas.height / dpr);
    else for (const r of last) ctx.clearRect(r[0] - 1, r[1] - 1, r[2] + 2, r[3] + 2);
    if (!enabled) { last = []; return { rects: [], speed: 0 }; }
    const still = !!reduce?.matches;
    const out = drawEdgeDecor(ctx, cam, w, (performance.now() - t0) / 1000, { dpr, avoid, still });
    last = out.rects;
    return out;
  }

  function schedule(out) {
    if (timer) clearTimeout(timer);
    timer = 0;
    if (!enabled || !out.rects.length || !out.speed || reduce?.matches) return;
    // enough frames that the fastest thing moves about half a pixel per frame, 6..30 per second
    const fps = clamp(out.speed * 2, 6, 30);
    timer = setTimeout(() => {
      timer = 0;
      if (document.hidden) {
        document.addEventListener("visibilitychange", () => requestAnimationFrame(tick), { once: true });
        return;
      }
      requestAnimationFrame(tick);
    }, 1000 / fps);
  }
  function tick() {
    if (timer) return; // a map draw already scheduled the next one
    schedule(paint(false));
  }

  return {
    resize(cssW, cssH, ratio) {
      dpr = ratio;
      canvas.width = Math.round(cssW * dpr);
      canvas.height = Math.round(cssH * dpr);
      last = [];
    },
    /** Redraw for the current camera (called by the map's draw); `bannerRects` are screen rects to keep clear. */
    render(bannerRects = null) {
      avoid = bannerRects;
      schedule(paint(true));
    },
    setEnabled(on) {
      enabled = !!on;
      schedule(paint(true));
    },
    get enabled() { return enabled; },
  };
}
