"""More lenses for lenses.json: Children, Growth since 2000, Employment rate, Temperature, Warming, Rainfall, Rainfall
change, Vineyards, Olive groves, Orchards and Forest height. Run after build_climate.py (it adds to the groups that
build_lenses.py and build_climate.py made).

People and prosperity (Eurostat, fetched by es.py):
  children      share of residents aged 0-14, NUTS 3 (demo_r_pjanind3, PC_Y0_14)
  growth_2000   population change from 1 January 2000 to the latest year (demo_r_pjanaggr3). Where a NUTS 3 region was
                redrawn and has no 2000 figure, it takes the change of the smallest parent region (NUTS 2, 1, country)
                that has both years.
  employment    employment rate, ages 20-64, NUTS 2 (lfst_r_lfe2emprt), the EU's headline jobs target measure
Land use (Eurostat Integrated Farm Statistics, ef_lus_allcrops, NUTS 2, latest of 2023 or 2020):
  vineyards     grapes (W1000), olives (O1000) and orchards (fruit, berries and nuts F0000 plus citrus T0000), each as a
                share of the NUTS 2 region's land area
Climate (ERA5-Land monthly means, Copernicus Climate Data Store, fetched by cds.py; needs CDSAPI_KEY):
  temperature   mean 2 m air temperature, 1996-2025
  warming       1996-2025 minus 1961-1990
  rainfall      mean yearly precipitation, 1996-2025
  rain_change   1996-2025 against 1961-1990, in per cent
  Sampled on a 2 km lattice over every land hex from the 0.1 degree (about 9 km) grid and averaged per hex.
Forest height (Meta and WRI Global Canopy Height Map, 2024, CC-BY 4.0, read from the public AWS bucket):
  forest_height mean canopy height of the hex's treed ground. A 1 km lattice over every land hex reads the map's
                1/4000-degree (about 25 m) average-height grid (one pixel row per km); samples at least 5 m tall count as trees, and the hex
                shows their mean height. Hexes where under 3% of samples are trees show no value.

Needs raw/nuts (NUTS 3 polygons, 2021 and 2024, as for build_world.py) and network access to Eurostat, the CDS and AWS.
Downloads are cached in raw/eurostat, raw/cds and raw/chm.
"""
import os
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import shapely
from shapely.geometry import shape
import es
from common import *

world = load_json(OUT + '/world.json')
counties = load_json(OUT + '/counties.json')
cols = counties['columns']
REG = [c['geoid'] for c in world['counties']]
rows = {r[0]: dict(zip(cols, r)) for r in counties['rows']}
NR = len(REG)
grid = Grid(**world['grid'])
S = grid.size
county = np.array(world['county'])
LAND = np.where(county >= 0)[0]

nuts3 = nuts3_features()
assert [f['properties']['id'] for f in nuts3] == REG
g3 = [shape(f['geometry']) for f in nuts3]
proj = Proj(min(g.bounds[0] for g in g3) / 1000, max(g.bounds[3] for g in g3) / 1000, 150.0)


def lattice(step):
    """Sample points every `step` km over every land hex: (hex index, lon, lat, x3035, y3035)."""
    cx, cy = grid.center(LAND)
    offs = np.arange(-grid.radius + step / 2, grid.radius, step)
    ox, oy = [a.ravel() for a in np.meshgrid(offs, offs)]
    PX = (cx[:, None] + ox[None, :]).ravel()
    PY = (cy[:, None] + oy[None, :]).ravel()
    PC = grid.cell_at(PX, PY)
    keep = PC == np.repeat(LAND, len(ox))
    PX, PY, PC = PX[keep], PY[keep], PC[keep]
    X3, Y3 = proj.to3035(PX, PY)
    LON, LAT = TO4326.transform(X3, Y3)
    return PC, np.asarray(LON), np.asarray(LAT), X3, Y3


def hex_mean(PC, v, ok=None):
    ok = np.isfinite(v) if ok is None else ok & np.isfinite(v)
    n = np.bincount(PC[ok], minlength=S)
    s = np.bincount(PC[ok], weights=v[ok], minlength=S)
    out = [None] * S
    for i in LAND:
        if n[i]:
            out[i] = float(s[i] / n[i])
    return out


