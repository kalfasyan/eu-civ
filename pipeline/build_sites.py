"""resources.json (power plants), infrastructure.json (roads, rail, ports, airports), wonders.json (World Heritage)."""
import csv, math, re
from collections import defaultdict
import numpy as np
import es
from common import *

meta, proj, grid = world_ctx()
REG = meta['regions']
world = load_json(OUT + '/world.json')
owner = np.array(world['owner']); county = np.array(world['county'])
COUNTRIES = meta['countries']
cross = load_interim('_cross')
metro_of = cross['metro_of']
CX, CY = grid.center(np.arange(grid.size))
ISO2EU = {'GR': 'EL'}


def place(lon, lat, maxr=2):
    """(x, y, cell) for a point: the EU land cell at the point, else the nearest within maxr hexes."""
    x, y = proj(lon, lat)
    x, y = float(x), float(y)
    c = int(grid.cell_at(x, y))
    if c >= 0 and owner[c] >= 0:
        return x, y, c
    d = (CX - x) ** 2 + (CY - y) ** 2
    lim = (grid.radius * SQRT3 * maxr) ** 2
    for k in np.argsort(d)[:60]:
        if d[k] > lim:
            break
        if owner[k] >= 0:
            return x, y, int(k)
    return x, y, None


def site_meta(cell):
    ri = int(county[cell])
    r = REG[ri] if ri >= 0 else None
    return {'county': r, 'cbsa': metro_of.get(r) if r else None, 'state': COUNTRIES[owner[cell]]}


# ---------------------------------------------------------------- resources (WRI Global Power Plant Database) -------
EU_ISO3 = {'AUT': 'AT', 'BEL': 'BE', 'BGR': 'BG', 'CYP': 'CY', 'CZE': 'CZ', 'DEU': 'DE', 'DNK': 'DK', 'EST': 'EE', 'GRC': 'EL',
           'ESP': 'ES', 'FIN': 'FI', 'FRA': 'FR', 'HRV': 'HR', 'HUN': 'HU', 'IRL': 'IE', 'ITA': 'IT', 'LTU': 'LT', 'LUX': 'LU',
           'LVA': 'LV', 'MLT': 'MT', 'NLD': 'NL', 'POL': 'PL', 'PRT': 'PT', 'ROU': 'RO', 'SWE': 'SE', 'SVN': 'SI', 'SVK': 'SK'}
