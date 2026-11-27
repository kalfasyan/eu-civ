"""climate.json: the 2050 lens. Today's climate and its path to 2050 for two emissions paths, a 'climate twin' for every
region, and the low-lying land along the coast. Also adds three lenses (Hot days, Tropical nights, Low-lying land) and
a 'Climate' group to lenses.json. Run after build_history.py.

Climate: Copernicus European Climate Data Explorer, NUTS-aggregated indicators (sis-ecde-aggregated-climate-indicators,
CC-BY 4.0), fetched by cds.py (needs CDSAPI_KEY at build time only).
  today     ERA5 reanalysis, 1991-2020 average, per NUTS 2 region
  the path  EURO-CORDEX ensemble, yearly quantiles (17th, 50th, 83rd percentile of the models) for RCP4.5 ('if
            emissions fall') and RCP8.5 ('if they don't'). We add the models' change against their own 1991-2020 mean to
            the ERA5 values, so model bias drops out. Each year is the centre of a 21-year mean, as a single year is
            mostly weather.
  twins     each region's 2050 climate (hot days, tropical nights, summer and winter temperature, summer rain) against
            every region's 1991-2020 climate, at least 300 km away.
The indicators are published on NUTS 2 regions (2021 borders), so every NUTS 3 region takes the value of the NUTS 2
region its centre falls in.

Low-lying land: land samples every 500 m within 100 km of the sea at or below 5 m (AWS Terrain Tiles, zoom 9: SRTM and
EU-DEM), with water and sea removed using ESA WorldCover 2021. People on it are estimated from WorldCover's built-up
class. It is exposure, not a flood forecast: dykes, dunes and storm surges are not modelled.

Needs raw/nuts (NUTS 2 polygons, 2016, 2021 and 2024), raw/worldcover (fetch_worldcover.py) and network access to the
CDS and to the AWS terrain tiles.
"""
import glob, io, json, math, os, urllib.request
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import shapely
import xarray as xr
from PIL import Image
from shapely.geometry import shape
import cds
from common import *

world = load_json(OUT + '/world.json')
counties = load_json(OUT + '/counties.json')
cols = counties['columns']
REG = [c['geoid'] for c in world['counties']]
rows = [dict(zip(cols, r)) for r in counties['rows']]
NR = len(REG)
grid = Grid(**world['grid'])
S = grid.size
county = np.array(world['county'])
water = np.array(world['water'])

nuts3 = nuts3_features()
assert [f['properties']['id'] for f in nuts3] == REG
g3 = [shape(f['geometry']) for f in nuts3]
proj = Proj(min(g.bounds[0] for g in g3) / 1000, max(g.bounds[3] for g in g3) / 1000, 150.0)

Y0, Y1 = 2025, 2050
YEARS = list(range(Y0, Y1 + 1))
SCEN = {'s45': 'rcp_4_5', 's85': 'rcp_8_5'}
HALF = 10  # 21-year centred means


# --- climate units: the NUTS 2 regions the indicators come on --------------------------------------------------------
def open_nc(var, product, origin, agg, other=None):
    return xr.open_dataset(cds.get(var, product, origin, agg, other))


ref_hot = open_nc('hot_days', 'average', 'reanalysis', 'yearly', '30_c')
UNITS = [str(u) for u in ref_hot.nuts.values]
uidx = {u: i for i, u in enumerate(UNITS)}
polys = {}
for vint in ('2024', '2021', '2016'):
    p = f'{RAW}/nuts/nutsrg_{vint}_2.json'
    for f in load_json(p)['features']:
        i = f['properties']['id']
        if i in uidx and i not in polys:
            polys[i] = shape(f['geometry'])
pids = list(polys)
tree = shapely.STRtree([polys[i] for i in pids])
unit_of = []
for g, geom in zip(REG, g3):
    pt = geom.representative_point()
    hits = [pids[k] for k in tree.query(pt, predicate='within')]
    u = g[:4] if g[:4] in hits else (hits[0] if hits else (g[:4] if g[:4] in uidx else None))
    if u is None:  # a coastal centre just outside a generalised polygon: nearest unit in the same country
        same = [i for i in pids if i[:2] == g[:2]]
        u = min(same, key=lambda i: polys[i].distance(pt)) if same else None
    unit_of.append(uidx[u] if u else -1)
print('regions without climate data:', sorted({g[:2] for g, u in zip(REG, unit_of) if u < 0}))


def arr(da):
    return np.asarray(da.values, float)


