"""Context places: towns and cities without stats, drawn as grey dots and names under the full city banners.

The 300-odd cities with stats (data/cities.json) are Eurostat metro regions, places of 250,000+ people where Eurostat has
no metro regions, the capitals, and the towns of Leuven and Edessa. Every other place of PLACE_MIN+ people gets a name
on the map, and nothing else: no yields, no panel, no hex of its own.

Sources:
- Eurostat GISCO LAU (municipalities, latest population of 2024 / 2023 / 2021), where a municipality is a town. A city
  split into several LAUs ("Bratislava - mestská časť Petržalka", "Belgrade - Voždovac") is summed into one place.
  The dot sits at the Natural Earth place inside the municipality when there is one, else at the municipality's centre.
- Natural Earth populated places where LAUs are not towns (Greek and Cypriot local communities, Portuguese parishes,
  Irish electoral areas, Lithuanian districts) or carry no population (UK, Türkiye, Montenegro, Iceland, Bosnia and
  Herzegovina, Kosovo).

Writes data/places.json: {"min": PLACE_MIN, "places": [[name, x, y, population], ...]}, biggest first, x / y in map km.
Run after build_econ.py (it skips places that already have a city).
"""
import json, re, unicodedata
from collections import defaultdict
import shapely
from shapely.geometry import Point
from common import RAW, OUT, TO3035, Proj, Grid, load_json, save_json
import lau

PLACE_MIN = 15000
NE_ONLY = {'EL', 'CY', 'PT', 'IE', 'LT'}  # LAUs there are not towns
NE_FILL = {'UK', 'TR', 'ME', 'IS', 'BA', 'XK', 'LI'}  # no LAU population
LAU_COUNTRIES = {'AL', 'AT', 'BE', 'BG', 'CH', 'CZ', 'DE', 'DK', 'EE', 'ES', 'FI', 'FR', 'HR', 'HU', 'IT', 'LU', 'LV',
                 'MK', 'MT', 'NL', 'NO', 'PL', 'RO', 'RS', 'SE', 'SI', 'SK'}

world = load_json(OUT + '/world.json')
cities = load_json(OUT + '/cities.json')
grid = Grid(**world['grid'])
owner = world['owner']

# The map projection is a shift of EPSG:3035 (common.Proj): recover it from a city placed at a known lon/lat.
_lv = next(c for c in cities if c['id'] == 'BE242C')  # Leuven, placed at (4.7005, 50.8798) by build_econ
_X, _Y = TO3035.transform(4.7005, 50.8798)
m = world['margin']
proj = Proj(_X / 1000 - _lv['x'] + m, _Y / 1000 + _lv['y'] - m, m)
_ed = proj(22.0473, 40.8016)
assert abs(_ed[0] - next(c['x'] for c in cities if c['id'] == 'EL524C')) < 0.2, 'projection does not match cities.json'

# ---- names --------------------------------------------------------------------------------------------------------
CYR = dict(zip('абвгдежзийклмнопрстуфхцчшщъьюяѓѕјљњќџ',
               ['a', 'b', 'v', 'g', 'd', 'e', 'zh', 'z', 'i', 'y', 'k', 'l', 'm', 'n', 'o', 'p', 'r', 's', 't', 'u', 'f',
                'h', 'ts', 'ch', 'sh', 'sht', 'a', 'y', 'yu', 'ya', 'gj', 'dz', 'j', 'lj', 'nj', 'kj', 'dzh']))
CYR_MK = dict(CYR, ц='c', и='i', й='j')


def latin(s, cc):
    """Bulgarian (Streamlined System) and Macedonian (official) romanisation; other names are already Latin."""
    if not re.search('[Ѐ-ӿ]', s):
        return s
    tab = CYR_MK if cc == 'MK' else CYR
    out = []
    for ch in s:
        lo = ch.lower()
        t = tab.get(lo, ch)
        out.append(t.capitalize() if ch != lo else t)
    return ''.join(out)


SPECIAL = {'Столична': 'Sofia', 'Municipiul Bucureşti': 'Bucureşti'}


def clean(name, cc):
    name = SPECIAL.get(name, name)
    if cc == 'DE':
        name = name.split(',')[0]  # "Berlin, Stadt", "Karlstadt, St"
    name = re.split(r'\s*/\s*', name)[0]  # bilingual "Antwerpen / Anvers", "Namsos/Nåavmesjenjaelmie"
    name = re.sub(r' \(.*\)$', '', name)  # "Sint-Niklaas (Sint-Niklaas)", "Halle (Halle-Vilvoorde)"
    name = re.sub(r'^(Municipiul|Oraş|Oraș|Grad) ', '', name)
    name = re.sub(r' (linn|vald)$', '', name)
    m_ = re.match(r"^(.*), (El|La|Los|Las|L'|A|O|Os|As|Les|Es|Sa|Ses|Il|Lo)$", name)
    if m_:  # Spanish and Italian lists put the article last: "Coruña, A", "Hospitalet de Llobregat, L'"
        name = m_.group(2) + ('' if m_.group(2).endswith("'") else ' ') + m_.group(1)
    if name.isupper():
        name = name.title()
    return latin(name, cc)