plants = [{k: (v.replace('\ufffd', '?') if isinstance(v, str) else v) for k, v in r.items()} for r in csv.DictReader(open(RAW + '/misc/gppd.csv', encoding='utf-8')) if r['country'] in EU_ISO3]
print('EU plants', len(plants))
SRC = 'wri_gppd'
TYPES = [
    ('nuclear', 'Nuclear plant', 'energy', '☢️', '#e8d44d', 'Every nuclear power plant in the database. Value is the plant capacity in MW.', 'Nuclear', 0, False),
    ('hydro', 'Hydroelectric dam', 'energy', '\U0001F4A7', '#3fa7d6', 'Hydro plants of at least 250 MW.', 'Hydro', 250, False),
    ('coal_plant', 'Coal & lignite plant', 'energy', '\U0001F3ED', '#5a5a5a', 'Coal and lignite plants of at least 1,000 MW. Several have closed since 2021; the database is not updated.', 'Coal', 1000, False),
    ('gas_plant', 'Gas power plant', 'energy', '⚡', '#f08a24', 'Gas-fired plants of at least 800 MW.', 'Gas', 800, False),
    ('wind', 'Wind farms', 'energy', '\U0001F32C️', '#9fd8cb', 'Wind capacity, shown where a hex totals at least 300 MW (onshore and offshore; offshore farms snap to the nearest coast hex within 2 hexes).', 'Wind', 300, True),
    ('solar', 'Solar farms', 'energy', '☀️', '#ffc93c', 'Utility-scale solar capacity, shown where a hex totals at least 150 MW (rooftop solar not included).', 'Solar', 150, True),
    ('geothermal', 'Geothermal field', 'energy', '♨️', '#d9534f', 'Geothermal capacity, shown where a hex totals at least 50 MW.', 'Geothermal', 50, True),
    ('biomass', 'Biomass plant', 'energy', '\U0001F33F', '#6b8e23', 'Biomass and waste plants of at least 150 MW.', 'Biomass', 150, False),
]
types = []
items = []
for tid, name, cat, emoji, color, desc, fuel, thr, per_hex in TYPES:
    types.append({'id': tid, 'name': name, 'category': cat, 'emoji': emoji, 'icon': 'r-' + tid, 'color': color, 'unit': 'MW',
                  'description': desc + ' Source: WRI Global Power Plant Database v1.3 (2021).', 'source': SRC})
    rows = [p for p in plants if p['primary_fuel'] == fuel]
    if per_hex:
        acc = defaultdict(lambda: [0.0, 0, None, None])
        for p in rows:
            x, y, c = place(float(p['longitude']), float(p['latitude']))
            if c is None:
                continue
            a = acc[c]; a[0] += float(p['capacity_mw']); a[1] += 1
            if a[2] is None or float(p['capacity_mw']) > a[3]:
                a[2], a[3] = p['name'], float(p['capacity_mw'])
        for c, (mw, n, big, _) in acc.items():
            if mw >= thr:
                m = site_meta(c)
                items.append({'type': tid, 'name': f'{name} near {world["counties"][county[c]]["name"]}', 'x': round(float(CX[c]), 1), 'y': round(float(CY[c]), 1),
                              'cell': c, 'value': round(mw), 'detail': f'{n} sites, largest {big}', 'state': m['state'], 'cbsa': m['cbsa']})
    else:
        for p in rows:
            mw = float(p['capacity_mw'])
            if mw < thr:
                continue
            x, y, c = place(float(p['longitude']), float(p['latitude']))
            if c is None:
                continue
            m = site_meta(c)
            det = ', '.join(x for x in [p.get('owner') or '', ('commissioned ' + p['commissioning_year'][:4]) if p.get('commissioning_year') else ''] if x)
            items.append({'type': tid, 'name': p['name'], 'x': round(x, 1), 'y': round(y, 1), 'cell': c, 'value': round(mw),
                          'detail': det or None, 'state': m['state'], 'cbsa': m['cbsa']})
summary = {'note': 'Totals of the mapped sites only (each type’s threshold applies), not each country’s full generating capacity.',
           'national': {}, 'states': defaultdict(dict)}
for t in types:
    its = [i for i in items if i['type'] == t['id']]
    summary['national'][t['id']] = {'count': len(its), 'value': sum(i['value'] for i in its), 'unit': 'MW'}
    for i in its:
        s = summary['states'][i['state']].setdefault(t['id'], {'count': 0, 'value': 0, 'unit': 'MW'})
        s['count'] += 1; s['value'] += i['value']
summary['states'] = dict(summary['states'])
save_json('resources', {'types': types, 'items': items, 'summary': summary})
print('resources', len(items))

# country energy into states.json
states = load_json(OUT + '/states.json')
for s in states:
    by = {t['id']: 0 for t in types}; sites = {t['id']: 0 for t in types}
    for i in items:
        if i['state'] == s['abbr']:
            by[i['type']] += i['value']; sites[i['type']] += 1
    s['energy'] = {'unit': 'MW', 'total': sum(by.values()), 'by_type': by, 'sites': sites,
                   'note': 'Only the mapped sites in resources.json (each type has a size threshold), not the country’s total capacity.'}
save_json('states', states)

# ---------------------------------------------------------------- infrastructure --------------------------------------
NB = set()


def is_nb(a, b):
    return b in grid.neighbours(a)


