"""cities.json (metro regions), states.json (countries), nation.json (the whole map), counties.json (NUTS 3), plus interims."""
import math, re
from collections import defaultdict
import numpy as np
import openpyxl, shapely
from shapely.geometry import shape, Point
import es, uk, lau
from common import *

meta, proj, grid = world_ctx()
REG = meta['regions']
RIDX = {r: i for i, r in enumerate(REG)}
COUNTRIES = meta['countries']
world = load_json(OUT + '/world.json')
owner = np.array(world['owner']); county = np.array(world['county']); water = np.array(world['water'])
cell_samples = {int(k): {int(a): b for a, b in v.items()} for k, v in meta['cell_samples'].items()}
regc = load_interim('_regions')  # id -> [x, y, area_km2]

# ---- crosswalks 2024 -> 2021 / 2016 by centroid ---------------------------------------------------------------------
pt24 = nuts3_points()


def crosswalk(year):
    """2024 NUTS3 -> the NUTS3 of `year` that it overlaps most (same code when it still exists)."""
    feats = load_json(f'{RAW}/nuts/nutsrg_{year}_3.json')['features']
    geoms = [shape(f['geometry']).buffer(0) for f in feats]
    ids = [f['properties']['id'] for f in feats]
    tree = shapely.STRtree(geoms)
    cur = {f['properties']['id']: shape(f['geometry']).buffer(0) for f in nuts3_features()}
    out = {}
    for r in REG:
        if r in ids:
            out[r] = r
            continue
        g = cur[r]
        best, ba = None, 0
        for k in tree.query(g):
            a = g.intersection(geoms[k]).area
            if a > ba:
                best, ba = ids[k], a
        if best:
            out[r] = best
    return out


X21 = crosswalk(2021)
X16 = crosswalk(2016)
REGSET = set(REG)


def sibling_share(series):
    """For regions found only through their 2021 code: the share of that 2021 region they stand for. When a 2021 region
    was split in 2024 (Norway's counties, for instance), each piece gets its population share instead of the whole value."""
    groups = defaultdict(list)
    for r in REG:
        if r not in series and X21.get(r) in series:
            groups[X21[r]].append(r)
    share = {}
    for c, rs in groups.items():
        ps = [val(pop.get(r)) or 0 for r in rs]
        tot = sum(ps)
        for r, p in zip(rs, ps):
            share[r] = (p / tot) if tot and len(rs) > 1 else 1.0
    return share


def get3(series, r, *alts):
    """Value of a NUTS3-keyed dict for 2024 region r, falling back to its 2021 code."""
    if r in series:
        return series[r]
    for x in alts:
        c = x.get(r)
        if c and c in series:
            return series[c]
    return None


def get2(series, r):
    """NUTS2-level value for NUTS3 region r (2024 code prefix, then its 2021 code's prefix, then NUTS1)."""
    for code in (r[:4], X21.get(r, r)[:4], r[:3]):
        if code in series:
            return series[code]
    return None


def val(x):
    return None if x is None else x[0]


# ---- Eurostat downloads ------------------------------------------------------------------------------------------
print('fetching eurostat...')
pop = es.latest('demo_r_pjanaggr3', sex='T', age='TOTAL', unit='NR', sinceTimePeriod=2023)
pop_rows, _ = es.table('demo_r_pjanaggr3', sex='T', age='TOTAL', unit='NR', sinceTimePeriod=2015)
pop_series = defaultdict(dict)
for co, v in pop_rows:
    pop_series[co['geo']][co['time']] = v
age_rows, _ = es.table('demo_r_pjangrp3', sex='T', unit='NR', time=2025)
ages = defaultdict(dict)
for co, v in age_rows:
    ages[co['geo']][co['age']] = v
medage = es.latest('demo_r_pjanind3', indic_de='MEDAGEPOP', unit='YR', sinceTimePeriod=2022)
gdp = es.latest('nama_10r_3gdp', unit='MIO_EUR', sinceTimePeriod=2021)
gdp_pps = es.latest('nama_10r_3gdp', unit='PPS_EU27_2020_HAB', sinceTimePeriod=2021)
area = es.latest('reg_area3', landuse='L0008', unit='KM2', sinceTimePeriod=2015)
area_tot = es.latest('reg_area3', landuse='TOTAL', unit='KM2', sinceTimePeriod=2015)
NACE = ['TOTAL', 'A', 'B-E', 'C', 'F', 'G-I', 'J', 'K', 'L', 'M_N', 'O-Q', 'R-U', 'G-J', 'K-N', 'O-U']
emp_rows, _ = es.table('nama_10r_3empers', wstatus='EMP', unit='THS', nace_r2=NACE, sinceTimePeriod=2021)
gva_rows, _ = es.table('nama_10r_3gva', unit='CP_MEUR', nace_r2=NACE, sinceTimePeriod=2021)


def latest_by(rows, dim):
    best = defaultdict(dict)
    for co, v in rows:
        g, k, t = co['geo'], co[dim], co['time']
        if k not in best[g] or t > best[g][k][1]:
            best[g][k] = (v, t)
    return best


emp = latest_by(emp_rows, 'nace_r2')
gva = latest_by(gva_rows, 'nace_r2')
NACE_TREE = {'G-J': ['G-I', 'J'], 'K-N': ['K', 'L', 'M_N'], 'O-U': ['O-Q', 'R-U'], 'B-E': ['C']}
ESTIMATED = set()


def fill_children(tables):
    """Some countries (DE, AT, ES, PL) publish only G-J, K-N, O-U at NUTS 3: split them with the nearest parent region's mix."""
    for g, t in tables.items():
        if len(g) != 5:
            continue
        for parent, kids in NACE_TREE.items():
            if parent not in t or all(k in t for k in kids):
                continue
            for anc in (g[:4], g[:3], g[:2]):
                a = tables.get(anc)
                if a and parent in a and all(k in a for k in kids) and a[parent][0]:
                    for k in kids:
                        if k not in t:
                            t[k] = (t[parent][0] * a[k][0] / a[parent][0], t[parent][1])
                            ESTIMATED.add(g)
                    break


fill_children(emp)
fill_children(gva)
print('regions with industry splits estimated from their parent region:', len(ESTIMATED))

# ---- United Kingdom: ONS population & GDP, BRES jobs ------------------------------------------------------------------
fx_rows, _ = es.table('ert_bil_eur_a', currency='GBP', statinfo='AVG', unit='NAC', sinceTimePeriod=2015)
GBP_PER_EUR = {co['time']: v for co, v in fx_rows}
UKREG = {r: world['counties'][RIDX[r]]['name'] for r in REG if r[:2] == 'UK'}
UK_ONS = uk.ons_regions(UKREG)
UK_JOBS = uk.bres_jobs()
for r, d in UK_ONS.items():
    ps = d.get('population', {})
    if ps:
        y = max(ps)
        pop[r] = (round(ps[y]), str(int(y) + 1))  # mid-year estimate ~ 1 January of the next year
        pop_series[r] = {str(int(y) + 1): round(v) for y, v in ps.items()}
    gs = d.get('gdp_gbp', {})
    if gs:
        y = max(gs)
        gdp[r] = (gs[y] / GBP_PER_EUR[y] / 1e6, y)
