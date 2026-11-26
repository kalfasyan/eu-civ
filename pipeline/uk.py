"""United Kingdom figures from UK sources. Eurostat stopped publishing UK regional accounts after Brexit, so:

- population (mid-year) and GDP at current market prices come from the ONS release "Regional gross domestic product:
  all ITL regions" (1998 to 2024, ITL 2025 regions; the 1998 to 2022 release on ITL 2021 regions fills regions that were
  redrawn in 2025, scaled by their ITL 1 region's growth);
- jobs by industry come from the Business Register and Employment Survey (BRES) via Nomis, on ITL 2021 level 3 regions
  (Great Britain only: Northern Ireland is not in BRES).

ITL 2021 codes are the NUTS 2021 codes with TL in place of UK, so the map's UK regions (NUTS 2021) line up directly.
All functions return dicts keyed by the map's UK NUTS 3 codes.
"""
import csv, io, os, re, unicodedata, urllib.request
from collections import defaultdict
import openpyxl
from common import RAW

D = RAW + '/uk'
os.makedirs(D, exist_ok=True)
ONS = 'https://www.ons.gov.uk'
GDP_PAGE = ONS + '/economy/grossdomesticproductgdp/datasets/regionalgrossdomesticproductallnutslevelregions'
NOMIS = 'https://www.nomisweb.co.uk/api/v01/dataset/'


def _open(url, timeout=300):
    return urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=timeout)


def _get(url, path):
    if not os.path.exists(path):
        with _open(url) as r:
            open(path, 'wb').write(r.read())
    return path


def _release(edition):
    p = f'{D}/gdp_{edition}.xlsx'
    if not os.path.exists(p):
        html = _open(GDP_PAGE, 120).read().decode()
        m = re.search(r'/file\?uri=[^"]+' + edition + r'/[^"]+\.xlsx', html)
        _get(ONS + m.group(0), p)
    return openpyxl.load_workbook(p, read_only=True, data_only=True)


def _norm(s):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().lower()
    s = re.sub(r'\b(cc|ua|and|the|of)\b', ' ', s)
    return re.sub(r'[^a-z]', '', s)


def _table(wb, n):
    """{code: (name, {year: value})} for the ITL 3 rows of a table, plus the ITL 1 rows."""
    ws = wb[f'Table {n}']
    head, out = None, {}
    for row in ws.iter_rows(values_only=True):
        if row[0] == 'ITL':
            head = [str(x) for x in row]
            continue
        if head and row[1] and row[0] in ('ITL1', 'ITL3'):
            out[row[1]] = (row[2], {head[i]: row[i] for i in range(3, len(row)) if isinstance(row[i], (int, float))})
    return out


def ons_regions(nuts_names):
    """{UKxxx: {'population': {year: mid-year pop}, 'gdp_gbp': {year: GBP}}} for the map's UK regions.
    nuts_names: {UKxxx: name} of the map's UK NUTS 3 regions."""
    new, old = _release('1998to2024'), _release('1998to2022')
    out = {}
    for key, n in (('population', 6), ('gdp_gbp', 5)):
        tn, to = _table(new, n), _table(old, n)
        by_name = {_norm(v[0]): v[1] for c, v in tn.items() if len(c) == 5}
        scale = 1e6 if key == 'gdp_gbp' else 1
        for code in nuts_names:
            tl = 'TL' + code[2:]
            o = to.get(tl)
            series = None
            for nm in ([o[0]] if o else []) + [nuts_names[code]]:
                if _norm(nm) in by_name:
                    series = by_name[_norm(nm)]
                    break
            if series is None and o:
                # redrawn in ITL 2025: carry the 2022 value forward with the ITL 1 region's growth
                l1n, l1o = tn.get(tl[:3]), to.get(tl[:3])
                series = dict(o[1])
                base = max((y for y in o[1] if l1o and l1o[1].get(y)), default=None)
                if l1n and base:
                    for y, v in l1n[1].items():
                        if int(y) > int(base):
                            series[y] = o[1][base] * v / l1o[1][base]
            if series:
                out.setdefault(code, {})[key] = {y: v * scale for y, v in series.items() if v is not None}
    return out