def rasterise(coords_list, step=2.0):
    links = []
    for coords in coords_list:
        a = np.array(coords, float)
        if len(a) < 2:
            continue
        x, y = proj(a[:, 0], a[:, 1])
        pts = [(x[0], y[0])]
        for k in range(1, len(x)):
            d = math.hypot(x[k] - x[k - 1], y[k] - y[k - 1])
            n = max(1, int(d / step))
            for j in range(1, n + 1):
                pts.append((x[k - 1] + (x[k] - x[k - 1]) * j / n, y[k - 1] + (y[k] - y[k - 1]) * j / n))
        px = np.array([p[0] for p in pts]); py = np.array([p[1] for p in pts])
        cells = grid.cell_at(px, py)
        prev = None
        for c in cells:
            c = int(c)
            if c < 0:
                prev = None; continue
            if prev is not None and c != prev and is_nb(prev, c):
                if (owner[prev] >= 0 or owner[c] >= 0) and owner[prev] != -2 and owner[c] != -2:
                    links.append((min(prev, c), max(prev, c)))
            if c != prev:
                prev = c
    return links


def lines_of(g):
    if g['type'] == 'LineString':
        return [g['coordinates']]
    if g['type'] == 'MultiLineString':
        return g['coordinates']
    return []


def in_box(coords):
    a = np.array([p for ln in coords for p in ln])
    return len(a) and a[:, 0].max() > -11 and a[:, 0].min() < 35 and a[:, 1].max() > 34 and a[:, 1].min() < 71


roads = {}
for f in load_json(RAW + '/ne/ne_10m_roads.geojson')['features']:
    pr = f['properties']
    if pr.get('continent') != 'Europe':
        continue
    ls = lines_of(f['geometry'])
    if not ls or not in_box(ls):
        continue
    cls = None
    if pr.get('expressway') == 1:
        cls = 0
    elif pr.get('type') == 'Major Highway' and (pr.get('scalerank') or 99) <= 6:
        cls = 1
    if cls is None:
        continue
    nm = pr.get('name') or pr.get('label') or None
    for l in rasterise(ls):
        if l not in roads or roads[l][0] > cls:
            roads[l] = (cls, nm)
rail = {}
for f in load_json(RAW + '/ne/ne_10m_railroads.geojson')['features']:
    pr = f['properties']
    if pr.get('continent') not in (None, 'Europe'):
        continue
    ls = lines_of(f['geometry'])
    if not ls or not in_box(ls):
        continue
    sr = pr.get('scalerank') or 99
    if sr > 8:
        continue
    tier = 0 if sr <= 6 else 1
    for l in rasterise(ls):
        if l not in rail or rail[l] > tier:
            rail[l] = tier
print('road links', len(roads), 'rail links', len(rail))

# ports: Eurostat main ports, positioned by UN/LOCODE
loc = {}
for r in csv.DictReader(open(RAW + '/misc/unlocode.csv', encoding='utf-8')):
    co = r['Coordinates'].strip()
    m = re.match(r'(\d{2})(\d{2})([NS]) (\d{3})(\d{2})([EW])', co)
    if m:
        lat = int(m[1]) + int(m[2]) / 60; lon = int(m[4]) + int(m[5]) / 60
        if m[3] == 'S': lat = -lat
        if m[6] == 'W': lon = -lon
        loc[r['Country'] + r['Location']] = (lon, lat)
ports = []
for cc in COUNTRIES:
    if cc in ('AT', 'CZ', 'HU', 'LU', 'SK'):
        continue
    try:
        rows, d = es.table('mar_go_am_' + cc.lower(), freq='A', direct='TOTAL', cargo='TOTAL', natvessr='TOTAL', unit='THS_T', par_mar='TOTAL', sinceTimePeriod=2022)
    except Exception as e:
        print('ports', cc, e); continue
    lab = d['dimension']['rep_mar']['category']['label']
    best = {}
    for co, v in rows:
        k = co['rep_mar']
        if '_' not in k or (k in best and best[k][1] >= co['time']):
            continue
        best[k] = (v, co['time'])
    for k, (v, t) in best.items():
        code = k.split('_', 1)[1][1:]
        if not re.match(r'^[A-Z]{2}[A-Z]{3}$', code):
            continue
        p = loc.get(code)
        if not p or v < 5000:
            continue
        x, y, c = place(*p, maxr=3)
        if c is None:
            continue
        m = site_meta(c)
        ports.append({'id': code, 'name': re.sub(r'\s*\(.*?\)', '', lab[k]), 'type': 'coastal', 'tons': int(v * 1000), 'domestic': None, 'foreign': None,
                      'imports': None, 'exports': None, 'year': int(t), 'x': round(x, 1), 'y': round(y, 1), 'cell': c, **m})
