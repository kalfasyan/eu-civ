"""lenses.json: NUTS 3 / NUTS 2 indicators spread onto hexes, plus land lenses from the hex samples."""
import numpy as np
from common import *

meta, proj, grid = world_ctx()
REG = meta['regions']
world = load_json(OUT + '/world.json')
counties = load_json(OUT + '/counties.json')
cols = counties['columns']
rowsby = {r[0]: dict(zip(cols, r)) for r in counties['rows']}
cell_samples = {int(k): {int(a): b for a, b in v.items()} for k, v in meta['cell_samples'].items()}
S = grid.size

# weight of a region's samples inside a hex = sample count x population density (so a hex is a population-weighted mean)
dens = {i: (rowsby[r]['density'] or 1.0) for i, r in enumerate(REG)}


def spread(col, weighting=True):
    out = [None] * S
    for c, sm in cell_samples.items():
        num = den = 0.0
        for ri, n in sm.items():
            v = rowsby[REG[ri]].get(col)
            if v is None:
                continue
            w = n * (dens[ri] if weighting else 1)
            num += v * w; den += w
        if den > 0:
            out[c] = num / den
    return out


def domain(vals, log=False):
    v = np.array([x for x in vals if x is not None and (not log or x > 0)], float)
    if len(v) == 0:
        return [0, 1]
    return [float(np.percentile(v, 2)), float(np.percentile(v, 98))]


def rnd(vals, d):
    return [None if v is None else round(v, d) for v in vals]


RAMPS = {
    'magma': ['#1b1035', '#4b2377', '#9a3b8a', '#e0645e', '#f9b24a', '#fff3a8'],
    'gold': ['#3a1c0b', '#7a4413', '#b8781f', '#e3b23c', '#f6e27f', '#fffbe0'],
    'teal': ['#0b2a2e', '#165a5c', '#2f8f83', '#7cc29a', '#d4ecb0', '#ffffe0'],
    'poverty': ['#03051a', '#4c1d4b', '#a11a5b', '#e83f3f', '#f69c73', '#faebdd'],
    'age': ['#00224e', '#35456c', '#666970', '#948e77', '#c8b866', '#fee838'],
    'mako': ['#0b0405', '#382a54', '#395d9c', '#3497a9', '#60ceac', '#def5e5'],
    'blue': ['#08203e', '#0f4c81', '#2a7fc1', '#5fa8e0', '#a6d1f2', '#eaf5ff'],
    'purple': ['#1a0a2e', '#3f1d6b', '#6a3fa0', '#9a72c9', '#c9a9e6', '#f3e8ff'],
    'rose': ['#2b0b1e', '#5e1742', '#93275f', '#c84f7c', '#ea8fa8', '#fbd9e1'],
    'olive': ['#1c1a05', '#45410f', '#76701d', '#a8a033', '#d4ce62', '#f8f6c4'],
    'red': ['#1a0505', '#4a0f0f', '#80201a', '#b8452b', '#e07b54', '#f9c9a8'],
    'forest': ['#0b1f0f', '#14401c', '#1f6b2b', '#3a9443', '#7fc07a', '#d5efcd'],
    'farm': ['#141d05', '#2f4510', '#557019', '#84a02a', '#b8cf55', '#eef7b8'],
    'grey': ['#121218', '#2c2c3c', '#4b4b66', '#727294', '#a3a3c2', '#e2e2f0'],
    'well': ['#3b0a1e', '#7a1f3d', '#b9534f', '#e3a35c', '#c9d97a', '#7ecf8e'],
    'diverge': ['#7a1f3d', '#b9534f', '#e3c29c', '#c9d9c0', '#5fae9a', '#1f6b6b'],
    'elev': ['#1f4d2b', '#5a8a3a', '#b8b06a', '#a8865a', '#8a6a5a', '#f2f2f2'],
}

L = []


def lens(id, group, name, icon, emoji, unit, fmt, values, ramp, higher='neutral', scale='linear', source='', desc='', note=None, dom=None, digits=4):
    vals = rnd(values, digits)
    d = dom or domain(vals, scale == 'log')
    o = {'id': id, 'group': group, 'name': name, 'icon': icon, 'emoji': emoji, 'unit': unit, 'format': fmt, 'scale': scale,
         'domain': [round(d[0], 4), round(d[1], 4)], 'ramp': RAMPS[ramp], 'higher_is': higher, 'source': source,
         'description': desc, 'values': vals}
    if note:
        o['note'] = note
    L.append(o)