UK_GVA, UK_GVA_YEAR = uk.gva_industry(UKREG, {r: 1 for r in gdp if r[:2] == 'UK'})
_m = [(t['TOTAL'][0], UK_ONS[r]['gdp_gbp'][UK_GVA_YEAR]) for r, t in UK_GVA.items()
      if not t.get('_share') and 'TOTAL' in t and UK_GVA_YEAR in UK_ONS.get(r, {}).get('gdp_gbp', {})]
GVA_PER_GDP = sum(a for a, _ in _m) / sum(b for _, b in _m)
for r, t in UK_GVA.items():
    rate = GBP_PER_EUR[UK_GVA_YEAR]
    if t.pop('_share', False):
        base = UK_ONS[r]['gdp_gbp'][UK_GVA_YEAR] * GVA_PER_GDP
        gva[r] = {k: (v * base / rate / 1e6, y) for k, (v, y) in t.items()}
    else:
        gva[r] = {k: (v / rate / 1e6, y) for k, (v, y) in t.items()}
print('UK regions with GVA by industry', len(UK_GVA), 'GVA/GDP', round(GVA_PER_GDP, 3))
for r, t in UK_JOBS.items():
    if r in REGSET:
        emp[r] = {k: (v / 1000, yr) for k, (v, yr) in t.items()}
print('UK regions with ONS data', len(UK_ONS), 'with BRES jobs', len([r for r in UK_JOBS if r in REGSET]))

# ---- jobs estimated from GVA where Eurostat has no NUTS 3 employment (CH, TR, AL, ME...) --------------------------------
# jobs in an industry = the region's GVA in it ÷ the country's GVA per worker in that industry (national accounts and LFS).
LEAVES = {'A': ['A'], 'BDE': ['B', 'D', 'E'], 'C': ['C'], 'F': ['F'], 'G-I': ['G', 'H', 'I'], 'J': ['J'], 'K': ['K'], 'L': ['L'],
          'M_N': ['M', 'N'], 'O-Q': ['O', 'P', 'Q'], 'R-U': ['R', 'S', 'T', 'U']}
GROUPS = {'B-E': ['BDE', 'C'], 'G-J': ['G-I', 'J'], 'K-N': ['K', 'L', 'M_N'], 'O-U': ['O-Q', 'R-U'], 'TOTAL': list(LEAVES)}
NO_EMP = sorted({r[:2] for r in REG if r[:2] != 'UK'} - {g[:2] for g in emp if len(g) == 5})
ALLC = sorted({r[:2] for r in REG})
nat_jobs_rows, _ = es.table('lfsa_egan2', geo=ALLC, sex='T', age='Y15-74', unit='THS_PER', sinceTimePeriod=2019)
nat_a10e_rows, _ = es.table('nama_10_a10_e', geo=ALLC, unit='THS_PER', na_item='EMP_DC',
                            nace_r2=['TOTAL', 'A', 'B-E', 'C', 'F', 'G-I', 'J', 'K', 'L', 'M_N', 'O-Q', 'R-U'], sinceTimePeriod=2019)
nat_gva_rows, _ = es.table('nama_10_a10', geo=ALLC, unit='CP_MEUR', na_item='B1G',
                           nace_r2=['TOTAL', 'A', 'B-E', 'C', 'F', 'G-I', 'J', 'K', 'L', 'M_N', 'O-Q', 'R-U'], sinceTimePeriod=2019)
nat_jobs = latest_by(nat_jobs_rows, 'nace_r2')
nat_a10e = latest_by(nat_a10e_rows, 'nace_r2')
nat_gva = latest_by(nat_gva_rows, 'nace_r2')


def nat_job_leaves(cc):
    """National jobs by leaf industry: national accounts (nama_10_a10_e), else the Labour Force Survey (lfsa_egan2)."""
    a = nat_a10e.get(cc)
    if a and all(k in a for k in ('A', 'B-E', 'C', 'F', 'G-I', 'J', 'K', 'L', 'M_N', 'O-Q', 'R-U')):
        return leaf_table(a)
    nj = nat_jobs.get(cc)
    if not nj:
        return None
    return {k: sum(nj[x][0] for x in secs if x in nj) for k, secs in LEAVES.items()}


def leaf_table(t):
    """{leaf: value} from a {nace: (v, t)} table; BDE = B-E minus C."""
    o = {k: t[k][0] for k in LEAVES if k in t and k != 'BDE'}
    if 'B-E' in t and 'C' in t:
        o['BDE'] = max(0.0, t['B-E'][0] - t['C'][0])
    return o


def complete(t, mix):
    """Fill the missing leaves of a region's GVA: a group's (or the total's) remainder is split by the country's mix."""
    have = leaf_table(t)
    if 'B-E' in t and 'C' not in t:
        have.pop('BDE', None)
    for grp in ('B-E', 'G-J', 'K-N', 'O-U', 'TOTAL'):
        if grp not in t:
            continue
        kids = GROUPS[grp]
        miss = [k for k in kids if k not in have]
        if not miss:
            continue
        rest = max(0.0, t[grp][0] - sum(have.get(k, 0) for k in kids))
        w = sum(mix.get(k, 0) for k in miss)
        for k in miss:
            have[k] = rest * (mix.get(k, 0) / w if w else 1 / len(miss))
    return have


JOBS_FROM_GVA = set()
for r in REG:
    cc = r[:2]
    if cc not in NO_EMP:
        continue
    g = get3(gva, r, X21)
    nj, ng = nat_job_leaves(cc), nat_gva.get(cc)
    if not g or not nj or not ng:
        continue
    mix = leaf_table(ng)
    leaves = complete(g, mix)
    yr = g['TOTAL'][1] if 'TOTAL' in g else max(v[1] for v in g.values())
    per_worker = {}
    for k in LEAVES:
        w = nj.get(k)
        if w and mix.get(k):
            per_worker[k] = mix[k] / w
    jobs = {k: v / per_worker[k] for k, v in leaves.items() if per_worker.get(k)}
    if len(jobs) < len(LEAVES):
        continue
    def pack(d):
        o = {k: (d[k], yr) for k in LEAVES if k != 'BDE'}
        o['B-E'] = (d['BDE'] + d['C'], yr)
        o['TOTAL'] = (sum(d.values()), yr)
        return o
    emp[r] = pack(jobs)
    gva[r] = pack(leaves)
    JOBS_FROM_GVA.add(r)
