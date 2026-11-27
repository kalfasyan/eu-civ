"""Bosnia and Herzegovina (BA) and Kosovo* (XK): the two Western Balkan countries Eurostat does not map by NUTS region.

Run last, after build_more_lenses.py. It adds both countries on top of the NUTS build without touching the other regions:
each becomes one region of its own (BA000, XK000), the way Montenegro is one NUTS 3 region (ME000), and every data file
gets them with the same rules as everywhere else. Figures come from Eurostat's national tables (Bosnia and Herzegovina
and Kosovo report to Eurostat as candidate and potential candidate countries); anything Eurostat does not publish for
them stays empty (null) rather than estimated.

  hexes      GISCO country boundaries (CNTR_RG_10M_2024, the same 1:10M generalisation as Nuts2json). Only hexes that
             were land outside the map (owner -2) can change; the build_world rule decides which country owns each one.
  terrain    already in world.json for those hexes (elevation, land cover and relief are computed for all land).
  economy    demo_gind (population), demo_pjan / demo_pjanind (ages), nama_10_gdp, nama_10_pc, nama_10_a10(_e) (GVA and
             jobs by industry), lfsa_urgan, edat_lfse_03, isoc_ci_it_h, rd_e_gerdtot, htec_emp_nat2, demo_mlexpec.
  cities     the build_econ rule for countries without Eurostat metro regions: one city per region, at its Natural Earth
             place of 250,000+ people or its capital, so Sarajevo and Pristina (GISCO has no LAU populations for either).
  climate    the ECDE indicators come on NUTS 2 regions only, so Hot days and Tropical nights stay empty; low-lying land
             is measured as in build_climate (Copernicus DEM).
  more lenses  build_more_lenses.py's children, employment rate and growth since 2000 from the national tables, and forest
             height from the canopy height map. ERA5-Land temperature and rainfall (needs a CDS key) and the farm-survey
             crops (no survey for either country) stay empty.
  sites      WRI power plants (BIH, KOS), Natural Earth roads, rail and rivers, the UNESCO cultural-wonder rule.
             Eurostat publishes no port or airport traffic for either country, so none are drawn.

*This designation is without prejudice to positions on status, and is in line with UNSCR 1244/1999 and the ICJ Opinion
on the Kosovo declaration of independence (the wording Eurostat uses).
"""
import csv, math, os, re, sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import urllib.request
import numpy as np
import shapely
from shapely.geometry import shape, Point
from PIL import Image
import es
from common import *

NEW = ['BA', 'XK']
NAMES = {'BA': 'Bosnia and Herzegovina', 'XK': 'Kosovo*'}
REGION_NAMES = {'BA': 'Bosna i Hercegovina', 'XK': 'Kosovo*'}
LANGS = {'BA': ['bs', 'hr', 'sr'], 'XK': ['sq', 'sr']}
YEAR_POP = 2025
RIDS = [c + '000' for c in NEW]

world = load_json(OUT + '/world.json')
if any(c['geoid'] in RIDS for c in world['counties']):
    sys.exit('Bosnia and Herzegovina and Kosovo are already on the map: rebuild from build_world.py first.')

# ---------------------------------------------------------------- projection and grid (as build_world) -------------
nuts = nuts3_features()
nuts_geoms = [shape(f['geometry']) for f in nuts]
minx = min(g.bounds[0] for g in nuts_geoms) / 1000
maxy = max(g.bounds[3] for g in nuts_geoms) / 1000
proj = Proj(minx, maxy, world['margin'])
grid = Grid(**world['grid'])
S = grid.size
W, H = world['width'], world['height']
STEP = 4.0
assert abs(round(float(proj(19.8189, 41.3275)[0]), 1) - 2656.0) < 0.2, 'projection does not match world.json'

REG = [c['geoid'] for c in world['counties']]
NOLD = len(REG)
COUNTRIES = [s['abbr'] for s in world['states']]
NC_OLD = len(COUNTRIES)
owner = np.array(world['owner']); county = np.array(world['county'])
owner0 = owner.copy()

# Outlines from the same GISCO 1:10M country file build_world uses for land (Nuts2json cntrg). GISCO draws Kosovo inside
# Serbia's outline and Serbia's NUTS regions leave it out, so Kosovo is Serbia's outline minus Serbia's NUTS 3 regions
# (the largest piece; the rest are generalisation slivers along the border).
cntrg = {f['properties']['id']: shape(f['geometry']).buffer(0) for f in load_json(RAW + '/nuts/cntrg.json')['features']}
rest = cntrg['RS'].difference(shapely.union_all([g.buffer(0) for f, g in zip(nuts, nuts_geoms) if f['properties']['id'][:2] == 'RS']))
cntr = {'BA': cntrg['BA'], 'XK': max(getattr(rest, 'geoms', [rest]), key=lambda g: g.area)}
print('outline km2', {c: round(g.area / 1e6) for c, g in cntr.items()})
# Bosnia and Herzegovina has no Eurostat land area: its GISCO 1:1M outline gives it.
cntr01 = {f['properties']['CNTR_ID']: shape(f['geometry']) for f in load_json(RAW + '/gisco/CNTR_RG_01M_2024_3035.geojson')['features']
          if f['properties']['CNTR_ID'] == 'BA'}

# ---------------------------------------------------------------- hexes --------------------------------------------
# The 4 km sample lattice of build_world, kept only in hexes that are land outside the map today.
xs = np.arange(STEP / 2, W, STEP)
ys = np.arange(STEP / 2, H, STEP)
PX, PY = np.meshgrid(xs, ys)
PX, PY = PX.ravel(), PY.ravel()
PC = grid.cell_at(PX, PY)
k = (PC >= 0)
k[k] = owner[PC[k]] == -2
PX, PY, PC = PX[k], PY[k], PC[k]
X3, Y3 = proj.to3035(PX, PY)
pts = shapely.points(X3, Y3)


def assign(geoms, pts):
    tree = shapely.STRtree(geoms)
    out = np.full(len(pts), -1, int)
    pi, gi = tree.query(pts, predicate='within')
    out[pi] = gi
    return out


lake_geoms = []
for fn in ('ne_10m_lakes', 'ne_10m_lakes_europe'):
    for f in load_json(f'{RAW}/ne/{fn}.geojson')['features']:
        g = shape(f['geometry'])
        if g.bounds[2] < 12 or g.bounds[0] > 25 or g.bounds[3] < 40 or g.bounds[1] > 47:
            continue
        lake_geoms.append(shapely.transform(g, lambda c: np.column_stack(TO3035.transform(c[:, 0], c[:, 1]))))
land_geoms = [shape(f['geometry']) for f in load_json(RAW + '/nuts/cntrg.json')['features']]
all_geoms = nuts_geoms + [cntr[c] for c in NEW]  # region index: NUTS 3 regions, then BA000, XK000
p_reg = assign(all_geoms, pts)
p_lake = assign(lake_geoms, pts) >= 0 if lake_geoms else np.zeros(len(pts), bool)
p_land = ((assign(land_geoms, pts) >= 0) | (p_reg >= 0)) & ~p_lake
p_reg[p_lake] = -1

