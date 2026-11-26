"""Tiny Eurostat JSON-stat fetcher with cache. get(ds, **filters) -> {geo: {time: value}} for the remaining dims fixed."""
import json, os, urllib.request, urllib.parse, itertools, hashlib
B = 'https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/'
CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'raw', 'eurostat')

def raw(ds, **f):
    q = [('format', 'JSON'), ('lang', 'EN')]
    for k, v in sorted(f.items()):
        for x in (v if isinstance(v, (list, tuple)) else [v]):
            q.append((k, str(x)))
    qs = urllib.parse.urlencode(q)
    key = ds + '_' + hashlib.md5(qs.encode()).hexdigest()[:10] + '.json'
    p = os.path.join(CACHE, key)
    if not os.path.exists(p):
        with urllib.request.urlopen(B + ds + '?' + qs, timeout=300) as r:
            data = r.read()
        open(p, 'wb').write(data)
    return json.load(open(p))

def table(ds, **f):
    """Returns list of (coords dict, value)."""
    d = raw(ds, **f)
    ids = d['id']; size = d['size']
    cats = [sorted(d['dimension'][i]['category']['index'].items(), key=lambda kv: kv[1]) for i in ids]
    cats = [[k for k, _ in c] for c in cats]
    vals = d['value']
    out = []
    strides = []
    s = 1
    for n in reversed(size):
        strides.append(s); s *= n
    strides = list(reversed(strides))
    for k, v in (vals.items() if isinstance(vals, dict) else enumerate(vals)):
        if v is None: continue
        k = int(k); co = {}
        for dim, st, c in zip(ids, strides, cats):
            co[dim] = c[(k // st) % len(c)]
        out.append((co, v))
    return out, d

def latest(ds, key='geo', min_year=None, **f):
    """{geo: (value, year)} with the latest available year per geo."""
    rows, d = table(ds, **f)
    best = {}
    for co, v in rows:
        g = co[key]; t = co['time']
        if min_year and int(t[:4]) < min_year: continue
        if g not in best or t > best[g][1]:
            best[g] = (v, t)
    return best

def labels(ds, dim, **f):
    d = raw(ds, **f)
    return d['dimension'][dim]['category']['label']