def ref_avg(var, agg='yearly', other=None, month=None):
    ds = ref_hot if var == 'hot_days' else open_nc(var, 'average', 'reanalysis', agg, other)
    da = ds[var].sel(avg_period='1991-01-01')
    da = da.sel(month=month) if month else da.squeeze('month', drop=True)
    return arr(da.squeeze(drop=True))


base = {
    'hot': ref_avg('hot_days', other='30_c'),
    'trop': ref_avg('tropical_nights'),
    'tjja': ref_avg('mean_temperature', 'seasonal', month=6) - 273.15,
    'tdjf': ref_avg('mean_temperature', 'seasonal', month=12) - 273.15,
    'pjja': ref_avg('total_precipitation', 'seasonal', month=6),
}


def path(var, other=None):
    """{scen: {q: array[units, years]}}: ERA5 1991-2020 + models' 21-year-mean change against their 1991-2020 mean."""
    ds = open_nc(var, 'quantile_time_series', 'projections', 'yearly', other)
    yrs = ds.time.dt.year.values
    out = {}
    b = base['hot' if var == 'hot_days' else 'trop']
    for k, sc in SCEN.items():
        out[k] = {}
        for q in (0.17, 0.5, 0.83):
            a = arr(ds[var].sel(scenario=sc, quantile=q).transpose('nuts', 'time'))
            ref = a[:, (yrs >= 1991) & (yrs <= 2020)].mean(axis=1)
            m = np.stack([a[:, (yrs >= y - HALF) & (yrs <= y + HALF)].mean(axis=1) for y in YEARS], axis=1)
            out[k][q] = np.clip(b[:, None] + (m - ref[:, None]), 0, 365)
    return out


P = {'hot': path('hot_days', '30_c'), 'trop': path('tropical_nights')}


def change30(var, agg, month):
    ds = open_nc(var, 'absolute_change_quantiles', 'projections', agg)
    da = ds[var].sel(ref_period='1991-01-01', avg_period='2041-01-01', quantile=0.5, month=month)
    return {k: arr(da.sel(scenario=sc).squeeze(drop=True)) for k, sc in SCEN.items()}


# (The ECDE's relative_change product for rain is off by about +100% everywhere in v2.0, so we use the absolute one.)
dT = change30('mean_temperature', 'seasonal', 6)
dTw = change30('mean_temperature', 'seasonal', 12)
dP = change30('total_precipitation', 'seasonal', 6)
fut = {k: {'tjja': base['tjja'] + dT[k], 'tdjf': base['tdjf'] + dTw[k], 'pjja': np.maximum(base['pjja'] + dP[k], 0),
           'hot': P['hot'][k][0.5][:, -1], 'trop': P['trop'][k][0.5][:, -1]} for k in SCEN}

# --- climate twins (per unit) ----------------------------------------------------------------------------------------
# Features: sqrt of hot days and tropical nights (so 0 -> 4 matters as much as 40 -> 60), summer and winter mean
# temperature and log summer rain, each scaled by its spread across today's regions. Winter keeps an Atlantic city from
# matching an Alpine valley with the same summer.
cent = {}
for u, p in polys.items():
    c = p.representative_point()
    cent[u] = (c.x / 1000, c.y / 1000)


def feats(d):
    return np.column_stack([np.sqrt(np.maximum(d['hot'], 0)), np.sqrt(np.maximum(d['trop'], 0)), d['tjja'], d['tdjf'], np.log1p(np.maximum(d['pjja'], 0))])


F0 = feats(base)
ok0 = np.all(np.isfinite(F0), axis=1)
sd = F0[ok0].std(axis=0)
W = np.array([1.0, 1.0, 1.2, 0.6, 0.5])
XY = np.array([cent.get(u, (np.nan, np.nan)) for u in UNITS])

# A twin is named after the biggest city (or region) in that unit.
cities = load_json(OUT + '/cities.json')
unit_name = {}
for u in range(len(UNITS)):
    best = None
    for c in cities:
        if any(unit_of[REG.index(g)] == u for g in c.get('counties', []) if g in REG) and (best is None or c['population'] > best['population']):
            best = c
    if best:
        unit_name[u] = best['name']
    else:
        rs = [i for i in range(NR) if unit_of[i] == u]
        if rs:
            unit_name[u] = max(rs, key=lambda i: rows[i]['population'] or 0)
            unit_name[u] = rows[unit_name[u]]['name']
unit_country = {u: next((REG[i][:2] for i in range(NR) if unit_of[i] == u), UNITS[u][:2]) for u in range(len(UNITS))}
used_units = sorted({u for u in unit_of if u >= 0})