new_cells, cell_samples = [], {}
for i in np.unique(PC):
    idx = np.where(PC == i)[0]
    land = p_land[idx]
    nl = land.sum()
    if nl * 2 < len(idx):
        continue
    reg = p_reg[idx][land]
    reg_in = reg[reg >= 0]
    if len(reg_in) * 2 < nl:
        continue
    if not (reg_in >= NOLD).any():  # only hexes that hold some of the two countries
        continue
    vals, cnt = np.unique(reg_in, return_counts=True)
    ri = int(vals[np.argmax(cnt)])
    cc = RIDS[ri - NOLD][:2] if ri >= NOLD else REG[ri][:2]
    owner[i] = COUNTRIES.index(cc) if cc in COUNTRIES else NC_OLD + NEW.index(cc)
    county[i] = ri
    cell_samples[int(i)] = {int(v): int(c) for v, c in zip(vals, cnt)}
    new_cells.append(int(i))
REG_ALL = REG + RIDS
CTRY_ALL = COUNTRIES + NEW
for i in new_cells:
    if owner[i] < NC_OLD:
        print('hex', i, 'goes to', CTRY_ALL[owner[i]], '(its NUTS region holds most of the hex)')
print('new hexes', {c: int((owner == NC_OLD + k).sum()) for k, c in enumerate(NEW)})
CELLS = {c: np.where(owner == NC_OLD + k)[0] for k, c in enumerate(NEW)}

# ---------------------------------------------------------------- Eurostat national tables ---------------------------
GEO = NEW


def latest(ds, max_year=None, min_year=None, **f):
    out = {}
    for co, v in es.table(ds, geo=GEO, **f)[0]:
        y = int(co['time'][:4])
        if (max_year and y > max_year) or (min_year and y < min_year):
            continue
        if co['geo'] not in out or y > out[co['geo']][1]:
            out[co['geo']] = (v, y)
    return out


def series(ds, key=None, **f):
    out = defaultdict(dict)
    for co, v in es.table(ds, geo=GEO, **f)[0]:
        out[(co['geo'], co[key]) if key else co['geo']][int(co['time'][:4])] = v
    return out


val = lambda d, c: d[c][0] if c in d else None
pop_s = series('demo_gind', indic_de='JAN', sinceTimePeriod=2000)
pop = {c: max(((y, v) for y, v in pop_s[c].items() if y <= YEAR_POP), default=(None, None)) for c in NEW}
print('population', pop)
age_rows = defaultdict(lambda: defaultdict(float))
age_year = {}
for co, v in es.table('demo_pjan', geo=GEO, sex='T', unit='NR', sinceTimePeriod=2015)[0]:
    age_year[co['geo']] = max(age_year.get(co['geo'], 0), int(co['time']))
