"""world.json: hex grid over the EU27 with terrain, water, land cover, owners (countries) and NUTS 3 regions."""
import math, os, glob
import numpy as np
import shapely
from shapely.geometry import shape
from PIL import Image
from common import *

RADIUS = 20.0
MARGIN = 150.0
STEP = 4.0  # km between sample points

# --- regions ----------------------------------------------------------------------------------------------------
nuts3 = load_json(RAW + '/nuts/nutsrg_2024_3.json')['features']
nuts3 = [f for f in nuts3 if f['properties']['id'][:2] in EU27 and not f['properties']['id'].startswith(EXCLUDED_PREFIXES)]
nuts3.sort(key=lambda f: f['properties']['id'])
reg_ids = [f['properties']['id'] for f in nuts3]
reg_names = [f['properties']['na'] for f in nuts3]
reg_geoms = [shape(f['geometry']) for f in nuts3]
print('NUTS3 regions', len(reg_ids))

countries = [c for c in EU27]
cidx = {c: i for i, c in enumerate(countries)}

minx = min(g.bounds[0] for g in reg_geoms) / 1000
miny = min(g.bounds[1] for g in reg_geoms) / 1000
maxx = max(g.bounds[2] for g in reg_geoms) / 1000
maxy = max(g.bounds[3] for g in reg_geoms) / 1000
proj = Proj(minx, maxy, MARGIN)
W = (maxx - minx) + 2 * MARGIN
H = (maxy - miny) + 2 * MARGIN
grid = Grid(RADIUS, math.ceil(W / (SQRT3 * RADIUS)) + 1, math.ceil(H / (1.5 * RADIUS)) + 1)
print('grid', grid.cols, grid.rows, grid.size, 'map km', round(W), round(H))

land_feats = load_json(RAW + '/nuts/cntrg.json')['features']
land_geoms = [shape(f['geometry']) for f in land_feats]
lake_geoms = []
for fn in ('ne_10m_lakes', 'ne_10m_lakes_europe'):
    for f in load_json(f'{RAW}/ne/{fn}.geojson')['features']:
        g = shape(f['geometry'])
        if g.bounds[2] < -15 or g.bounds[0] > 40 or g.bounds[3] < 30 or g.bounds[1] > 75:
            continue
        g = shapely.transform(g, lambda c: np.column_stack(TO3035.transform(c[:, 0], c[:, 1])))
        lake_geoms.append(g)

# --- sample lattice ----------------------------------------------------------------------------------------------
xs = np.arange(STEP / 2, W, STEP)
ys = np.arange(STEP / 2, H, STEP)
PX, PY = np.meshgrid(xs, ys)
PX = PX.ravel(); PY = PY.ravel()
PC = grid.cell_at(PX, PY)
keep = PC >= 0
PX, PY, PC = PX[keep], PY[keep], PC[keep]
N = len(PX)
print('samples', N)
X3, Y3 = proj.to3035(PX, PY)
pts = shapely.points(X3, Y3)


def assign(geoms, pts):
    tree = shapely.STRtree(geoms)
    out = np.full(len(pts), -1, int)
    pi, gi = tree.query(pts, predicate='within')
    out[pi] = gi
    return out


p_reg = assign(reg_geoms, pts)
p_land = assign(land_geoms, pts) >= 0
p_lake = assign(lake_geoms, pts) >= 0 if lake_geoms else np.zeros(N, bool)
p_land = (p_land | (p_reg >= 0)) & ~p_lake
p_reg[p_lake] = -1
print('in regions', (p_reg >= 0).sum(), 'land', p_land.sum())

LON, LAT = TO4326.transform(X3, Y3)
LON = np.asarray(LON); LAT = np.asarray(LAT)

# --- elevation (Terrarium tiles, z7) --------------------------------------------------------------------------------
Z = 7
TX0, TX1, TY0, TY1 = 60, 76, 26, 52
mosaic = np.full(((TY1 - TY0 + 1) * 256, (TX1 - TX0 + 1) * 256), np.nan, np.float32)
for tx in range(TX0, TX1 + 1):
    for ty in range(TY0, TY1 + 1):
        p = f'{RAW}/terrarium/{Z}_{tx}_{ty}.png'
        if not os.path.exists(p):
            continue
        a = np.asarray(Image.open(p).convert('RGB')).astype(np.float32)
        mosaic[(ty - TY0) * 256:(ty - TY0 + 1) * 256, (tx - TX0) * 256:(tx - TX0 + 1) * 256] = a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768