ports.sort(key=lambda p: -p['tons'])
# Antwerp and Zeebrugge merged into Antwerp-Bruges; keep the parts (they are separate harbours) and skip the merged code
for i, p in enumerate(ports):
    p['rank'] = i + 1
print('ports', len(ports))

# airports: Eurostat passengers carried per airport, positioned with OurAirports by ICAO code
ap = {}
for r in csv.DictReader(open(RAW + '/misc/airports.csv', encoding='utf-8')):
    ap[r['ident']] = r
rows, d = es.table('avia_paoa', freq='A', unit='PAS', tra_meas='PAS_CRD', schedule='TOTAL', tra_cov='TOTAL', sinceTimePeriod=2023)
lab = d['dimension']['rep_airp']['category']['label']
best = {}
for co, v in rows:
    k = co['rep_airp']
    if k not in best or best[k][1] < co['time']:
        best[k] = (v, co['time'])
prev = {k: v for (co, v) in rows for k in [co['rep_airp']] if best.get(k) and co['time'] == str(int(best[k][1]) - 1)}
airports = []
for k, (v, t) in best.items():
    if '_' not in k or v < 1_000_000:
        continue
    icao = k.split('_', 1)[1]
    a = ap.get(icao)
    if not a:
        continue
    x, y, c = place(float(a['longitude_deg']), float(a['latitude_deg']))
    if c is None:
        continue
    m = site_meta(c)
    hub = 'L' if v >= 20e6 else 'M' if v >= 8e6 else 'S' if v >= 3e6 else 'N'
    airports.append({'id': a.get('iata_code') or icao, 'name': a['name'], 'city': a.get('municipality') or '', 'hub': hub,
                     'enplanements': int(v), 'enplanements_prev': int(prev[k]) if k in prev else None, 'cargo_lbs': None, 'year': int(t),
                     'x': round(x, 1), 'y': round(y, 1), 'cell': c, **m})
airports.sort(key=lambda a: -a['enplanements'])
print('airports', len(airports))
save_json('infrastructure', {
    'version': 1,
    'vintage': {'roads': 'Natural Earth v5.1.2 (1:10m)', 'rail': 'Natural Earth v5.1.2 (1:10m)', 'ports': 'Eurostat main ports, gross weight of goods handled (latest year)',
                'airports': 'Eurostat passengers carried per airport (latest full year)'},
    'sources': ['natural_earth_roads', 'eurostat_ports', 'eurostat_airports', 'unlocode', 'ourairports'],
    'rules': {
        'roads': 'Natural Earth 1:10m roads in Europe, sampled every 2 km and snapped to hex-centre links. Class 0: every road Natural Earth marks as an expressway (motorways). Class 1: other major highways at Natural Earth scale rank 6 or less.',
        'rail': 'Natural Earth 1:10m railroads at scale rank 8 or less, snapped to hex-centre links; tier 0 (main line) is scale rank 6 or less. Natural Earth is map art, not statistics: it holds only part of the real network.',
        'ports': 'Eurostat “main ports” (over 1 million tonnes a year) handling at least 5 million tonnes of goods, placed at their UN/LOCODE position.',
        'airports': 'Airports with at least 1 million passengers carried in the latest full year (Eurostat avia_paoa), placed by ICAO code with OurAirports. Hub classes here: large 20M+, medium 8M+, small 3M+, otherwise 1M+.'},
    'road_classes': [{'id': 'interstate', 'name': 'Motorway'}, {'id': 'major', 'name': 'Major highway'}],
    'rail_tiers': [{'id': 'main', 'name': 'Main line'}, {'id': 'secondary', 'name': 'Secondary line'}],
    'hubs': {'L': 'Large hub (20M+ passengers)', 'M': 'Medium hub (8M+)', 'S': 'Small hub (3M+)', 'N': 'Regional (1M+)'},
    'roads': [[a, b, c, n] for (a, b), (c, n) in sorted(roads.items())],
    'rail': [[a, b, t] for (a, b), t in sorted(rail.items())],
    'ports': ports, 'airports': airports})

