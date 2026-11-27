"""advisor.json: what the "Where to live" advisor needs for every NUTS 3 region of the map.

Run after build_history.py (it reads history.json for momentum). Needs data/world.json, counties.json, cities.json.

For each of about 25 trades (an ISCO-08 occupation group crossed with a NACE sector):
  pay    estimated gross monthly pay in the region, EUR. National mean for the trade (Structure of Earnings Survey 2022,
         earn_ses22_48, enterprises with 10+ employees) x the region's pay level: its NUTS 1 mean hourly pay against the
         country's (earn_ses22_rhr), refined by NUTS 2 compensation per employee (nama_10r_2coe / employees), damped.
  jobs   how common the trade is: (share of employed residents in the occupation group, Census 2021 NUTS 2) x (share
         of jobs in the sector, NUTS 3 regional accounts), both against the EU, as one index (1 = EU average).
Per region: estimated 1-bed rent, languages, momentum (jobs and population growth from history.json), and per country a
net-pay curve (earn_nt_net, single person, 50-167% of the average wage) and the price level of consumption.

Rent is the weakest number. Eurostat's only rent figure for every country is the monthly rent of a 1-bed flat in the
capital (prc_colc_rents, a survey used to set EU staff pay, plus a few other cities with EU sites). Every other region
is estimated from the nearest one: anchor rent x (household income ratio)^0.96 x (metro size ratio)^0.17, clamped
(exponents fitted on Urban Audit city rents). It is marked as an
estimate in the app.
"""
import json, math
from collections import defaultdict
import es
from common import OUT, load_json

world = load_json(OUT + '/world.json')
counties = load_json(OUT + '/counties.json')
cities = load_json(OUT + '/cities.json')
history = load_json(OUT + '/history.json')
cols = counties['columns']
REG = [c['geoid'] for c in world['counties']]
R = {r[0]: dict(zip(cols, r)) for r in counties['rows']}
CTRY = sorted({R[g]['state'] for g in REG})

# --- trades: (id, label, group, isco, nace for pay, sector for jobs) ----------------------------------------------------
TRADES = [
    ('software', 'Software, AI and data', 'Tech and science', 'OC2', 'J', 'J'),
    ('it_tech', 'IT support and network technician', 'Tech and science', 'OC3', 'J', 'J'),
    ('engineer', 'Engineer (mechanical, electrical, industrial)', 'Tech and science', 'OC2', 'C', 'C'),
    ('researcher', 'Researcher or lecturer', 'Tech and science', 'OC2', 'P', 'M_N'),
    ('scientist', 'Scientist or lab professional', 'Tech and science', 'OC2', 'M', 'M_N'),
    ('doctor', 'Doctor, pharmacist or other health professional', 'Health and care', 'OC2', 'Q', 'O-Q'),
    ('nurse', 'Nurse or health technician', 'Health and care', 'OC3', 'Q', 'O-Q'),
    ('carer', 'Care worker', 'Health and care', 'OC5', 'Q', 'O-Q'),
    ('teacher', 'Teacher', 'Public service', 'OC2', 'P', 'O-Q'),
    ('civil', 'Civil servant or policy professional', 'Public service', 'OC2', 'O', 'O-Q'),
    ('finance', 'Finance or banking professional', 'Business', 'OC2', 'K', 'K'),
    ('consultant', 'Lawyer, accountant or consultant', 'Business', 'OC2', 'M', 'M_N'),
    ('manager', 'Manager', 'Business', 'OC1', 'B-S', 'TOTAL'),
    ('office', 'Office and admin staff', 'Business', 'OC4', 'N', 'M_N'),
    ('sales', 'Sales and marketing associate', 'Business', 'OC3', 'G', 'G-I'),
    ('media', 'Media, design or arts', 'Culture', 'OC2', 'R', 'R-U'),
    ('hospitality', 'Chef, waiter or hotel staff', 'Services', 'OC5', 'I', 'G-I'),
    ('retail', 'Shop staff', 'Services', 'OC5', 'G', 'G-I'),
    ('craft', 'Electrician, plumber or builder', 'Hands-on', 'OC7', 'F', 'F'),
    ('mechanic', 'Mechanic or machinist', 'Hands-on', 'OC7', 'C', 'C'),
    ('operator', 'Factory or machine operator', 'Hands-on', 'OC8', 'C', 'C'),
    ('driver', 'Driver or logistics', 'Hands-on', 'OC8', 'H', 'G-I'),
    ('cleaner', 'Cleaner or general labourer', 'Hands-on', 'OC9', 'N', 'TOTAL'),
    ('farmer', 'Farmer, forester or fisher', 'Hands-on', 'OC6', 'B-S', 'A'),
]

