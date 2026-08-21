#!/usr/bin/env python
# coding: utf-8

# # Read realtime data from IOOS Sensor Map via ERDDAP tabledap
# 
# Created: 2026-07-22
# 
# Updated: 2026-07-22
# 
# Suppose you are exploring the [IOOS Sensor Map](https://sensors.ioos.us/),
# and would like to build a map of the recently active stations. (stations that have reported data in the last 30 days)
# 
# One can download the data in multiple forms from the site, but aggregating all the stations together on one map is tricky.
# 
# These features makes Sensor map an extremely useful tool for quick data explorations but now imagine if you want automate that instead of exploring the Sensor Map interactively? Or if you want to make multiple small modification to your query? It would be very tedious and error prone to try that with the Sensor Map interface. The good news is that we cab automate that by querying the ERDDAP server directly.
# 
# We can search for datasets reporting wave data in the last 30 days. We can return the unique coordinates for each dataset so we can build a map.


import time
from xmlrpc import server
from erddapy import ERDDAP
from erddapy.core.url import urlopen
import folium
import geopandas as gpd
import pandas as pd
import lxml

## function to collect appropriate CF standard names
def get_cf_std_name():
    url = "https://cfconventions.org/Data/cf-standard-names/current/src/cf-standard-name-table.xml"

    tbl_version = pd.read_xml(url, xpath="./*")["version_number"][0].astype(int)
    df = pd.read_xml(url, xpath="entry")

    std_names = df.loc[
        (df["id"].str.contains("sea_surface_wave_") | 
         df["id"].str.contains("sea_surface_swell_") |
         df["id"].str.contains("sea_surface_wind_wave_")
         )
    ]

    print(f"CF Standard Name Table: {tbl_version}")

    sensor_map_std_names = pd.read_csv('https://erddap.sensors.ioos.us/erddap/categorize/standard_name/index.csv')

    refine_ctd_names = sensor_map_std_names.merge(std_names, left_on='Category', right_on='id')

    print(f"Number of appropriate CF Standard Names in Sensor Map: {len(refine_ctd_names)}")
    print(f"Appropriate CF Standard Names in Sensor Map:\n{refine_ctd_names['id'].tolist()}")   

    return refine_ctd_names

def get_sensor_map_data(std_names):

    server = "http://erddap.sensors.ioos.us/erddap"
    e = ERDDAP(server=server, protocol="tabledap")

    df_dsets_out = pd.DataFrame()
    for std_name in std_names["id"].tolist():
        kw = {
            "min_time": "now-30days",
            "standard_name": std_name,
        }

        url = e.get_search_url(response="csv", **kw)
        df_dsets = pd.read_csv(url)
        #time.sleep(1)
        df_dsets_out = pd.concat([df_dsets_out, df_dsets])


    dataset_ids = sorted(set(df_dsets_out["Dataset ID"]))

    ## get coords for each station
    e.variables = ["longitude", "latitude"]
    e.constraints = {
    "time>=": "now-30days",
    "time<": "now",
    }
    kw = {"distinct": True}

    sensor_gdf = gpd.GeoDataFrame()
    for dataset_id in dataset_ids:
        if 'glider' not in dataset_id:
            e.dataset_id = dataset_id
            try:
                # df = e.to_pandas(
                #     response="csvp",
                #     **kw
                #     )
                url = e.get_download_url(response="geoJson",
                    **kw
                    )
                
                gdf = gpd.read_file(urlopen(url))
                gdf = gdf.explode(ignore_index=False)
                #time.sleep(1)
                gdf.set_crs(epsg=4326, inplace=True)

                gdf['dataset_id'] = dataset_id
                gdf['info_url'] = e.get_info_url(response="html")
                gdf["href"] = [
                    f'<a href="{url}" target="_blank">{url}</a>' for url in gdf["info_url"]
                    ]
            except:
                print(f"{dataset_id} no valid data from {server}.")


        sensor_gdf = pd.concat([sensor_gdf, gdf])

    return sensor_gdf

# Finally, we can make a map of the stations that have reported data in the last 30 days.

# ## Get HF-Radar stations with wave info
def get_hfradar_data():
   
    server = "https://hfradar.ioos.us/erddap/"
    e = ERDDAP(server=server, protocol="tabledap")

    kw = {
        "min_time": "now-30days",
        "search_for": "Wave data"
    }

    url = e.get_search_url(response="csv", **kw)
    df = pd.read_csv(url)
    dataset_ids = df["Dataset ID"]

    e.variables = ["longitude", "latitude"]
    e.constraints = {
    "time>=": "now-30days",
    "time<": "now",
    }
    kw = {"distinct": True}

    hfr_gdf = gpd.GeoDataFrame()
    for dataset_id in dataset_ids:
        # skip the UPR_FRDO_hfr_wave dataset because coordinates are incorrect.
        if dataset_id != "UPR_FRDO_hfr_wave":
            e.dataset_id = dataset_id
            try:
                url = e.get_download_url(response="geoJson",
                    **kw
                    )
                
                gdf = gpd.read_file(urlopen(url))
                gdf = gdf.explode(ignore_index=False)
                #time.sleep(1)
                gdf.set_crs(epsg=4326, inplace=True)
                gdf['dataset_id'] = dataset_id
                gdf['info_url'] = e.get_info_url(response="html")
                gdf["href"] = [
                    f'<a href="{url}" target="_blank">{url}</a>' for url in gdf["info_url"]
                    ]
            except:
                print(f"{dataset_id} no valid data from {server}.")


        hfr_gdf = pd.concat([hfr_gdf, gdf])

    return hfr_gdf