def twins(k):
    F1 = feats(fut[k])
    out = []
    for u in range(len(UNITS)):
        if u not in used_units or not np.all(np.isfinite(F1[u])):
            out.append(None)
            continue
        d = np.sqrt((((F0 - F1[u]) / sd * W) ** 2).sum(axis=1))
        far = np.hypot(XY[:, 0] - XY[u, 0], XY[:, 1] - XY[u, 1]) >= 300
        d[~ok0 | ~far | ~np.isin(np.arange(len(UNITS)), used_units)] = np.inf
        j = int(np.argmin(d))
        out.append([j, round(float(d[j]), 2)] if np.isfinite(d[j]) else None)
    return out


TW = {k: twins(k) for k in SCEN}

# --- low-lying land --------------------------------------------------------------------------------------------------
print('low-lying land')
land = (water == 0) & (county >= 0)
sea = (water == 1) | (water == 2)
dist = np.full(S, 99)
front = [i for i in range(S) if sea[i]]
for i in front:
    dist[i] = 0
for step in range(1, 4):
    nxt = []
    for i in front:
        for j in grid.neighbours(i):
            if dist[j] > step:
                dist[j] = step
                nxt.append(j)
    front = nxt
cand = np.where(land & (dist <= 3) & (np.array(world['elev']) < 120))[0]
STEP = 0.5
cx, cy = grid.center(cand)
offs = np.arange(-grid.radius, grid.radius + 1e-9, STEP)
ox, oy = np.meshgrid(offs, offs)
ox, oy = ox.ravel(), oy.ravel()
PX = (cx[:, None] + ox[None, :]).ravel()
PY = (cy[:, None] + oy[None, :]).ravel()
PC = grid.cell_at(PX, PY)
keep = PC == np.repeat(cand, len(ox))  # each sample once, by the hex whose square it came from
PX, PY, PC = PX[keep], PY[keep], PC[keep]
X3, Y3 = proj.to3035(PX, PY)
LON, LAT = TO4326.transform(X3, Y3)
LON, LAT = np.asarray(LON), np.asarray(LAT)
print('samples', len(PX))

rtree = shapely.STRtree(g3)


def region_of(x3, y3):
    out = np.full(len(x3), -1)
    pi, gi = rtree.query(shapely.points(x3, y3), predicate='within')
    out[pi] = gi
    return out


def worldcover(lon, lat):
    cls = np.zeros(len(lon), np.uint8)
    tla = (np.floor(lat / 3) * 3).astype(int)
    tlo = (np.floor(lon / 3) * 3).astype(int)
    for la, lo in set(zip(tla.tolist(), tlo.tolist())):
        name = f"{'N' if la >= 0 else 'S'}{abs(la):02d}{'E' if lo >= 0 else 'W'}{abs(lo):03d}"
        p = f'{RAW}/worldcover/{name}.npy'
        if not os.path.exists(p):
            continue
        a = np.load(p)
        m = (tla == la) & (tlo == lo)
        r = np.clip(((la + 3 - lat[m]) / 3 * a.shape[0]).astype(int), 0, a.shape[0] - 1)
        c = np.clip(((lon[m] - lo) / 3 * a.shape[1]).astype(int), 0, a.shape[1] - 1)
        cls[m] = a[r, c]
    return cls



# Terrarium z9 elevation
Z = 9
n = 2 ** Z
fx = (LON + 180) / 360 * n
fy = (1 - np.log(np.tan(np.radians(LAT)) + 1 / np.cos(np.radians(LAT))) / math.pi) / 2 * n
tx, ty = fx.astype(int), fy.astype(int)
tiles = sorted(set(zip(tx.tolist(), ty.tolist())))
TD = f'{RAW}/terrarium{Z}'
os.makedirs(TD, exist_ok=True)


def fetch(t):
    p = f'{TD}/{Z}_{t[0]}_{t[1]}.png'
    if not os.path.exists(p):
        with urllib.request.urlopen(f'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{Z}/{t[0]}/{t[1]}.png', timeout=60) as r:
            open(p, 'wb').write(r.read())
    return p


with ThreadPoolExecutor(16) as ex:
    list(ex.map(fetch, tiles))
print('tiles', len(tiles))
elev = np.full(len(PX), np.nan, np.float32)
key = tx * 100000 + ty
for t in tiles:
    a = np.asarray(Image.open(f'{TD}/{Z}_{t[0]}_{t[1]}.png').convert('RGB')).astype(np.float32)
    e = a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768
    m = key == t[0] * 100000 + t[1]
    px = np.clip(((fx[m] - t[0]) * 256).astype(int), 0, 255)
    py = np.clip(((fy[m] - t[1]) * 256).astype(int), 0, 255)
    elev[m] = e[py, px]

