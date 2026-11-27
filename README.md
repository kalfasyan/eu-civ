# EU Civ

A Civilization-style hex map of Europe built from real public data: the 27 EU countries plus every other country
Eurostat maps by region (the UK, Switzerland, Norway, Iceland, Liechtenstein, Türkiye, Serbia, North Macedonia,
Montenegro and Albania). 325 cities (Eurostat metro regions, plus large cities where Eurostat defines none, plus the
towns of Leuven and Edessa), 1,499 NUTS 3 regions, terrain from elevation and land cover, and yields from Eurostat
(Food = farm jobs, Production = industry + construction jobs, Gold = GDP, Science = ICT + professional jobs,
Culture = arts and services jobs).

**Live:** https://kalfasyan.github.io/eu-civ/

![EU Civ map](docs/screenshot.jpg)

This is an adaptation of Andrej Karpathy's [usaciv](https://github.com/karpathy/usaciv) (MIT, see
`LICENSE-usaciv`). The frontend is his engine with EU wording, euros and the games and military advisor removed;
the data pipeline in `pipeline/` is new.

## Run locally

It is a static site with no build step:

```
python3 -m http.server 8765
# open http://localhost:8765/
```

## Rebuild the data

The scripts write JSON into `data/`. Downloads go into `raw/` and intermediate files into `interim/` (neither is committed).

Requirements: Python 3.10+, `numpy shapely pyproj pillow rasterio openpyxl`.

Inputs to place in `raw/` before running:

- `nuts/` NUTS 2016/2021/2024 region and country files from [eurostat/Nuts2json](https://github.com/eurostat/Nuts2json) (EPSG:3035, 1:10M)
- `ne/` Natural Earth 1:10m rivers, lakes, roads, railroads, populated places (GeoJSON)
- `terrarium/` Terrarium elevation tiles at zoom 7 (AWS Terrain Tiles)
- `worldcover/` ESA WorldCover 2021 overviews (`pipeline/fetch_worldcover.py`)
- `metro/Metro-regions-NUTS-2016.xlsx` from Eurostat's metropolitan regions page
- `uk/` ONS regional GDP and GVA-by-industry workbooks and a BRES extract from Nomis (fetched automatically by `pipeline/uk.py`)
- `misc/` WRI Global Power Plant Database (`gppd.csv`), UNESCO World Heritage list (`whc_sites.csv`), UN/LOCODE (`unlocode.csv`), OurAirports (`airports.csv`)
- `usaciv_world.json`: usaciv's `web/data/world.json`, used only as the template for the terrain rule tables (or set `USACIV_WORLD`)

Eurostat tables are fetched on demand from the JSON-stat API and cached in `raw/eurostat/`. The UK left Eurostat's regional
statistics after Brexit, so its population, GDP and jobs come from the ONS (www.ons.gov.uk) and Nomis (www.nomisweb.co.uk).

Then, from `pipeline/`:

```
python3 build_world.py
python3 build_econ.py
python3 build_lenses.py
python3 build_sites.py
python3 build_people.py
python3 build_sources.py
python3 build_history.py   # yearly series for the time dial (data/history.json) and the GDP vs EU average lens
python3 build_advisor.py   # pay, rent, jobs and languages per region for the Where to live advisor (data/advisor.json)
python3 build_climate.py   # the 2050 dial, climate twins and low-lying land (data/climate.json) and the Climate lenses
```

`build_climate.py` downloads the European Climate Data Explorer's NUTS-aggregated indicators from the Copernicus Climate
Data Store. It needs a free CDS account: put your personal access token in `CDSAPI_KEY` and accept the dataset's CC-BY
licence on [its download page](https://cds.climate.copernicus.eu/datasets/sis-ecde-aggregated-climate-indicators?tab=download).
The key is only used at build time and never reaches `data/` or the site. Downloads are cached in `raw/cds/`; the script
also needs `raw/worldcover/` and fetches zoom 9 terrain tiles near the coast into `raw/terrarium9/`
(`pip install xarray netCDF4` for the netCDF files).

Every source, with links and licences, is listed in the in-app Almanac (`data/sources.json`).