# --- region weights per hex: which NUTS 3 regions a hex's 2 km samples fall in -----------------------------------------
PC2, LON2, LAT2, X2, Y2 = lattice(2.0)
print('2 km samples', len(PC2))
tree = shapely.STRtree(g3)
pi, gi = tree.query(shapely.points(X2, Y2), predicate='within')
preg = np.full(len(PC2), -1)
preg[pi] = gi
cell_samples = {}
for c, r in zip(PC2[preg >= 0].tolist(), preg[preg >= 0].tolist()):
    d = cell_samples.setdefault(c, {})
    d[r] = d.get(r, 0) + 1
for i in LAND:  # a hex whose samples all miss the generalised polygons keeps its own region
    cell_samples.setdefault(int(i), {int(county[i]): 1})
dens = [rows[g]['density'] or 1.0 for g in REG]


def spread(val, people=True):
    """Region values -> hexes: the mean of the regions under a hex's samples, weighted by population when `people`
    (as build_lenses.py does) and by area otherwise."""
    out = [None] * S
    for c, sm in cell_samples.items():
        num = den = 0.0
        for ri, n in sm.items():
            v = val[ri]
            if v is None:
                continue
            w = n * (dens[ri] if people else 1)
            num += v * w; den += w
        if den > 0:
            out[c] = num / den
    return out


def gaps(val):
    return sorted({g[:2] for g, v in zip(REG, val) if v is None})


# --- Eurostat -----------------------------------------------------------------------------------------------------------
print('children')
ch = es.latest('demo_r_pjanind3', indic_de='PC_Y0_14', unit='PC', sinceTimePeriod=2022)
children = [ch[g][0] / 100 if g in ch else None for g in REG]
print('  no data:', gaps(children))

print('employment rate')
em = es.latest('lfst_r_lfe2emprt', sex='T', age='Y20-64', unit='PC', sinceTimePeriod=2022)
employment = [em[g[:4]][0] / 100 if g[:4] in em else None for g in REG]
EMP_YEAR = max(v[1] for v in em.values())
print('  no data:', gaps(employment), 'year', EMP_YEAR)

print('growth since 2000')
Y0 = 2000
pop_rows, _ = es.table('demo_r_pjanaggr3', sex='T', age='TOTAL', unit='NR', sinceTimePeriod=Y0)
pop = {}
for co, v in pop_rows:
    pop.setdefault(co['geo'], {})[int(co['time'])] = v
cov = {}
for d in pop.values():
    for y in d:
        cov[y] = cov.get(y, 0) + 1
Y1 = max(y for y, n in cov.items() if n >= 0.8 * max(cov.values()))  # newest year most regions have
growth_2000, from_parent = [], 0
for g in REG:
    v = None
    for k, code in enumerate((g, g[:4], g[:3], g[:2])):
        d = pop.get(code, {})
        if d.get(Y0) and d.get(Y1):
            v = d[Y1] / d[Y0] - 1
            from_parent += k > 0
            break
    growth_2000.append(v)
print('  years', Y0, Y1, '; from a parent region:', from_parent, '; no data:', gaps(growth_2000))

print('farm crops')
crop_rows, _ = es.table('ef_lus_allcrops', statinfo='TOTAL', so_eur='TOTAL', uaarea='TOTAL', unit='HA',
                        crops=['W1000', 'O1000', 'F0000', 'T0000'], sinceTimePeriod=2020)
crops = {}
for co, v in crop_rows:
    crops.setdefault(co['geo'], {}).setdefault(co['time'], {})[co['crops']] = v
land2 = {}
for g in REG:
    land2[g[:4]] = land2.get(g[:4], 0) + (rows[g]['land_km2'] or 0)