# ---------------------------------------------------------------- wonders (UNESCO World Heritage) ----------------------
whs = list(csv.DictReader(open(RAW + '/misc/whc_sites.csv', encoding='utf-8')))
eu = []
for w in whs:
    isos = [ISO2EU.get(c.strip().upper(), c.strip().upper()) for c in (w['iso_codes'] or '').split(',')]
    isos = [c for c in isos if c in COUNTRIES]
    if not isos or not w['latitude']:
        continue
    x, y, c = place(float(w['longitude']), float(w['latitude']), maxr=1)
    if c is None:
        continue
    eu.append((w, isos, x, y, c))
print('EU World Heritage sites on map', len(eu))
wonders = []


def add(w, isos, x, y, c, rule, kind, rank):
    m = site_meta(c)
    nm = w['name']
    short = re.split(r'[,:(]| and its | of the ', nm)[0].strip()
    wonders.append({'id': 'whs-' + w['id_no'], 'name': nm, 'short': short[:40], 'kind': kind, 'rule': rule, 'rank': rank,
                    'metrics': {'inscribed': int(w['date_inscribed']), 'area_km2': round(float(w['area_hectares'] or 0) / 100, 1) or None,
                                'category': w['category'], 'countries': isos},
                    'x': round(x, 1), 'y': round(y, 1), 'cell': c, **m, 'cells': None, 'curated': False})


nat = [e for e in eu if e[0]['category'] in ('Natural', 'Mixed')]
nat.sort(key=lambda e: (int(e[0]['date_inscribed']), int(e[0]['id_no'])))
for k, e in enumerate(nat[:30]):
    nm = e[0]['name'].lower()
    kind = 'coastal' if any(s in nm for s in ('coast', 'island', 'sea', 'lagoon', 'delta', 'bay', 'gulf')) else 'natural'
    add(*e, 'natural_heritage', kind, k + 1)
cul = [e for e in eu if e[0]['category'] == 'Cultural']
cul.sort(key=lambda e: (int(e[0]['date_inscribed']), int(e[0]['id_no'])))
picked, per = [], defaultdict(int)
for e in cul:  # first: each country's earliest-inscribed cultural site
    if per[e[1][0]] == 0:
        picked.append(e); per[e[1][0]] += 1
for e in cul:  # then the earliest remaining, at most 3 per country, up to 45
    if len(picked) >= 45:
        break
    if e not in picked and per[e[1][0]] < 3:
        picked.append(e); per[e[1][0]] += 1
picked.sort(key=lambda e: (int(e[0]['date_inscribed']), int(e[0]['id_no'])))
used_cells = set(w['cell'] for w in wonders)
for k, e in enumerate(picked):
    nm = e[0]['name'].lower()
    kind = 'monument' if any(s in nm for s in ('cathedral', 'church', 'monaster', 'abbey', 'palace', 'castle', 'temple', 'acropolis', 'basilica', 'mosque', 'tower', 'cave', 'amphitheat', 'mines', 'mine ')) else 'landmark'
    add(*e, 'cultural_heritage', kind, k + 1)
save_json('wonders', {
    'version': 1, 'vintage': {'heritage': 'UNESCO World Heritage List (sites inscribed to 2023)'}, 'sources': ['unesco_whc'],
    'rules': [
        {'id': 'natural_heritage', 'kind': 'natural', 'kinds': ['natural', 'coastal'],
         'text': 'The 30 earliest-inscribed natural and mixed UNESCO World Heritage sites on the EU map (ties by site number). Coasts, islands and lagoons are drawn as coastal wonders.'},
        {'id': 'cultural_heritage', 'kind': 'landmark', 'kinds': ['landmark', 'monument'],
         'text': 'Each EU country’s earliest-inscribed cultural UNESCO World Heritage site, then the earliest-inscribed remaining sites up to 45 in all, at most 3 per country. Cathedrals, palaces, castles, temples and mines are drawn as monuments, everything else (old towns, landscapes) as landmarks.'}],
    'national': {'heritage_sites': len(eu)}, 'wonders': wonders})
print('wonders', len(wonders))