# Regions whose jobs total is published but some industries are withheld (e.g. Oslo's farm jobs): the withheld
# industries share the remainder in the proportions of the country's job mix.
# The regional GVA year can lag the national one: scale each country's estimates so its jobs add up to the national total.
for cc in NO_EMP:
    rs = [r for r in JOBS_FROM_GVA if r[:2] == cc]
    nj = nat_job_leaves(cc)
    est = sum(emp[r]['TOTAL'][0] for r in rs)
    if rs and nj and est:
        f = sum(nj.values()) / est
        for r in rs:
            emp[r] = {k: (v[0] * f, v[1]) for k, v in emp[r].items()}


def fill_withheld():
    n = 0
    for r, t in list(emp.items()):
        if len(r) != 5 or r[:2] not in ALLC or 'TOTAL' not in t:
            continue
        if all(k in t for k in ('A', 'B-E', 'C', 'F', 'G-I', 'J', 'K', 'L', 'M_N', 'O-Q', 'R-U')):
            continue
        mix = nat_job_leaves(r[:2])
        if not mix:
            continue
        leaves = complete(t, mix)
        yr = t['TOTAL'][1]
        for k in LEAVES:
            if k != 'BDE' and k not in t and k in leaves:
                t[k] = (leaves[k], yr)
        if 'B-E' not in t and 'BDE' in leaves and 'C' in t:
            t['B-E'] = (leaves['BDE'] + t['C'][0], yr)
        n += 1

    return n


print('regions with withheld industries filled from the national mix:', fill_withheld())
print('countries without NUTS 3 jobs', NO_EMP, '; regions with jobs estimated from GVA', len(JOBS_FROM_GVA))

# NUTS 2 indicators
inc = es.latest('nama_10r_2hhinc', unit='EUR_HAB', direct='BAL', na_item='B6N', sinceTimePeriod=2019)
inc_pps = es.latest('nama_10r_2hhinc', unit='PPS_EU27_2020_HAB', direct='BAL', na_item='B6N', sinceTimePeriod=2019)
unemp = es.latest('lfst_r_lfu3rt', isced11='TOTAL', sex='T', age='Y15-74', unit='PC', sinceTimePeriod=2021)
edu = {k: es.latest('edat_lfse_04', isced11=k, sex='T', age='Y25-64', unit='PC', sinceTimePeriod=2021) for k in ('ED0-2', 'ED3_4', 'ED5-8')}
life = es.latest('demo_r_mlifexp', sex='T', age='Y_LT1', unit='YR', sinceTimePeriod=2020)
arope = es.latest('ilc_peps11n', unit='PC', sinceTimePeriod=2019)
broad = es.latest('isoc_r_broad_h', unit='PC_HH', sinceTimePeriod=2018)
nights = es.latest('tour_occ_nin2', c_resid='TOTAL', unit='NR', nace_r2='I551-I553', sinceTimePeriod=2022)
rd = es.latest('rd_e_gerdreg', sectperf='TOTAL', unit='PC_GDP', sinceTimePeriod=2018)
htec = es.latest('htec_emp_reg2', nace_r2='HTC', sex='T', unit='PC_EMP', sinceTimePeriod=2021)
cob_rows, _ = es.table('lfst_r_lfsd2pwc', wstatus='POP', sex='T', age='Y15-74', unit='THS_PER', c_birth=['TOTAL', 'NAT', 'EU27_2020_FOR', 'NEU27_2020_FOR', 'FOR'], sinceTimePeriod=2022)
cob = latest_by(cob_rows, 'c_birth')
print('eurostat done')

YEAR_POP = 2025

# ---- per NUTS3 base rows --------------------------------------------------------------------------------------------
IND = [('agriculture', 'A', 'Agriculture, forestry & fishing'),
       ('energy_mining', None, 'Mining, energy & water (B, D, E)'),
       ('manufacturing', 'C', 'Manufacturing'), ('construction', 'F', 'Construction'),
       ('trade', 'G-I', 'Trade, transport, hotels & restaurants'), ('information', 'J', 'Information & communication'),
       ('finance', 'K', 'Finance & insurance'), ('real_estate', 'L', 'Real estate'),
       ('professional', 'M_N', 'Professional, scientific, technical & support services'),
       ('public_admin', 'O-Q', 'Public administration, education & health'), ('arts', 'R-U', 'Arts, recreation & other services')]


def ind_split(table, scale):
    """{key: value} from a {nace: (v, t)} dict (or None)."""
    if not table:
        return None, None
    o = {}
    for k, code, _ in IND:
        if code:
            v = table.get(code)
            o[k] = None if v is None else v[0] * scale
        else:
            be, c = table.get('B-E'), table.get('C')
            o[k] = None if (be is None or c is None) else max(0.0, (be[0] - c[0]) * scale)
    tot = table.get('TOTAL')
    year = tot[1] if tot else None
    return o, year


def fill_from_parent(series, is_table):
    """Regions with no NUTS 3 value (2024 or 2021 code) get their NUTS 2 parent's remainder, split by population."""
    missing = [r for r in REG if r not in series and X21.get(r) not in series]
    by_parent = defaultdict(list)
    for r in missing:
        p = X21.get(r, r)[:4]
        if p in series:
            by_parent[p].append(r)
    n = 0
    for p, rs in by_parent.items():
        known = [c for c in series if len(c) == 5 and c[:4] == p]
        tot_pop = sum(val(pop.get(r)) or 0 for r in rs)
        if not tot_pop:
            continue
        if is_table:
            rest = {k: (max(0.0, v[0] - sum(series[c][k][0] for c in known if k in series[c])), v[1]) for k, v in series[p].items()}
        else:
            rest = (max(0.0, series[p][0] - sum(series[c][0] for c in known)), series[p][1])
        for r in rs:
            f = (val(pop.get(r)) or 0) / tot_pop
            series[r] = {k: (v[0] * f, v[1]) for k, v in rest.items()} if is_table else (rest[0] * f, rest[1])
            n += 1
    return n


# Countries with no regional accounts at all (Iceland, Liechtenstein): national GDP and jobs, split by population.
nat_gdp = es.latest('nama_10_gdp', geo=ALLC, unit='CP_MEUR', na_item='B1GQ', sinceTimePeriod=2019)
BY_POP = []
for cc in ALLC:
    rs = [r for r in REG if r[:2] == cc]
    if any(r in gdp or X21.get(r) in gdp for r in rs) or cc not in nat_gdp:
        continue
    tp = sum(val(pop.get(r)) or 0 for r in rs)
    nj = nat_job_leaves(cc)
    for r in rs:
        f = (val(pop.get(r)) or 0) / tp if tp else 0
        gdp[r] = (nat_gdp[cc][0] * f, nat_gdp[cc][1])
        if nj and r not in emp:
            yr = nat_gdp[cc][1]
            t = {k: (v * f, yr) for k, v in nj.items() if k != 'BDE'}
            t['B-E'] = ((nj['BDE'] + nj['C']) * f, yr)
            t['TOTAL'] = (sum(nj.values()) * f, yr)
            emp[r] = t
        BY_POP.append(r)