# ---- places from LAUs -----------------------------------------------------------------------------------------------
L = lau.LAU(geo_years=(2024,))
tree, geoms, props = L.layers[0]
ne = []
for f in load_json(RAW + '/ne/ne_10m_populated_places_simple.geojson')['features']:
    pr = f['properties']
    cc = 'XK' if pr.get('adm0name') == 'Kosovo' else {'GR': 'EL', 'GB': 'UK'}.get(pr.get('iso_a2'), pr.get('iso_a2'))
    lon, lat = f['geometry']['coordinates']
    ne.append((cc, pr.get('name'), lon, lat, int(max(pr.get('pop_min') or 0, 0)), int(pr.get('pop_max') or 0),
               [a for a in (pr.get('namealt'), pr.get('nameascii')) if a]))
ne_xy = [Point(*TO3035.transform(n[2], n[3])) for n in ne]
ne_tree = shapely.STRtree(ne_xy)

groups = defaultdict(list)  # (cc, name) -> [(pop, geom index)]
for k, pr in enumerate(props):
    cc = pr['CNTR_CODE']
    if cc not in LAU_COUNTRIES:
        continue
    p = L.pop.get(pr['GISCO_ID'])
    if not p:
        continue
    nm = pr['LAU_NAME']
    if cc == 'LV' and nm.endswith(' novads'):
        continue  # rural districts
    if ' - ' in nm:
        nm = nm.split(' - ')[0]  # a city split into parts ("Belgrade - Voždovac"), or bilingual ("Poreč - Parenzo")
    groups[(cc, clean(nm, cc))].append((p[0], k))

places = []
for (cc, nm), parts in groups.items():
    # the same name twice in a country is two towns unless they touch (city parts): keep parts that touch the biggest
    parts.sort(reverse=True)
    big = geoms[parts[0][1]]
    keep = [(v, k) for v, k in parts if k == parts[0][1] or geoms[k].distance(big) < 1]
    pop = sum(v for v, _ in keep)
    if pop < PLACE_MIN:
        continue
    g = shapely.union_all([geoms[k] for _, k in keep]) if len(keep) > 1 else big
    hit = [i for i in ne_tree.query(g, predicate='contains') if ne[i][0] == cc]
    alias = []
    if hit:
        i = max(hit, key=lambda i: ne[i][5])
        pt, alias = ne_xy[i], [ne[i][1]] + ne[i][6]
    else:
        pt = g.centroid if g.contains(g.centroid) else g.representative_point()
    places.append([nm, pt.x, pt.y, pop, cc, alias])

# ---- places from Natural Earth --------------------------------------------------------------------------------------
for i, (cc, nm, lon, lat, pmin, pmax, alias) in enumerate(ne):
    if cc in NE_ONLY or cc in NE_FILL:
        pop = pmin or pmax  # city proper where Natural Earth has it
        if pop >= PLACE_MIN:
            places.append([nm, ne_xy[i].x, ne_xy[i].y, pop, cc, alias])

# ---- onto the map, skipping places that have a city ----------------------------------------------------------------
# A city's tile is drawn at its hex centre; a place that close to it is the city itself (or its centre).
city_at = [tuple(float(v) for v in grid.center(c['cell'])) for c in cities] + [(c['x'], c['y']) for c in cities]
NEAR = 14  # km (a hex is 40 km across)
norm = lambda s: re.sub(r'[^a-z]', '', unicodedata.normalize('NFKD', s.lower()))
# every part of a metro's name ("Oviedo - Gijón", "Alicante/Alacant - Elche/Elx"), and its own words
city_names = [(c['x'], c['y'], {norm(w) for part in re.split(r' - |/', c['name']) for w in (part, part.split(' ')[0])} - {''})
              for c in cities]


def same_name(a, b):  # "Lisbon" ~ "Lisboa", "Palma" ~ "Palma de Mallorca"
    return a == b or (min(len(a), len(b)) >= 5 and a[:5] == b[:5])


def is_city(names, x, y):
    ns = {norm(n) for n in names} - {''}
    return any((x - cx) ** 2 + (y - cy) ** 2 < 60 ** 2 and any(same_name(a, b) for a in ns for b in cn)
               for cx, cy, cn in city_names)

out = []
seen = []
for nm, X, Y, pop, cc, alias in sorted(places, key=lambda p: -p[3]):
    x, y = (float(v) for v in proj.from3035(X, Y))
    cell = int(grid.cell_at(x, y))
    if cell < 0:
        continue
    if owner[cell] < 0 and all(owner[n] < 0 for n in grid.neighbours(cell)):
        continue  # off the map (outermost regions) or out at sea
    if any((x - cx) ** 2 + (y - cy) ** 2 < NEAR ** 2 for cx, cy in city_at):
        continue
    if is_city([nm] + alias, x, y):
        continue
    if any(n == nm and (x - sx) ** 2 + (y - sy) ** 2 < 10 ** 2 for n, sx, sy in seen):
        continue
    seen.append((nm, x, y))
    out.append([nm, round(x, 1), round(y, 1), int(pop)])

print('context places:', len(out), 'of', len(places), 'candidates, min', PLACE_MIN)
save_json('places', {'min': PLACE_MIN, 'places': out})
