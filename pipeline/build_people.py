"""districts.json (industry specialisation from Eurostat SBS) and citizens.json (census 2021 + LFS + demography)."""
import math
from collections import defaultdict
import numpy as np
import es
from common import *

meta, proj, grid = world_ctx()
REG = meta['regions']
world = load_json(OUT + '/world.json')
cities = load_json(OUT + '/cities.json')
regdata = load_interim('_regdata')
cross = load_interim('_cross')
X21 = cross['x21']
owner = np.array(world['owner']); water = np.array(world['water'])
COUNTRIES = meta['countries']

# ------------------------------------------------------------------ districts -----------------------------------------
rows, d = es.table('sbs_r_nuts2021', indic_sbs='EMP_LOC_NR', sinceTimePeriod=2021)
titles = d['dimension']['nace_r2']['category']['label']
sbs = defaultdict(dict)
for co, v in rows:
    g, k, t = co['geo'], co['nace_r2'], co['time']
    if k not in sbs[g] or sbs[g][k][1] < t:
        sbs[g][k] = (v, t)
SECTIONS = ['B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'P', 'Q', 'R', 'S95', 'S96']


def total(t):
    return sum((t[s][0] if isinstance(t[s], tuple) else t[s]) for s in SECTIONS if s in t)


# population per NUTS 2 (2024 codes) from NUTS 3
pop2 = defaultdict(float)
for r in REG:
    p = regdata[r]['population'] or 0
    pop2[r[:4]] += p


def n2_of(r):
    for c in (r[:4], X21.get(r, r)[:4]):
        if c in sbs:
            return c
    return None


CATALOG = [
    dict(id='research_park', name='Research Park', icon='d-research-park', color='#4a7bd0', codes=['M72', 'J62', 'J63', 'M71'],
         sub={'M72': 'Research labs', 'J62': 'Software', 'J63': 'Data & web services', 'M71': 'Engineering consultancies'},
         badge={'id': 'scientific', 'label': 'Knowledge city', 'labels': {'J62': 'Tech city', 'J63': 'Tech city', 'M72': 'Research city'}},
         description='Scientific R&D, software, information services and engineering offices.'),
    dict(id='financial_district', name='Financial District', icon='d-financial-district', color='#d0a93a', codes=['K64', 'K65', 'K66'],
         sub={'K64': 'Banking', 'K65': 'Insurance', 'K66': 'Financial services'},
         badge={'id': 'commercial', 'label': 'Finance city', 'labels': {'K65': 'Insurance city'}},
         description='Banks, insurers, funds and the services around them.'),
    dict(id='industrial_park', name='Industrial Park', icon='d-industrial-park', color='#c0663a', codes=['C', 'B'],
         sub={'C29': 'Car making', 'C26': 'Electronics', 'C21': 'Pharmaceuticals', 'C20': 'Chemicals', 'C19': 'Oil refining', 'C24': 'Metals',
              'C28': 'Machinery', 'C30': 'Aircraft, ships & trains', 'C27': 'Electrical equipment', 'C10': 'Food processing', 'C11': 'Drinks',
              'C16': 'Wood', 'C17': 'Paper', 'C13': 'Textiles', 'C14': 'Clothing', 'C15': 'Leather & shoes', 'C31': 'Furniture',
              'B05': 'Coal & lignite mining', 'B06': 'Oil & gas'},
         badge={'id': 'industrial', 'label': 'Factory town', 'labels': {'C29': 'Motor city', 'C26': 'Chip city', 'C21': 'Pharma city', 'C20': 'Chemical city',
                'C19': 'Refinery town', 'C24': 'Steel town', 'C28': 'Machine city', 'C30': 'Aerospace city', 'C10': 'Food town', 'C11': 'Wine & beer town',
                'C16': 'Timber town', 'C17': 'Paper town', 'C13': 'Textile town', 'C14': 'Fashion town', 'C15': 'Shoe town', 'C31': 'Furniture town',
                'B05': 'Coal town', 'B06': 'Oil town', 'C27': 'Electrical city'}},
         description='Manufacturing and mining.'),
    dict(id='port_district', name='Port District', icon='d-port-district', color='#3a8ab0', codes=['H50', 'H52'],
         sub={'H50': 'Shipping lines', 'H52': 'Port & logistics services'},
         badge={'id': 'maritime', 'label': 'Port city', 'labels': {'H52': 'Logistics hub'}},
         description='Water transport, warehousing and the services that support transport.'),
    dict(id='arts_district', name='Arts District', icon='d-arts-district', color='#a05ac0', codes=['R90', 'R91', 'J59', 'J60', 'J58'],
         sub={'R90': 'Performing arts', 'R91': 'Museums & heritage', 'J59': 'Film & music', 'J60': 'Broadcasting', 'J58': 'Publishing'},
         badge={'id': 'cultural', 'label': 'Arts city', 'labels': {'J59': 'Film city', 'J58': 'Publishing city'}},
         description='Arts, museums, film, broadcasting and publishing.'),
    dict(id='leisure_district', name='Leisure District', icon='d-leisure-district', color='#e07a5a', codes=['I55', 'R93', 'R92', 'N79'],
         sub={'I55': 'Hotels', 'R93': 'Sport & amusement', 'R92': 'Casinos & betting', 'N79': 'Travel agencies'},
         badge={'id': 'entertainment', 'label': 'Resort city', 'labels': {'R92': 'Casino town'}},
         description='Hotels and holiday homes, sport, amusement and gambling.'),
    dict(id='aviation_hub', name='Aviation Hub', icon='d-aviation-hub', color='#5aa0c8', codes=['H51'],
         sub={'H51': 'Airlines'},
         badge={'id': 'aviation', 'label': 'Air hub', 'labels': {}},
         description='Passenger and freight airlines.'),
    dict(id='utility_district', name='Utility District', icon='d-utility-district', color='#7a9a3a', codes=['D35', 'E36', 'E38'],
         sub={'D35': 'Power & gas', 'E36': 'Water', 'E38': 'Waste & recycling'},
         badge={'id': 'utility', 'label': 'Energy town', 'labels': {}},
         description='Power, gas, water and waste.'),
]
RULE = {'min_lq': 1.25, 'min_jobs': 1000, 'min_share': 0.01, 'specialty_lq': 3.0, 'specialty_jobs': 1000, 'specialty_share': 0.005,
        'max_per_city': 5, 'port_district_needs_water': True, 'badge_lq': 6.0, 'badge_share': 0.03}
RULE['text'] = ('A district appears when its industries together employ at least 1.25× the EU share of jobs (location quotient) and at least '
                '1,000 people or 1% of the metro’s jobs, or when one of its specialities reaches 3× the EU share with at least 1,000 jobs. '
                'Districts are ranked by jobs above the EU norm; up to 5. A Port District needs a footprint hex on or next to water. '
                'Jobs come from Eurostat structural business statistics (persons employed in local units, by NUTS 2 region): a metro gets '
                'its NUTS 2 regions’ jobs in proportion to the share of their population that lives in the metro, so metros inside one NUTS 2 region share one profile.')
RULE['county_note'] = 'Not computed for NUTS 3 regions: the source is published for NUTS 2 regions only.'

# EU reference
eu_t = defaultdict(float)
for g, t in sbs.items():
    if len(g) == 4 and g[:2] in COUNTRIES and not g.endswith('ZZ'):
        for k, (v, _) in t.items():
            eu_t[k] += v
eu_total = sum(eu_t[s] for s in SECTIONS)


def metro_profile(c):
    w = defaultdict(float)
    for r in c['counties']:
        n2 = n2_of(r)
        p = regdata[r]['population'] or 0
        if n2 and pop2.get(r[:4]):
            w[n2] += p / pop2[r[:4]]
    prof = defaultdict(float)
    for n2, f in w.items():
        for k, (v, _) in sbs[n2].items():
            prof[k] += v * f
    return prof


def water_adjacent(fp):
    for i in fp:
        if water[i]:
            return True
        for j in grid.neighbours(i):
            if water[j]:
                return True
    return False


industries = {k: {'title': titles.get(k, k), 'us_emp': round(eu_t[k])} for k in eu_t if len(k) <= 3}
dcities = {}
for c in cities:
    prof = metro_profile(c)
    tot = total(prof)
    if tot <= 0:
        dcities[c['id']] = None
        continue
    lq = lambda k: (prof.get(k, 0) / tot) / (eu_t[k] / eu_total) if eu_t.get(k) else None
    dl = []
    for cat in CATALOG:
        emp = sum(prof.get(k, 0) for k in cat['codes'])
        ref = sum(eu_t.get(k, 0) for k in cat['codes'])
        if not ref:
            continue
        L = (emp / tot) / (ref / eu_total)
        best = None
        for k in cat['sub']:
            if k in prof and prof[k] >= 1000:
                l2 = lq(k)
                if l2 and l2 > 1 and (best is None or l2 > best[1]):
                    best = (k, l2, prof[k])
        broad = L >= RULE['min_lq'] and (emp >= RULE['min_jobs'] or emp / tot >= RULE['min_share'])
        spec = best is not None and best[1] >= RULE['specialty_lq'] and best[2] >= RULE['specialty_jobs']
        if not (broad or spec):
            continue
        if cat['id'] == 'port_district' and not water_adjacent(c['footprint']):
            continue
        strength = max(emp - emp / L if L > 0 else 0, (best[2] - best[2] / best[1]) if best else 0)
        dl.append({'id': cat['id'], 'lq': round(L, 2), 'emp': round(emp), 'share': round(emp / tot, 3), 'avg_pay': None,
                   'sub': best[0] if best else None, 'sub_lq': round(best[1], 2) if best else None, 'sub_emp': round(best[2]) if best else None,
                   'sub_lower_bound': False, 'via': 'broad' if broad else 'specialty', 'strength': round(strength), 'suppressed': 0, 'lower_bound': False})
    dl.sort(key=lambda x: -x['strength'])
    dl = dl[:RULE['max_per_city']]
    badge = None
    if dl:
        strong = [x for x in dl if x['lq'] >= RULE['badge_lq'] and x['share'] >= RULE['badge_share']]
        b = strong[0] if strong else dl[0]
        cat = next(k for k in CATALOG if k['id'] == b['id'])
        label = cat['badge']['labels'].get(b['sub'], cat['badge']['label']) if b['sub'] and b['sub_lq'] and b['sub_lq'] >= 3 else cat['badge']['label']
        what = cat['sub'].get(b['sub']) if (b['sub'] and b['sub_lq'] and b['sub_lq'] >= 3) else cat['name']
        ratio = b['sub_lq'] if (b['sub'] and b['sub_lq'] and b['sub_lq'] >= 3) else b['lq']
        badge = {'id': cat['badge']['id'], 'label': label, 'district': b['id'], 'basis': 'sbs', 'text': f'{what}: {ratio:.1f}× the EU share of jobs'}
    top = []
    for k, v in prof.items():
        if len(k) == 3 and v >= 1000 and k[0] not in 'GLNQ':
            l2 = lq(k)
            if l2:
                top.append({'naics': k, 'emp': round(v), 'lq': round(l2, 2), 'avg_pay': None, 'oty_pct': None, 'suppressed': 0, 'lower_bound': False})
    top.sort(key=lambda t: -t['lq'])
    dcities[c['id']] = {'emp': round(tot), 'avg_pay': None, 'counties': [len(c['counties']), len(c['counties'])], 'top': top[:8], 'districts': dl, 'badge': badge}

catalog = []
for cat in CATALOG:
    catalog.append({'id': cat['id'], 'name': cat['name'], 'icon': cat['icon'], 'color': cat['color'], 'naics': cat['codes'], 'own': [],
                    'sub': cat['sub'], 'badge': cat['badge'], 'description': cat['description'], 'caveat': None})
save_json('districts', {'version': 1, 'vintage': 'Eurostat structural business statistics by NUTS 2 region (sbs_r_nuts2021), latest year', 'year': 2023,
                        'sources': ['eurostat_sbs'], 'rule': RULE, 'catalog': catalog, 'industries': industries,
                        'national': {'emp': round(eu_total), 'avg_pay': None}, 'cities': dcities, 'counties': {}})
from collections import Counter
print('badges', Counter((v['badge'] or {}).get('label') for v in dcities.values() if v).most_common(20))

# ------------------------------------------------------------------ citizens -----------------------------------------
occ_rows, _ = es.table('cens_21cobo_r2', c_birth='TOTAL', sex='T', age='TOTAL', unit='NR')
occ = defaultdict(dict)
for co, v in occ_rows:
    occ[co['geo']][co['isco08']] = v
cob_rows, _ = es.table('cens_21cob_r3', sex='T', age='TOTAL', unit='NR')
cobr = defaultdict(dict)
for co, v in cob_rows:
    cobr[co['geo']][co['c_birth']] = v
edu_rows, _ = es.table('edat_lfse_04', sex='T', age='Y25-64', unit='PC', isced11=['ED0-2', 'ED3_4', 'ED5-8'], sinceTimePeriod=2023)
edu = defaultdict(dict)
for co, v in edu_rows:
    g = co['geo']
    if co['isced11'] not in edu[g] or edu[g][co['isced11']][1] < co['time']:
        edu[g][co['isced11']] = (v, co['time'])

W_GROUPS = [('executive', 'Managers', ['OC1']), ('engineer', 'Professionals', ['OC2']), ('scholar', 'Technicians & associate professionals', ['OC3']),
            ('clerk', 'Clerical support workers', ['OC4']), ('service', 'Service & sales workers', ['OC5']), ('farmer', 'Farmers, foresters & fishers', ['OC6']),
            ('builder', 'Craft & trades workers', ['OC7']), ('maker', 'Machine operators & labourers', ['OC8', 'OC9'])]
A_GROUPS = [('child', 'Under 15', ['Y_LT5', 'Y5-9', 'Y10-14']), ('young', '15–34', ['Y15-19', 'Y20-24', 'Y25-29', 'Y30-34']),
            ('midlife', '35–64', ['Y35-39', 'Y40-44', 'Y45-49', 'Y50-54', 'Y55-59', 'Y60-64']),
            ('elder', '65 and over', ['Y65-69', 'Y70-74', 'Y75-79', 'Y80-84', 'Y_GE85'])]
E_GROUPS = [('less_than_hs', 'Lower secondary or less', 'ED0-2'), ('high_school', 'Upper secondary', 'ED3_4'), ('bachelors', 'Tertiary (degree)', 'ED5-8')]
N_GROUPS = [('born_in_state', 'Born in this country'), ('other_state', 'Born in another EU country'), ('foreign_born', 'Born outside the EU')]
FIG = {'workforce': 20, 'age': 10}


def lrr(counts, n):
    tot = sum(counts.values())
    if tot <= 0:
        return {k: 0 for k in counts}
    raw = {k: v / tot * n for k, v in counts.items()}
    fl = {k: int(math.floor(v)) for k, v in raw.items()}
    rem = n - sum(fl.values())
    for k in sorted(raw, key=lambda k: -(raw[k] - fl[k]))[:rem]:
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


def n2codes(regs):
    w = defaultdict(float)
    for r in regs:
        for c in (r[:4], X21.get(r, r)[:4]):
            w[c] += regdata[r]['population'] or 0
    return w


def row_for(regs, national=False):
    out = {}
    # workforce: census 2021 occupations, NUTS 2 apportioned by population share
    wc = defaultdict(float)
    if national:
        src = {g: v for g, v in occ.items() if g in COUNTRIES}
        for g, t in src.items():
            for key, _, codes in W_GROUPS:
                wc[key] += sum(t.get(c, 0) for c in codes)
    else:
        for r in regs:
            p = regdata[r]['population'] or 0
            for c in (r[:4], X21.get(r, r)[:4]):
                if c in occ and pop2.get(r[:4]):
                    for key, _, codes in W_GROUPS:
                        wc[key] += sum(occ[c].get(x, 0) for x in codes) * p / pop2[r[:4]]
                    break
    out['workforce'] = mkrow({k: wc.get(k, 0) for k, _, _ in W_GROUPS}, FIG['workforce'])
    # age: 2025 population by 5-year group, NUTS 3
    ac = defaultdict(float)
    ok = False
    med = []
    for r in regs:
        ag = regdata[r]['ages'] or {}
        if ag:
            ok = True
        for key, _, codes in A_GROUPS:
            ac[key] += sum(ag.get(c, 0) or 0 for c in codes)
        if regdata[r]['median_age'] and regdata[r]['population']:
            med.append((regdata[r]['median_age'], regdata[r]['population']))
    m = round(sum(a * b for a, b in med) / sum(b for _, b in med), 1) if med else None
    out['age'] = mkrow({k: ac.get(k, 0) for k, _, _ in A_GROUPS}, FIG['age'], {'median': m}) if ok else None
    out['commute'] = None
    # education: LFS 2025, NUTS 2 shares weighted by population
    num = defaultdict(float); den = 0
    for r in regs:
        p = regdata[r]['population'] or 0
        for c in (r[:4], X21.get(r, r)[:4], r[:3]):
            if c in edu and len(edu[c]) == 3:
                for key, _, code in E_GROUPS:
                    num[key] += edu[c][code][0] * p
                den += p
                break
    if national:
        num = defaultdict(float); den = 0
        for g in COUNTRIES:
            if g in edu and len(edu[g]) == 3:
                p = sum(regdata[r]['population'] or 0 for r in REG if r[:2] == g)
                for key, _, code in E_GROUPS:
                    num[key] += edu[g][code][0] * p
                den += p
    if den:
        adults = sum(sum((regdata[r]['ages'] or {}).get(a, 0) or 0 for a in ('Y25-29', 'Y30-34', 'Y35-39', 'Y40-44', 'Y45-49', 'Y50-54', 'Y55-59', 'Y60-64')) for r in regs)
        sh = {k: num[k] / den / 100 for k, _, _ in E_GROUPS}
        ssum = sum(sh.values()) or 1
        cnt = {k: adults * v / ssum for k, v in sh.items()}
        out['education'] = mkrow(cnt, None, {'bachelors_plus': round(sh['bachelors'] / ssum, 3)})
    else:
        out['education'] = None
    # nativity: census 2021 country of birth, NUTS 3
    nc = defaultdict(float); ok = False
    for r in regs:
        for c in (r, X21.get(r)):
            if c and c in cobr:
                t = cobr[c]; cc = r[:2]
                tot = t.get('TOTAL') or 0
                nat = t.get('NAT') or t.get(cc) or 0
                eu_oth = t.get('EU_OTH')
                if eu_oth is None:
                    eu_oth = sum(t.get(k, 0) for k in COUNTRIES if k != cc)
                nc['born_in_state'] += nat; nc['other_state'] += eu_oth; nc['foreign_born'] += max(0, tot - nat - eu_oth - (t.get('UNK') or 0))
                ok = True
                break
    if ok:
        row = mkrow({k: nc[k] for k, _ in N_GROUPS})
        if row:
            row['foreign_born'] = round((nc['other_state'] + nc['foreign_born']) / row['total'], 3)
            row['born_in_state'] = row['shares']['born_in_state']
        out['nativity'] = row
    else:
        out['nativity'] = None
    return out


national = row_for(REG, national=True)
national['specialists'] = []
crow = {}
for c in cities:
    r = row_for(c['counties'])
    specs = []
    for rk in ('workforce', 'age', 'education', 'nativity'):
        a, b = r.get(rk), national.get(rk)
        if not a or not b:
            continue
        for k, s in a['shares'].items():
            ns = b['shares'].get(k)
            if not ns or (s < 0.01 and ns < 0.01):
                continue
            specs.append({'row': rk, 'key': k, 'share': s, 'national': ns, 'ratio': round(s / ns, 2)})
    hi = sorted([s for s in specs if s['ratio'] >= 1.5], key=lambda s: -s['ratio'])[:4]
    lo = sorted([s for s in specs if s['ratio'] <= 0.67], key=lambda s: s['ratio'])[:2]
    r['specialists'] = hi + lo
    r['reliable'] = True
    crow[c['id']] = r
groups = {
    'workforce': [{'key': k, 'label': l, 'icon': 'c-' + k, 'lines': 'ISCO-08 ' + '+'.join(c)} for k, l, c in W_GROUPS],
    'age': [{'key': k, 'label': l, 'icon': 'c-' + k, 'lines': ', '.join(c)} for k, l, c in A_GROUPS],
    'commute': [],
    'education': [{'key': k, 'label': l, 'icon': 'c-' + k, 'lines': c} for k, l, c in E_GROUPS],
    'nativity': [{'key': k, 'label': l, 'icon': 'c-' + k, 'lines': ''} for k, l in N_GROUPS],
}
save_json('citizens', {'version': 1, 'vintage': 'Census 2021 (occupations, country of birth); population 1 Jan 2025; LFS 2025 (education)', 'year': 2025,
                       'sources': ['eurostat_census', 'eurostat_demo', 'eurostat_lfs'], 'figures': FIG,
                       'rows': {'workforce': 'Employed residents by occupation (Census 2021, NUTS 2 shared out by population)',
                                'age': 'Residents by age (1 January 2025)', 'commute': 'Not available for EU regions',
                                'education': 'Adults 25–64 by highest education (Labour Force Survey)',
                                'nativity': 'Residents by country of birth (Census 2021)'},
                       'groups': groups,
                       'rule': {'specialist_high': 1.5, 'specialist_low': 0.67, 'min_share': 0.01, 'max_high': 4, 'max_low': 2,
                                'text': 'A group is a speciality when its share is at least 1.5× (up to 4) or at most 0.67× (up to 2) the EU27 share; groups under 1% both here and in the EU are skipped.'},
                       'national': national, 'cities': crow})