def crop_share(codes):
    out = []
    for g in REG:
        d = crops.get(g[:4])
        if not d or not land2.get(g[:4]):
            out.append(None); continue
        t = d[max(d)]  # a crop missing from a region's survey row is a crop the region does not grow (Eurostat omits zeros)
        ha = sum(t.get(c, 0) for c in codes)
        out.append(min(ha / (land2[g[:4]] * 100), 1.0))
    return out


vineyards, olives, orchards = crop_share(['W1000']), crop_share(['O1000']), crop_share(['F0000', 'T0000'])
CROP_YEARS = sorted({max(d) for d in crops.values()})
print('  years', CROP_YEARS, '; no data:', gaps(vineyards))

# --- ERA5-Land climate --------------------------------------------------------------------------------------------------
import cds
import xarray as xr

P_OLD, P_NEW = (1961, 1990), (1996, 2025)


def era(y0, y1, var):
    return cds.retrieve('reanalysis-era5-land-monthly-means', {
        'product_type': ['monthly_averaged_reanalysis'], 'variable': [var],
        'year': [str(y) for y in range(y0, y1 + 1)], 'month': [f'{m:02d}' for m in range(1, 13)], 'time': ['00:00'],
        'area': [72, -25, 33, 46], 'data_format': 'netcdf', 'download_format': 'unarchived'})


def climatology(period, var, short):
    ds = xr.open_dataset(era(*period, var))
    da = ds[short]
    tdim = 'valid_time' if 'valid_time' in da.dims else 'time'
    days = da[tdim].dt.days_in_month.astype(float)
    nyears = period[1] - period[0] + 1
    assert da.sizes[tdim] == 12 * nyears, (var, period, da.sizes)
    if short == 't2m':  # day-weighted mean of the monthly means, in degC
        a = (da * days).sum(tdim, skipna=False) / days.sum() - 273.15  # sea cells stay NaN
    else:  # monthly means of daily totals (m/day) -> mm a year
        a = (da * days).sum(tdim, skipna=False) * 1000 / nyears
    lat, lon = ds.latitude.values, ds.longitude.values
    return np.asarray(a.values, float), lat, lon


def fill(a, n=6):
    """Spread land values a few cells into the sea so coastal samples and small islands find a value."""
    a = a.copy()
    for _ in range(n):
        m = ~np.isfinite(a)
        if not m.any():
            break
        p = np.pad(a, 1, constant_values=np.nan)
        nb = np.stack([p[1 + dy:p.shape[0] - 1 + dy, 1 + dx:p.shape[1] - 1 + dx]
                       for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx])
        cnt = np.isfinite(nb).sum(0)
        s = np.nansum(nb, 0)
        upd = m & (cnt > 0)
        a[upd] = s[upd] / cnt[upd]
    return a


def sample(a, lat, lon):
    r = np.clip(np.round((lat[0] - LAT2) / (lat[0] - lat[1])).astype(int), 0, len(lat) - 1)
    c = np.clip(np.round((LON2 - lon[0]) / (lon[1] - lon[0])).astype(int), 0, len(lon) - 1)
    return a[r, c]


print('ERA5-Land')
T = {p: climatology(p, '2m_temperature', 't2m') for p in (P_OLD, P_NEW)}
R = {p: climatology(p, 'total_precipitation', 'tp') for p in (P_OLD, P_NEW)}
lat, lon = T[P_NEW][1], T[P_NEW][2]
t_new, t_old = fill(T[P_NEW][0]), fill(T[P_OLD][0])
r_new, r_old = fill(R[P_NEW][0]), fill(R[P_OLD][0])
temperature = hex_mean(PC2, sample(t_new, lat, lon))
warming = hex_mean(PC2, sample(t_new - t_old, lat, lon))
rainfall = hex_mean(PC2, sample(r_new, lat, lon))
rn, ro = hex_mean(PC2, sample(r_new, lat, lon)), hex_mean(PC2, sample(r_old, lat, lon))
rain_change = [None if a is None or not b else a / b - 1 for a, b in zip(rn, ro)]
print('  hexes with temperature', sum(v is not None for v in temperature), 'of', len(LAND))

