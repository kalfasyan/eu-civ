import rasterio, numpy as np, os, sys
from concurrent.futures import ThreadPoolExecutor
os.environ['CURL_CA_BUNDLE']='/root/.ccr/ca-bundle.crt'
import os
out=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'raw', 'worldcover')
def name(lat,lon):
    return f"{'N' if lat>=0 else 'S'}{abs(lat):02d}{'E' if lon>=0 else 'W'}{abs(lon):03d}"
def job(a):
    lat,lon=a; n=name(lat,lon); p=f'{out}/{n}.npy'
    if os.path.exists(p) or os.path.exists(p+'.none'): return
    url=f'https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{n}_Map.tif'
    try:
        with rasterio.open(url) as s:
            np.save(p, s.read(1,out_shape=(1125,1125)))
        print('ok',n,flush=True)
    except Exception as e:
        open(p+'.none','w').write(str(e)[:200]); print('none',n,flush=True)
jobs=[(lat,lon) for lat in range(33,72,3) for lon in range(-12,36,3)]
with ThreadPoolExecutor(4) as ex: list(ex.map(job,jobs))