print('regions with national figures split by population:', BY_POP)
uk_mix = {}
for r, t in gva.items():
    if r[:2] == 'UK' and len(r) == 5:
        for k, v in leaf_table(t).items():
            uk_mix[k] = uk_mix.get(k, 0) + v
for r, t in gva.items():
    if r[:2] == 'UK' and len(r) == 5 and 'TOTAL' in t:
        leaves = complete(t, uk_mix)
        yr = t['TOTAL'][1]
        for k in LEAVES:
            if k != 'BDE' and k not in t and k in leaves:
                t[k] = (leaves[k], yr)
        if 'B-E' not in t and 'BDE' in leaves and 'C' in t:
            t['B-E'] = (leaves['BDE'] + t['C'][0], yr)
print('regions filled from their NUTS 2 parent:', fill_from_parent(gdp, False), fill_from_parent(emp, True), fill_from_parent(gva, True), fill_withheld())
SH_POP, SH_EMP, SH_GVA, SH_GDP = sibling_share(pop), sibling_share(emp), sibling_share(gva), sibling_share(gdp)


def scaled(entry, f):
    if entry is None or f == 1:
        return entry
    if isinstance(entry, tuple):
        return (entry[0] * f, entry[1])
    return {k: (v[0] * f, v[1]) for k, v in entry.items()}


R = {}
for r in REG:
    p = val(get3(pop, r, X21))
    ps = get3(pop_series, r, X21) or {}
    e_ind, e_year = ind_split(scaled(get3(emp, r, X21), SH_EMP.get(r, 1)), 1000)
    g_ind, g_year = ind_split(scaled(get3(gva, r, X21), SH_GVA.get(r, 1)), 1e6)
    etot = scaled(get3(emp, r, X21), SH_EMP.get(r, 1))
    g = scaled(get3(gdp, r, X21), SH_GDP.get(r, 1))
    a = val(get3(area, r, X21)) or val(get3(area_tot, r, X21)) or regc[r][2]
    R[r] = dict(
        population=p, series=ps, area=a,
        employed=None if not etot or 'TOTAL' not in etot else etot['TOTAL'][0] * 1000,
        jobs=e_ind, jobs_year=e_year, gva=g_ind,
        gdp=None if g is None else g[0] * 1e6, gdp_year=None if g is None else int(g[1]),
        gdp_pps=val(get3(gdp_pps, r, X21)), median_age=val(get3(medage, r, X21)),
        ages=get3(ages, r, X21),
        income=val(get2(inc, r)), income_pps=val(get2(inc_pps, r)), unemployment=val(get2(unemp, r)),
        tertiary=val(get2(edu['ED5-8'], r)), edu_low=val(get2(edu['ED0-2'], r)), edu_mid=val(get2(edu['ED3_4'], r)),
        life=val(get2(life, r)), arope=val(get2(arope, r)), broadband=val(get2(broad, r)),
        nights=val(get2(nights, r)), rd=val(get2(rd, r)), htec=val(get2(htec, r)),
        cob=get2(cob, r),
    )

# Population of NUTS2 (for nights per capita) computed from NUTS3 sums
pop2 = defaultdict(float)
for r in REG:
    if R[r]['population']:
        pop2[r[:4]] += R[r]['population']

# ---- metro regions ------------------------------------------------------------------------------------------------
wb = openpyxl.load_workbook(RAW + '/metro/Metro-regions-NUTS-2016.xlsx', read_only=True)
ws = wb['List of 2016 metroregions']
m16 = {}
mname = {}
for row in ws.iter_rows(min_row=2, values_only=True):
    if row[0] and row[1]:
        m16[row[0]] = row[1]; mname[row[1]] = row[3]
# Norway in the 2016 file: Rogaland is listed under Bergen and Trøndelag is missing; Eurostat's current list has
# Stavanger (NO004M) and Trondheim (NO003M) as metros of their own.
m16.update({'NO043': 'NO004M', 'NO060': 'NO003M'})
met_labels = es.labels('met_pjanaggr3', 'metroreg', sex='T', age='TOTAL', lastTimePeriod=1)
met_pop = es.latest('met_pjanaggr3', key='metroreg', sex='T', age='TOTAL', lastTimePeriod=1)
members = defaultdict(list)
# A 2024 region joins a metro when a 2016 member region covers at least 40% of it (merged regions such as Norway's
# Vestland, which took in Bergen's Hordaland, would otherwise follow whichever old region was larger).
f16 = load_json(f'{RAW}/nuts/nutsrg_2016_3.json')['features']
g16 = [shape(f['geometry']).buffer(0) for f in f16]
id16 = [f['properties']['id'] for f in f16]
t16 = shapely.STRtree(g16)
geo_now = {f['properties']['id']: shape(f['geometry']).buffer(0) for f in nuts3_features()}
for r in REG:
    m = m16.get(X16.get(r))
    if not m:
        g = geo_now[r]
        best = 0
        for k in t16.query(g):
            mm = m16.get(id16[k])
            if mm:
                a = g.intersection(g16[k]).area / g.area
                if a >= 0.4 and a > best:
                    m, best = mm, a
    if m and m[:2] in COUNTRIES:
        members[m].append(r)
print('metros with members', len(members))

# principal city position: Natural Earth populated places matched by name within the metro's regions
places = load_json(RAW + '/ne/ne_10m_populated_places_simple.geojson')['features']
cntry_iso = {'EL': 'GR', 'UK': 'GB'}


def norm(s):
    import unicodedata
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z]', '', s)


pl_by_iso = defaultdict(list)
for f in places:
    pr = f['properties']
    pl_by_iso[pr.get('iso_a2')].append((norm(pr.get('name')), norm(pr.get('nameascii')), pr.get('pop_max') or 0, f['geometry']['coordinates'], pr.get('name')))

# region of each map cell centre -> used to test whether a place sits in the metro
cell_of_region = defaultdict(list)
for i in range(grid.size):
    if county[i] >= 0:
        cell_of_region[REG[county[i]]].append(i)