# --- national pay by trade ----------------------------------------------------------------------------------------
print('SES 2022')
ses = {}
for size in ('GE10', 'TOTAL'):
    rows, _ = es.table('earn_ses22_48', sex='T', unit='EUR', indic_se='ERN', sizeclas=size)
    for co, v in rows:
        ses.setdefault((co['geo'], co['isco08'], co['nace_r2']), v)


def nat_pay(c, isco, nace):
    """Mean monthly gross pay; falls back to wider sectors, then the EU, scaled by the country's overall level."""
    for n in (nace, {'J': 'G-J', 'K': 'K-N', 'M': 'K-N', 'N': 'K-N', 'P': 'P-S', 'Q': 'P-S', 'R': 'P-S', 'O': 'O-S',
                     'G': 'G-J', 'H': 'G-J', 'I': 'G-J', 'C': 'B-E', 'F': 'B-F'}.get(nace), 'B-S'):
        if n and (c, isco, n) in ses:
            return ses[(c, isco, n)], n == nace
    eu, tot, eu_tot = ses.get(('EU27_2020', isco, nace)), ses.get((c, 'TOTAL', 'B-S')), ses.get(('EU27_2020', 'TOTAL', 'B-S'))
    if eu and tot and eu_tot:
        return eu * tot / eu_tot, False
    return None, False


# --- regional pay level -------------------------------------------------------------------------------------------
print('regional pay level')
rhr = {co['geo']: v for co, v in es.table('earn_ses22_rhr', sex='T', unit='EUR')[0]}
coe = es.latest('nama_10r_2coe', currency='MIO_EUR', nace_r2='TOTAL', sinceTimePeriod=2018)
sal = defaultdict(float)
for g, (v, t) in es.latest('nama_10r_3empers', wstatus='SAL', nace_r2='TOTAL', unit='THS', sinceTimePeriod=2018).items():
    if len(g) == 5:
        sal[g[:4]] += v
pop = {g: R[g]['population'] or 0 for g in REG}


def n1_level(g):
    c = g[:2]
    v = rhr.get(g[:3])
    if v is None:
        return 1.0
    sib = [(rhr[k], sum(pop[x] for x in REG if x[:3] == k)) for k in rhr if k[:2] == c and len(k) == 3]
    w = sum(p for _, p in sib)
    mean = sum(a * p for a, p in sib) / w if w else v
    return v / mean if mean else 1.0


def n2_level(g):
    """NUTS 2 pay per employee against its NUTS 1 region, square-rooted (the SES level already carries most of it)."""
    k = g[:4]
    if k not in coe or not sal.get(k):
        return 1.0
    mine = coe[k][0] / sal[k]
    sib = [x for x in coe if len(x) == 4 and x[:3] == g[:3] and sal.get(x)]
    num = sum(coe[x][0] for x in sib)
    den = sum(sal[x] for x in sib)
    return math.sqrt(mine / (num / den)) if den and num else 1.0


level = {g: n1_level(g) * n2_level(g) for g in REG}

# --- net pay curves -----------------------------------------------------------------------------------------------
print('net pay')
net = defaultdict(dict)
for co, v in es.table('earn_nt_net', currency='EUR', sinceTimePeriod=2022)[0]:
    if co['ecase'].startswith('P1_NCH_AW') and co['estruct'] in ('GRS', 'NET'):
        net[(co['geo'], co['ecase'])].setdefault(co['time'], {})[co['estruct']] = v
curves = {}
for c in CTRY:
    pts = []
    for case in ('P1_NCH_AW50', 'P1_NCH_AW67', 'P1_NCH_AW80', 'P1_NCH_AW100', 'P1_NCH_AW125', 'P1_NCH_AW167'):
        ys = net.get((c, case), {})
        good = [t for t in ys if 'GRS' in ys[t] and 'NET' in ys[t] and ys[t]['GRS']]
        if good:
            t = max(good)
            pts.append([round(ys[t]['GRS']), round(ys[t]['NET'])])
    if len(pts) >= 3:
        curves[c] = sorted(pts)

