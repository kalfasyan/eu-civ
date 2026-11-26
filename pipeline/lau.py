"""Population of the municipality (LAU, local administrative unit) at a point, from Eurostat GISCO's LAU files.
Used for cities that are single places rather than metro regions, so they show the town's own population."""
import csv, json, os, urllib.request
import shapely
from shapely.geometry import shape, Point
from common import RAW, TO3035

D = RAW + '/lau'
BASE = 'https://gisco-services.ec.europa.eu/distribution/v2/lau/'
os.makedirs(D, exist_ok=True)


def _get(name, path):
    if not os.path.exists(path):
        with urllib.request.urlopen(BASE + name, timeout=900) as r:
            open(path, 'wb').write(r.read())
    return path


class LAU:
    def __init__(self, geo_years=(2024, 2021), pop_years=(2024, 2023, 2021)):
        self.pop = {}  # GISCO_ID -> (pop, year), latest non-zero
        for y in pop_years:
            p = _get(f'csv/LAU_RG_01M_{y}_4326.csv', f'{D}/lau_{y}.csv')
            for r in csv.DictReader(open(p, encoding='utf-8')):
                v = float(r.get(f'POP_{y}') or 0)
                if v > 0 and r['GISCO_ID'] not in self.pop:
                    self.pop[r['GISCO_ID']] = (int(v), y)
        self.layers = []
        for y in geo_years:
            p = _get(f'geojson/LAU_RG_01M_{y}_3035.geojson', f'{D}/lau_{y}_3035.geojson')
            feats = json.load(open(p, encoding='utf-8'))['features']
            geoms = [shape(f['geometry']) for f in feats]
            self.layers.append((shapely.STRtree(geoms), geoms, [f['properties'] for f in feats]))

    def at(self, lon, lat):
        """(name, population, year) of the LAU holding the point, or None when no layer has a population for it."""
        X, Y = TO3035.transform(lon, lat)
        pt = Point(X, Y)
        for tree, geoms, props in self.layers:
            hit = tree.query(pt, predicate='within')
            if len(hit) == 0:
                hit = tree.query_nearest(pt, max_distance=3000)
            for k in hit:
                pr = props[k]
                p = self.pop.get(pr['GISCO_ID'])
                if p:
                    return pr['LAU_NAME'], p[0], p[1]
        return None
