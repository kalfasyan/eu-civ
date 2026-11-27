# EU Civ: FAQ for researchers

This FAQ is for climate, environment, sustainability and policy researchers who want to know what the map shows, where
each number comes from and how far it can be trusted. It describes the code in this repository (`pipeline/` builds
everything in `data/`, and the browser only reads it). Where the code makes a simplification, the FAQ says so.

**The short version.** EU Civ is a way to explore official regional statistics and published climate indicators. It is
not a model and not a forecast. It makes no new climate projections and no new flood or heat-risk assessments. Every
value is copied or simply derived from a public dataset, and the method notes below explain how. For analysis or
publication, go back to the original datasets, which are linked here and in the in-app Almanac.

Contents

1. [General: how the map works](#1-general-how-the-map-works)
2. [Data sources and versions](#2-data-sources-and-versions)
3. [Spatial and temporal resolution](#3-spatial-and-temporal-resolution)
4. [How values are put onto hexes](#4-how-values-are-put-onto-hexes)
5. [Climate: scenarios, models and the 2050 dial](#5-climate-scenarios-models-and-the-2050-dial)
6. [Low-lying land](#6-low-lying-land)
7. [The time dial (2000 to today)](#7-the-time-dial-2000-to-today)
8. [The "Where to live" advisor](#8-the-where-to-live-advisor)
9. [Uncertainty and reliability](#9-uncertainty-and-reliability)
10. [Known gaps and caveats](#10-known-gaps-and-caveats)
11. [Licences and how to cite](#11-licences-and-how-to-cite)
12. [Reproducibility](#12-reproducibility)

---

## 1. General: how the map works

**What area does the map cover?**
The 27 EU member states plus every other country Eurostat maps by NUTS region: the United Kingdom, Switzerland, Norway,
Iceland, Liechtenstein, Türkiye, Serbia, North Macedonia, Montenegro and Albania (37 countries, 1,499 NUTS 3 regions).
The outermost regions (Canary Islands, Azores, Madeira, the French overseas departments), Ceuta and Melilla, and
Svalbard and Jan Mayen are left off (`EXCLUDED_PREFIXES` in `pipeline/common.py`). Countries outside NUTS, such as
Bosnia and Herzegovina, Kosovo and Ukraine, have no data on the map.

**Which borders are used?**
NUTS 2024 for every country except the UK, which uses NUTS 2021 (the same as ITL 2021), because the UK left NUTS after
2020. The polygons are Eurostat GISCO's 1:10 million generalised boundaries from
[Nuts2json](https://github.com/eurostat/Nuts2json). The climate indicators come on NUTS 2 regions, which the pipeline
matches to the 2024, 2021 and 2016 NUTS 2 polygons (see [section 4](#4-how-values-are-put-onto-hexes)).

**How does it choose which cities to show? Is it by size?**
Mostly by an official definition, and then by size when deciding what fits on screen.

- *Which places count as cities (325 in total).* In countries covered by Eurostat's
  [metropolitan regions](https://ec.europa.eu/eurostat/web/metropolitan-regions) typology, each metro region is one city
  (288 of the 325). A metro region is a group of NUTS 3 regions built around a functional urban area of at least 250,000
  people. Its numbers cover the whole metro region, not just the city proper, so "Paris" means the Paris metro region.
  The banner sits on the principal city, found by name in Natural Earth's populated places.
- *Countries with no metro regions* (Türkiye, Serbia, North Macedonia, Montenegro, Albania, Iceland and Liechtenstein):
  a city is placed at every Natural Earth place of 250,000+ people and at each capital, one per NUTS 3 region.
- *Two towns added by name:* Leuven and Edessa.
- *Population of single-place cities.* These cities (the last two groups) do not take the population of their whole
  NUTS 3 region, since Arrondissement Leuven, for instance, has about five times as many people as Leuven. They take the
  population of the municipality (LAU) at the city's position, from Eurostat GISCO's LAU files (2021 to 2024), or
  Natural Earth's city-proper estimate when that is larger, capped at the region's population. Their jobs, GDP and
  yields are the region's, scaled by the town's share of the population, so those numbers are estimates. In Türkiye
  the 30 metropolitan municipalities cover their whole province by law, so there the province is the city.
- *Which banners you see.* On screen, the selected and hovered cities are drawn first, then the others from largest to
  smallest. A population floor falls as you zoom in: about 2 million at the widest view, then 700,000, 250,000, 150,000,
  100,000, 40,000, and every city when you are fully zoomed in. A screen-area budget and a rule that banners never
  overlap hide the rest. So at any zoom, the cities you see are the largest ones that fit (`js/render/banners.js`).

The code is in `pipeline/build_econ.py` (city definitions) and `pipeline/lau.py` (municipal populations).

**What are "yields", "districts" and "wonders"?**
They are game words for real measures. Food is farm jobs, Production is industry and construction jobs, Gold is GDP,
Science is ICT and professional jobs, and Culture is arts and services jobs. The Almanac's *Yields* page lists the
exact industry groups. They are a way to read the data, not extra data.

**Where is the in-app documentation?**
The **Almanac** button opens pages on how the map is built, each lens (with its source) and every source with links and
licences (`data/sources.json`). The **?** button lists the controls and links to this FAQ.

---

## 2. Data sources and versions

Every source is listed in `data/sources.json` and in the Almanac's *Sources* page. These are the main ones.

| Use | Dataset | Version used | Licence |
|---|---|---|---|
| Climate today and in 2050 | Copernicus C3S [Climate and energy indicators for Europe: aggregated climate indicators (European Climate Data Explorer)](https://cds.climate.copernicus.eu/datasets/sis-ecde-aggregated-climate-indicators), `sis-ecde-aggregated-climate-indicators` | `version: v2_0`, NUTS 2 regional layer | CC BY 4.0 |
| Elevation on land (terrain, low-lying land) | [Copernicus DEM GLO-90](https://registry.opendata.aws/copernicus-dem/) (AWS Open Data, `pipeline/copdem.py`) | 2021 release; 1/4 overview (~360 m) for terrain, full 90 m for low-lying land | Copernicus DEM licence (free for any use, with attribution) |
| Sea depth | [AWS Terrain Tiles](https://registry.opendata.aws/terrain-tiles/) (Terrarium encoding) | zoom 7 | Open, attribution per source |
| Land cover | [ESA WorldCover](https://esa-worldcover.org) 10 m | 2021, v200 (downsampled overviews, `pipeline/fetch_worldcover.py`) | CC BY 4.0 |
| Population | Eurostat `demo_r_pjanaggr3`, `demo_r_pjangrp3`, `demo_r_pjanind3` | 1 January 2025 (series from 2000) | CC BY 4.0 |
| GDP | Eurostat `nama_10r_3gdp` | 2023 to 2024 | CC BY 4.0 |
| Jobs and value added by industry | Eurostat `nama_10r_3empers`, `nama_10r_3gva` | 2022 to 2024 | CC BY 4.0 |
| Unemployment | Eurostat LFS `lfst_r_lfu3rt` (NUTS 2) | to 2025 | CC BY 4.0 |
| Employment rate | Eurostat LFS `lfst_r_lfe2emprt`, ages 20–64 (NUTS 2) | to 2025 | CC BY 4.0 |
| Vineyards, olive groves, orchards | Eurostat Integrated Farm Statistics `ef_lus_allcrops` (NUTS 2) | 2023 survey (2020 where 2023 is missing) | CC BY 4.0 |
| Temperature, warming, rainfall, rainfall change | Copernicus C3S [ERA5-Land monthly averaged data](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land-monthly-means), `reanalysis-era5-land-monthly-means` | 1961–1990 and 1996–2025, 0.1° grid | CC BY 4.0 |
| Forest height | Meta and WRI [Global Canopy Height Map](https://registry.opendata.aws/dataforgood-fb-forests/) (Tolan et al. 2024), downsampled `alsgedi_global_v6_float_epsg4326_v3_10deg` average-height tiles | 2024 release (mostly 2018–2020 imagery) | CC BY 4.0 |
| Metro regions | Eurostat metropolitan regions (`met_pjanaggr3` and the metro typology workbook) | 2016 typology on 2024 NUTS | CC BY 4.0 |
| Municipal populations | Eurostat GISCO LAU | 2021 to 2024 | © EuroGeographics for the boundaries |
| UK economy | ONS regional GDP, Nomis BRES | 2024 | Open Government Licence v3.0 |
| Pay (advisor) | Eurostat Structure of Earnings Survey `earn_ses22_48`, `earn_ses22_rhr`; `nama_10r_2coe`; `earn_nt_net` | SES 2022 | CC BY 4.0 |
| Rent (advisor) | Eurostat `prc_colc_rents` (rents used to set EU staff pay) | 2025 | CC BY 4.0 |
| Occupations (advisor) | Eurostat Census 2021 (NUTS 2) | 2021 | CC BY 4.0 |
| Power plants | WRI Global Power Plant Database | v1.3 (2021) | CC BY 4.0 |
| Rivers, lakes, places, roads | Natural Earth 1:10m | 5.1.2 | Public domain |

Eurostat tables are downloaded through the JSON-stat API when the pipeline runs, so you get whatever release Eurostat
serves on that day (see [section 12](#12-reproducibility)).

---

## 3. Spatial and temporal resolution

**How big is a hex?**
The map is in ETRS89 Lambert azimuthal equal-area (EPSG:3035), so every hex has the same area on the ground. A hex has
a radius of 20 km: 40 km corner to corner, about 35 km across, about 1,040 km². The grid is 145 × 146 hexes. A hex is a
display unit. It is never finer than the data behind it.

**What is the resolution of the data behind a hex?**

| Layer | Native unit | Time |
|---|---|---|
| Hot days, tropical nights, seasonal temperature and rain | NUTS 2 region (340 units in the ECDE file) | 1991–2020 average; yearly path 2025–2050 |
| Temperature, warming, rainfall, rainfall change | ERA5-Land 0.1° grid (about 9 km), sampled every 2 km inside each hex | 1996–2025 mean, against 1961–1990 |
| Forest height | 1/4000° cells (about 25 m) of the canopy height map, sampled every 1 km inside each hex | static (mostly 2018–2020 imagery) |
| Vineyards, olive groves, orchards | NUTS 2 region | 2023 (2020 for some regions) |
| Low-lying land | samples every 500 m on the Copernicus DEM GLO-90 (90 m pixels) | static |
| Terrain and land cover | samples every 4 km inside each hex | elevation static; WorldCover 2021 |
| Most socio-economic lenses | NUTS 3 region | latest year Eurostat publishes, mostly 2023 to 2025 |
| Unemployment, employment rate, household income, life expectancy, R&D, some others | NUTS 2 region | as above |
| Time dial | NUTS 3 (unemployment: NUTS 2) | yearly, 2000 to the latest year |

NUTS 2 regions are large: often a whole province or small country, typically 800,000 to 3 million people. Anything
that varies inside a region, such as a city's heat island, a mountain against its valley, or one stretch of coast, is
averaged away.

---

## 4. How values are put onto hexes

**Which region does a hex belong to?**
Each hex is sampled every 4 km. A hex belongs to the NUTS 3 region that most of its land samples fall in
(`pipeline/build_world.py`). Hexes that are mostly sea, or mostly land outside the map's countries, belong to no
region.

**How do the socio-economic lenses get onto hexes?**
Most lenses take a weighted mean over all the NUTS 3 regions sampled in the hex. Each region is weighted by its number
of samples times its population density, so a hex shared by a city and farmland leans towards the city
(`spread()` in `pipeline/build_lenses.py`). NUTS 2 indicators are given to every NUTS 3 region inside them first.

**How do the climate lenses get onto hexes?**
More simply. Each NUTS 3 region takes the value of the ECDE NUTS 2 unit that contains its representative point. If
the point falls just outside the generalised polygons, as it can on a coast, it takes the nearest unit in the same
country. Each hex then shows the value of its own NUTS 3 region (`per_hex()` and `unit_of` in
`pipeline/build_climate.py`). There is no averaging across a hex, so a hex on a NUTS 2 border shows one region's
climate, not a blend. Every region of the map gets a climate unit.

**How do the lenses in `build_more_lenses.py` get onto hexes?**
Children, Growth since 2000 and Employment rate use the same population-weighted mean as the other socio-economic
lenses, with the hex's regions read from a 2 km lattice of samples. Vineyards, Olive groves and Orchards are shares of
land, so they use an area-weighted mean instead. Temperature, Warming, Rainfall and Rainfall change are the mean of the
hex's 2 km samples on the ERA5-Land grid; sea cells next to the coast are filled from their land neighbours first, so
small islands get a value. Forest height is computed per hex from 1 km samples of the canopy height map: samples at
least 5 m tall count as trees, and the hex shows their mean height. A hex where under 3% of the samples are trees
shows no value.

**Why does Growth since 2000 sometimes show a larger region?**
Eurostat backcasts population onto today's NUTS 2024 borders, but not for every redrawn region. Where a NUTS 3 region
has no 2000 figure, it takes the change of the smallest region above it (NUTS 2, NUTS 1, then the country) that has
both years. The lens's note says how many regions this affects.

**How does low-lying land get onto hexes?**
It is computed per hex from the 500 m samples: the share of the hex's land samples at or below 5 m. Region totals add
up the samples inside each NUTS 3 polygon. See [section 6](#6-low-lying-land).

---

## 5. Climate: scenarios, models and the 2050 dial

**Which climate indicators are used?**
Five indicators from the European Climate Data Explorer (ECDE) on the Copernicus Climate Data Store, as defined there:

- *Hot days:* days a year with a daily maximum temperature above 30 °C.
- *Tropical nights:* nights a year when the temperature stays above 20 °C.
- *Mean summer (June to August) and winter (December to February) temperature.*
- *Summer rain:* total June to August precipitation.

Hot days and tropical nights are shown as lenses. All five are used for climate twins.

**What does "today" mean?**
The *Hot days* and *Tropical nights* lenses show the **ERA5 reanalysis average for 1991–2020**. That period is centred
on 2005, so it is already behind today's climate. The dial's first year, 2025, is model-based and shows more hot days:
for example, about 99 million people live in regions with 30 or more hot days a year in the 1991–2020 data, against
about 122 million on the dial's 2025 median.

**Which scenarios?**
Two RCPs from EURO-CORDEX, the regional models the ECDE uses:

- "If emissions fall" is **RCP4.5** (emissions peak around 2040, then fall).
- "If they don't" is **RCP8.5** (emissions keep rising through the century).

These are the older RCP scenarios used by CMIP5 and EURO-CORDEX, not the CMIP6 SSPs. RCP8.5 is a high-emissions path,
and calling it the path "if they don't" fall is a simplification.

**Which models? How many?**
The ensemble is whatever ECDE v2.0 provides for each indicator. The pipeline does not choose or weight models. It uses
the ECDE's precomputed quantiles across the ensemble. For the list of models and the grid, see the dataset's
documentation on the [CDS page](https://cds.climate.copernicus.eu/datasets/sis-ecde-aggregated-climate-indicators).

**How is the path from 2025 to 2050 built?**
For hot days and tropical nights (`path()` in `pipeline/build_climate.py`):

1. Take the ECDE's yearly quantile time series (`product: quantile_time_series`), at the 17th, 50th and 83rd
   percentiles across the models, for each scenario.
2. For each year Y from 2025 to 2050, average the series over the 21 years from Y−10 to Y+10, because a single model
   year is mostly weather. The 2050 value is therefore the mean over 2040–2060.
3. Subtract the same series' own 1991–2020 mean, and add the remainder (the change) to the ERA5 1991–2020 value. This
   delta method removes the models' mean bias against ERA5 for the reference period.
4. Clip to between 0 and 365 days.

One limit of this: the change is taken from a percentile series, not from each model's own change. A percentile across
models in each year is not the same as the percentile of the models' changes. The two are usually close, but the
17th to 83rd range shown is an approximation of the spread of the change.

For summer and winter temperature and summer rain, the pipeline uses the ECDE's ensemble-median absolute change from
1991–2020 to the 30-year period starting in 2041 (`absolute_change_quantiles`), added to ERA5. These are used only for
climate twins. The ECDE's *relative* change product for rain looked wrong in v2.0, about +100% everywhere, so the
absolute change is used instead.

**What is a "climate twin"?**
For each NUTS 2 unit, its twin is the unit whose **1991–2020** climate is closest to this unit's projected **2050**
climate (ensemble median, per scenario), and that is at least 300 km away. The distance uses five features: the square
roots of hot days and tropical nights (so going from 0 to 4 counts as much as going from 40 to 60), summer and winter
mean temperature, and the log of summer rain. Each feature is scaled by its spread across today's regions and weighted
1.0, 1.0, 1.2, 0.6 and 0.5. Twins are named after the largest city in the unit. They are an aid to explaining
projections, in the spirit of "climate analogue" studies. They are not a validated analogue method, and they ignore
humidity, wind, extremes beyond these indicators, and everything that is not climate.

**What are the headline numbers?**
They are stored in `data/climate.json` under `stats`, all ensemble medians, with populations from Eurostat 2025 held
fixed (no population projection):

| | RCP4.5 | RCP8.5 |
|---|---|---|
| People in regions with 30+ hot days a year, 2050 | about 177 million | about 191 million |
| People in regions with 20+ tropical nights a year, 2050 | about 219 million | about 236 million |

The total population with climate data is about 627 million. Because whole NUTS 2 regions are counted, each figure is
"people living in regions whose average crosses the threshold". It does not count people who experience that many hot
days.

---

## 6. Low-lying land

**What does the Low-lying land lens show?**
The share of each hex's land at or below 5 m above sea level, for hexes near the sea (within three hexes, about 100 km,
of a sea hex, with a mean elevation under 120 m). Within those hexes, land is sampled every 500 m. Elevation comes from
the Copernicus DEM GLO-90. Open water and sea are removed using ESA WorldCover 2021.

**How are the people on low-lying land estimated?**
For each NUTS 3 region: population × (built-up land at or below 5 m ÷ all built-up land), using WorldCover's built-up
class. This assumes people are spread evenly over a region's built-up land. Low built-up land is counted on the 500 m
samples and all built-up land on a 1 km lattice, and the ratio is capped at 1. Across the map this gives about 23
million people, and about €1.3 trillion of GDP if GDP is shared out in the same way.

**Is this a flood map or a sea-level-rise projection?**
No. It is exposure: land that is low. Dykes, dunes, storm surges, tides, subsidence and sea-level rise are not
modelled. Much of the Netherlands and other polders shows as low-lying, and is protected. Reading it as "will flood"
would be wrong.

**How accurate is the elevation?**
Rough for a 5 m threshold. The Copernicus DEM GLO-90 is one consistent source (TanDEM-X radar, 2011–2015), with a
stated absolute vertical accuracy under 4 m (90% of points), still close to the threshold itself. It is a surface model, so buildings and trees can raise
cities and forests above their ground level, and heights are above the EGM2008 geoid, not local tide datums. Treat the lens as a regional
pattern, not a parcel-level answer. For serious work, use a coastal DEM with vertical accuracy of a metre or better, and
local defence data.

---

## 7. The time dial (2000 to today)

**Which lenses have a time dial, and from what data?**
Population (`demo_r_pjanaggr3`, with ONS mid-year estimates for the UK), GDP per person in PPS against the EU average
(`nama_10r_3gdp`, EU27 = 100), unemployment (`lfst_r_lfu3rt`, NUTS 2, ages 15–74), and farm and factory shares of jobs
(`nama_10r_3empers`, NACE A and C). The series run from 2000 to the latest year Eurostat publishes. In the current
build, population and unemployment reach 2025, and GDP and jobs 2023.

**What about border changes?**
Eurostat publishes these series on current (NUTS 2024) borders. Where a region was redrawn and Eurostat did not
recalculate its past, the early years show as "no data" rather than a guess. Each series plays only over years where at
least 60% of regions have data, because the newest year is often published for a few countries only.

**What about the UK after Brexit?**
UK population comes from the ONS, so it runs to the latest year. The other UK series come from Eurostat only. In the
current build, UK unemployment stops in 2019, and the GDP index and job shares have no UK data at all, so the UK shows as
"no data" on those dials.

---

## 8. The "Where to live" advisor

**How does it score a region?**
In the browser, from `data/advisor.json`. Regions that fail the hard filters (travel time, language) are removed. The
rest are ranked 0 to 100 on each part, and the parts are weighted:

- *Money:* estimated take-home pay for the chosen trade, minus the estimated rent of a 1-bed flat, adjusted for
  national price levels.
- *Jobs in your field:* how common the trade is against the EU average.
- *Nature:* forest share. *Momentum:* 10-year growth in jobs and population. *Low unemployment.*
- *Mild summers:* fewer hot days plus tropical nights. A 2-year stay uses the dial's 2026 value. A 10-year stay uses
  2035 and a 25-year stay uses 2050, each the average of the RCP4.5 and RCP8.5 medians.

**How reliable are pay and rent?**
Pay is an estimate: the national mean for an occupation group in a sector (SES 2022, firms with 10+ staff), scaled by
the region's pay level. Rent is the roughest number in the app. Eurostat's only rent figure for every country is the
rent of a 1-bed flat in the capital, plus a few cities with EU sites, from a survey used to set EU staff pay. Every
other region is estimated from the nearest surveyed city by household income and metro size, and the app marks these
as estimates.

**Which countries are missing?**
There is no comparable pay data for the UK, Türkiye, Liechtenstein or Montenegro, so they are left out of the Money
part. There is no occupation census for the UK, Türkiye, Serbia, Albania, North Macedonia or Montenegro, so they are
left out of the Jobs part. The advisor is a way to explore the data, not advice.

---

## 9. Uncertainty and reliability

**What uncertainty is shown?**
Only for the climate path. The 2050 dial shows the 17th to 83rd percentile range across the EURO-CORDEX models (see the
caveat in [section 5](#5-climate-scenarios-models-and-the-2050-dial)) next to the median. Climate twins, the seasonal
features and the headline numbers use the median only. No other value in the app has an error bar.

**What does that range leave out?**
It shows how much the models disagree, for one scenario. It is not a probability, and it leaves out:

- scenario uncertainty beyond the two RCPs shown;
- uncertainty in ERA5 itself;
- natural year-to-year variability, which the 21-year mean smooths out;
- variation within NUTS 2 regions;
- everything that is not climate, such as land use, adaptation and population change.

**How reliable are the socio-economic numbers?**
They are official statistics, with the same quality and revision notes as Eurostat and the ONS publish. The app adds
estimates in a few places, and marks them:

- town jobs and GDP scaled from their region;
- regional pay and rent in the advisor;
- regional jobs estimated from value added where a country publishes no regional job counts;
- the spread of NUTS 2 values onto NUTS 3 regions.

**Has any of this been validated?**
No formal validation is done. The pipeline has some sanity checks, such as comparing city totals against Eurostat's own
metro populations and checking region lists. Values are copied from the sources, so spot-check any number you plan to
use against the original table.

---

## 10. Known gaps and caveats

- **Reanalysis rainfall trends.** Rainfall change compares two 30-year means of ERA5-Land, which inherits ERA5's
  precipitation. Reanalysis rain has known biases and its long-term trends are less certain than temperature trends
  (the observing system changed a lot since the 1960s). Read changes of a few per cent as no clear change.
- **Canopy height underestimates tall forests.** The Meta and WRI model saturates in the tallest stands, and the
  downsampled tiles average out single tall trees. Compare regions with each other rather than reading absolute heights.
- **Farm crops are per NUTS 2 region and per farm.** Vineyards, olive groves and orchards count the area on farms in the
  Integrated Farm Statistics, so small non-farm plots are missed, and a large region shows one share for every hex.
  There is no survey for the UK after Brexit, Türkiye, Serbia, Albania, North Macedonia, Montenegro or Liechtenstein.
- **Older climate data.** ECDE v2.0 uses CMIP5-era RCPs and EURO-CORDEX, not CMIP6 SSPs.
- **The base period lags.** "Today" in the climate lenses is the 1991–2020 average.
- **Coarse climate units.** Climate is per NUTS 2 region, so urban heat islands and altitude differences within a
  region are not resolved.
- **Mixed region vintages.** The climate data's NUTS 2 regions are matched to NUTS 2024 regions through polygons, with a
  nearest-unit fallback on coasts.
- **No defences in low-lying land.** No dykes, surges or sea-level rise are modelled, and the elevation error is close to
  the 5 m threshold.
- **Populations are fixed.** Population exposure uses 2025 populations held constant to 2050.
- **Coverage.** Outermost regions are excluded. UK data comes from the ONS and Nomis, with different methods and dates
  than Eurostat. The Western Balkans and Türkiye have no metro regions and no occupation census.
- **Cities are metro regions.** Most "city" figures are metro-region totals, not the city proper.
- **Mixed reference years.** Different lenses come from different years (mostly 2021 to 2025). Each lens names its source
  in the Almanac.
- **The game wording is a metaphor.** Yields, districts and wonders are labels on real data, not extra information.

---

## 11. Licences and how to cite

**Data.** The data in `data/` is derived from the sources above and keeps their terms. Most are CC BY 4.0
(Eurostat, ESA WorldCover, WRI, Copernicus, the Meta and WRI canopy height map), so they need attribution. UK data is under the Open Government Licence
v3.0, administrative boundaries are © EuroGeographics, and Natural Earth is public domain. For anything derived from the
climate data, Copernicus requires a statement like the one in the Almanac: *"Contains modified Copernicus Climate
Change Service information [year]. Neither the European Commission nor ECMWF is responsible for any use that may be
made of the Copernicus information or data it contains."*

**Code.** The map engine, art and interface come from Andrej Karpathy's
[usaciv](https://github.com/karpathy/usaciv), under the MIT licence (`LICENSE-usaciv`). This repository does not yet
have a licence file of its own for the new pipeline and EU changes. Ask the maintainer before reusing that code beyond
what the MIT-licensed parts allow.

For the Forest height lens, cite Tolan, J. et al. (2024), *Very high resolution canopy height maps from RGB imagery
using self-supervised vision transformer and convolutional decoder trained on aerial lidar*, Remote Sensing of
Environment 300, 113888 (CC BY 4.0). For the ERA5-Land lenses, cite Muñoz Sabater, J. (2019), *ERA5-Land monthly
averaged data from 1950 to present*, Copernicus Climate Change Service (C3S) Climate Data Store, DOI
10.24381/cds.68d2bb30.

**How to cite.** There is no paper. If you use the app or its derived data, cite:

1. The **original datasets** you rely on, using the citation each publisher gives. For the climate data, use the
   citation and DOI on the
   [CDS dataset page](https://cds.climate.copernicus.eu/datasets/sis-ecde-aggregated-climate-indicators) and name
   version 2.0.
2. This repository, with the commit you used, for example: *kalfasyan, "EU Civ: a Civilization-style map of Europe from
   public data", GitHub, https://github.com/kalfasyan/eu-civ, commit `<hash>`, accessed `<date>`.*
3. usaciv (Karpathy), for the engine.

---

## 12. Reproducibility

**Can I rebuild the data?**
Yes. The README lists the inputs and the order to run the scripts. In short: Python 3.10+ with
`numpy shapely pyproj pillow rasterio openpyxl` (plus `xarray netCDF4` for the climate step), the raw inputs listed in
the README in `raw/`, then from `pipeline/`:

```
python3 build_world.py && python3 build_econ.py && python3 build_lenses.py && python3 build_sites.py \
  && python3 build_people.py && python3 build_sources.py && python3 build_history.py \
  && python3 build_advisor.py && python3 build_climate.py && python3 build_more_lenses.py
```

**Do I need a Copernicus key?**
Only for `build_climate.py` and `build_more_lenses.py` (ERA5-Land), and only at build time. For ERA5-Land, also accept
its licence on [its download page](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land-monthly-means?tab=download). Create a free CDS account, accept the dataset's CC BY licence on its
download page, and put your personal access token in `CDSAPI_KEY`. `pipeline/cds.py` sends it only to the CDS API. It is
never written to `data/`, `raw/` or the site, and the browser never contacts the CDS. Downloads are cached in `raw/cds/`.
Requests pin `version: v2_0`.

**Will I get exactly the same numbers?**
Not necessarily:

- Eurostat tables are fetched live through the JSON-stat API, and Eurostat revises its figures, so a rebuild picks up
  the latest release. The API responses are cached in `raw/eurostat/`, but that cache is not committed, and
  `data/sources.json` does not record retrieval dates.
- Python package versions are not pinned.
- The AWS terrain tiles and the GISCO and LAU files are fetched by URL without checksums.
- The committed `data/` files are the build that the live site serves, so to work with exactly what the app shows, use
  those files rather than a rebuild.

**Is the computation deterministic?**
Yes. Given the same inputs, the scripts use no random sampling. Low-lying land and climate twins come from fixed
lattices and a nearest-match search.
