"""history.json: yearly series per NUTS 3 region for the time dial, 2000 to the latest year, plus the 'GDP vs EU
average' lens written into lenses.json.

Needs only data/world.json and data/counties.json (from the earlier steps) and network access to Eurostat (and ONS for
the UK). Run after build_lenses.py.

Series (one value per region and year, null where the source has none):
  pop      population on 1 January (demo_r_pjanaggr3); UK: ONS mid-year estimates
  gdp_idx  GDP per inhabitant in PPS, EU27 = 100 (nama_10r_3gdp, PPS_HAB_EU27_2020)
  unemp    unemployment rate 15-74, NUTS 2 (lfst_r_lfu3rt); every NUTS 3 region takes its NUTS 2 value
  jobs     employed persons, place of work (nama_10r_3empers, thousands -> persons)
  farm     share of jobs in NACE A
  factory  share of jobs in NACE C
Eurostat publishes these on today's NUTS 2024 borders; where a region was redrawn and not back-cast, early years are
missing and the map shows them as 'no data' rather than a guess.
"""
import json
from collections import defaultdict
import es
from common import OUT, load_json

Y0 = 2000
world = load_json(OUT + '/world.json')
counties = load_json(OUT + '/counties.json')
cols = counties['columns']
REG = [c['geoid'] for c in world['counties']]
rows = {r[0]: dict(zip(cols, r)) for r in counties['rows']}
assert [r[0] for r in counties['rows']] == REG


def series(ds, key='geo', scale=1.0, **f):
    """{geo: {year: value}}"""
    out = defaultdict(dict)
    tab, _ = es.table(ds, sinceTimePeriod=Y0, **f)
    for co, v in tab:
        out[co[key]][int(co['time'][:4])] = v * scale
    return out


print('population')
pop = series('demo_r_pjanaggr3', sex='T', age='TOTAL', unit='NR')
print('gdp')
gdp = series('nama_10r_3gdp', unit='PPS_HAB_EU27_2020')
print('unemployment')
un = series('lfst_r_lfu3rt', sex='T', age='Y15-74', isced11='TOTAL', unit='PC', scale=0.01)
print('jobs')
emp = {n: series('nama_10r_3empers', wstatus='EMP', nace_r2=n, unit='THS', scale=1000) for n in ('TOTAL', 'A', 'C')}

# UK: Eurostat stopped after Brexit; population comes from the ONS (1998 onwards).
try:
    import uk
    uk_names = {g: rows[g]['name'] for g in REG if g.startswith('UK')}
    for g, d in uk.ons_regions(uk_names).items():
        for y, v in d.get('population', {}).items():
            if int(y) >= Y0:
                pop[g][int(y)] = v
    print('UK population from ONS')
except Exception as e:  # the dial still works without it; the UK shows no data
    print('UK population skipped:', e)

ys = sorted({y for s in (pop, gdp, un, emp['TOTAL']) for d in s.values() for y in d})
YEARS = list(range(Y0, ys[-1] + 1))
print('years', YEARS[0], YEARS[-1])


def grid(get, digits):
    out = []
    for g in REG:
        for y in YEARS:
            v = get(g, y)
            out.append(None if v is None else round(v, digits) if digits else int(round(v)))
    return out


def share(n):
    def f(g, y):
        t, a = emp['TOTAL'].get(g, {}).get(y), emp[n].get(g, {}).get(y)
        return a / t if t and a is not None else None
    return f


S = {
    'pop': grid(lambda g, y: pop.get(g, {}).get(y), 0),
    'gdp_idx': grid(lambda g, y: gdp.get(g, {}).get(y), 0),
    'unemp': grid(lambda g, y: un.get(g[:4], {}).get(y), 3),
    'jobs': grid(lambda g, y: emp['TOTAL'].get(g, {}).get(y), 0),
    'farm': grid(share('A'), 4),
    'factory': grid(share('C'), 4),
}
NY = len(YEARS)


def at(key, i, y):
    return S[key][i * NY + YEARS.index(y)]


# Each series plays over the years where it covers at least 60% of its best year's regions (the newest year is often
# published for a few countries only).
def span(key):
    cov = [sum(1 for i in range(len(REG)) if at(key, i, y) is not None) for y in YEARS]
    ok = [y for y, c in zip(YEARS, cov) if c >= 0.6 * max(cov)]
    return [ok[0], ok[-1]]


RANGE = {k: span(k) for k in S}
print('ranges', RANGE)


# --- story beats: for each series and year, the biggest rise and fall since the first year a region has data,
# among regions with at least 250,000 people (so a tiny island never headlines).
def latest_pop(i):
    for y in reversed(YEARS):
        v = at('pop', i, y)
        if v:
            return v
    return rows[REG[i]]['population'] or 0