wc = worldcover(LON, LAT)  # 0 = no data / open sea, 80 = water, 50 = built-up
on_land = (wc != 0) & (wc != 80)
low = on_land & (elev <= 5)
A = STEP * STEP  # km2 per sample
cell_land = np.bincount(PC, weights=on_land, minlength=S) * A
cell_low = np.bincount(PC, weights=low, minlength=S) * A
low_built = np.bincount(PC, weights=low & (wc == 50), minlength=S) * A
hex_low = [None] * S
for i in np.where(land)[0]:
    hex_low[i] = round(float(cell_low[i] / cell_land[i]), 3) if cell_land[i] > 0 else 0.0

# Region totals: each sample goes to the NUTS 3 region it falls in. People on low land = population x the share of the
# region's built-up land (WorldCover class 50) that is low. All built-up land comes from a 1 km lattice over every land hex.
pr = region_of(X3, Y3)
inr = pr >= 0
low_km2 = np.bincount(pr[inr], weights=low[inr], minlength=NR) * A
low_b = np.bincount(pr[inr], weights=(low & (wc == 50))[inr], minlength=NR) * A
allc = np.where(county >= 0)[0]
bx, by = grid.center(allc)
o1 = np.arange(-grid.radius, grid.radius + 1e-9, 1.0)
qx, qy = np.meshgrid(o1, o1)
BX = (bx[:, None] + qx.ravel()[None, :]).ravel()
BY = (by[:, None] + qy.ravel()[None, :]).ravel()
kb = grid.cell_at(BX, BY) == np.repeat(allc, qx.size)
BX, BY = BX[kb], BY[kb]
B3x, B3y = proj.to3035(BX, BY)
blon, blat = TO4326.transform(B3x, B3y)
bwc = worldcover(np.asarray(blon), np.asarray(blat))
br = region_of(B3x, B3y)
ok = (br >= 0) & (bwc == 50)
built = np.bincount(br[ok], minlength=NR) * 1.0
coast = []
for r in range(NR):
    pop = rows[r]['population'] or 0
    land_km2 = rows[r]['land_km2'] or 0
    share_pop = min(1.0, low_b[r] / built[r]) if built[r] > 0 else 0.0
    coast.append([round(float(low_km2[r])), round(min(1.0, low_km2[r] / land_km2), 3) if land_km2 else 0, round(pop * share_pop)])
print('people on low land', sum(c[2] for c in coast))

# --- headline numbers --------------------------------------------------------------------------------------------------
pop = np.array([rows[r]['population'] or 0 for r in range(NR)], float)
gdp = np.array([rows[r]['gdp'] or 0 for r in range(NR)], float)
U = np.array(unit_of)
hasU = U >= 0


def people_over(vals, thr):
    v = np.where(hasU, vals[np.maximum(U, 0)], np.nan)
    return float(pop[hasU & (v >= thr)].sum())


hot_now = P['hot']['s45'][0.5][:, 0]
stats = {
    'pop_hot30_today': round(people_over(base['hot'], 30)),
    'pop_hot30_2025': round(people_over(hot_now, 30)),
    'pop_hot30_2050': {k: round(people_over(P['hot'][k][0.5][:, -1], 30)) for k in SCEN},
    'pop_trop20_2050': {k: round(people_over(P['trop'][k][0.5][:, -1], 20)) for k in SCEN},
    'pop_low_coast': round(sum(c[2] for c in coast)),
    'gdp_low_coast': round(float(sum(gdp[r] * (coast[r][2] / pop[r]) for r in range(NR) if pop[r]))),
    'mild_2050': {k: int(sum(1 for r in range(NR) if hasU[r] and P['hot'][k][0.5][U[r], -1] < 5)) for k in SCEN},
    'pop_total': round(float(pop[hasU].sum())),
}
print(json.dumps(stats))


def r1(a):
    return [None if not np.isfinite(x) else round(float(x), 1) for x in a]