# --- forest height (Meta / WRI canopy height) ---------------------------------------------------------------------------
CHM = 'https://dataforgood-fb-data.s3.amazonaws.com/forests/v1/alsgedi_global_v6_float_epsg4326_v3_10deg/meta_chm_lat={top:.1f}_lon={left:.1f}_avg.tif'
RES = 0.00025
CHM_DIR = RAW + '/chm'
os.makedirs(CHM_DIR, exist_ok=True)
PC1, LON1, LAT1, _, _ = lattice(1.0)
print('1 km samples', len(PC1))
TOP = (np.floor(LAT1 / 10) * 10 + 10).astype(int)
LEFT = (np.floor(LON1 / 10) * 10).astype(int)
BIN = 40  # read one pixel row in 40 (1 km): each sample moves at most ~0.5 km north or south to the nearest one read
ROW = np.clip(np.round((TOP - LAT1) / RES / BIN).astype(int) * BIN, 0, 39999)
COL = np.clip(((LON1 - LEFT) / RES).astype(int), 0, 39999)
chm = np.full(len(PC1), 65535, np.uint16)


def read_tile(key):
    top, left = key
    m = np.where((TOP == top) & (LEFT == left))[0]
    cache = f'{CHM_DIR}/lat{top}_lon{left}_{len(m)}.npy'
    if os.path.exists(cache):
        return m, np.load(cache)
    import rasterio
    from rasterio.windows import Window
    os.environ.setdefault('GDAL_DISABLE_READDIR_ON_OPEN', 'EMPTY_DIR')
    try:
        src = rasterio.open(CHM.format(top=float(top), left=float(left)))
    except Exception as e:  # no tile: open sea or nothing mapped
        print('  no canopy tile', top, left, str(e)[:80], flush=True)
        return m, None
    out = np.full(len(m), 65535, np.uint16)
    order = np.argsort(ROW[m], kind='stable')
    rs = ROW[m][order]
    bounds = np.flatnonzero(np.diff(rs)) + 1
    with src:
        for grp in np.split(np.arange(len(rs)), bounds):
            row = src.read(1, window=Window(0, int(rs[grp[0]]), 40000, 1))[0]
            out[order[grp]] = row[COL[m][order[grp]]]
    np.save(cache, out)
    print('  canopy tile', top, left, len(bounds) + 1, 'rows', flush=True)
    return m, out


tiles = sorted(set(zip(TOP.tolist(), LEFT.tolist())))
with ThreadPoolExecutor(12) as ex:
    for m, vals in ex.map(read_tile, tiles):
        if vals is not None:
            chm[m] = vals
valid = chm != 65535
tall = valid & (chm >= 500)
nv = np.bincount(PC1[valid], minlength=S)
nt = np.bincount(PC1[tall], minlength=S)
ht = np.bincount(PC1[tall], weights=chm[tall].astype(float) / 100, minlength=S)
forest_height = [None] * S
for i in LAND:
    if nv[i] and nt[i] >= 0.03 * nv[i]:
        forest_height[i] = float(ht[i] / nt[i])
print('  hexes with forest height', sum(v is not None for v in forest_height))

# --- lenses -------------------------------------------------------------------------------------------------------------
L = load_json(OUT + '/lenses.json')


def domain(vals, lo=2, hi=98):
    v = np.array([x for x in vals if x is not None], float)
    return [round(float(np.percentile(v, lo)), 4), round(float(np.percentile(v, hi)), 4)]


def lens(id, group, name, icon, emoji, unit, fmt, values, ramp, higher='neutral', scale='linear', source='', desc='',
         note=None, dom=None, digits=4):
    vals = [None if v is None else round(v, digits) for v in values]
    o = {'id': id, 'group': group, 'name': name, 'icon': icon, 'emoji': emoji, 'unit': unit, 'format': fmt, 'scale': scale,
         'domain': dom or domain(vals), 'ramp': ramp, 'higher_is': higher, 'source': source, 'description': desc, 'values': vals}
    if note:
        o['note'] = note
    return o