BIG = [i for i in range(len(REG)) if latest_pop(i) >= 250000]


def movers(key, rel=False):
    out = {}
    a, b = RANGE[key]
    for y in YEARS:
        if y <= a or y > b:
            continue
        best = []
        for i in BIG:
            v1 = at(key, i, y)
            v0 = next((at(key, i, z) for z in YEARS if a <= z < y and at(key, i, z) is not None), None)
            if v1 is None or v0 is None or (rel and not v0):
                continue
            d = (v1 / v0 - 1) if rel else (v1 - v0)
            best.append((d, i, v0, v1))
        if best:
            best.sort()
            lo, hi = best[0], best[-1]
            out[y] = [[REG[hi[1]], hi[2], hi[3]], [REG[lo[1]], lo[2], lo[3]]]
    return out


beats = {'pop': movers('pop', rel=True), 'gdp_idx': movers('gdp_idx'), 'unemp': movers('unemp'),
         'factory': movers('factory'), 'farm': movers('farm')}

# Notes written by hand, for moments the numbers alone would mislead or undersell.
NOTES = [
    {'series': 'gdp_idx', 'year': 2015, 'geo': 'IE061',
     'text': 'Dublin and southern Ireland jump in 2015 as multinationals move intellectual property to Ireland. Much of this GDP never reaches households; the Income lens is the fairer view.'},
    {'series': 'gdp_idx', 'year': 2009, 'geo': None,
     'text': 'The 2008–09 financial crisis. Output falls almost everywhere; Greece, Spain and Ireland fall furthest over the next years.'},
    {'series': 'unemp', 'year': 2013, 'geo': 'ES618',
     'text': 'Peak of the euro crisis: unemployment passes a third of the workforce in Andalucía and parts of Greece.'},
    {'series': 'gdp_idx', 'year': 2004, 'geo': None,
     'text': 'Ten countries join the EU in 2004, eight of them in Central and Eastern Europe. Watch their capitals climb from here.'},
    {'series': 'gdp_idx', 'year': 2020, 'geo': None,
     'text': 'COVID-19. Tourism regions (the Balearics, the Canaries, the Algarve) drop hardest relative to the EU average.'},
]

out = {
    'vintage': f'Eurostat regional series {YEARS[0]}–{YEARS[-1]} (ONS for UK population)',
    'years': YEARS,
    'range': RANGE,
    'regions': REG,
    'series': S,
    'beats': beats,
    'notes': NOTES,
    'eu_note': 'GDP per person is measured in purchasing power standards relative to the EU27 average of each year (EU = 100), so inflation and exchange rates do not colour the map.',
}
with open(OUT + '/history.json', 'w') as f:
    json.dump(out, f, separators=(',', ':'), allow_nan=False)
print('history.json', len(REG), 'regions x', NY, 'years')

# --- the 'GDP vs EU average' lens (latest year), spread onto hexes by each hex's region
L = load_json(OUT + '/lenses.json')
last = {}
for i, g in enumerate(REG):
    for y in reversed(range(RANGE['gdp_idx'][0], RANGE['gdp_idx'][1] + 1)):
        v = at('gdp_idx', i, y)
        if v is not None:
            last[i] = (v, y)
            break
vals = [None if c < 0 or c not in last else last[c][0] for c in world['county']]
yrs = sorted({y for _, y in last.values()})
lens = {'id': 'gdp_index', 'group': 'prosperity', 'name': 'GDP vs EU average', 'icon': 'l-income', 'emoji': '\U0001F4CA',
        'unit': 'GDP per person, EU27 = 100 (PPS)', 'format': 'int', 'scale': 'log', 'domain': [30, 250],
        'ramp': ['#2a1846', '#4f3a7e', '#7c76a3', '#b8a46a', '#e8c766', '#fff3c4'], 'higher_is': 'good', 'source': 'eurostat_gdp',
        'description': 'GDP per inhabitant in purchasing power standards as a percentage of the EU27 average of the same year (nama_10r_3gdp). '
                       'Has a time dial: press play to watch 2000 to ' + str(YEARS[-1]) + '.',
        'note': f'Latest year {yrs[-1]}' + (f' ({yrs[0]} for a few regions).' if yrs[0] != yrs[-1] else '.'),
        'values': vals}
L['lenses'] = [l for l in L['lenses'] if l['id'] != 'gdp_index']
k = next((n + 1 for n, l in enumerate(L['lenses']) if l['id'] == 'gdp_pps'), len(L['lenses']))
L['lenses'].insert(k, lens)
with open(OUT + '/lenses.json', 'w') as f:
    json.dump(L, f, ensure_ascii=False, separators=(',', ':'))
print('lenses.json: gdp_index lens added')
