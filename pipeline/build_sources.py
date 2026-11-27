"""sources.json: the Almanac's list of data sources."""
from common import *

ES = 'https://ec.europa.eu/eurostat/databrowser/view/{}/default/table'
EL = 'Eurostat (European Commission)'
LIC = 'CC BY 4.0 (Eurostat re-use policy)'


def s(id, title, publisher, homepage, license, description, used_for, vintage, tables=()):
    return {'id': id, 'title': title, 'publisher': publisher, 'homepage': homepage, 'license': license, 'description': description,
            'used_for': used_for, 'vintage': vintage, 'files': [{'file': t, 'url': ES.format(t)} for t in tables]}


SOURCES = [
    s('eurostat_demo', 'Regional population and demography', EL, 'https://ec.europa.eu/eurostat/web/population-demography', LIC,
      'Population on 1 January by NUTS 3 region and 5-year age group, median age and the yearly series used for growth (2021–2025, compared on today’s 2024 NUTS borders).',
      ['City & country populations', 'Growth', 'Age lenses', 'City View ages'], '1 January 2025', ['demo_r_pjanaggr3', 'demo_r_pjangrp3', 'demo_r_pjanind3']),
    s('eurostat_gdp', 'Regional GDP', EL, 'https://ec.europa.eu/eurostat/web/national-accounts', LIC,
      'Gross domestic product at current market prices by NUTS 3 region, in euros and in purchasing power standards per inhabitant. Gold is GDP.',
      ['Gold yield', 'GDP lenses', 'Economy advisor'], '2023–2024', ['nama_10r_3gdp']),
    s('eurostat_emp', 'Regional employment and value added by industry', EL, 'https://ec.europa.eu/eurostat/web/national-accounts', LIC,
      'Employed persons and gross value added by NUTS 3 region and NACE A*10 industry group (place of work). Food, Production, Science and Culture count jobs in these groups. '
      'Germany, Austria, Spain and Poland publish only wider groups (G-J, K-N, O-U) at NUTS 3; these are split with the mix of the parent NUTS 2 region.',
      ['Food, Production, Science, Culture yields', 'GDP by industry', 'Jobs by industry'], '2022–2024', ['nama_10r_3empers', 'nama_10r_3gva']),
    s('eurostat_area', 'Area by NUTS 3 region', EL, 'https://ec.europa.eu/eurostat', LIC, 'Land area used for population density.', ['Density'], 'latest', ['reg_area3']),
    s('eurostat_hhinc', 'Household income by NUTS 2 region', EL, 'https://ec.europa.eu/eurostat', LIC, 'Net disposable income of private households per inhabitant (EUR and PPS).',
      ['Income lens', 'City income'], '2022–2023', ['nama_10r_2hhinc']),
    s('eurostat_lfs', 'Labour Force Survey, regional', EL, 'https://ec.europa.eu/eurostat/web/lfs', LIC,
      'Unemployment rate, educational attainment of adults 25–64 and population by country of birth, NUTS 2 regions.',
      ['Unemployment', 'Degrees', 'Born abroad', 'City View education'], '2025', ['lfst_r_lfu3rt', 'edat_lfse_04', 'lfst_r_lfsd2pwc']),
    s('eurostat_life', 'Life expectancy by NUTS 2 region', EL, 'https://ec.europa.eu/eurostat', LIC, 'Life expectancy at birth.', ['Life expectancy lens'], '2023–2024', ['demo_r_mlifexp']),
    s('eurostat_silc', 'Poverty or social exclusion (EU-SILC)', EL, 'https://ec.europa.eu/eurostat/web/income-and-living-conditions', LIC,
      'Share of people at risk of poverty or social exclusion (AROPE) by NUTS 2 region (some countries only NUTS 1).', ['Poverty lens'], '2024–2025', ['ilc_peps11n']),
    s('eurostat_isoc', 'Digital economy and society, regional', EL, 'https://ec.europa.eu/eurostat', LIC, 'Households with broadband (latest regional year, 2021).', ['Broadband lens'], '2021', ['isoc_r_broad_h']),
    s('eurostat_tour', 'Tourism: nights spent, regional', EL, 'https://ec.europa.eu/eurostat/web/tourism', LIC, 'Nights spent at tourist accommodation, NUTS 2.', ['Tourism lens'], '2025', ['tour_occ_nin2']),
    s('eurostat_rd', 'R&D expenditure by NUTS 2 region', EL, 'https://ec.europa.eu/eurostat/web/science-technology-innovation', LIC, 'GERD as % of GDP.', ['R&D lens'], '2021–2023', ['rd_e_gerdreg']),
    s('eurostat_htec', 'High-tech employment by NUTS 2 region', EL, 'https://ec.europa.eu/eurostat/web/science-technology-innovation', LIC, 'Employment in high-technology sectors.', ['High-tech jobs lens'], '2025', ['htec_emp_reg2']),
    s('eurostat_sbs', 'Structural business statistics by NUTS 2 region', EL, 'https://ec.europa.eu/eurostat/web/structural-business-statistics', LIC,
      'Persons employed in local units by NACE division (2 digits). The source of city districts and badges (Motor city, Chip city, Finance city…).', ['City districts', 'City badges'], '2023', ['sbs_r_nuts2021']),
    s('eurostat_census', 'Population and Housing Census 2021', EL, 'https://ec.europa.eu/eurostat/web/population-and-housing-census', LIC,
      'Employed residents by occupation (ISCO-08, NUTS 2) and residents by country of birth (NUTS 3).', ['City View workforce and origins'], '2021', ['cens_21cobo_r2', 'cens_21cob_r3']),
    s('eurostat_metro', 'Metropolitan regions', EL, 'https://ec.europa.eu/eurostat/web/metropolitan-regions', LIC,
      'Metro regions (agglomerations of 250,000+ people made of NUTS 3 regions) are the map’s cities. Membership comes from Eurostat’s 2016 metro-region file, carried to 2024 NUTS codes by area overlap (Norway’s Stavanger and Trondheim follow Eurostat’s current list); a few metros redrawn since (Brussels, Lisbon, Riga, Oslo, Cagliari, Charleroi, Liège) differ by more than 8% from Eurostat’s current metro population. Türkiye, Serbia, North Macedonia, Montenegro, Albania, Iceland and Liechtenstein have no Eurostat metro regions: there a city is a NUTS 3 region holding a Natural Earth place of 250,000+ people or the capital. Leuven and Edessa are added as towns. These single-place cities show the population of the municipality itself (Eurostat GISCO LAU; Natural Earth’s city-proper estimate where GISCO has none), not of their NUTS 3 region, and their jobs and GDP are the region’s scaled by that population share; in Türkiye the 30 metropolitan municipalities cover their whole province, so the province is the city.',
      ['Cities'], '2016 typology on 2024 NUTS', ['met_pjanaggr3']),
    s('eurostat_ports', 'Maritime transport: goods handled in main ports', EL, 'https://ec.europa.eu/eurostat/web/transport', LIC, 'Gross weight of goods handled per port.', ['Ports'], '2024–2025', ['mar_go_am_be', 'mar_go_am_nl', 'mar_go_am_de']),
    s('eurostat_airports', 'Air transport: passengers by airport', EL, 'https://ec.europa.eu/eurostat/web/transport', LIC, 'Passengers carried per reporting airport.', ['Airports'], '2025', ['avia_paoa']),
    {'id': 'ons_gdp', 'title': 'Regional gross domestic product: all ITL regions', 'publisher': 'Office for National Statistics (UK)',
     'homepage': 'https://www.ons.gov.uk/economy/grossdomesticproductgdp/datasets/regionalgrossdomesticproductallnutslevelregions', 'license': 'Open Government Licence v3.0',
     'description': 'UK population (mid-year) and GDP at current market prices by ITL 3 region, 1998 to 2024. Eurostat stopped publishing UK regional figures after Brexit. Regions redrawn in ITL 2025 use the 1998 to 2022 release, carried forward with their ITL 1 region’s growth. Pounds are converted at the year’s average euro rate (Eurostat ert_bil_eur_a).',
     'used_for': ['UK population', 'UK GDP'], 'vintage': '2024', 'files': []},
    {'id': 'ons_bres', 'title': 'Business Register and Employment Survey (BRES)', 'publisher': 'Office for National Statistics, via Nomis', 'homepage': 'https://www.nomisweb.co.uk/datasets/newbres6pub',
     'license': 'Open Government Licence v3.0', 'description': 'Employment by SIC 2007 division on ITL 3 (2021) regions, Great Britain. Northern Ireland is not covered.',
     'used_for': ['UK Food, Production, Science, Culture yields', 'UK jobs by industry'], 'vintage': '2024', 'files': []},
    s('eurostat_nat', 'National accounts and Labour Force Survey by industry', EL, 'https://ec.europa.eu/eurostat/web/national-accounts', LIC,
      'Value added and employment by industry for whole countries. Used where a country publishes no regional jobs (Switzerland, Türkiye, Albania, Montenegro): a region’s jobs in an industry are its value added there ÷ the country’s value added per worker, scaled to the national total. Iceland and Liechtenstein have no regional accounts, so their national GDP and jobs are split by population.',
      ['Jobs estimates outside the EU'], '2023–2025', ['nama_10_a10', 'nama_10_a10_e', 'lfsa_egan2', 'nama_10_gdp']),
    {'id': 'gisco_lau', 'title': 'Local administrative units (LAU) with population', 'publisher': 'Eurostat GISCO', 'homepage': 'https://ec.europa.eu/eurostat/web/gisco/geodata/statistical-units/local-administrative-units',
     'license': '© EuroGeographics for the administrative boundaries', 'description': 'Municipality boundaries and populations (2021–2024), used for the population of towns and of cities outside Eurostat’s metro regions.',
     'used_for': ['Town populations'], 'vintage': '2021–2024', 'files': []},
    {'id': 'gisco_nuts', 'title': 'NUTS 2024 boundaries (Nuts2json)', 'publisher': 'Eurostat GISCO', 'homepage': 'https://github.com/eurostat/Nuts2json', 'license': '© EuroGeographics for the administrative boundaries',
     'description': 'NUTS 3 regions (1:10 million) in ETRS89-LAEA (EPSG:3035), the projection of this map, plus country outlines for land and foreign land. The UK, no longer in NUTS 2024, uses its NUTS 2021 regions (identical to ITL 2021). Svalbard, Jan Mayen and the EU’s outermost regions are left off.', 'used_for': ['Regions', 'Countries', 'Land mask'], 'vintage': 'NUTS 2024 (UK: NUTS 2021)', 'files': []},
    {'id': 'worldcover', 'title': 'ESA WorldCover 10 m 2021 v200', 'publisher': 'European Space Agency', 'homepage': 'https://esa-worldcover.org', 'license': 'CC BY 4.0',
     'description': 'Land cover read from the cloud-optimised GeoTIFF overviews (about 300 m), sampled every 4 km.', 'used_for': ['Terrain', 'Land lenses'], 'vintage': '2021', 'files': []},
    {'id': 'terrarium', 'title': 'Terrain Tiles (Terrarium)', 'publisher': 'Mapzen / AWS Open Data', 'homepage': 'https://registry.opendata.aws/terrain-tiles/', 'license': 'Various open (SRTM, EU-DEM, GMTED, ETOPO1); see attribution',
     'description': 'Elevation at zoom 7 (about 800 m in Europe), sampled every 4 km: hills, mountains, peaks, snow, sea depth. The Low-lying land lens samples zoom 9 (about 200 m) every 500 m near the coast.', 'used_for': ['Terrain', 'Elevation lens', 'Low-lying land'], 'vintage': 'static', 'files': []},
    {'id': 'copernicus_ecde', 'title': 'Aggregated climate indicators for Europe (European Climate Data Explorer)', 'publisher': 'Copernicus Climate Change Service (C3S) / European Environment Agency', 'homepage': 'https://cds.climate.copernicus.eu/datasets/sis-ecde-aggregated-climate-indicators', 'license': 'CC BY 4.0',
     'description': 'Hot days (30 °C), tropical nights (20 °C), seasonal mean temperature and rain per NUTS 2 region: ERA5 reanalysis 1991–2020, and EURO-CORDEX projections for RCP4.5 and RCP8.5 as yearly quantiles across the models and 30-year changes. Contains modified Copernicus Climate Change Service information; neither the European Commission nor ECMWF is responsible for any use of it.', 'used_for': ['Hot days', 'Tropical nights', '2050 dial', 'Climate twins', 'Where to live (climate)'], 'vintage': 'v2.0 (ERA5 to 2025, projections to 2100)', 'files': []},
    {'id': 'natural_earth', 'title': 'Natural Earth 1:10m', 'publisher': 'Natural Earth', 'homepage': 'https://www.naturalearthdata.com', 'license': 'Public domain',
     'description': 'Rivers, lakes, populated places (city positions), roads and railroads.', 'used_for': ['Rivers', 'Lakes', 'Roads', 'Railroads', 'City positions'], 'vintage': '5.1.2', 'files': []},
    {'id': 'natural_earth_roads', 'title': 'Natural Earth roads and railroads', 'publisher': 'Natural Earth', 'homepage': 'https://www.naturalearthdata.com', 'license': 'Public domain',
     'description': 'Motorways, major highways and railroads, snapped to hex links.', 'used_for': ['Roads', 'Railroads'], 'vintage': '5.1.2', 'files': []},
    {'id': 'wri_gppd', 'title': 'Global Power Plant Database v1.3', 'publisher': 'World Resources Institute', 'homepage': 'https://datasets.wri.org/dataset/globalpowerplantdatabase', 'license': 'CC BY 4.0',
     'description': 'Power plants with capacity, fuel and position. Last updated 2021, so some coal plants shown have since closed and newer wind and solar farms are missing.', 'used_for': ['Resources', 'Energy advisor'], 'vintage': '2021', 'files': []},
    {'id': 'unesco_whc', 'title': 'UNESCO World Heritage List', 'publisher': 'UNESCO World Heritage Centre', 'homepage': 'https://whc.unesco.org/en/list/', 'license': 'UNESCO terms (data via a public CSV extract)',
     'description': 'Site names, categories, inscription years and positions; the wonders are picked by inscription order.', 'used_for': ['Wonders'], 'vintage': 'to 2023', 'files': []},
    {'id': 'unlocode', 'title': 'UN/LOCODE', 'publisher': 'UNECE', 'homepage': 'https://unece.org/trade/uncefact/unlocode', 'license': 'Open', 'description': 'Port positions.', 'used_for': ['Ports'], 'vintage': 'latest', 'files': []},
    {'id': 'ourairports', 'title': 'OurAirports', 'publisher': 'OurAirports', 'homepage': 'https://ourairports.com/data/', 'license': 'Public domain', 'description': 'Airport positions and names by ICAO code.', 'used_for': ['Airports'], 'vintage': 'latest', 'files': []},
]
save_json('sources', SOURCES)