n = 2 ** Z
fx = (LON + 180) / 360 * n
fy = (1 - np.log(np.tan(np.radians(LAT)) + 1 / np.cos(np.radians(LAT))) / math.pi) / 2 * n
ix = np.clip(((fx - TX0) * 256).astype(int), 0, mosaic.shape[1] - 1)
iy = np.clip(((fy - TY0) * 256).astype(int), 0, mosaic.shape[0] - 1)
p_elev = mosaic[iy, ix]

# --- land cover (ESA WorldCover 2021, read at 1/32 resolution ~300 m) ------------------------------------------
p_wc = np.zeros(N, np.uint8)
tlat = (np.floor(LAT / 3) * 3).astype(int)
tlon = (np.floor(LON / 3) * 3).astype(int)
keys = tlat * 1000 + tlon
for k in np.unique(keys[p_land]):
    la, lo = int(k // 1000), int(k - (k // 1000) * 1000)
    if lo > 500: la, lo = la + 1, lo - 1000
    name = f"{'N' if la >= 0 else 'S'}{abs(la):02d}{'E' if lo >= 0 else 'W'}{abs(lo):03d}"
    p = f'{RAW}/worldcover/{name}.npy'
    if not os.path.exists(p):
        continue
    a = np.load(p)
    m = (keys == k)
    r = np.clip(((la + 3 - LAT[m]) / 3 * a.shape[0]).astype(int), 0, a.shape[0] - 1)
    c = np.clip(((LON[m] - lo) / 3 * a.shape[1]).astype(int), 0, a.shape[1] - 1)
    p_wc[m] = a[r, c]
print('cover samples', (p_wc > 0).sum())

# --- per cell ------------------------------------------------------------------------------------------------------
S = grid.size
order = np.argsort(PC, kind='stable')
bounds = np.searchsorted(PC[order], np.arange(S + 1))
owner = np.full(S, -1, int)
county = np.full(S, -1, int)
elev = np.zeros(S, int); elev_max = np.zeros(S, int)
water = np.zeros(S, int); relief = np.zeros(S, int); cover = np.zeros(S, int)
PCT_KEYS = ['forest', 'crop', 'pasture', 'grass', 'shrub', 'wetland', 'developed']
pct = {k: np.zeros(S, int) for k in PCT_KEYS}
lake_cell = np.zeros(S, bool)
cell_samples = {}  # cell -> {region index: count}

for i in range(S):
    idx = order[bounds[i]:bounds[i + 1]]
    if len(idx) == 0:
        continue
    land = p_land[idx]
    nl = land.sum()
    e = p_elev[idx]
    if nl * 2 >= len(idx):
        reg = p_reg[idx][land]
        reg_in = reg[reg >= 0]
        if len(reg_in) * 2 >= nl:  # mostly EU land
            vals, cnt = np.unique(reg_in, return_counts=True)
            county[i] = int(vals[np.argmax(cnt)])
            owner[i] = cidx[reg_ids[county[i]][:2]]
            cell_samples[i] = {int(v): int(c) for v, c in zip(vals, cnt)}
        else:
            owner[i] = -2
        el = e[land]
        el = el[~np.isnan(el)]
        if len(el):
            elev[i] = int(round(float(el.mean())))
            elev_max[i] = int(round(float(el.max())))
            sd = float(el.std())
            srt = np.sort(el)
            low = srt[:max(1, int(len(srt) * 0.6))]
            r = 0
            if sd >= 85: r = 1
            if sd >= 260 or el.mean() >= 2000: r = 2
            if el.mean() >= 2300 or (elev_max[i] >= 3500 and sd >= 400): r = 3
            if r and (low.max() - low.min()) < 60 and low.max() < 400: r -= 1
            relief[i] = r
        # land cover
        wc = p_wc[idx][land]
        wc = wc[wc > 0]
        wc = wc[wc != 80]
        if len(wc):
            tot = len(wc)
            f = lambda *cls: int(round(100 * np.isin(wc, cls).sum() / tot))
            forest = f(10); crop = f(40); grassall = f(30); shrub = f(20, 100); wet = f(90, 95); dev = f(50)
            bare = f(60); ice = f(70)
            past = grassall if elev[i] < 600 else 0
            grass = grassall - past
            for k, v in zip(PCT_KEYS, (forest, crop, past, grass, shrub, wet, dev)):
                pct[k][i] = v
            groups = {'forest': forest, 'scrub': shrub, 'grassland': grass, 'pasture': past, 'cropland': crop,
                      'wetland': wet, 'barren': bare, 'ice': ice}
            best = max(groups, key=groups.get)
            if dev >= 22:
                cover[i] = 9
            elif best == 'forest':
                lat_c = float(np.mean(LAT[idx]))
                if lat_c > 58 or elev[i] > 900:
                    cover[i] = 2
                elif lat_c > 52 or elev[i] > 500:
                    cover[i] = 3
                else:
                    cover[i] = 1
            else:
                cover[i] = {'scrub': 4, 'grassland': 5, 'pasture': 6, 'cropland': 7, 'wetland': 8, 'barren': 10, 'ice': 11}[best]
    else:
        ew = e[~land]
        ew = ew[~np.isnan(ew)]
        lakes = p_lake[idx].sum()
        if lakes * 2 > (len(idx) - nl):
            lake_cell[i] = True
            elev[i] = int(min(float(ew.mean()) if len(ew) else 0, 0))
        else:
            below = ew[ew <= 0]
            elev[i] = int(round(float(below.mean()))) if len(below) else -4000

# Make sure every small NUTS 3 island / micro-region that got no hex but sits in water gets one (e.g. Malta, Gozo).
pt = {f['properties']['id']: f['geometry']['coordinates'] for f in load_json(RAW + '/nuts/nutspt_2024_3.json')['features']}
has = set(county[county >= 0].tolist())
forced = []
for ri, rid in enumerate(reg_ids):
    if ri in has or rid not in pt:
        continue
    cx, cy = proj.from3035(*pt[rid])
    c = int(grid.cell_at(cx, cy))
    if c >= 0 and owner[c] == -1:
        owner[c] = cidx[rid[:2]]; county[c] = ri; elev[c] = max(elev[c], 20); relief[c] = 0
        cover[c] = 9 if (reg_geoms[ri].area < 5e8) else 6
        cell_samples[c] = {ri: 1}
        lake_cell[c] = False
        forced.append(rid)
print('forced island cells', forced)

# Water classes
for i in range(S):
    if owner[i] != -1:
        water[i] = 0
        continue
    if lake_cell[i]:
        water[i] = 3
        continue
    nb_land = any(owner[j] != -1 for j in grid.neighbours(i))
    water[i] = 2 if (nb_land or elev[i] > -200) else 1
    elev[i] = min(elev[i], 0)

# --- rivers ----------------------------------------------------------------------------------------------------------
rivers = []
seen = {}
for fn in ('ne_10m_rivers_lake_centerlines', 'ne_10m_rivers_europe'):
    for f in load_json(f'{RAW}/ne/{fn}.geojson')['features']:
        pr = f['properties']
        if pr.get('featurecla', '').lower().startswith('lake'):
            continue
        g = f['geometry']
        lines = g['coordinates'] if g['type'] == 'MultiLineString' else [g['coordinates']]
        rank = pr.get('scalerank') or pr.get('rivernum') or 9
        name = pr.get('name_en') or pr.get('name') or None
        for ln in lines:
            a = np.array(ln)
            if a.size == 0 or a[:, 0].max() < -12 or a[:, 0].min() > 36 or a[:, 1].max() < 33 or a[:, 1].min() > 72:
                continue
            x, y = proj(a[:, 0], a[:, 1])
            c = grid.cell_at(x, y)
            inside = (c >= 0)
            if inside.sum() < 2:
                continue
            on_eu = np.array([owner[k] >= 0 for k in c[inside]])
            if on_eu.mean() < 0.3:
                continue
            ptsxy = []
            for xx, yy in zip(x[inside], y[inside]):
                ptsxy += [round(float(xx), 1), round(float(yy), 1)]
            if len(ptsxy) >= 4:
                rivers.append({'name': name, 'rank': int(rank), 'pts': ptsxy})
rivers.sort(key=lambda r: r['rank'])
print('rivers', len(rivers))

# Province / country tables
states = [{'fips': c, 'abbr': c, 'name': COUNTRY_NAMES[c]} for c in countries]
counties = [{'geoid': rid, 'name': nm} for rid, nm in zip(reg_ids, reg_names)]

us = load_json(os.environ.get('USACIV_WORLD', os.path.join(ROOT, 'raw', 'usaciv_world.json')))  # table rules template from usaciv
tables = us['tables']
tables['water'][0]['rule'] = 'At least half of the hex’s sample points (one every 4 km) fall on land (GISCO country outlines), outside Natural Earth lakes.'
tables['water'][2]['rule'] = 'Sea next to a land hex, or shallower than 200 m (mean of the Terrarium/SRTM samples).'
tables['water'][3]['rule'] = 'Water hex where Natural Earth 1:10m lake samples outnumber sea samples.'
tables['relief'] = [
    {'id': 0, 'name': 'Flat', 'rule': 'Elevation standard deviation inside the hex under 85 m.'},
    {'id': 1, 'name': 'Hills', 'rule': 'Elevation standard deviation ≥ 85 m.'},
    {'id': 2, 'name': 'Mountains', 'rule': 'Elevation standard deviation ≥ 260 m, or mean elevation ≥ 2,000 m.'},
    {'id': 3, 'name': 'Peaks', 'rule': 'Mean elevation ≥ 2,300 m, or a summit ≥ 3,500 m with a standard deviation ≥ 400 m (alpine).'}]
wcmap = {1: 'Tree cover (10), drawn as broadleaf below 52°N and 500 m', 2: 'Tree cover (10), drawn as conifer above 58°N or 900 m',
         3: 'Tree cover (10), drawn as mixed forest in between', 4: 'Shrubland (20) plus moss & lichen (100)',
         5: 'Grassland (30) at or above 600 m (alpine meadows, rough grazing)', 6: 'Grassland (30) below 600 m (mostly managed pasture and meadows)',
         7: 'Cropland (40)', 8: 'Herbaceous wetland (90) and mangroves (95)', 9: 'Built-up (50) ≥ 22% of the hex’s land samples',
         10: 'Bare / sparse vegetation (60)', 11: 'Snow and ice (70)'}
for t in tables['cover']:
    t.pop('nlcd', None)
    if t['id'] in wcmap:
        t['rule'] = 'ESA WorldCover 2021 class ' + wcmap[t['id']] + ('' if t['id'] == 9 else ' is the largest group of the hex’s land samples.')
    if t['id'] == 0:
        t['rule'] = 'Water, land outside the EU, or no WorldCover samples.'

world = {
    'version': 2, 'grid': grid.to_dict(), 'width': round(W, 1), 'height': round(H, 1), 'margin': MARGIN,
    'owner': owner.tolist(), 'county': county.tolist(), 'elev': elev.tolist(), 'elev_max': elev_max.tolist(),
    'water': water.tolist(), 'relief': relief.tolist(), 'cover': cover.tolist(),
    'pct': {k: v.tolist() for k, v in pct.items()}, 'tables': tables, 'states': states, 'counties': counties,
    'rivers': rivers,
}
save_json('world', world)

# Interim for later builders: projection, per-cell region sample counts, sample-level region & cell (thinned).
save_interim('_world_meta', {'grid': grid.to_dict(), 'projection': proj.to_dict(), 'regions': reg_ids, 'countries': countries,
                             'cell_samples': {str(k): v for k, v in cell_samples.items()}})
np.savez_compressed(INTERIM + '/_samples.npz', cell=PC, reg=p_reg, land=p_land, lon=LON, lat=LAT, elev=p_elev, wc=p_wc)
# region geometry areas & centroids (map km)
cent = {}
for ri, g in enumerate(reg_geoms):
    c = pt.get(reg_ids[ri])
    if c is None:
        c = list(g.representative_point().coords)[0]
    x, y = proj.from3035(*c)
    cent[reg_ids[ri]] = [round(float(x), 1), round(float(y), 1), round(g.area / 1e6, 1)]
save_interim('_regions', cent)
print('land cells', int((owner >= 0).sum()), 'foreign', int((owner == -2).sum()))