# ## Read in data from CY2025 Asset Inventory
# 
# Gather appropriate wave datasets from https://erddap.ioos.us/erddap/tabledap/processed_asset_inventory.html
# 
# Wave datasets are defined by `Waves="X"`.

def get_asset_inventory_data():

    server = "https://erddap.ioos.us/erddap/"
    e = ERDDAP(server=server, protocol="tabledap")

    e.constraints = {
    "Year=": "max(Year)",
    "Waves=": "X",
    }

    e.dataset_id = "processed_asset_inventory"
    url = e.get_download_url(response="geoJson")
    asset_inventory_gdf = gpd.read_file(urlopen(url))
    asset_inventory_gdf.set_crs(epsg=4326, inplace=True)
    #asset_inventory_gdf = gpd.read_file(e.get_download_url(response="geoJson"))
    asset_inventory_gdf['info_url'] = e.get_info_url(response="html")
    asset_inventory_gdf["href"] = [
        f'<a href="{url}" target="_blank">{url}</a>' for url in asset_inventory_gdf["info_url"]
        ]
    
    return asset_inventory_gdf

## Cross check those standard names with what is actually in sensor map https://erddap.sensors.ioos.us/erddap/categorize/standard_name/index.csvp
std_names = get_cf_std_name()
sensor_gdf = get_sensor_map_data(std_names)

cdip_gdf = sensor_gdf[sensor_gdf["dataset_id"].str.contains("cdip")]
ndbc_gdf = sensor_gdf[sensor_gdf["dataset_id"].str.contains("ndbc")]
sensor_gdf = sensor_gdf[(~sensor_gdf["dataset_id"].str.contains("ndbc") & ~sensor_gdf["dataset_id"].str.contains("cdip") & ~sensor_gdf["dataset_id"].str.contains("glider"))]

hfr_gdf = get_hfradar_data()
asset_inventory_gdf = get_asset_inventory_data()

print(f"Asset Inventory Stations: {len(asset_inventory_gdf)}")
print(f"HFRadar Stations: {len(hfr_gdf)}")
print(f"RA Stations: {len(sensor_gdf)}")
print(f"NDBC Stations: {len(ndbc_gdf)}")
print(f"CDIP Stations: {len(cdip_gdf)}")

# Now make a map with those layers
## Initialize map
m = folium.Map(
    tiles=None,
    zoom_start=13,
)

## Add base Layers
tiles = "https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}"
gh_repo = "https://github.com/MathewBiddle/ioos_wave_assets"
attr = f'Tiles &copy; Esri &mdash; Sources: GEBCO, NOAA, CHS, OSU, UNH, CSUMB, National Geographic, DeLorme, NAVTEQ, and Esri | <a href="{gh_repo}" target="_blank">{gh_repo}</a>'
folium.raster_layers.TileLayer(
    name="Ocean",
    tiles=tiles,
    attr=attr,
).add_to(m)

tiles = "https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Reference/MapServer/tile/{z}/{y}/{x}"
folium.raster_layers.TileLayer(
    tiles=tiles,
    name="OceanRef",
    attr=attr,
    overlay=True,
    control=False,
).add_to(m)

# Add asset inventory to map
folium.GeoJson(
    data=asset_inventory_gdf,
    name=f"Asset Inventory: {len(asset_inventory_gdf)}",#.format(name),
    marker=folium.CircleMarker(radius=1, color="green"),
    tooltip=folium.features.GeoJsonTooltip(
        fields=["station_long_name"],
        aliases=[""],
    ),
    popup=folium.features.GeoJsonPopup(
        fields=["href"],
        aliases=[""],
    ),
    show=True,
).add_to(m)

# Add sensor map to map
folium.GeoJson(
    data=sensor_gdf,
    name=f"RA Stations: {len(sensor_gdf)}",#.format(name),
    marker=folium.CircleMarker(radius=5, color="red"),
    tooltip=folium.features.GeoJsonTooltip(
        fields=["dataset_id"],
        aliases=[""],
    ),
    popup=folium.features.GeoJsonPopup(
        fields=["href"],
        aliases=[""],
    ),
    show=True,
).add_to(m)

# Add sensor map to map
folium.GeoJson(
    data=cdip_gdf,
    name=f"CDIP Stations: {len(cdip_gdf)}",#.format(name),
    marker=folium.CircleMarker(radius=5, color="orange"),
    tooltip=folium.features.GeoJsonTooltip(
        fields=["dataset_id"],
        aliases=[""],
    ),
    popup=folium.features.GeoJsonPopup(
        fields=["href"],
        aliases=[""],
    ),
    show=True,
).add_to(m)

# Add sensor map to map
folium.GeoJson(
    data=ndbc_gdf,
    name=f"NDBC Stations: {len(ndbc_gdf)}",#.format(name),
    marker=folium.CircleMarker(radius=5, color="purple"),
    tooltip=folium.features.GeoJsonTooltip(
        fields=["dataset_id"],
        aliases=[""],
    ),
    popup=folium.features.GeoJsonPopup(
        fields=["href"],
        aliases=[""],
    ),
    show=True,
).add_to(m)

# Add hfr stations to map
folium.GeoJson(
    data=hfr_gdf,
    name=f"HFR: {len(hfr_gdf)}",#.format(name),
    marker=folium.CircleMarker(radius=5, color="blue"),
    tooltip=folium.features.GeoJsonTooltip(
        fields=["dataset_id"],
        aliases=[""],
    ),
    popup=folium.features.GeoJsonPopup(
        fields=["href"],
        aliases=[""],
    ),
    show=True,
).add_to(m)

## Configure the map
folium.LayerControl(collapsed=True).add_to(m)
m.fit_bounds(m.get_bounds())
m.save("docs/index.html")

