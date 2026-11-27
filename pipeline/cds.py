"""Tiny Copernicus Climate Data Store fetcher with cache, for the European Climate Data Explorer's NUTS-aggregated
indicators (sis-ecde-aggregated-climate-indicators, CC-BY 4.0).

Needs a free CDS account: set CDSAPI_KEY to your personal access token and accept the dataset's CC-BY licence on its
download page. The key is only used here, at build time; nothing about it reaches data/ or the site.

get(variable, product, origin, aggregation, other=None) -> path to the cached netCDF file.
"""
import hashlib, io, json, os, time, urllib.error, urllib.request, zipfile

B = 'https://cds.climate.copernicus.eu/api/retrieve/v1'
DS = 'sis-ecde-aggregated-climate-indicators'
CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'raw', 'cds')


def _call(url, data=None):
    key = os.environ.get('CDSAPI_KEY')
    if not key:
        raise SystemExit('Set CDSAPI_KEY to your Copernicus CDS personal access token.')
    h = {'PRIVATE-TOKEN': key, 'Content-Type': 'application/json'}
    for attempt in range(6):  # the CDS gateway answers 5xx now and then
        r = urllib.request.Request(url, data=json.dumps(data).encode() if data else None, headers=h)
        try:
            with urllib.request.urlopen(r, timeout=300) as f:
                return json.load(f)
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == 5:
                raise
            time.sleep(30 * (attempt + 1))


def get(variable, product, origin='projections', aggregation='yearly', other=None, layer='nuts_level_2'):
    inputs = {'variable': [variable], 'origin': origin, 'product': [product], 'temporal_aggregation': [aggregation],
              'spatial_aggregation': 'regional_layer', 'regional_layer': [layer], 'version': 'v2_0'}
    if other:
        inputs['other_parameters'] = [other]
    tag = hashlib.md5(json.dumps(inputs, sort_keys=True).encode()).hexdigest()[:10]
    d = os.path.join(CACHE, f'{variable}_{product}_{origin}_{aggregation}_{tag}')
    if not os.path.isdir(d) or not any(n.endswith('.nc') for n in os.listdir(d)):
        os.makedirs(d, exist_ok=True)
        jid = _call(f'{B}/processes/{DS}/execution', {'inputs': inputs})['jobID']
        while True:
            s = _call(f'{B}/jobs/{jid}')['status']
            if s in ('successful', 'failed', 'rejected', 'dismissed'):
                break
            time.sleep(5)
        if s != 'successful':
            raise RuntimeError(f'CDS job {jid} {s}: {inputs}')
        href = _call(f'{B}/jobs/{jid}/results')['asset']['value']['href']
        with urllib.request.urlopen(href, timeout=300) as f:
            zipfile.ZipFile(io.BytesIO(f.read())).extractall(d)
    return os.path.join(d, next(n for n in sorted(os.listdir(d)) if n.endswith('.nc')))


def retrieve(dataset, inputs, ext='.nc'):
    """Any CDS dataset (e.g. ERA5-Land monthly means): submit, wait, download once, cache. Returns the file path."""
    tag = hashlib.md5(json.dumps([dataset, inputs], sort_keys=True).encode()).hexdigest()[:10]
    p = os.path.join(CACHE, f'{dataset}_{tag}{ext}')
    if os.path.exists(p):
        return p
    os.makedirs(CACHE, exist_ok=True)
    jid = _call(f'{B}/processes/{dataset}/execution', {'inputs': inputs})['jobID']
    while True:
        s = _call(f'{B}/jobs/{jid}')['status']
        if s in ('successful', 'failed', 'rejected', 'dismissed'):
            break
        time.sleep(10)
    if s != 'successful':
        raise RuntimeError(f'CDS job {jid} {s}: {dataset}')
    href = _call(f'{B}/jobs/{jid}/results')['asset']['value']['href']
    with urllib.request.urlopen(href, timeout=900) as f:
        data = f.read()
    if data[:2] == b'PK':  # some requests come back zipped
        z = zipfile.ZipFile(io.BytesIO(data))
        data = z.read(next(n for n in z.namelist() if n.endswith(ext)))
    with open(p + '.part', 'wb') as f:
        f.write(data)
    os.replace(p + '.part', p)
    return p