N2 = 'Published for NUTS 2 regions: every NUTS 3 region inside one shares its value.'
lens('density', 'people', 'Population', 'l-people', '\U0001F465', 'people / km²', 'int', spread('density', False), 'magma', scale='log',
     source='eurostat_demo', desc='Residents per km² of land, from NUTS 3 population on 1 January 2025 and land area; a hex shows the area-weighted mean of the regions under its sample points.', digits=1)
lens('growth', 'people', 'Growth', 'l-growth', '\U0001F4C8', 'population change 2021–2025', 'pct', spread('growth'), 'diverge', 'neutral',
     source='eurostat_demo', desc='Population change between 1 January 2021 and 1 January 2025, NUTS 3 regions.', dom=[-0.05, 0.05])
lens('age', 'people', 'Median age', 'l-age', '\U0001F382', 'years', 'years', spread('median_age'), 'age', source='eurostat_demo',
     desc='Median age of residents, NUTS 3 regions (demo_r_pjanind3).', digits=1)
lens('elderly', 'people', 'Aged 65+', 'l-age', '\U0001F9D3', 'share of residents aged 65 or over', 'pct', spread('elderly'), 'olive', source='eurostat_demo',
     desc='Share of the population aged 65 or over, NUTS 3 regions (demo_r_pjangrp3).')
lens('foreign_born', 'people', 'Born abroad', 'l-foreign-born', '\U0001F30D', 'share of residents 15–74 born in another country', 'pct', spread('foreign_born'), 'mako',
     source='eurostat_lfs', desc='People aged 15–74 born outside the country they live in (Labour Force Survey, lfst_r_lfsd2pwc).', note=N2)
lens('gdp_pc', 'prosperity', 'GDP per person', 'l-income', '\U0001F4B6', 'GDP per resident, €', 'usd', spread('gdp_per_capita'), 'gold', 'good', 'log',
     source='eurostat_gdp', desc='GDP at current market prices divided by population, NUTS 3. Counts output where people work, so commuter hubs (Luxembourg, city centres) score far above their surroundings.', digits=0)
lens('gdp_pps', 'prosperity', 'GDP per person (PPS)', 'l-income', '⚖️', 'purchasing power standards per resident', 'int', spread('gdp_pps'), 'gold', 'good', 'log',
     source='eurostat_gdp', desc='GDP per inhabitant in purchasing power standards (prices adjusted between countries), NUTS 3.', digits=0)
lens('income', 'prosperity', 'Income', 'l-income', '\U0001F4B5', 'household disposable income per person, PPS', 'int', spread('income_pps'), 'teal', 'good',
     source='eurostat_hhinc', desc='Net disposable income of private households per inhabitant, in purchasing power standards (nama_10r_2hhinc).', note=N2, digits=0)
lens('unemployment', 'prosperity', 'Unemployment', 'l-poverty', '\U0001F4BC', 'unemployment rate, ages 15–74', 'pct', spread('unemployment'), 'red', 'bad',
     source='eurostat_lfs', desc='Unemployed as a share of the labour force aged 15–74 (lfst_r_lfu3rt).', note=N2)
lens('poverty', 'prosperity', 'Poverty', 'l-poverty', '\U0001F963', 'share at risk of poverty or social exclusion', 'pct', spread('poverty'), 'poverty', 'bad',
     source='eurostat_silc', desc='People at risk of poverty or social exclusion (AROPE), EU-SILC (ilc_peps11n). Some countries publish only NUTS 1 or national values.', note=N2)
lens('bachelors', 'knowledge', 'Degrees', 'l-degrees', '\U0001F393', 'adults 25–64 with tertiary education', 'pct', spread('tertiary'), 'blue', 'good',
     source='eurostat_lfs', desc='Share of adults aged 25–64 with tertiary education, ISCED 5–8 (edat_lfse_04).', note=N2)
lens('rd', 'knowledge', 'R&D', 'l-degrees', '\U0001F9EA', 'R&D spending, % of GDP', 'float', spread('rd'), 'purple', 'good',
     source='eurostat_rd', desc='Gross domestic expenditure on research and development as a percentage of GDP (rd_e_gerdreg).', note=N2, digits=2)