for co, v in es.table('demo_pjan', geo=GEO, sex='T', unit='NR', sinceTimePeriod=2015)[0]:
    g, a = co['geo'], co['age']
    if int(co['time']) != age_year[g] or a in ('TOTAL', 'UNK'):
        continue
    n = 0 if a == 'Y_LT1' else 85 if a == 'Y_OPEN' else int(a[1:]) if a[1:].isdigit() else None
    if n is None:
        continue
    lo = min(85, n // 5 * 5)
    key = 'Y_LT5' if lo == 0 else 'Y_GE85' if lo >= 85 else f'Y{lo}-{lo + 4}'
    age_rows[g][key] += v
ages = {c: (dict(age_rows[c], TOTAL=sum(age_rows[c].values())) if age_rows[c] else None) for c in NEW}
medage = latest('demo_pjanind', indic_de='MEDAGEPOP', min_year=2022)
gdp = latest('nama_10_gdp', unit='CP_MEUR', na_item='B1GQ', min_year=2021)
gdp_pps = latest('nama_10_pc', unit='CP_PPS_EU27_2020_HAB', na_item='B1GQ', min_year=2021)
A10 = ['TOTAL', 'A', 'B-E', 'C', 'F', 'G-I', 'J', 'K', 'L', 'M_N', 'O-Q', 'R-U']
emp_s = series('nama_10_a10_e', key='nace_r2', unit='THS_PER', na_item='EMP_DC', nace_r2=A10, sinceTimePeriod=2000)
gva_s = series('nama_10_a10', key='nace_r2', unit='CP_MEUR', na_item='B1G', nace_r2=A10, sinceTimePeriod=2019)


def latest_table(s, c):
    """{nace: (v, year)} for the latest year with every industry."""
    yrs = [y for y in s.get((c, 'TOTAL'), {}) if all(y in s.get((c, n), {}) for n in A10)]
    if not yrs:
        return None
    y = max(yrs)
    return {n: (s[(c, n)][y], y) for n in A10}


emp = {c: latest_table(emp_s, c) for c in NEW}
gva = {c: latest_table(gva_s, c) for c in NEW}
unemp_s = series('lfsa_urgan', sex='T', age='Y15-74', citizen='TOTAL', unit='PC', sinceTimePeriod=2000)
unemp = {c: max(((y, v) for y, v in unemp_s[c].items() if y >= 2021), default=(None, None)) for c in NEW}
edu = {k: latest('edat_lfse_03', isced11=k, sex='T', age='Y25-64', unit='PC', min_year=2021) for k in ('ED0-2', 'ED3_4', 'ED5-8')}
try:
    life = latest('demo_mlexpec', sex='T', age='Y_LT1', unit='YR', min_year=2020)
except Exception as e:  # Eurostat sometimes answers this one asynchronously; it has no recent value for either country
    print('life expectancy skipped:', e)
    life = {}
broad = latest('isoc_ci_it_h', indic_is='H_BROAD', unit='PC_HH', hhtyp='TOTAL', min_year=2018)
rd = latest('rd_e_gerdtot', sectperf='TOTAL', unit='PC_GDP', min_year=2018)
htec = latest('htec_emp_nat2', nace_r2='HTC', sex='T', unit='PC_EMP', min_year=2021)
area = latest('reg_area3', landuse='L0008', unit='KM2')
gdp_idx_s = series('nama_10_pc', unit='PC_EU27_2020_HAB_MPPS_CP', na_item='B1GQ', sinceTimePeriod=2000)
print('eurostat done')

IND = [('agriculture', 'A'), ('energy_mining', None), ('manufacturing', 'C'), ('construction', 'F'), ('trade', 'G-I'),
       ('information', 'J'), ('finance', 'K'), ('real_estate', 'L'), ('professional', 'M_N'), ('public_admin', 'O-Q'), ('arts', 'R-U')]


def ind_split(t, scale):
    if not t:
        return None
    o = {}
    for key, code in IND:
        o[key] = (t[code][0] if code else max(0.0, t['B-E'][0] - t['C'][0])) * scale
    return o


R = {}
for c, r in zip(NEW, RIDS):
    p = pop[c][1]
    a = val(area, c) or round(cntr01[c].area / 1e6)  # Eurostat land area, else the GISCO 1:1M outline (Bosnia)
    jobs = ind_split(emp[c], 1000)
    R[r] = dict(population=p, pop_year=pop[c][0], series={str(y): v for y, v in pop_s[c].items()}, area=a,
                employed=emp[c]['TOTAL'][0] * 1000 if emp[c] else None, jobs=jobs, jobs_year=emp[c]['TOTAL'][1] if emp[c] else None,
                gva=ind_split(gva[c], 1e6), gdp=val(gdp, c) and val(gdp, c) * 1e6, gdp_year=gdp[c][1] if c in gdp else None,
                gdp_pps=val(gdp_pps, c), median_age=val(medage, c), ages=ages[c], income=None, income_pps=None,
                unemployment=unemp[c][1], tertiary=val(edu['ED5-8'], c), edu_low=val(edu['ED0-2'], c), edu_mid=val(edu['ED3_4'], c),
                life=val(life, c), arope=None, broadband=val(broad, c), nights=None, rd=val(rd, c), htec=val(htec, c), cob=None)
    print(r, {k: v for k, v in R[r].items() if k not in ('series', 'ages', 'jobs', 'gva')})

# ---------------------------------------------------------------- cities (build_econ rule for countries without metros)
TOWN_MIN = 250000
best_place = {}
for f in load_json(RAW + '/ne/ne_10m_populated_places_simple.geojson')['features']:
    pr = f['properties']
    cc = 'XK' if pr.get('adm0name') == 'Kosovo' else pr.get('iso_a2')  # Natural Earth gives Kosovo no ISO code
    if cc not in NEW or ((pr.get('pop_max') or 0) < TOWN_MIN and not pr.get('adm0cap')):
        continue
    lon, lat = f['geometry']['coordinates']
    if not cntr[cc].contains(Point(*TO3035.transform(lon, lat))):
        continue
    key = (bool(pr.get('adm0cap')), pr.get('pop_max') or 0)
    if cc not in best_place or key > best_place[cc][0]:
        best_place[cc] = (key, pr.get('name'), lon, lat, bool(pr.get('adm0cap')), pr.get('pop_min') or 0)
print('cities', {c: v[1] for c, v in best_place.items()})

CX, CY = grid.center(np.arange(S))


def nearest_cell(x, y, allowed):
    d = (CX[allowed] - x) ** 2 + (CY[allowed] - y) ** 2
    return int(allowed[int(np.argmin(d))])


def yields(j, g):
    y = lambda *ks: None if not j or any(j[k] is None for k in ks) else round(sum(j[k] for k in ks))
    return {'food': y('agriculture'), 'production': y('manufacturing', 'energy_mining', 'construction'), 'gold': g,
            'science': y('information', 'professional'), 'culture': y('arts')}


new_cities = []
for c, r in zip(NEW, RIDS):
    if c not in best_place or not R[r]['population']:
        continue
    _, nm, lon, lat, cap, ne_pop = best_place[c]
    d = R[r]
    x, y = proj(lon, lat)
    x, y = float(x), float(y)
    fp = sorted(int(i) for i in CELLS[c])
    cell = nearest_cell(x, y, CELLS[c])
    rp = d['population']
    # no GISCO LAU population for either country: Natural Earth's city-proper estimate, never more than the region
    p = ne_pop if ne_pop and ne_pop < rp * 0.97 else None
    f = p / rp if p else 1.0
    sc = lambda v: None if v is None else round(v * f)
    s21, s25 = d['series'].get('2021'), d['series'].get(str(YEAR_POP))
    g = sc(d['gdp'])
    jobs = {k: sc(v) for k, v in d['jobs'].items()} if d['jobs'] else {k: None for k, _ in IND}
    row = {'id': r + 'C', 'name': nm, 'full': f'{nm} (town; jobs and GDP scaled from {REGION_NAMES[c]})' if p else f'{nm} ({REGION_NAMES[c]})',
           'states': [c], 'metro': False, 'capital': cap, 'x': round(x, 1), 'y': round(y, 1), 'cell': cell,
           'population': int(p or rp), 'employed': sc(d['employed']), 'jobs': jobs, 'gdp': g, 'gdp_year': d['gdp_year'],
           'gdp_by_industry': {k: sc(v) for k, v in d['gva'].items()} if d['gva'] else {k: None for k, _ in IND},
           'yields': yields(jobs if d['jobs'] else None, g), 'median_income': None, 'median_rent': None, 'home_value': None,
           'unemployment': None if d['unemployment'] is None else round(d['unemployment'] / 100, 4), 'rent_burden': None,
           'growth': round(s25 / s21 - 1, 4) if s21 and s25 else None, 'growth_years': [2021, YEAR_POP],
           'pop_series': {str(yy): sc(d['series'].get(str(yy))) for yy in range(2015, YEAR_POP + 1)},
           'gdp_undisclosed': None, 'gdp_estimated': None, 'counties': [r], 'footprint': [cell] if f < 0.6 else fp,
           'population_source': 'city proper (Natural Earth estimate)'}
    if p:
        row['region_population'] = rp
        row['scaled_from_region'] = REGION_NAMES[c]
    new_cities.append(row)
    print('city', nm, row['population'], 'of', rp)

cities = load_json(OUT + '/cities.json')
used = {c['cell'] for c in cities}
for c in new_cities:
    if c['cell'] in used:
        c['cell'] = next((k for k in c['footprint'] if k not in used), c['cell'])
cities = sorted(cities + new_cities, key=lambda c: -c['population'])


def rank(rows, fn):
    vals = [fn(r) for r in rows]
    idx = sorted((i for i, v in enumerate(vals) if v is not None), key=lambda i: (-vals[i], -(rows[i]['population'] or 0)))
    out = [None] * len(rows)
    for n, i in enumerate(idx):
        out[i] = n + 1
    return out


YK = ['food', 'production', 'gold', 'science', 'culture']
rk = {'population': rank(cities, lambda r: r['population']), 'gdp': rank(cities, lambda r: r['gdp']),
      'gdp_per_capita': rank(cities, lambda r: r['gdp'] / r['population'] if r['gdp'] and r['population'] else None),
      'growth': rank(cities, lambda r: r['growth'])}
for k in YK:
    rk[k] = rank(cities, lambda r, k=k: r['yields'].get(k))
for i, c in enumerate(cities):
    c['ranks'] = {k: v[i] for k, v in rk.items()}
    lp = math.log(c['population'])
    c['peers'] = [o['id'] for o in sorted((o for o in cities if o is not c), key=lambda o: abs(math.log(o['population']) - lp))[:5]]
metro_of = {c['counties'][0]: c['id'] for c in new_cities}

# ---------------------------------------------------------------- world.json -----------------------------------------
pct = world['pct']
world['owner'] = owner.tolist()
world['county'] = county.tolist()
world['states'] += [{'fips': c, 'abbr': c, 'name': NAMES[c]} for c in NEW]
world['counties'] += [{'geoid': r, 'name': REGION_NAMES[r[:2]]} for r in RIDS]

# rivers that now run at least 30% over mapped land (the build_world rule), and were left out before
had = {(r['name'], r['pts'][0], r['pts'][1]) for r in world['rivers']}
added_rivers = 0
for fn in ('ne_10m_rivers_lake_centerlines', 'ne_10m_rivers_europe'):
    for f in load_json(f'{RAW}/ne/{fn}.geojson')['features']:
        pr = f['properties']
        if pr.get('featurecla', '').lower().startswith('lake'):
            continue
        g = f['geometry']
        lines = g['coordinates'] if g['type'] == 'MultiLineString' else [g['coordinates']]
        rk_ = pr.get('scalerank') or pr.get('rivernum') or 9
        name = pr.get('name_en') or pr.get('name') or None
        for ln in lines:
            a = np.array(ln)
            if a.size == 0 or a[:, 0].max() < 15 or a[:, 0].min() > 22 or a[:, 1].max() < 41.5 or a[:, 1].min() > 45.5:
                continue
            x, y = proj(a[:, 0], a[:, 1])
            c = grid.cell_at(x, y)
            inside = c >= 0
            if inside.sum() < 2:
                continue
            ci = c[inside]
            if (owner[ci] >= 0).mean() < 0.3 or (owner0[ci] >= 0).mean() >= 0.3 or not np.isin(ci, new_cells).any():
                continue
            p_ = []
            for xx, yy in zip(x[inside], y[inside]):
                p_ += [round(float(xx), 1), round(float(yy), 1)]
            if len(p_) >= 4 and (name, p_[0], p_[1]) not in had:
                world['rivers'].append({'name': name, 'rank': int(rk_), 'pts': p_})
                had.add((name, p_[0], p_[1])); added_rivers += 1
world['rivers'].sort(key=lambda r: r['rank'])
print('rivers added', added_rivers)
save_json('world', world)

# ---------------------------------------------------------------- counties.json --------------------------------------
counties = load_json(OUT + '/counties.json')
cols = counties['columns']
reg_cells = defaultdict(list)
for i, v in cell_samples.items():
    for ri, n in v.items():
        reg_cells[ri].append((i, n))


def land_share(ri, key):
    cs = reg_cells.get(ri)
    if not cs:
        return None
    den = sum(n for _, n in cs)
    return round(sum(pct[key][i] * n for i, n in cs) / den / 100, 3) if den else None


pc = lambda v: None if v is None else round(v / 100, 4)
new_rows = {}
for k, r in enumerate(RIDS):
    d, ri = R[r], NOLD + k
    p, la, tot, jobs = d['population'], d['area'], d['employed'], d['jobs'] or {}
    sh = lambda key: None if not tot or jobs.get(key) is None else round(jobs[key] / tot, 4)
    ag = d['ages'] or {}
    old = round(sum(ag[x] for x in ('Y65-69', 'Y70-74', 'Y75-79', 'Y80-84', 'Y_GE85')) / ag['TOTAL'], 4) if ag.get('TOTAL') else None
    s = d['series']
    gr = round(s[str(YEAR_POP)] / s['2021'] - 1, 4) if s.get('2021') and s.get(str(YEAR_POP)) else None
    cs = reg_cells.get(ri)
    cell = max(cs, key=lambda t: t[1])[0] if cs else nearest_cell(*proj.from3035(*cntr[r[:2]].representative_point().coords[0]), CELLS[r[:2]])
    row = dict(geoid=r, name=REGION_NAMES[r[:2]], state=r[:2], population=p, land_km2=la, density=round(p / la, 1) if p and la else None,
               gdp=d['gdp'], gdp_per_capita=round(d['gdp'] / p) if d['gdp'] and p else None, gdp_pps=d['gdp_pps'], growth=gr,
               median_age=d['median_age'], elderly=old, employed=tot, agriculture_share=sh('agriculture'), manufacturing_share=sh('manufacturing'),
               information_share=sh('information'), finance_share=sh('finance'), public_admin_share=sh('public_admin'), arts_share=sh('arts'),
               income=None, income_pps=None, unemployment=pc(d['unemployment']), tertiary=pc(d['tertiary']), life_expectancy=d['life'],
               poverty=None, broadband=pc(d['broadband']), foreign_born=None, rd=d['rd'], hightech=pc(d['htec']), tourism=None,
               forest=land_share(ri, 'forest'), crop=land_share(ri, 'crop'), pasture=land_share(ri, 'pasture'), developed=land_share(ri, 'developed'),
               cbsa=metro_of.get(r), cell=int(cell))
    unknown = [c for c in cols if c not in row]
    if unknown:  # a column another step added: no national figure for it here
        print('counties.json: no value for', unknown)
    counties['rows'].append([row.get(c) for c in cols])
    new_rows[r] = dict(zip(cols, counties['rows'][-1]))
save_json('counties', counties)
rows_by = {r[0]: dict(zip(cols, r)) for r in counties['rows']}

# ---------------------------------------------------------------- states.json ----------------------------------------
states = load_json(OUT + '/states.json')
for k, (c, r) in enumerate(zip(NEW, RIDS)):
    d = R[r]
    cells = CELLS[c]
    cx, cy = grid.center(cells)
    ext = max(cx.max() - cx.min(), cy.max() - cy.min())
    jobs = {key: (None if v is None else round(v)) for key, v in (d['jobs'] or {key: None for key, _ in IND}).items()}
    s = d['series']
    states.append({
        'fips': c, 'abbr': c, 'name': NAMES[c], 'population': d['population'], 'employed': d['employed'], 'jobs': jobs,
        'gdp': None if d['gdp'] is None else round(d['gdp']), 'gdp_year': d['gdp_year'],
        'gdp_by_industry': {key: (None if v is None else round(v)) for key, v in (d['gva'] or {key: None for key, _ in IND}).items()},
        'yields': yields(d['jobs'] and jobs, None if d['gdp'] is None else round(d['gdp'])),
        'median_income': None, 'median_rent': None, 'home_value': None,
        'unemployment': None if d['unemployment'] is None else round(d['unemployment'] / 100, 4), 'rent_burden': None,
        'growth': new_rows[r]['growth'], 'growth_years': [2021, YEAR_POP],
        'pop_series': {str(y): s.get(str(y)) for y in range(2015, YEAR_POP + 1)},
        'label': {'x': round(float(np.median(cx)), 1), 'y': round(float(np.median(cy)), 1), 'angle': 0, 'size': float(max(14, min(110, ext / 9)))},
        'land': {key: round(float(np.mean([pct[key][i] for i in cells if world['cover'][i] > 0] or [0])) / 100, 3) for key in pct}})
for key in YK:
    rr = rank(states, lambda s, key=key: s['yields'].get(key))
    for i, s in enumerate(states):
        s.setdefault('ranks', {})[key] = rr[i]
save_json('cities', cities)

# ---------------------------------------------------------------- history.json --------------------------------------
history = load_json(OUT + '/history.json')
HY = history['years']
add = {'pop': lambda c, y: pop_s[c].get(y), 'gdp_idx': lambda c, y: gdp_idx_s[c].get(y),
       'unemp': lambda c, y: None if unemp_s[c].get(y) is None else round(unemp_s[c][y] / 100, 3),
       'jobs': lambda c, y: None if emp_s.get((c, 'TOTAL'), {}).get(y) is None else int(round(emp_s[(c, 'TOTAL')][y] * 1000)),
       'farm': lambda c, y: share(c, 'A', y), 'factory': lambda c, y: share(c, 'C', y)}


def share(c, n, y):
    t, a = emp_s.get((c, 'TOTAL'), {}).get(y), emp_s.get((c, n), {}).get(y)
    return round(a / t, 4) if t and a is not None else None


for key in history['series']:
    for c in NEW:
        for y in HY:
            v = add[key](c, y) if key in add else None
            if key in ('pop', 'gdp_idx') and v is not None:
                v = int(round(v))
            history['series'][key].append(v)
history['regions'] += RIDS
# The story beats are left as they are: Bosnia's 2016 population drop is the 2013 census replacing older estimates.
with open(OUT + '/history.json', 'w') as f:
    json.dump(history, f, separators=(',', ':'), allow_nan=False)
print('history.json: +', RIDS)


def hval(key, i, y):
    return history['series'][key][i * len(HY) + (y - HY[0])] if HY[0] <= y <= HY[-1] else None


# ---------------------------------------------------------------- lenses.json ---------------------------------------
L = load_json(OUT + '/lenses.json')
COL = {'density': ('density', False, 1), 'growth': ('growth', True, 4), 'age': ('median_age', True, 1), 'elderly': ('elderly', True, 4),
       'foreign_born': ('foreign_born', True, 4), 'gdp_pc': ('gdp_per_capita', True, 0), 'gdp_pps': ('gdp_pps', True, 0),
       'income': ('income_pps', True, 0), 'unemployment': ('unemployment', True, 4), 'poverty': ('poverty', True, 4),
       'bachelors': ('tertiary', True, 4), 'rd': ('rd', True, 2), 'hightech': ('hightech', True, 4), 'broadband': ('broadband', True, 4),
       'life': ('life_expectancy', True, 1), 'tourism': ('tourism', True, 2), 'farm_jobs': ('agriculture_share', True, 4),
       'factory_jobs': ('manufacturing_share', True, 4)}


def spread(i, col, weighting):
    """build_lenses' population-weighted mean over the hex's samples, but empty when the hex's own country has no value,
    so a Bosnian or Kosovan hex never shows a neighbour's figure for a measure its country does not publish."""
    if rows_by[REG_ALL[county[i]]].get(col) is None:
        return None
    num = den = 0.0
    for ri, n in cell_samples[i].items():
        rw = rows_by[REG_ALL[ri]]
        v = rw.get(col)
        if v is None:
            continue
        w = n * ((rw['density'] or 1.0) if weighting else 1)
        num += v * w; den += w
    return num / den if den > 0 else None


last_idx = {}
for k, r in enumerate(RIDS):
    a, b = history['range']['gdp_idx']
    for y in range(b, a - 1, -1):
        v = hval('gdp_idx', NOLD + k, y)
        if v is not None:
            last_idx[NOLD + k] = v
            break

# low-lying land (build_climate): 0.5 km samples in hexes within 3 hexes of the sea and below 120 m mean elevation
water = np.array(world['water']); elev_c = np.array(world['elev'])
sea = (water == 1) | (water == 2)
dist = np.full(S, 99)
front = list(np.where(sea)[0])
dist[front] = 0
for step in range(1, 4):
    nxt = []
    for i in front:
        for j in grid.neighbours(i):
            if dist[j] > step:
                dist[j] = step; nxt.append(j)
    front = nxt
cand = np.array([i for i in new_cells if dist[i] <= 3 and elev_c[i] < 120], int)
hex_low = {i: 0.0 for i in new_cells}
low_km2 = defaultdict(float)
if len(cand):
    cx, cy = grid.center(cand)
    offs = np.arange(-grid.radius, grid.radius + 1e-9, 0.5)
    ox, oy = np.meshgrid(offs, offs)
    ox, oy = ox.ravel(), oy.ravel()
    QX = (cx[:, None] + ox[None, :]).ravel(); QY = (cy[:, None] + oy[None, :]).ravel()
    QC = grid.cell_at(QX, QY)
    keep = QC == np.repeat(cand, len(ox))
    QX, QY, QC = QX[keep], QY[keep], QC[keep]
    Q3x, Q3y = proj.to3035(QX, QY)
    LON, LAT = (np.asarray(v) for v in TO4326.transform(Q3x, Q3y))
    Z = 9
    n = 2 ** Z
    fx = (LON + 180) / 360 * n
    fy = (1 - np.log(np.tan(np.radians(LAT)) + 1 / np.cos(np.radians(LAT))) / math.pi) / 2 * n
    tx, ty = fx.astype(int), fy.astype(int)
    TD = f'{RAW}/terrarium{Z}'
    os.makedirs(TD, exist_ok=True)

    def fetch(t):
        p = f'{TD}/{Z}_{t[0]}_{t[1]}.png'
        if not os.path.exists(p):
            with urllib.request.urlopen(f'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{Z}/{t[0]}/{t[1]}.png', timeout=60) as r:
                open(p, 'wb').write(r.read())
        return p
    # as build_climate: Copernicus DEM GLO-90 where it has a tile, Terrarium z9 only where it has none (open sea)
    import copdem
    el = np.asarray(copdem.sample(LON, LAT, level=0), np.float32)
    need = ~np.isfinite(el)
    tiles = sorted(set(zip(tx[need].tolist(), ty[need].tolist())))
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(fetch, tiles))
    for t in tiles:
        a = np.asarray(Image.open(f'{TD}/{Z}_{t[0]}_{t[1]}.png').convert('RGB')).astype(np.float32)
        e = a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768
        m = need & (tx == t[0]) & (ty == t[1])
        el[m] = e[np.clip(((fy[m] - t[1]) * 256).astype(int), 0, 255), np.clip(((fx[m] - t[0]) * 256).astype(int), 0, 255)]
    wc = np.zeros(len(QX), np.uint8)
    tla, tlo = (np.floor(LAT / 3) * 3).astype(int), (np.floor(LON / 3) * 3).astype(int)
    for la, lo in set(zip(tla.tolist(), tlo.tolist())):
        p = f"{RAW}/worldcover/N{la:02d}E{lo:03d}.npy"
        if not os.path.exists(p):
            sys.exit('missing ' + p + ' (run fetch_worldcover.py)')
        a = np.load(p)
        m = (tla == la) & (tlo == lo)
        wc[m] = a[np.clip(((la + 3 - LAT[m]) / 3 * a.shape[0]).astype(int), 0, a.shape[0] - 1),
                  np.clip(((LON[m] - lo) / 3 * a.shape[1]).astype(int), 0, a.shape[1] - 1)]
    on_land = (wc != 0) & (wc != 80)
    low = on_land & (el <= 5)
    A = 0.25
    for i in cand:
        m = QC == i
        cl = on_land[m].sum() * A
        hex_low[int(i)] = round(float(low[m].sum() * A / cl), 3) if cl > 0 else 0.0
    preg = assign([cntr[c] for c in NEW], shapely.points(Q3x, Q3y))
    for k, c in enumerate(NEW):
        low_km2[c] = float((low & (preg == k)).sum() * A)