TEAL = ['#0b2a2e', '#165a5c', '#2f8f83', '#7cc29a', '#d4ecb0', '#ffffe0']
DIVERGE = ['#7a1f3d', '#b9534f', '#e3c29c', '#c9d9c0', '#5fae9a', '#1f6b6b']
N2 = 'Published for NUTS 2 regions: every NUTS 3 region inside one shares its value.'
crop_note = (f'Farm survey {CROP_YEARS[-1]}' + (f' ({CROP_YEARS[0]} where newer figures are missing)' if len(CROP_YEARS) > 1 else '')
             + '. Published for NUTS 2 regions, so every hex in a region shares its share. No data for the UK, Türkiye and most of the Western Balkans.')
ERA_NOTE = 'ERA5-Land reanalysis on a ~9 km grid, averaged over the hex.'

new = {
    'people': [
        lens('children', 'people', 'Children', 'l-children', '\U0001F9D2', 'share of residents aged under 15', 'pct',
             spread(children), ['#1d1433', '#3b2a6b', '#5f4da0', '#8f7fc8', '#c3b6e6', '#f2ecff'], source='eurostat_demo', dom=[0.1, 0.25],
             desc='Share of the population aged 0–14 on 1 January, NUTS 3 regions (demo_r_pjanind3).'),
        lens('growth_2000', 'people', f'Growth since {Y0}', 'l-growth', '\U0001F4C8', f'population change {Y0}–{Y1}', 'pct',
             spread(growth_2000), DIVERGE, source='eurostat_demo', dom=[-0.25, 0.25],
             desc=f'Population change between 1 January {Y0} and 1 January {Y1} (demo_r_pjanaggr3). The long view behind the Growth lens: '
                  'where Europe has emptied out and where it has filled up over a generation.',
             note=f'Where a NUTS 3 region was redrawn since {Y0} it shows the change of its NUTS 2 region (or larger), '
                  f'which has a continuous series. {from_parent} of {NR} regions.'),
    ],
    'prosperity': [
        lens('employment', 'prosperity', 'Employment rate', 'l-employment', '\U0001F477', 'share of people aged 20–64 in work', 'pct',
             spread(employment), TEAL, 'good', source='eurostat_lfs',
             desc=f'Employed people as a share of everyone aged 20–64 (lfst_r_lfe2emprt, {EMP_YEAR}). Unlike unemployment, it also '
                  'counts people who are not looking for work. The EU target for 2030 is 78%.', note=N2),
    ],
    'land': [
        lens('vineyards', 'land', 'Vineyards', 'l-vineyard', '\U0001F347', 'vineyards as a share of land', 'pct', spread(vineyards, False),
             ['#1c0f1a', '#3d1633', '#66204d', '#93315f', '#c4607a', '#f2b6b8'], scale='sqrt', source='eurostat_ifs', dom=[0, 0.1],
             desc='Area of farms’ grape vines (for wine and for the table) as a share of the region’s land (Integrated Farm Statistics, ef_lus_allcrops, W1000).',
             note=crop_note),
        lens('olives', 'land', 'Olive groves', 'l-olive', '\U0001FAD2', 'olive groves as a share of land', 'pct', spread(olives, False),
             ['#1a1a0c', '#3a3a14', '#5e5e1f', '#86872f', '#b4b65a', '#e4e6a6'], scale='sqrt', source='eurostat_ifs', dom=[0, 0.25],
             desc='Area of farms’ olive trees as a share of the region’s land (Integrated Farm Statistics, ef_lus_allcrops, O1000).',
             note=crop_note),
        lens('orchards', 'land', 'Orchards', 'l-orchard', '\U0001F34E', 'orchards as a share of land', 'pct', spread(orchards, False),
             ['#1f0f0a', '#47201a', '#74352a', '#a6553b', '#d48a5d', '#f6cfa6'], scale='sqrt', source='eurostat_ifs', dom=[0, 0.06],
             desc='Area of fruit, berry, nut and citrus plantations as a share of the region’s land (Integrated Farm Statistics, '
                  'ef_lus_allcrops, F0000 + T0000). Grapes and olives are counted in their own lenses.',
             note=crop_note),
        lens('forest_height', 'land', 'Forest height', 'l-forest-height', '\U0001F332', 'mean canopy height of treed land, metres', 'm',
             forest_height, ['#13200f', '#1f3d1a', '#2f5e27', '#4a8538', '#86b45c', '#d9efa8'], source='meta_chm', dom=[7, 17], digits=1,
             desc='How tall the trees are: the mean canopy height of the hex’s ground covered by trees at least 5 m tall '
                  '(Meta and WRI Global Canopy Height Map, ~25 m cells read on a 1 km lattice).',
             note='Hexes where trees cover under 3% of the ground show no value. The model tends to underestimate the tallest forests.'),
    ],
    'climate': [
        lens('temperature', 'climate', 'Temperature', 'l-temperature', '\U0001F321️', 'mean temperature, °C', 'deg', temperature,
             ['#2b3a67', '#3f6e9a', '#7fb0c4', '#e8dca8', '#e59a55', '#b8402f'], source='era5_land', dom=[0, 18], digits=1,
             desc=f'Mean air temperature 2 m above ground over the year, averaged over {P_NEW[0]}–{P_NEW[1]}.', note=ERA_NOTE),
        dict(lens('warming', 'climate', 'Warming', 'l-warming', '\U0001F4C8', f'°C warmer than {P_OLD[0]}–{P_OLD[1]}', 'deg', warming,
                  ['#f2eee6', '#f3d3a6', '#eaa56e', '#d8693f', '#b2352a', '#6e1424'], 'bad', source='era5_land', dom=[0.6, 1.8], digits=2,
                  desc=f'How much warmer {P_NEW[0]}–{P_NEW[1]} was than {P_OLD[0]}–{P_OLD[1]}, year-round mean temperature.',
                  note=ERA_NOTE), signed=True),
        lens('rainfall', 'climate', 'Rainfall', 'l-rain', '\U0001F327️', 'precipitation, mm a year', 'mm', rainfall,
             ['#5a3a1a', '#9a7a3e', '#d8cf9a', '#9fc9c9', '#4a90b8', '#1d3f7a'], scale='log', source='era5_land', dom=[300, 2000], digits=0,
             desc=f'Mean yearly precipitation (rain and melted snow), {P_NEW[0]}–{P_NEW[1]}.', note=ERA_NOTE),
        lens('rain_change', 'climate', 'Rainfall change', 'l-rain-change', '\U0001F326️', f'change against {P_OLD[0]}–{P_OLD[1]}', 'pct',
             rain_change, ['#8a4a14', '#c98b4a', '#ecd9b0', '#c4e0d8', '#5fae9a', '#1f6b6b'], source='era5_land', dom=[-0.15, 0.15],
             desc=f'Yearly precipitation in {P_NEW[0]}–{P_NEW[1]} against {P_OLD[0]}–{P_OLD[1]}. Brown is drier, green wetter.',
             note=ERA_NOTE + ' Rainfall trends in reanalysis are less certain than temperature trends; read small changes as no change.'),
    ],
}
AFTER = {'people': 'growth', 'prosperity': 'unemployment', 'land': 'farmland', 'climate': None}
ids = {l['id'] for ls in new.values() for l in ls}
lst = [l for l in L['lenses'] if l['id'] not in ids]
for g, ls in new.items():
    if AFTER[g] is None:  # first in its group
        k = next(n for n, l in enumerate(lst) if l['group'] == g)
    else:
        k = next(n for n, l in enumerate(lst) if l['id'] == AFTER[g]) + 1
    if g == 'land':  # vineyards, olives and orchards after farmland; forest height after forest
        lst[k:k] = ls[:3]
        k = next(n for n, l in enumerate(lst) if l['id'] == 'forest') + 1
        ls = ls[3:]
    lst[k:k] = ls
L['lenses'] = lst
with open(OUT + '/lenses.json', 'w') as f:
    json.dump(L, f, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
print('lenses.json:', len(ids), 'lenses added;', len(lst), 'in all')
