"""Copernicus DEM GLO-90 elevation, sampled at points. Public on AWS Open Data: no account or key.

The DEM is published as one cloud-optimised GeoTIFF per 1 x 1 degree tile (only tiles with land exist), 3 arc seconds
(about 90 m) with internal overviews at 1/2 and 1/4. A tile is read once at the requested level and cached in
raw/copdem/ as .npz, so a rebuild reads nothing from the network. Heights are metres above the EGM2008 geoid. The DEM
is a surface model: it includes buildings and forest canopy, and open water inside land tiles is flattened.

This replaces the Terrarium tiles on land (their sources are a patchwork of SRTM, EU-DEM, GMTED and others). Terrarium
stays for the sea, because the Copernicus DEM has no bathymetry. Same source and tile scheme as vresto's DEM overlay
(github.com/kalfasyan/vresto, src/vresto/services/dem.py), which streams the 30 m version.

    from copdem import sample
    elev = sample(lon, lat, level=2)   # NaN where there is no DEM tile (open sea)
"""
import os, urllib.request
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from common import RAW

URL = 'https://copernicus-dem-90m.s3.amazonaws.com'
DIR = RAW + '/copdem'
NODATA = -32767.0


def tile_name(la, lo):
    return f"Copernicus_DSM_COG_30_{'N' if la >= 0 else 'S'}{abs(la):02d}_00_{'E' if lo >= 0 else 'W'}{abs(lo):03d}_00_DEM"


def tile_list():
    """Names of the tiles that exist (the bucket's tileList.txt, cached)."""
    os.makedirs(DIR, exist_ok=True)
    p = DIR + '/tileList.txt'
    if not os.path.exists(p):
        with urllib.request.urlopen(URL + '/tileList.txt', timeout=120) as r:
            open(p, 'wb').write(r.read())
    return set(open(p).read().split())


def load_tile(la, lo, level=0):
    """(array float32 with NaN for no data, (west, north, deg per px x, deg per px y)) for the tile at overview level
    0 (full), 1 (1/2) or 2 (1/4). Cached."""
    import rasterio
    name = tile_name(la, lo)
    p = f'{DIR}/{name}_L{level}.npz'
    if not os.path.exists(p):
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', AWS_NO_SIGN_REQUEST='YES'):
            with rasterio.open(f'{URL}/{name}/{name}.tif') as d:
                f = 2 ** level
                h, w = max(1, d.height // f), max(1, d.width // f)
                a = d.read(1, out_shape=(h, w)).astype(np.float32)  # GDAL picks the matching overview
                b = d.bounds
        a[a <= NODATA] = np.nan
        geo = np.array([b.left, b.top, (b.right - b.left) / w, (b.top - b.bottom) / h])
        tmp = p + '.tmp.npz'
        np.savez_compressed(tmp, a=a, geo=geo)
        os.replace(tmp, p)
    z = np.load(p)
    return z['a'], tuple(z['geo'])


def sample(lon, lat, level=0, mask=None, workers=16):
    """Elevation (m) at each point, nearest pixel. NaN where there is no tile or no data, and where mask is False."""
    lon = np.asarray(lon, float); lat = np.asarray(lat, float)
    out = np.full(lon.shape, np.nan, np.float32)
    ok = np.isfinite(lon) & np.isfinite(lat) if mask is None else (np.asarray(mask, bool) & np.isfinite(lon) & np.isfinite(lat))
    tla = np.floor(lat).astype(int); tlo = np.floor(lon).astype(int)
    key = tla * 1000 + tlo
    have = tile_list()
    tiles = [(int(k // 1000), int(k - (k // 1000) * 1000)) for k in np.unique(key[ok])]
    tiles = [(la, lo if lo < 500 else lo - 1000) for la, lo in tiles]
    tiles = [(la, lo) for la, lo in tiles if tile_name(la, lo) in have]
    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(lambda t: load_tile(t[0], t[1], level), tiles))
    for la, lo in tiles:
        a, (west, north, dx, dy) = load_tile(la, lo, level)
        m = ok & (key == la * 1000 + lo)
        c = np.clip(((lon[m] - west) / dx).astype(int), 0, a.shape[1] - 1)
        r = np.clip(((north - lat[m]) / dy).astype(int), 0, a.shape[0] - 1)
        out[m] = a[r, c]
    print('copdem: tiles', len(tiles), 'level', level, 'points with data', int(np.isfinite(out).sum()), 'of', int(ok.sum()))
    return out