print('low-lying land km2', dict(low_km2))

# build_more_lenses.py: the country's own national figure on each of its hexes (no blend with neighbours), forest height
# from the canopy height map as there. Temperature and rainfall (ERA5-Land, needs a CDS key) and the farm-survey crops
# (no survey for either country) stay empty.
own = {}
ch = latest('demo_pjanind', indic_de='PC_Y0_14', min_year=2022)
own['children'] = {c: ch[c][0] / 100 for c in ch}
er = latest('lfsa_ergan', sex='T', age='Y20-64', citizen='TOTAL', unit='PC', min_year=2022)
own['employment'] = {c: er[c][0] / 100 for c in er}
g2000 = next((l for l in L['lenses'] if l['id'] == 'growth_2000'), None)
if g2000:
    y0, y1 = (int(y) for y in re.search(r'(\d{4})–(\d{4})', g2000['unit']).groups())
    own['growth_2000'] = {c: pop_s[c][y1] / pop_s[c][y0] - 1 for c in NEW if pop_s[c].get(y0) and pop_s[c].get(y1)}
OWN_DIGITS = {'children': 4, 'employment': 4, 'growth_2000': 4}
forest_height = {}
if any(l['id'] == 'forest_height' for l in L['lenses']):
    from rasterio.windows import Window
    import rasterio
    CHM = 'https://dataforgood-fb-data.s3.amazonaws.com/forests/v1/alsgedi_global_v6_float_epsg4326_v3_10deg/meta_chm_lat={top:.1f}_lon={left:.1f}_avg.tif'
    os.environ.setdefault('GDAL_DISABLE_READDIR_ON_OPEN', 'EMPTY_DIR')
    nc = np.array(new_cells)
    cx, cy = grid.center(nc)
    offs = np.arange(-grid.radius + 0.5, grid.radius, 1.0)
    ox, oy = [a_.ravel() for a_ in np.meshgrid(offs, offs)]
    FX = (cx[:, None] + ox[None, :]).ravel(); FY = (cy[:, None] + oy[None, :]).ravel()
    FC = grid.cell_at(FX, FY)
    keep = FC == np.repeat(nc, len(ox))
    FX, FY, FC = FX[keep], FY[keep], FC[keep]
    FLON, FLAT = (np.asarray(v_) for v_ in TO4326.transform(*proj.to3035(FX, FY)))
    TOP = (np.floor(FLAT / 10) * 10 + 10).astype(int); LEFT = (np.floor(FLON / 10) * 10).astype(int)
    ROW = np.clip(np.round((TOP - FLAT) / 0.00025 / 40).astype(int) * 40, 0, 39999)  # one pixel row per km, as there
    COLS = np.clip(((FLON - LEFT) / 0.00025).astype(int), 0, 39999)
    chm = np.full(len(FC), 65535, np.uint16)
    os.makedirs(RAW + '/chm', exist_ok=True)
    for top, left in sorted(set(zip(TOP.tolist(), LEFT.tolist()))):
        m = np.where((TOP == top) & (LEFT == left))[0]
        cache = f'{RAW}/chm/ba_xk_lat{top}_lon{left}_{len(m)}.npy'
        if not os.path.exists(cache):
            out_ = np.full(len(m), 65535, np.uint16)
            with rasterio.open(CHM.format(top=float(top), left=float(left))) as src:
                for r_ in np.unique(ROW[m]):
                    k_ = m[ROW[m] == r_]
                    out_[np.searchsorted(m, k_)] = src.read(1, window=Window(0, int(r_), 40000, 1))[0][COLS[k_]]
            np.save(cache, out_)
        chm[m] = np.load(cache)
    valid = chm != 65535
    tall = valid & (chm >= 500)
    for i in new_cells:
        nv, nt = (valid & (FC == i)).sum(), (tall & (FC == i)).sum()
        if nv and nt >= 0.03 * nv:
            forest_height[i] = round(float(chm[tall & (FC == i)].astype(float).mean() / 100), 1)
    print('forest height for', len(forest_height), 'of', len(new_cells), 'hexes')