# --- price level of consumption (EU27 = 100) ----------------------------------------------------------------------
pli = {}
try:
    for g, (v, t) in es.latest('prc_ppp_ind', na_item='PLI_EU27_2020', ppp_cat='A01', sinceTimePeriod=2019).items():
        pli[g] = v
except Exception as e:
    print('price levels skipped', e)

# --- rent -----------------------------------------------------------------------------------------------------------
print('rent')
rent_pts = es.latest('prc_colc_rents', currency='EUR', building='FLAT1', sinceTimePeriod=2019)
lab = es.labels('prc_colc_rents', 'geo', currency='EUR', building='FLAT1', sinceTimePeriod=2019)
metro_of = {}
for c in cities:
    for g in c.get('counties') or []:
        metro_of.setdefault(g, c)


ALIAS = {'Den Haag': "s' Gravenhage"}


def find_metro(country, name):
    name = ALIAS.get(name, name).split(' (')[0].split('/')[0].lower()
    best = [c for c in cities if country in (c.get('states') or []) and c['name'].lower().startswith(name[:5])]
    return max(best, key=lambda c: c['population'] or 0) if best else None


anchors = defaultdict(list)  # country -> [(metro, rent, label)]
for code, (v, t) in rent_pts.items():
    c = code[:2]
    c = 'EL' if c == 'GR' else c
    if c not in CTRY:
        continue
    if code.endswith('_CAP'):
        m = next((x for x in cities if c in (x.get('states') or []) and x.get('capital')), None) or find_metro(c, lab[code])
    else:
        m = find_metro(c, lab[code])
    if m:
        anchors[c].append((m, v, lab[code], code.endswith('_CAP')))
if 'LI' in CTRY and 'LI' not in anchors and 'CH' in anchors:
    anchors['LI'] = anchors['CH']


def inc(g):
    return R[g]['income_pps'] or R[g]['gdp_pps'] or None


def group_mean(gs, f):
    num = den = 0
    for g in gs:
        v = f(g)
        if v and pop[g]:
            num += v * pop[g]; den += pop[g]
    return num / den if den else None


# Exponents fitted on Urban Audit rents per m2 (urb_clivcon SA1049V) for 68 cities in five countries against their
# capital: log rent ratio ~ 0.96 log(income ratio) + 0.17 log(metro population ratio). A region outside a metro uses
# its own population. The nearest rent anchor in the country is used (Germany and Switzerland have several).
grid = world['grid']
GR, GC = grid['radius'], grid['cols']


def xy(cell):
    r = cell // GC
    return (math.sqrt(3) * GR * ((cell % GC) + 0.5 * (r & 1)), 1.5 * GR * r)


def size_of(g):
    m = metro_of.get(g)
    return (m['population'] if m and m.get('population') else R[g]['population']) or None


rent, rent_q = {}, {}
for g in REG:
    c = R[g]['state']
    al = anchors.get(c)
    if not al:
        rent[g], rent_q[g] = None, None
        continue
    m = metro_of.get(g)
    own = next((a for a in al if m and a[0]['id'] == m['id']), None)
    if own:
        a = own
    else:
        gx, gy = xy(R[g]['cell']) if R[g]['cell'] is not None else (0, 0)
        a = min(al, key=lambda a: math.hypot(gx - a[0]['x'], gy - a[0]['y']))
    ag = a[0].get('counties') or []
    ai = group_mean(ag, inc)
    ri = inc(g)
    ratio = 1.0
    if ri and ai:
        ratio *= (ri / ai) ** 0.96
    sg, sa = size_of(g), a[0].get('population')
    if sg and sa:
        ratio *= (sg / sa) ** 0.17
    ratio = max(0.3, min(1.3, ratio))
    rent[g] = int(round(a[1] * ratio / 10) * 10)
    rent_q[g] = 'survey' if own else 'estimate'

# --- jobs in your field -------------------------------------------------------------------------------------------
print('occupations and sectors')
occ = defaultdict(dict)
for co, v in es.table('cens_21cobo_r2', c_birth='TOTAL', sex='T', age='TOTAL', unit='NR')[0]:
    occ[co['geo']][co['isco08']] = v