def nearest_land_cell(x, y, allowed=None, maxr=3):
    c = int(grid.cell_at(x, y))
    if c >= 0 and owner[c] >= 0 and (allowed is None or c in allowed):
        return c
    best, bd = -1, 1e9
    cx, cy = grid.center(np.arange(grid.size))
    d = (cx - x) ** 2 + (cy - y) ** 2
    cand = np.argsort(d)[:200]
    for k in cand:
        if owner[k] >= 0 and (allowed is None or int(k) in allowed):
            return int(k)
    return c


cities = []
for m, regs in members.items():
    label = met_labels.get(m, mname.get(m, m))
    label = re.sub(r'\s*\(.*\)$', '', label)
    cc = m[:2]
    p = sum(R[r]['population'] or 0 for r in regs)
    if p <= 0:
        continue
    # true position
    iso = cntry_iso.get(cc, cc)
    names = [norm(x) for x in re.split(r'[/\-–,]', label) if x.strip()]
    regset = set(regs)
    pos = None
    best = None
    for (n1, n2, pm, (lon, lat), nm) in pl_by_iso.get(iso, []):
        if n1 in names or n2 in names or (names and (n1 == names[0] or n2 == names[0])):
            x, y = proj(lon, lat)
            if best is None or pm > best[0]:
                best = (pm, float(x), float(y))
    if best:
        pos = best[1:]
    else:
        dens = max(regs, key=lambda r: (R[r]['population'] or 0) / max(1, R[r]['area'] or 1))
        pos = tuple(regc[dens][:2])
    footprint = sorted(set(c for r in regs for c in cell_of_region.get(r, [])))
    cell = nearest_land_cell(pos[0], pos[1], set(footprint) if footprint else None)
    if cell not in footprint:
        footprint = sorted(set(footprint) | {cell})
    cities.append(dict(id=m, name=label, regs=sorted(regs), x=round(pos[0], 1), y=round(pos[1], 1), cell=cell,
                       footprint=footprint, capital=m.endswith('MC'), country=cc))

# Countries outside Eurostat's metro typology (TR, RS, MK, ME, AL, IS, LI): a city for each NUTS 3 region holding a
# Natural Earth place of 250,000+ people or the national capital, named after that place and made of that one region.
TOWN_MIN = 250000
no_metro = sorted(set(COUNTRIES) - {m[:2] for m in members})
reg_geom = {f['properties']['id']: shape(f['geometry']).buffer(0) for f in nuts3_features() if f['properties']['id'][:2] in no_metro}
rtree_ids = list(reg_geom)
rtree = shapely.STRtree([reg_geom[r] for r in rtree_ids])
best_place = {}
for f in places:
    pr = f['properties']
    cc = {'GR': 'EL', 'GB': 'UK'}.get(pr.get('iso_a2'), pr.get('iso_a2'))
    if cc not in no_metro:
        continue
    pm = pr.get('pop_max') or 0
    if pm < TOWN_MIN and not pr.get('adm0cap'):
        continue
    lon, lat = f['geometry']['coordinates']
    X, Y = TO3035.transform(lon, lat)
    hit = [rtree_ids[k] for k in rtree.query(Point(X, Y), predicate='within')]
    if not hit:  # places on a strait or shore (Istanbul) can fall just outside the generalised polygons
        hit = [rtree_ids[k] for k in rtree.query_nearest(Point(X, Y), max_distance=15000)]
    if not hit:
        continue
    r = hit[0]
    key = (bool(pr.get('adm0cap')), pm)
    if r not in best_place or key > best_place[r][0]:
        best_place[r] = (key, pr.get('name'), lon, lat, bool(pr.get('adm0cap')), pr.get('pop_min') or 0)
# Towns asked for by name (not metro regions in Eurostat's typology): Leuven and Edessa.
TOWNS = {'BE242': ('Leuven', 4.7005, 50.8798), 'EL524': ('Edessa', 22.0473, 40.8016)}
metro_regs = {r for regs in members.values() for r in regs}
for r, (nm, lon, lat) in TOWNS.items():
    if r in REGSET and r not in metro_regs:
        best_place[r] = ((False, 0), nm, lon, lat, False, 0)
for r, (_, nm, lon, lat, cap, ne_pop) in sorted(best_place.items()):
    if r[:2] == 'TR':
        nm = world['counties'][RIDX[r]]['name']  # a Turkish metro municipality is the whole province: use its name
    if not R[r]['population']:
        continue
    x, y = proj(lon, lat)
    footprint = sorted(cell_of_region.get(r, []))
    cell = nearest_land_cell(float(x), float(y), set(footprint) if footprint else None)
    if cell not in footprint:
        footprint = sorted(set(footprint) | {cell})
    cities.append(dict(id=r + 'C', name=nm, regs=[r], x=round(float(x), 1), y=round(float(y), 1), cell=cell, footprint=footprint,
                       capital=cap, country=r[:2], town=r in TOWNS, single=True, lon=lon, lat=lat, ne_pop=ne_pop))
print('cities from places (no Eurostat metro):', len(best_place), 'countries', no_metro)

# validate with Eurostat's own metro population
bad = []
for c in cities:
    mine = sum(R[r]['population'] or 0 for r in c['regs'])
    ref = val(met_pop.get(c['id']))
    if ref and abs(mine / ref - 1) > 0.08:
        bad.append((c['id'], c['name'], round(mine), ref))
print('metros', len(cities), 'population mismatches >8%:', len(bad), bad[:10])


# ---- aggregate helper --------------------------------------------------------------------------------------------------
def aggregate(regs):
    tot_pop = sum(R[r]['population'] or 0 for r in regs) or 1

    def covered_sum(vals):
        """Sum of the regions that report a value, if they hold at least 90% of the population; else None."""
        have = [(v, R[r]['population'] or 0) for v, r in zip(vals, regs) if v is not None]
        if not have or sum(p for _, p in have) / tot_pop < 0.9:
            return None
        return sum(v for v, _ in have)

    def ssum(key):
        return covered_sum([R[r][key] for r in regs])
    p = ssum('population')
    o = {'population': p, 'employed': ssum('employed')}
    jobs = {}
    gvab = {}
    for k, _, _ in IND:
        js = covered_sum([R[r]['jobs'][k] if R[r]['jobs'] else None for r in regs])
        jobs[k] = None if js is None else round(js)
        gs = covered_sum([R[r]['gva'][k] if R[r]['gva'] else None for r in regs])
        gvab[k] = None if gs is None else round(gs)
    o['jobs'] = jobs
    gd = ssum('gdp')
    o['gdp'] = None if gd is None else round(gd)
    yw = defaultdict(float)  # the GDP year that covers most of the population
    for r in regs:
        if R[r]['gdp_year']:
            yw[R[r]['gdp_year']] += R[r]['population'] or 0
    o['gdp_year'] = max(yw, key=yw.get) if yw else None
    o['gdp_by_industry'] = gvab

    def pw(key):  # population-weighted mean
        num = den = 0
        for r in regs:
            v, w = R[r][key], R[r]['population']
            if v is None or not w:
                continue
            num += v * w; den += w
        return None if den == 0 else num / den
    o['_pw'] = pw
    y = lambda *ks: None if any(jobs[k] is None for k in ks) else sum(jobs[k] for k in ks)
    o['yields'] = {'food': y('agriculture'), 'production': y('manufacturing', 'energy_mining', 'construction'),
                   'gold': o['gdp'], 'science': y('information', 'professional'), 'culture': y('arts')}
    inc_ = pw('income')
    une = pw('unemployment')
    o.update(median_income=None if inc_ is None else round(inc_), median_rent=None, home_value=None,
             unemployment=None if une is None else round(une / 100, 4), rent_burden=None)
    # growth 2021 -> 2025, like-for-like on the same regions
    p21 = [get3(pop_series, r, X21) or {} for r in regs]
    a = [s.get('2021') for s in p21]; b = [s.get(str(YEAR_POP)) for s in p21]
    if all(a) and all(b):
        g = sum(b) / sum(a) - 1
        o['growth'] = round(g, 4) if abs(g) < 0.25 else None
    else:
        o['growth'] = None
    o['growth_years'] = [2021, YEAR_POP]
    ser = {}
    for yr in range(2015, YEAR_POP + 1):
        vs = [s.get(str(yr)) for s in p21]
        ser[str(yr)] = None if not all(vs) else int(sum(vs))
    o['pop_series'] = ser
    return o