for l in L['lenses']:
    v = l['values']
    lid = l['id']
    for i in new_cells:
        if lid in own:
            x = own[lid].get(CTRY_ALL[owner[i]])
            v[i] = None if x is None else round(x, OWN_DIGITS[lid])
        elif lid == 'forest_height':
            v[i] = forest_height.get(i)
        elif lid in ('temperature', 'warming', 'rainfall', 'rain_change', 'vineyards', 'olives', 'orchards'):
            v[i] = None
        elif lid in COL:
            col, wgt, dg = COL[lid]
            x = spread(i, col, wgt)
            v[i] = None if x is None else (round(x, dg) if dg else round(x))
        elif lid == 'forest':
            v[i] = None if world['cover'][i] == 0 else pct['forest'][i] / 100
        elif lid == 'farmland':
            v[i] = None if world['cover'][i] == 0 else (pct['crop'][i] + pct['pasture'][i]) / 100
        elif lid == 'developed':
            v[i] = None if world['cover'][i] == 0 else pct['developed'][i] / 100
        elif lid == 'elevation':
            v[i] = world['elev'][i]
        elif lid == 'gdp_index':
            v[i] = last_idx.get(int(county[i]))
        elif lid in ('hot_days', 'tropical_nights'):
            v[i] = None  # the ECDE indicators come on NUTS 2 regions only
        elif lid == 'low_coast':
            v[i] = hex_low[i]
        else:
            print('lens', lid, ': no rule for Bosnia and Herzegovina and Kosovo, left empty')
            v[i] = None