def occ_share(g, isco):
    for k in (g[:4], g[:3], g[:2]):
        d = occ.get(k)
        if d and d.get('TOTAL') and isco in d:
            return d[isco] / d['TOTAL']
    return None


SECT = ['TOTAL', 'A', 'C', 'F', 'G-I', 'G-J', 'J', 'K', 'K-N', 'L', 'M_N', 'O-Q', 'O-U', 'R-U']
emp3 = defaultdict(dict)
for co, v in es.table('nama_10r_3empers', wstatus='EMP', nace_r2=SECT, unit='THS', sinceTimePeriod=2020)[0]:
    g, t = co['geo'], co['time']
    cur = emp3[g].get(co['nace_r2'])
    if cur is None or t > cur[1]:
        emp3[g][co['nace_r2']] = (v, t)

# counties.json already carries the sector shares the earlier pipeline split for countries that publish only wider
# groups at NUTS 3 (DE, AT, ES, PL); the rest come from the regional accounts, else the region's metro, else the
# country's metros on average.
COUNTY_COL = {'A': 'agriculture_share', 'C': 'manufacturing_share', 'J': 'information_share', 'K': 'finance_share',
              'O-Q': 'public_admin_share', 'R-U': 'arts_share'}
METRO_KEY = {'F': 'construction', 'G-I': 'trade', 'M_N': 'professional'}


def metro_share(c, key):
    j = c.get('jobs') or {}
    tot = sum(v for v in j.values() if v)
    return j.get(key) / tot if tot and j.get(key) is not None else None


country_metro = defaultdict(dict)
for key in METRO_KEY.values():
    acc = defaultdict(lambda: [0.0, 0.0])
    for c in cities:
        v = metro_share(c, key)
        if v is not None and c.get('population'):
            for st in c.get('states') or []:
                acc[st][0] += v * c['population']; acc[st][1] += c['population']
    for st, (a, b) in acc.items():
        country_metro[key][st] = a / b


def sector_share(g, s):
    if s == 'TOTAL':
        return 1.0
    if s in COUNTY_COL:
        return R[g].get(COUNTY_COL[s])
    d = emp3.get(g, {})
    tot = d.get('TOTAL', (None,))[0]
    if tot and s in d:
        return d[s][0] / tot
    key = METRO_KEY.get(s)
    m = metro_of.get(g)
    v = metro_share(m, key) if m else None
    return v if v is not None else country_metro[key].get(g[:2])


eu_occ = {i: (sum((occ_share(g, i) or 0) * pop[g] for g in REG) / sum(pop.values())) for i in {t[3] for t in TRADES}}
eu_sec = {}
for s in {t[5] for t in TRADES}:
    num = den = 0
    for g in REG:
        v = sector_share(g, s)
        if v is not None:
            num += v * pop[g]; den += pop[g]
    eu_sec[s] = num / den if den else None

# --- momentum from history.json -----------------------------------------------------------------------------------
HY = history['years']
NY = len(HY)


def hval(key, i, y):
    return history['series'][key][i * NY + (y - HY[0])] if HY[0] <= y <= HY[-1] else None


def growth(key, i, a, b):
    va = next((hval(key, i, y) for y in range(a, a + 3) if hval(key, i, y)), None)
    vb = next((hval(key, i, y) for y in range(b, b - 3, -1) if hval(key, i, y)), None)
    return round(vb / va - 1, 4) if va and vb else None


jl = history['range']['jobs'][1]
pl = history['range']['pop'][1]

# --- languages --------------------------------------------------------------------------------------------------------
LANG = {'AT': ['de'], 'BE': ['nl', 'fr'], 'BG': ['bg'], 'CY': ['el', 'tr'], 'CZ': ['cs'], 'DE': ['de'], 'DK': ['da'], 'EE': ['et'],
        'EL': ['el'], 'ES': ['es'], 'FI': ['fi', 'sv'], 'FR': ['fr'], 'HR': ['hr'], 'HU': ['hu'], 'IE': ['en', 'ga'], 'IT': ['it'],
        'LT': ['lt'], 'LU': ['lb', 'fr', 'de'], 'LV': ['lv'], 'MT': ['mt', 'en'], 'NL': ['nl'], 'PL': ['pl'], 'PT': ['pt'], 'RO': ['ro'],
        'SE': ['sv'], 'SI': ['sl'], 'SK': ['sk'], 'UK': ['en'], 'CH': ['de'], 'NO': ['no'], 'IS': ['is'], 'LI': ['de'], 'TR': ['tr'],
        'RS': ['sr'], 'MK': ['mk'], 'ME': ['sr'], 'AL': ['sq']}
