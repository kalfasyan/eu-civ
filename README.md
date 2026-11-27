# EU Civ

A Civilization-style hex map of Europe built from real public data: the 27 EU countries plus every other country
Eurostat maps by region (the UK, Switzerland, Norway, Iceland, Liechtenstein, Türkiye, Serbia, North Macedonia,
Montenegro and Albania). It has 1,499 NUTS 3 regions, terrain from elevation and land cover, and yields from Eurostat
(Food = farm jobs, Production = industry + construction jobs, Gold = GDP, Science = ICT + professional jobs,
Culture = arts and services jobs).

It also has 325 cities. Most are Eurostat metro regions, and their numbers cover the whole metro region. Where Eurostat
defines none (Türkiye, the Western Balkans, Iceland, Liechtenstein), a city is placed at every place of 250,000+ people
and at each capital, and the towns of Leuven and Edessa are added. These single-place cities show their own
municipality's population (Eurostat GISCO LAU), not their whole region's.

**Live:** https://kalfasyan.github.io/eu-civ/

![EU Civ map](docs/screenshot.jpg)

This is an adaptation of Andrej Karpathy's [usaciv](https://karpathy.ai/usaciv/) (MIT, see
`LICENSE-usaciv`). The frontend is his engine with EU wording, euros and the games and military advisor removed;
the data pipeline in `pipeline/` is new.

## What's on the map

- **Lenses** recolour the map by one measure: people, prosperity, knowledge, life, land and climate.
- **Time dial**: lenses with history (population, GDP vs EU average, unemployment, farm and factory jobs) replay year by
  year from 2000 to the latest Eurostat year.
- **2050 dial** on the Climate lenses (Hot days, Tropical nights). Push them from today to 2050 on two emissions paths
  (RCP4.5 and RCP8.5, Copernicus European Climate Data Explorer), and see each region's *climate twin*: the place whose
  climate today is closest to that region's 2050 climate. The **Low-lying land** lens shows land at or below 5 m near
  the coast. It shows exposure only: dykes and storm surges are not modelled.
- **City View** and **advisors**, including **Where to live**. It scores every region for a trade by take-home pay
  minus rent, jobs in that field, nature, momentum, unemployment and mild summers. Rents are estimated outside the
  cities Eurostat surveys. There is no pay data for the UK, Türkiye, Liechtenstein or Montenegro.
- **Almanac**: what every number means, with every source, licence and link.

**Researchers:** [docs/FAQ.md](docs/FAQ.md) covers data sources and versions, resolution, how values are mapped onto
hexes, the climate scenarios and ensemble, uncertainty, known gaps, licences, citation and reproducibility.

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

Every source, with links and licences, is listed in the in-app Almanac (`data/sources.json`) and in
[docs/FAQ.md](docs/FAQ.md). The Eurostat API serves the latest release on the day you build, and Eurostat revises its
figures, so a rebuild can differ slightly from the committed `data/`.