with open(OUT + '/lenses.json', 'w') as f:
    json.dump(L, f, ensure_ascii=False, separators=(',', ':'))
print('lenses.json: values for', len(new_cells), 'hexes')

# ---------------------------------------------------------------- climate.json ---------------------------------------
C = load_json(OUT + '/climate.json')
C['regions'] += RIDS
C['unit_of'] += [-1] * len(RIDS)
for c, r in zip(NEW, RIDS):
    la = new_rows[r]['land_km2'] or 0
    C['coast'].append([round(low_km2[c]), round(min(1.0, low_km2[c] / la), 3) if la else 0, 0])  # no low built-up land
save_json('climate', C)

# ---------------------------------------------------------------- districts.json and citizens.json -------------------
D = load_json(OUT + '/districts.json')
for c in new_cities:
    D['cities'][c['id']] = None  # Eurostat's structural business statistics have no regions here
save_json('districts', D)
Z_ = load_json(OUT + '/citizens.json')
FIG = Z_['figures']
A_GROUPS = [('child', ['Y_LT5', 'Y5-9', 'Y10-14']), ('young', ['Y15-19', 'Y20-24', 'Y25-29', 'Y30-34']),
            ('midlife', ['Y35-39', 'Y40-44', 'Y45-49', 'Y50-54', 'Y55-59', 'Y60-64']), ('elder', ['Y65-69', 'Y70-74', 'Y75-79', 'Y80-84', 'Y_GE85'])]


def lrr(counts, n):
    tot = sum(counts.values())
    raw = {k: v / tot * n for k, v in counts.items()}
    fl = {k: int(math.floor(v)) for k, v in raw.items()}
    for k in sorted(raw, key=lambda k: -(raw[k] - fl[k]))[:n - sum(fl.values())]:
        fl[k] += 1
    return fl


def mkrow(counts, figures=None, extra=None):
    tot = sum(counts.values())
    if tot <= 0:
        return None
    o = {'total': round(tot), 'counts': {k: round(v) for k, v in counts.items()}, 'shares': {k: round(v / tot, 3) for k, v in counts.items()}}
    if figures:
        o['figures'] = lrr(counts, figures)
    if extra:
        o.update(extra)
    return o


for c in new_cities:
    d = R[c['counties'][0]]
    f = c['population'] / c['region_population'] if c.get('region_population') else 1.0
    out = {'workforce': None, 'age': None, 'commute': None, 'education': None, 'nativity': None}
    ag = d['ages']
    if ag:
        out['age'] = mkrow({k: sum(ag.get(x, 0) for x in xs_) * f for k, xs_ in A_GROUPS}, FIG['age'], {'median': d['median_age']})
        sh = [d['edu_low'], d['edu_mid'], d['tertiary']]
        if all(v is not None for v in sh):
            adults = sum(ag.get(x, 0) for x in ('Y25-29', 'Y30-34', 'Y35-39', 'Y40-44', 'Y45-49', 'Y50-54', 'Y55-59', 'Y60-64')) * f
            ss = sum(sh)
            out['education'] = mkrow({k: adults * v / ss for k, v in zip(('less_than_hs', 'high_school', 'bachelors'), sh)}, None,
                                     {'bachelors_plus': round(sh[2] / ss, 3)})
    specs = []
    for rk_ in ('workforce', 'age', 'education', 'nativity'):
        a, b = out.get(rk_), Z_['national'].get(rk_)
        if not a or not b:
            continue
        for key, s in a['shares'].items():
            ns = b['shares'].get(key)
            if not ns or (s < 0.01 and ns < 0.01):
                continue
            specs.append({'row': rk_, 'key': key, 'share': s, 'national': ns, 'ratio': round(s / ns, 2)})
    out['specialists'] = sorted([s for s in specs if s['ratio'] >= 1.5], key=lambda s: -s['ratio'])[:4] + \
        sorted([s for s in specs if s['ratio'] <= 0.67], key=lambda s: s['ratio'])[:2]
    out['reliable'] = True
    Z_['cities'][c['id']] = out