def finish(o):
    o.pop('_pw', None)
    return o


# cities
city_rows = []
for c in cities:
    a = aggregate(c['regs'])
    single = c.get('single', False)
    full = c['name'] + (' (' + world['counties'][RIDX[c['regs'][0]]]['name'] + ')' if single else ' metropolitan region')
    row = {'id': c['id'], 'name': c['name'], 'full': full, 'states': [c['country']],
           'metro': not single, 'capital': c['capital'], 'x': c['x'], 'y': c['y'], 'cell': c['cell']}
    row.update(finish(a))
    row['gdp_undisclosed'] = None; row['gdp_estimated'] = None
    row['counties'] = c['regs']; row['footprint'] = c['footprint']
    city_rows.append(row)
city_rows = [c for c in city_rows if c['population']]

# Single-place cities (towns, and cities where Eurostat has no metro regions) must not take the population of their
# whole NUTS 3 region (Arr. Leuven is five times Leuven). They get the population of the municipality itself:
# - Türkiye's 30 metropolitan municipalities cover their whole province by law, so the province is the city there;
# - elsewhere the LAU (municipality, or Greek local community) at the city's position, from Eurostat GISCO, summing the
#   parts of a city split into several LAUs ("Niš - Medijana", ...); where GISCO has no population, Natural Earth's
#   city-proper estimate. The larger of the two is used, never more than the region.
# Jobs, GDP and yields are then the region's, scaled by the city's share of the region's population (an estimate).
TR_METRO = {'Adana', 'Ankara', 'Antalya', 'Aydın', 'Balıkesir', 'Bursa', 'Denizli', 'Diyarbakır', 'Erzurum', 'Eskişehir', 'Gaziantep',
            'Hatay', 'İstanbul', 'İzmir', 'Kahramanmaraş', 'Kayseri', 'Kocaeli', 'Konya', 'Malatya', 'Manisa', 'Mardin', 'Mersin',
            'Muğla', 'Ordu', 'Sakarya', 'Samsun', 'Şanlıurfa', 'Tekirdağ', 'Trabzon', 'Van'}  # the 30 büyükşehir provinces
LAUS = lau.LAU()
by_id = {c['id']: c for c in cities}


def place_population(c):
    if c['country'] == 'TR' and world['counties'][RIDX[c['regs'][0]]]['name'] in TR_METRO:
        return None, 'metropolitan municipality (whole province)'
    hit = LAUS.at(c['lon'], c['lat'])
    best, src = 0, None
    if hit:
        name, p, y = hit
        if ' - ' in name:  # a city split into several LAUs: add up the parts with the same prefix
            pre = name.split(' - ')[0] + ' - '
            tot = sum(v for k, v in LAU_BY_NAME.items() if k.startswith(pre))
            p, name = (tot or p), name.split(' - ')[0]
        best, src = p, f'municipality of {name}, {y} (Eurostat GISCO LAU)'
    if c.get('ne_pop', 0) > best:
        best, src = c['ne_pop'], 'city proper (Natural Earth estimate)'
    return (best or None), src


LAU_BY_NAME = {}
for tree, geoms, props in LAUS.layers:
    for pr in props:
        v = LAUS.pop.get(pr['GISCO_ID'])
        if v and pr['LAU_NAME'] not in LAU_BY_NAME:
            LAU_BY_NAME[pr['LAU_NAME']] = v[0]

EXT_KEYS = ('population', 'employed', 'gdp')
for row in city_rows:
    c = by_id[row['id']]
    if not c.get('single'):
        continue
    reg_name = world['counties'][RIDX[c['regs'][0]]]['name']
    p, src = place_population(c)
    row['population_source'] = src
    if p is None or p >= row['population'] * 0.97:
        row['full'] = f"{row['name']} ({src})" if src and 'metropolitan' in src else f"{row['name']} ({reg_name})"
        continue
    f = p / row['population']
    row['region_population'] = row['population']
    row['scaled_from_region'] = reg_name
    for k in ('employed', 'gdp'):
        if row.get(k) is not None:
            row[k] = round(row[k] * f)
    row['population'] = int(p)
    for d in ('jobs', 'gdp_by_industry', 'yields'):
        if row.get(d):
            row[d] = {k: (None if v is None else round(v * f)) for k, v in row[d].items()}
    if row.get('pop_series'):
        row['pop_series'] = {k: (None if v is None else round(v * f)) for k, v in row['pop_series'].items()}
    row['full'] = f"{row['name']} (town; jobs and GDP scaled from {reg_name})"
    if f < 0.6:
        row['footprint'] = [row['cell']]
print('single-place cities:', [(r['name'], r['population'], r.get('region_population')) for r in city_rows if not r['metro']])
city_rows.sort(key=lambda c: -c['population'])

# unique banner cells where possible
used = set()
for c in city_rows:
    if c['cell'] in used:
        for k in c['footprint']:
            if k not in used and owner[k] >= 0:
                c['cell'] = k; break
    used.add(c['cell'])


def rank(rows, key, fn=None, reverse=True):
    vals = [(fn(r) if fn else r.get(key)) for r in rows]
    idx = [i for i, v in enumerate(vals) if v is not None]
    idx.sort(key=lambda i: (-(vals[i]) if reverse else vals[i], -(rows[i]['population'] or 0)))
    out = [None] * len(rows)
    for k, i in enumerate(idx):
        out[i] = k + 1
    return out