out = {
    'vintage': 'Copernicus ECDE v2.0: ERA5 1991–2020 and EURO-CORDEX projections; AWS Terrain Tiles; ESA WorldCover 2021',
    'years': YEARS,
    'paths': {'s45': 'If emissions fall (RCP4.5)', 's85': "If they don't (RCP8.5)"},
    'regions': REG,
    'unit_of': unit_of,
    'units': UNITS,
    'unit_name': [unit_name.get(u) for u in range(len(UNITS))],
    'unit_country': [unit_country[u] for u in range(len(UNITS))],
    'base': {k: r1(v) for k, v in base.items()},
    'path': {v: {k: {q: [r1(row) for row in P[v][k][qq]] for q, qq in (('lo', 0.17), ('mid', 0.5), ('hi', 0.83))} for k in SCEN} for v in P},
    'f2050': {k: {v: r1(fut[k][v]) for v in ('tjja', 'tdjf', 'pjja')} for k in SCEN},
    'twin': TW,
    'coast': coast,
    'coast_fields': ['low_km2', 'low_land_share', 'people_on_low_land'],
    'stats': stats,
    'notes': {
        'path': 'Each year is the middle of a 21-year average of the EURO-CORDEX models (the ensemble median), shifted onto the ERA5 1991–2020 values. The range is the 17th to 83rd percentile of the models.',
        'twin': "A climate twin is the region whose 1991–2020 climate is closest to this region's 2050 climate: hot days, tropical nights, summer and winter mean temperature and summer rain. It is at least 300 km away.",
        'coast': 'Land at or below 5 m within 100 km of the sea. Dykes, dunes and storm surges are not modelled, so this is exposure, not a flood forecast.',
    },
}
with open(OUT + '/climate.json', 'w') as f:
    json.dump(out, f, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
print('climate.json', os.path.getsize(OUT + '/climate.json') // 1024, 'KB')

# --- lenses ----------------------------------------------------------------------------------------------------------
L = load_json(OUT + '/lenses.json')
if not any(g['id'] == 'climate' for g in L['groups']):
    L['groups'].append({'id': 'climate', 'name': 'Climate'})


def per_hex(v):
    return [None if county[i] < 0 or unit_of[county[i]] < 0 or v[unit_of[county[i]]] is None or not np.isfinite(v[unit_of[county[i]]])
            else round(float(v[unit_of[county[i]]]), 1) for i in range(S)]


HEAT = ['#20304a', '#3f5d7a', '#8fa6a0', '#e6c37a', '#e0823f', '#b8352f', '#6e1424']
new = [
    {'id': 'hot_days', 'group': 'climate', 'name': 'Hot days', 'icon': 'l-heat', 'emoji': '\U0001F321️',
     'unit': 'days above 30 °C a year', 'format': 'float', 'scale': 'sqrt', 'domain': [0, 90], 'ramp': HEAT, 'higher_is': 'bad',
     'source': 'copernicus_ecde', 'values': per_hex(base['hot']),
     'description': 'Days a year when the temperature reaches 30 °C, averaged over 1991–2020 (ERA5, per NUTS 2 region). Has a 2050 dial: push it forward and pick an emissions path.',
     'note': '1991–2020 average. Open the 2050 dial to see where it is heading.'},
    {'id': 'tropical_nights', 'group': 'climate', 'name': 'Tropical nights', 'icon': 'l-night', 'emoji': '\U0001F319',
     'unit': 'nights above 20 °C a year', 'format': 'float', 'scale': 'sqrt', 'domain': [0, 90], 'ramp': HEAT, 'higher_is': 'bad',
     'source': 'copernicus_ecde', 'values': per_hex(base['trop']),
     'description': 'Nights a year when the temperature stays above 20 °C, averaged over 1991–2020 (ERA5, per NUTS 2 region). Warm nights are what make heatwaves dangerous. Has a 2050 dial.',
     'note': '1991–2020 average. Open the 2050 dial to see where it is heading.'},
    {'id': 'low_coast', 'group': 'climate', 'name': 'Low-lying land', 'icon': 'l-flood', 'emoji': '\U0001F30A',
     'unit': 'share of the hex at or below 5 m', 'format': 'pct', 'scale': 'sqrt', 'domain': [0, 0.6],
     'ramp': ['#2a2c2e', '#33454f', '#2f6a86', '#3f95c2', '#86c7ea', '#e6f6ff'], 'higher_is': 'bad', 'source': 'terrarium',
     'values': hex_low,
     'description': out['notes']['coast'] + ' Elevation from AWS Terrain Tiles (SRTM, EU-DEM) at about 300 m, water removed with ESA WorldCover 2021.',
     'note': f"About {stats['pop_low_coast'] / 1e6:.0f} million people live at or below 5 m."},
]
ids = {l['id'] for l in new}
L['lenses'] = [l for l in L['lenses'] if l['id'] not in ids] + new
with open(OUT + '/lenses.json', 'w') as f:
    json.dump(L, f, ensure_ascii=False, separators=(',', ':'))
print('lenses.json: climate lenses added')