save_json('citizens', Z_)

# ---------------------------------------------------------------- advisor.json --------------------------------------
AD = load_json(OUT + '/advisor.json')
ses = {}
for size in ('GE10', 'TOTAL'):
    for co, v in es.table('earn_ses22_48', geo=GEO, sex='T', unit='EUR', indic_se='ERN', sizeclas=size)[0]:
        ses.setdefault((co['geo'], co['isco08'], co['nace_r2']), v)
eu_ses = {}
for co, v in es.table('earn_ses22_48', geo='EU27_2020', sex='T', unit='EUR', indic_se='ERN', sizeclas='GE10')[0]:
    eu_ses[(co['isco08'], co['nace_r2'])] = v
WIDER = {'J': 'G-J', 'K': 'K-N', 'M': 'K-N', 'N': 'K-N', 'P': 'P-S', 'Q': 'P-S', 'R': 'P-S', 'O': 'O-S', 'G': 'G-J', 'H': 'G-J', 'I': 'G-J',
         'C': 'B-E', 'F': 'B-F'}


def nat_pay(c, isco, nace):
    for n_ in (nace, WIDER.get(nace), 'B-S'):
        if n_ and (c, isco, n_) in ses:
            return ses[(c, isco, n_)], n_ == nace
    eu, tot, eu_tot = eu_ses.get((isco, nace)), ses.get((c, 'TOTAL', 'B-S')), eu_ses.get(('TOTAL', 'B-S'))
    return (eu * tot / eu_tot, False) if eu and tot and eu_tot else (None, False)


for t in AD['trades']:
    for c in NEW:
        p, ok = nat_pay(c, t['isco'], t['nace'])
        AD['pay'][t['id']].append(None if p is None else int(round(p / 10) * 10))  # pay level 1: no NUTS 1 pay for either country
        AD['payQuality'][t['id']][c] = ('trade' if ok else 'estimate') if p else None
        AD['jobs'][t['id']].append(None)  # no occupation census in Eurostat for either country
rents = es.latest('prc_colc_rents', currency='EUR', building='FLAT1', sinceTimePeriod=2019)
pli = latest('prc_ppp_ind', na_item='PLI_EU27_2020', ppp_cat='A01', min_year=2019)
eng = {}
for lev in ('PROF', 'GOOD'):
    for c, (v, _) in latest('edat_aes_l31', age='Y25-64', sex='T', lev_know=lev, unit='PC').items():
        eng[c] = round(eng.get(c, 0) + v, 1)
jl, pl = AD['momentumYears']['jobs'][1], AD['momentumYears']['pop'][1]


def growth(key, i, a, b):
    va = next((hval(key, i, y) for y in range(a, a + 3) if hval(key, i, y)), None)
    vb = next((hval(key, i, y) for y in range(b, b - 3, -1) if hval(key, i, y)), None)
    return round(vb / va - 1, 4) if va and vb else None


city_of = {c['counties'][0]: c for c in new_cities}
for k, (c, r) in enumerate(zip(NEW, RIDS)):
    rent = rents.get(c + '_CAP')
    m = city_of.get(r)
    if rent and m:
        AD['rentAnchors'][c] = [[es.labels('prc_colc_rents', 'geo', currency='EUR', building='FLAT1', sinceTimePeriod=2019)[c + '_CAP'], rent[0], m['id']]]
    # the anchor's own region: income and size ratios are both 1, so the rent is the survey rent
    AD['regions'].append([1.0, int(round(rent[0] / 10) * 10) if rent and m else None, bool(rent and m), '+'.join(LANGS[c]),
                          growth('jobs', NOLD + k, jl - 10, jl), growth('pop', NOLD + k, pl - 10, pl)])
    AD['pli'][c] = val(pli, c)
    AD['english'][c] = eng.get(c)
with open(OUT + '/advisor.json', 'w') as f:
    json.dump(AD, f, ensure_ascii=False, separators=(',', ':'))
print('advisor.json: +', RIDS)

# ---------------------------------------------------------------- resources (WRI power plants) ----------------------
RES = load_json(OUT + '/resources.json')
types = {t['id']: t for t in RES['types']}
FUEL = {'nuclear': ('Nuclear', 0, False), 'hydro': ('Hydro', 250, False), 'coal_plant': ('Coal', 1000, False), 'gas_plant': ('Gas', 800, False),
        'wind': ('Wind', 300, True), 'solar': ('Solar', 150, True), 'geothermal': ('Geothermal', 50, True), 'biomass': ('Biomass', 150, False)}
# The plants the database lists under Bosnia and Herzegovina and Kosovo (BIH, KOS), placed by the build_sites rule: the
# map hex at the plant, else the nearest map hex within 2 hexes. Plants listed under other countries are already there.
plants = [r for r in csv.DictReader(open(RAW + '/misc/gppd.csv', encoding='utf-8')) if r['country'] in ('BIH', 'KOS')]


def place(lon, lat, maxr=2):
    x, y = proj(lon, lat)
    x, y = float(x), float(y)
    c = int(grid.cell_at(x, y))
    if c >= 0 and owner[c] >= 0:
        return x, y, c
    d = (CX - x) ** 2 + (CY - y) ** 2
    for k_ in np.argsort(d)[:60]:
        if d[k_] > (grid.radius * SQRT3 * maxr) ** 2:
            break
        if owner[k_] >= 0:
            return x, y, int(k_)
    return x, y, None


new_items = []
for tid, (fuel, thr, per_hex) in FUEL.items():
    acc = defaultdict(lambda: [0.0, 0, None, 0.0])
    for p in plants:
        if p['primary_fuel'] != fuel:
            continue
        x, y, c = place(float(p['longitude']), float(p['latitude']))
        if c is None:
            continue
        mw = float(p['capacity_mw'])
        if per_hex:
            a = acc[c]; a[0] += mw; a[1] += 1
            if mw > a[3]:
                a[2], a[3] = p['name'], mw
        elif mw >= thr:
            det = ', '.join(v for v in [p.get('owner') or '', ('commissioned ' + p['commissioning_year'][:4]) if p.get('commissioning_year') else ''] if v)
            new_items.append({'type': tid, 'name': p['name'], 'x': round(x, 1), 'y': round(y, 1), 'cell': c, 'value': round(mw),
                              'detail': det or None, 'state': CTRY_ALL[owner[c]], 'cbsa': metro_of.get(REG_ALL[county[c]])})
    for c, (mw, n_, big, _) in acc.items():
        if mw >= thr:
            new_items.append({'type': tid, 'name': f"{types[tid]['name']} near {world['counties'][county[c]]['name']}",
                              'x': round(float(CX[c]), 1), 'y': round(float(CY[c]), 1), 'cell': c, 'value': round(mw),
                              'detail': f'{n_} sites, largest {big}', 'state': CTRY_ALL[owner[c]], 'cbsa': metro_of.get(REG_ALL[county[c]])})