REGIONAL = {'BE1': ['fr', 'nl'], 'BE2': ['nl'], 'BE3': ['fr'], 'BE336': ['de', 'fr'], 'CH01': ['fr'], 'CH02': ['de', 'fr'], 'CH07': ['it'],
            'CH013': ['fr'], 'ITH1': ['de', 'it'], 'ES51': ['es', 'ca'], 'ES52': ['es', 'ca'], 'ES53': ['es', 'ca'], 'ES21': ['es', 'eu'],
            'ES22': ['es', 'eu'], 'ES11': ['es', 'gl'], 'FI1B': ['fi', 'sv'], 'FI20': ['sv'], 'ITC2': ['it', 'fr'], 'UKL': ['en', 'cy']}


def langs(g):
    for k in (g, g[:4], g[:3]):
        if k in REGIONAL:
            return REGIONAL[k]
    return LANG.get(g[:2], [])


eng = {}
try:
    for g, (v, t) in es.latest('edat_aes_l31', age='Y25-64', sex='T', lev_know=['PROF'], unit='PC').items():
        eng[g] = v
    for g, (v, t) in es.latest('edat_aes_l31', age='Y25-64', sex='T', lev_know=['GOOD'], unit='PC').items():
        if g in eng:
            eng[g] = round(eng[g] + v, 1)
except Exception as e:
    print('language skills skipped', e)
for c in ('IE', 'MT', 'UK'):
    eng[c] = 100.0

# --- assemble -----------------------------------------------------------------------------------------------------------
pay_out, jobs_out, pay_q = {}, {}, {}
for tid, label, grp, isco, nace, sect in TRADES:
    pays, jobs = [], []
    exact = {}
    for c in CTRY:
        exact[c] = nat_pay(c, isco, nace)
    for g in REG:
        c = R[g]['state']
        p, ok = exact[c]
        pays.append(None if p is None else int(round(p * level[g] / 10) * 10))
        o, s = occ_share(g, isco), sector_share(g, sect)
        if o is None or s is None or not eu_occ.get(isco) or not eu_sec.get(sect):
            jobs.append(None)
        else:
            jobs.append(round(math.sqrt((o / eu_occ[isco]) * (s / eu_sec[sect])), 2))
    pay_out[tid], jobs_out[tid] = pays, jobs
    pay_q[tid] = {c: ('trade' if exact[c][1] else 'estimate') if exact[c][0] else None for c in CTRY}

regions = []
for i, g in enumerate(REG):
    r = R[g]
    regions.append([round(level[g], 3), rent[g], rent_q[g] == 'survey', '+'.join(langs(g)),
                    growth('jobs', i, jl - 10, jl), growth('pop', i, pl - 10, pl)])

out = {
    'vintage': 'SES 2022 pay, Census 2021 occupations, Eurostat regional accounts, EU rent survey 2025',
    'trades': [{'id': t[0], 'label': t[1], 'group': t[2], 'isco': t[3], 'nace': t[4], 'sector': t[5]} for t in TRADES],
    'regionFields': ['payLevel', 'rent1', 'rentSurvey', 'langs', 'jobsGrowth10y', 'popGrowth10y'],
    'regions': regions,
    'pay': pay_out,
    'payQuality': pay_q,
    'jobs': jobs_out,
    'net': curves,
    'pli': {c: pli.get(c) for c in CTRY},
    'english': {c: eng.get(c) for c in CTRY},
    'rentAnchors': {c: [[a[2], a[1], a[0]['id']] for a in al] for c, al in anchors.items()},
    'momentumYears': {'jobs': [jl - 10, jl], 'pop': [pl - 10, pl]},
}
with open(OUT + '/advisor.json', 'w') as f:
    json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
print('advisor.json', len(REG), 'regions,', len(TRADES), 'trades; net curves for', len(curves), 'countries; rent anchors for', len(anchors))