YK = ['food', 'production', 'gold', 'science', 'culture']
rk = {'population': rank(city_rows, 'population'), 'gdp': rank(city_rows, 'gdp'),
      'gdp_per_capita': rank(city_rows, None, lambda r: r['gdp'] / r['population'] if r['gdp'] and r['population'] else None),
      'growth': rank(city_rows, 'growth')}
for k in YK:
    rk[k] = rank(city_rows, None, lambda r, k=k: r['yields'].get(k))
for i, c in enumerate(city_rows):
    c['ranks'] = {k: v[i] for k, v in rk.items()}
    lp = math.log(c['population'])
    c['peers'] = [o['id'] for o in sorted((o for o in city_rows if o is not c), key=lambda o: abs(math.log(o['population']) - lp))[:5]]
save_json('cities', city_rows)

# metro of each region
metro_of = {}
for c in city_rows:
    for r in c['counties']:
        metro_of[r] = c['id']

# countries
states = []
by_country = defaultdict(list)
for r in REG:
    by_country[r[:2]].append(r)
state_rows = []
for ci, cc in enumerate(COUNTRIES):
    a = aggregate(by_country[cc])
    row = {'fips': cc, 'abbr': cc, 'name': COUNTRY_NAMES[cc]}
    row.update(finish(a))
    cells = np.where(owner == ci)[0]
    if len(cells):
        cx, cy = grid.center(cells)
        ext = max(cx.max() - cx.min(), cy.max() - cy.min())
        row['label'] = {'x': round(float(np.median(cx)), 1), 'y': round(float(np.median(cy)), 1), 'angle': 0,
                        'size': float(max(14, min(110, ext / 9)))}
        row['land'] = {k: round(float(np.mean([world['pct'][k][i] for i in cells if world['cover'][i] > 0] or [0])) / 100, 3)
                       for k in world['pct']}
    else:
        row['label'] = None; row['land'] = None
    state_rows.append(row)
for k in YK:
    rr = rank(state_rows, None, lambda r, k=k: r['yields'].get(k))
    for i, s in enumerate(state_rows):
        s.setdefault('ranks', {})[k] = rr[i]
save_json('states', state_rows)

# Map total
JOBS_NOTE = (' United Kingdom: BRES employment (ONS, via Nomis; Great Britain only). Switzerland, Türkiye, Albania and Montenegro, '
             'which publish no regional jobs: the region’s value added in each industry ÷ the country’s value added per worker, '
             'scaled to the national total. Iceland and Liechtenstein: national figures split by population.')
nat = finish(aggregate(REG))
nation = {
    'vintage': f'Eurostat regional accounts & demography (UK: ONS), {YEAR_POP}', 'year': YEAR_POP,
    'gdp_vintage': 'Eurostat nama_10r_3gdp, %s' % nat['gdp_year'],
    'nation': nat,
    'yields': [
        {'key': 'food', 'icon': 'y-food', 'emoji': '\U0001F33E', 'label': 'Food', 'color': '#7fbf3f', 'unit': 'workers', 'industries': ['agriculture'],
         'description': 'People employed in agriculture, forestry & fishing (NACE A), counted where they work (Eurostat nama_10r_3empers).' + JOBS_NOTE},
        {'key': 'production', 'icon': 'y-production', 'emoji': '⚙️', 'label': 'Production', 'color': '#d9823b', 'unit': 'workers',
         'industries': ['manufacturing', 'energy_mining', 'construction'],
         'description': 'People employed in industry (NACE B-E: manufacturing, mining, energy, water) and construction (F), counted where they work (Eurostat nama_10r_3empers).' + JOBS_NOTE},
        {'key': 'gold', 'icon': 'y-gold', 'emoji': '\U0001F4B0', 'label': 'Gold', 'color': '#f2c94c', 'unit': 'usd', 'industries': [],
         'description': 'Gross domestic product per year at current market prices, in euros, counted where the work is done (Eurostat nama_10r_3gdp, NUTS 3). Metro GDP is the sum of the metro region’s NUTS 3 regions. United Kingdom: ONS regional GDP (2024), converted at the year’s average pound–euro rate.'},
        {'key': 'science', 'icon': 'y-science', 'emoji': '\U0001F52C', 'label': 'Science', 'color': '#4fa3e0', 'unit': 'workers',
         'industries': ['information', 'professional'],
         'description': 'People employed in information & communication (NACE J) and professional, scientific, technical & support services (M-N), counted where they work (Eurostat nama_10r_3empers).' + JOBS_NOTE},
        {'key': 'culture', 'icon': 'y-culture', 'emoji': '\U0001F3AD', 'label': 'Culture', 'color': '#b07ce0', 'unit': 'workers', 'industries': ['arts'],
         'description': 'People employed in arts, entertainment, recreation & other services (NACE R-U), counted where they work (Eurostat nama_10r_3empers).' + JOBS_NOTE},
    ],
    'industries': {k: lbl for k, _, lbl in IND},
    'gdp_industries': {k: lbl for k, _, lbl in IND},
    'currency': 'EUR', 'region': 'Europe',
}
save_json('nation', nation)

# ---- counties.json (NUTS 3) --------------------------------------------------------------------------------------
cx_all, cy_all = grid.center(np.arange(grid.size))
reg_cells = defaultdict(list)
for i, v in cell_samples.items():
    for ri, n in v.items():
        reg_cells[ri].append((i, n))


def land_share(r, key):
    cs = reg_cells.get(RIDX[r])
    if not cs:
        return None
    num = sum(world['pct'][key][i] * n for i, n in cs)
    den = sum(n for i, n in cs)
    return round(num / den / 100, 3) if den else None


F = []


def field(key, label, fmt, unit, higher='neutral', source='', desc=''):
    F.append({'key': key, 'label': label, 'format': fmt, 'unit': unit, 'higher_is': higher, 'source': source, 'description': desc})