print('power plants', [(i['name'], i['value']) for i in new_items])
RES['items'] += new_items
for i in new_items:
    s = RES['summary']['national'][i['type']]
    s['count'] += 1; s['value'] += i['value']
    s = RES['summary']['states'].setdefault(i['state'], {}).setdefault(i['type'], {'count': 0, 'value': 0, 'unit': 'MW'})
    s['count'] += 1; s['value'] += i['value']
save_json('resources', RES)
for s in states:
    if s['abbr'] in NEW or any(i['state'] == s['abbr'] for i in new_items):
        by = {t: 0 for t in types}; sites = {t: 0 for t in types}
        for i in RES['items']:
            if i['state'] == s['abbr']:
                by[i['type']] += i['value']; sites[i['type']] += 1
        s['energy'] = {'unit': 'MW', 'total': sum(by.values()), 'by_type': by, 'sites': sites,
                       'note': 'Only the mapped sites in resources.json (each type has a size threshold), not the country’s total capacity.'}
save_json('states', states)

# ---------------------------------------------------------------- infrastructure (roads and rail) --------------------
INF = load_json(OUT + '/infrastructure.json')
NEWSET = set(new_cells)


def rasterise(coords_list, step=2.0):
    links = []
    for coords in coords_list:
        a = np.array(coords, float)
        if len(a) < 2:
            continue
        x, y = proj(a[:, 0], a[:, 1])
        px, py = [x[0]], [y[0]]
        for k in range(1, len(x)):
            n_ = max(1, int(math.hypot(x[k] - x[k - 1], y[k] - y[k - 1]) / step))
            for j in range(1, n_ + 1):
                px.append(x[k - 1] + (x[k] - x[k - 1]) * j / n_); py.append(y[k - 1] + (y[k] - y[k - 1]) * j / n_)
        prev = None
        for c in grid.cell_at(np.array(px), np.array(py)):
            c = int(c)
            if c < 0:
                prev = None; continue
            if prev is not None and c != prev and c in grid.neighbours(prev):
                if (prev in NEWSET or c in NEWSET) and owner[prev] != -2 and owner[c] != -2:
                    links.append((min(prev, c), max(prev, c)))
            if c != prev:
                prev = c
    return links


def lines_of(g):
    return [g['coordinates']] if g['type'] == 'LineString' else g['coordinates'] if g['type'] == 'MultiLineString' else []


def near(ls):
    a = np.array([p for ln in ls for p in ln])
    return len(a) and a[:, 0].max() > 15 and a[:, 0].min() < 22 and a[:, 1].max() > 41.5 and a[:, 1].min() < 45.5


roads = {}
for f in load_json(RAW + '/ne/ne_10m_roads.geojson')['features']:
    pr = f['properties']
    ls = lines_of(f['geometry'])
    if pr.get('continent') != 'Europe' or not ls or not near(ls):
        continue
    cls = 0 if pr.get('expressway') == 1 else 1 if pr.get('type') == 'Major Highway' and (pr.get('scalerank') or 99) <= 6 else None
    if cls is None:
        continue
    for l in rasterise(ls):
        if l not in roads or roads[l][0] > cls:
            roads[l] = (cls, pr.get('name') or pr.get('label') or None)
rail = {}
for f in load_json(RAW + '/ne/ne_10m_railroads.geojson')['features']:
    pr = f['properties']
    ls = lines_of(f['geometry'])
    sr = pr.get('scalerank') or 99
    if pr.get('continent') not in (None, 'Europe') or not ls or not near(ls) or sr > 8:
        continue
    for l in rasterise(ls):
        rail[l] = min(rail.get(l, 9), 0 if sr <= 6 else 1)
have_r = {(a, b) for a, b, *_ in INF['roads']}
have_t = {(a, b) for a, b, *_ in INF['rail']}
INF['roads'] = sorted(INF['roads'] + [[a, b, c, n_] for (a, b), (c, n_) in roads.items() if (a, b) not in have_r])
INF['rail'] = sorted(INF['rail'] + [[a, b, t] for (a, b), t in rail.items() if (a, b) not in have_t])
print('road links +', len([1 for l in roads if l not in have_r]), 'rail links +', len([1 for l in rail if l not in have_t]))
save_json('infrastructure', INF)

# ---------------------------------------------------------------- wonders (UNESCO cultural rule) ---------------------
# The rule: each country's earliest-inscribed cultural site, then the earliest remaining up to 60 in all, at most 3 per
# country. Bosnia and Herzegovina's earliest is the Old Bridge Area of the Old City of Mostar (2005); Kosovo has no site
# of its own on the list (UNESCO lists the Medieval Monuments in Kosovo under Serbia, inscribed 2004, after the 1998
# cut-off of the second round). Read from raw/misc/whc_sites.csv when present, else this row from the UNESCO list
# (https://whc.unesco.org/en/list/946).
WO = load_json(OUT + '/wonders.json')
first = None
whc = RAW + '/misc/whc_sites.csv'
if os.path.exists(whc):
    rows = [w for w in csv.DictReader(open(whc, encoding='utf-8')) if w['category'] == 'Cultural' and w['latitude']
            and 'ba' in [c.strip().lower() for c in (w['iso_codes'] or '').split(',')][:1]]
    rows.sort(key=lambda w: (int(w['date_inscribed']), int(w['id_no'])))
    if rows:
        w = rows[0]
        first = dict(id_no=w['id_no'], name=w['name'], date_inscribed=int(w['date_inscribed']), lon=float(w['longitude']), lat=float(w['latitude']),
                     area=round(float(w['area_hectares'] or 0) / 100, 1) or None)
else:
    first = dict(id_no='946', name='Old Bridge Area of the Old City of Mostar', date_inscribed=2005, lon=17.8150, lat=43.3373, area=None)
if first:
    x, y, c = place(first['lon'], first['lat'], maxr=1)
    if c in NEWSET:
        cul = [w for w in WO['wonders'] if w['rule'] == 'cultural_heritage']
        key = lambda w: (w['metrics']['inscribed'], int(w['id'][4:]))
        firsts = {}
        for w in sorted(cul, key=key):
            firsts.setdefault(w['metrics']['countries'][0], w['id'])
        if len(cul) >= 60:  # the newcomer takes a first-round place: the last second-round pick drops out
            drop = max((w for w in cul if firsts[w['metrics']['countries'][0]] != w['id']), key=key)
            print('wonders: Mostar joins, the last second-round pick drops out:', drop['name'])
            WO['wonders'].remove(drop)
        short = re.split(r'[,:(]| and its | of the ', first['name'])[0].strip()
        WO['wonders'].append({'id': 'whs-' + first['id_no'], 'name': first['name'], 'short': short[:40], 'kind': 'landmark', 'rule': 'cultural_heritage',
                              'rank': 0, 'metrics': {'inscribed': first['date_inscribed'], 'area_km2': first['area'], 'category': 'Cultural', 'countries': ['BA']},
                              'x': round(x, 1), 'y': round(y, 1), 'cell': c, 'county': REG_ALL[county[c]], 'cbsa': metro_of.get(REG_ALL[county[c]]),
                              'state': CTRY_ALL[owner[c]], 'cells': None, 'curated': False})
        cul = sorted((w for w in WO['wonders'] if w['rule'] == 'cultural_heritage'), key=key)
        for n_, w in enumerate(cul):
            w['rank'] = n_ + 1
save_json('wonders', WO)
print('done: Bosnia and Herzegovina', len(CELLS['BA']), 'hexes; Kosovo', len(CELLS['XK']), 'hexes; cities', [c['name'] for c in new_cities])