lens('hightech', 'knowledge', 'High-tech jobs', 'l-degrees', '\U0001F4BB', 'share of jobs in high-tech sectors', 'pct', spread('hightech'), 'blue', 'good',
     source='eurostat_htec', desc='Employment in high-technology manufacturing and knowledge-intensive high-tech services (htec_emp_reg2).', note=N2)
lens('broadband', 'knowledge', 'Broadband', 'l-broadband', '\U0001F4E1', 'households with broadband', 'pct', spread('broadband'), 'purple', 'good',
     source='eurostat_isoc', desc='Households with a broadband internet connection (isoc_r_broad_h; latest regional year, 2021).', note=N2)
lens('life', 'life', 'Life expectancy', 'l-amenities', '❤️', 'years at birth', 'years', spread('life_expectancy'), 'well', 'good',
     source='eurostat_life', desc='Life expectancy at birth (demo_r_mlifexp).', note=N2, digits=1)
lens('tourism', 'life', 'Tourism', 'l-amenities', '\U0001F3D6️', 'tourist nights per resident per year', 'float', spread('tourism'), 'rose', 'neutral', 'log',
     source='eurostat_tour', desc='Nights spent at hotels, holiday homes and campsites per resident (tour_occ_nin2).', note=N2, digits=2)
for k, lbl in [('farm_jobs', 'agriculture_share'), ('factory_jobs', 'manufacturing_share'), ('ict_jobs', 'information_share'), ('public_jobs', 'public_admin_share')]:
    pass
lens('farm_jobs', 'life', 'Farm jobs', 'l-farmland', '\U0001F9D1‍\U0001F33E', 'share of jobs in agriculture, forestry & fishing', 'pct', spread('agriculture_share'), 'farm',
     source='eurostat_emp', desc='Agriculture, forestry & fishing (NACE A) as a share of all jobs, NUTS 3.')
lens('factory_jobs', 'life', 'Factory jobs', 'l-developed', '\U0001F3ED', 'share of jobs in manufacturing', 'pct', spread('manufacturing_share'), 'red',
     source='eurostat_emp', desc='Manufacturing (NACE C) as a share of all jobs, NUTS 3. Where a country publishes only broader groups, the split follows the parent region.')
pct = world['pct']
land = lambda arr: [None if world['owner'][i] < 0 or world['cover'][i] == 0 else arr[i] / 100 for i in range(S)]
lens('forest', 'land', 'Forest', 'l-forest', '\U0001F332', 'share of land', 'pct', land(pct['forest']), 'forest', source='worldcover',
     desc='Tree cover share of the hex’s land samples (ESA WorldCover 2021).', dom=[0, 0.85])
lens('farmland', 'land', 'Farmland', 'l-farmland', '\U0001F69C', 'share of land', 'pct', land([a + b for a, b in zip(pct['crop'], pct['pasture'])]), 'farm', source='worldcover',
     desc='Cropland plus lowland grassland (mostly pasture and meadows) share of the hex’s land samples (ESA WorldCover 2021).', dom=[0, 0.9])
lens('developed', 'land', 'Built-up', 'l-developed', '\U0001F3D9️', 'share of land', 'pct', land(pct['developed']), 'grey', source='worldcover',
     desc='Built-up share of the hex’s land samples (ESA WorldCover 2021, 10 m buildings and roads read at ~300 m).', dom=[0, 0.3])
lens('elevation', 'land', 'Elevation', 'l-forest', '⛰️', 'metres above sea level', 'int', [None if world['owner'][i] < 0 else world['elev'][i] for i in range(S)], 'elev',
     source='copdem', desc='Mean elevation of the hex’s land samples (Copernicus DEM GLO-90).', dom=[0, 2200], digits=0)

save_json('lenses', {'vintage': 'Eurostat regional statistics, latest year (mostly 2023–2025)',
                     'groups': [{'id': 'people', 'name': 'People'}, {'id': 'prosperity', 'name': 'Prosperity'},
                                {'id': 'knowledge', 'name': 'Knowledge'}, {'id': 'life', 'name': 'Life & work'}, {'id': 'land', 'name': 'Land'}],
                     'lenses': L})