field('geoid', 'NUTS code', 'text', '')
field('name', 'Region', 'text', '')
field('state', 'Country', 'text', '')
field('population', 'Population', 'int', 'people', 'neutral', 'eurostat_demo', 'Population on 1 January %d (demo_r_pjanaggr3).' % YEAR_POP)
field('land_km2', 'Land area', 'km2', 'km²', 'neutral', 'eurostat_area', 'Land area (reg_area3).')
field('density', 'Density', 'float', 'people / km²', 'neutral', 'eurostat_demo', 'Population ÷ land area.')
field('gdp', 'GDP', 'usd', '€', 'good', 'eurostat_gdp', 'GDP at current market prices (nama_10r_3gdp).')
field('gdp_per_capita', 'GDP per person', 'usd', '€ / person', 'good', 'eurostat_gdp', 'GDP ÷ population (euros at current prices).')
field('gdp_pps', 'GDP per person (PPS)', 'int', 'PPS / person', 'good', 'eurostat_gdp', 'GDP per inhabitant in purchasing power standards (EU27 = about 37,000).')
field('growth', 'Population growth', 'pct', '2021–2025', 'neutral', 'eurostat_demo', 'Population change 1 Jan 2021 to 1 Jan 2025.')
field('median_age', 'Median age', 'years', 'years', 'neutral', 'eurostat_demo', 'Median age of the population (demo_r_pjanind3).')
field('elderly', 'Aged 65+', 'pct', 'share', 'neutral', 'eurostat_demo', 'Share of the population aged 65 or over.')
field('employed', 'Jobs', 'int', 'people', 'neutral', 'eurostat_emp', 'Employed persons by place of work (nama_10r_3empers).')
for k, lbl in [('agriculture', 'Farm jobs'), ('manufacturing', 'Factory jobs'), ('information', 'ICT jobs'), ('finance', 'Finance jobs'), ('public_admin', 'Public-sector jobs'), ('arts', 'Arts & leisure jobs')]:
    field(k + '_share', lbl, 'pct', 'share of jobs', 'neutral', 'eurostat_emp', f'{lbl} as a share of all jobs in the region.')
field('income', 'Disposable income', 'usd', '€ / person', 'good', 'eurostat_hhinc', 'Net disposable income of private households per inhabitant (NUTS 2, nama_10r_2hhinc).')
field('income_pps', 'Disposable income (PPS)', 'int', 'PPS / person', 'good', 'eurostat_hhinc', 'Same, in purchasing power standards (NUTS 2).')
field('unemployment', 'Unemployment', 'pct', 'rate', 'bad', 'eurostat_lfs', 'Unemployment rate, ages 15–74 (NUTS 2, lfst_r_lfu3rt).')
field('tertiary', 'Tertiary degree', 'pct', 'share of 25–64', 'good', 'eurostat_lfs', 'Share of adults 25–64 with tertiary education (NUTS 2, edat_lfse_04).')
field('life_expectancy', 'Life expectancy', 'years', 'years', 'good', 'eurostat_life', 'Life expectancy at birth (NUTS 2, demo_r_mlifexp).')
field('poverty', 'Poverty or exclusion risk', 'pct', 'share', 'bad', 'eurostat_silc', 'At risk of poverty or social exclusion (NUTS 2, ilc_peps11n).')
field('broadband', 'Broadband', 'pct', 'share of households', 'good', 'eurostat_isoc', 'Households with a broadband connection (NUTS 2, isoc_r_broad_h).')
field('foreign_born', 'Born abroad', 'pct', 'share of 15–74', 'neutral', 'eurostat_lfs', 'People aged 15–74 born in another country (NUTS 2, lfst_r_lfsd2pwc).')
field('rd', 'R&D spending', 'float', '% of GDP', 'good', 'eurostat_rd', 'Gross domestic expenditure on R&D as % of GDP (NUTS 2, rd_e_gerdreg).')
field('hightech', 'High-tech jobs', 'pct', 'share of jobs', 'good', 'eurostat_htec', 'Employment in high-technology sectors (NUTS 2, htec_emp_reg2).')
field('tourism', 'Tourist nights', 'float', 'nights / resident', 'neutral', 'eurostat_tour', 'Nights spent at tourist accommodation per resident (NUTS 2, tour_occ_nin2).')
for k, lbl in [('forest', 'Forest'), ('crop', 'Cropland'), ('pasture', 'Pasture'), ('developed', 'Built-up')]:
    field(k, lbl, 'pct', 'share of land', 'neutral', 'worldcover', f'{lbl} share of the region’s hex samples (ESA WorldCover 2021).')
field('cbsa', 'Metro region', 'text', '')
field('cell', 'Hex', 'int', '')

rows = []
nearest_cache = {}
for r in REG:
    d = R[r]
    p = d['population']
    la = d['area']
    jobs = d['jobs'] or {}
    tot = d['employed']
    sh = lambda k: None if not tot or jobs.get(k) is None else round(jobs[k] / tot, 4)
    ag = d['ages'] or {}
    old = None
    if ag.get('TOTAL') and all(ag.get(k) is not None for k in ('Y65-69', 'Y70-74', 'Y75-79', 'Y80-84', 'Y_GE85')):
        old = round(sum(ag[k] for k in ('Y65-69', 'Y70-74', 'Y75-79', 'Y80-84', 'Y_GE85')) / ag['TOTAL'], 4)
    s = get3(pop_series, r, X21) or {}
    gr = None
    if s.get('2021') and s.get(str(YEAR_POP)):
        gr = round(s[str(YEAR_POP)] / s['2021'] - 1, 4)
    cb = d['cob'] or {}
    fb = None
    if cb.get('TOTAL') and cb.get('FOR'):
        fb = round(cb['FOR'][0] / cb['TOTAL'][0], 4)
    n2 = d['nights']
    p2 = pop2.get(r[:4])
    tour = round(n2 / p2, 2) if (n2 and p2 and get2(nights, r) is not None and r[:4] in nights) else None
    pc = lambda v: None if v is None else round(v / 100, 4)
    cs = reg_cells.get(RIDX[r])
    if cs:
        cell = max(cs, key=lambda t: t[1])[0]
    else:
        x, y = regc[r][:2]
        cell = nearest_land_cell(x, y)
    rows.append([r, d and world['counties'][RIDX[r]]['name'], r[:2], p, la, None if not p or not la else round(p / la, 1),
                 d['gdp'], None if not d['gdp'] or not p else round(d['gdp'] / p), d['gdp_pps'], gr, d['median_age'], old, tot,
                 sh('agriculture'), sh('manufacturing'), sh('information'), sh('finance'), sh('public_admin'), sh('arts'),
                 d['income'], d['income_pps'], pc(d['unemployment']), pc(d['tertiary']), d['life'], pc(d['arope']), pc(d['broadband']), fb,
                 d['rd'], pc(d['htec']), tour,
                 land_share(r, 'forest'), land_share(r, 'crop'), land_share(r, 'pasture'), land_share(r, 'developed'),
                 metro_of.get(r), int(cell)])
save_json('counties', {'vintage': f'Eurostat {YEAR_POP}', 'fields': F, 'columns': [f['key'] for f in F], 'rows': rows})
save_interim('_regdata', {r: {k: v for k, v in R[r].items() if k not in ('series',)} for r in REG})
save_interim('_cross', {'x21': X21, 'x16': X16, 'metro_of': metro_of})
print('done; cities', len(city_rows), 'EU pop', nat['population'], 'GDP', nat['gdp'])