# BRES 2-digit SIC 2007 divisions -> the map's industry groups
SIC_GROUPS = [('A', range(1, 4)), ('B-E', range(5, 40)), ('C', range(10, 34)), ('F', range(41, 44)), ('G-I', range(45, 57)),
              ('J', range(58, 64)), ('K', range(64, 67)), ('L', range(68, 69)), ('M_N', range(69, 83)), ('O-Q', range(84, 89)),
              ('R-U', range(90, 100))]


def bres_jobs():
    """{UKxxx: {nace group: (jobs, year)}} from BRES employment (latest year), ITL 2021 level 3, Great Britain."""
    p = f'{D}/bres_itl3.csv'
    if not os.path.exists(p):
        codes = ','.join(str(146800640 + d) for d in range(1, 100))
        url = (NOMIS + 'NM_189_1.data.csv?geography=TYPE428&date=latest&industry=' + codes +
               '&employment_status=4&measure=1&measures=20100&select=date_name,geography_code,industry_name,obs_value')
        _get(url, p)
    out = defaultdict(lambda: defaultdict(float))
    year = {}
    for r in csv.DictReader(io.open(p, encoding='utf-8')):
        div = int(r['INDUSTRY_NAME'][:2])
        code = 'UK' + r['GEOGRAPHY_CODE'][2:]
        v = float(r['OBS_VALUE'] or 0)
        year[code] = r['DATE_NAME']
        for g, rng in SIC_GROUPS:
            if div in rng:
                out[code][g] += v
        out[code]['TOTAL'] += v
    return {c: {g: (v, year[c]) for g, v in t.items()} for c, t in out.items()}


GVA_PAGE = ONS + '/economy/grossvalueaddedgva/datasets/nominalandrealregionalgrossvalueaddedbalancedbyindustry'
GVA_GROUPS = {'A': ['AB (1-9)'], 'C': ['C (10-33)'], 'B-E': ['C (10-33)', 'DE (35-39)'], 'F': ['F (41-43)'],
              'G-I': ['G (45-47)', 'H (49-53)', 'I (55-56)'], 'J': ['J (58-63)'], 'K': ['K (64-66)'], 'L': ['L (68)'],
              'M_N': ['M (69-75)', 'N (77-82)'], 'O-Q': ['O (84)', 'P (85)', 'Q (86-88)'], 'R-U': ['R (90-93)', 'S (94-96)', 'T (97-98)'],
              'TOTAL': ['Total']}


def gva_industry(nuts_names, gdp_eur):
    """{UKxxx: {nace group: (GBP, year)}}: ONS balanced GVA by industry (current prices). Regions whose name has no ITL 2025
    match take their ITL 1 region's industry mix, applied to their GDP scaled by the UK's GVA/GDP ratio.
    (A here is agriculture with mining, ONS's AB.)"""
    p = f'{D}/gva_industry.xlsx'
    if not os.path.exists(p):
        html = _open(GVA_PAGE, 120).read().decode()
        _get(ONS + re.search(r'/file\?uri=[^"]+\.xlsx', html).group(0), p)
    wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
    rows = {}
    year = None
    for tab in ('Table 1c', 'Table 3c'):
        for r in wb[tab].iter_rows(values_only=True):
            if r[0] == 'ITL code':
                year = str(r[-1])
                continue
            if r[0] and r[2] and isinstance(r[-1], (int, float)):
                rows.setdefault(r[0], {'name': r[1], 'sic': {}})['sic'][r[2]] = r[-1]

    def group(sic):
        return {g: sum(sic.get(c, 0) for c in cs) for g, cs in GVA_GROUPS.items() if all(c in sic for c in cs)}
    by_name = {_norm(v['name']): group(v['sic']) for c, v in rows.items() if len(c) == 5}
    uk_tot = group(rows['UK']['sic'])['TOTAL'] if 'UK' in rows else None
    out = {}
    for code, nm in nuts_names.items():
        g = by_name.get(_norm(nm))
        if not g:
            l1 = rows.get('TL' + code[2:3])
            if not l1 or code not in gdp_eur or not uk_tot:
                continue
            mix = group(l1['sic'])
            out[code] = {k: (v / mix['TOTAL'], year) for k, v in mix.items()}  # shares; scaled by the caller
            out[code]['_share'] = True
            continue
        out[code] = {k: (v * 1e6, year) for k, v in g.items()}
    return out, year
