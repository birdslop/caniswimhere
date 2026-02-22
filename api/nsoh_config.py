"""
Shared NSOH (National Storm Overflow Hub) endpoint configuration.

Used by both the live detail API and the polling/social-bot scripts.
Each endpoint is an ArcGIS FeatureServer serving near-real-time
discharge status from a UK water company.
"""

# Default field mapping for English water companies on the NSOH hub.
NSOH_DEFAULT_FIELDS = {
    "id": "Id", "company": "Company", "status": "Status",
    "lat": "Latitude", "lon": "Longitude",
    "receiving_water": "ReceivingWaterCourse",
    "event_start": "LatestEventStart", "event_end": "LatestEventEnd",
}

# Tuples: (company_name, arcgis_feature_server_url, field_map | None)
# field_map=None means use NSOH_DEFAULT_FIELDS.
NSOH_ENDPOINTS = [
    ("Anglian Water", "https://services3.arcgis.com/VCOY1atHWVcDlvlJ/arcgis/rest/services/stream_service_outfall_locations_view/FeatureServer/0", None),
    ("Northumbrian Water", "https://services-eu1.arcgis.com/MSNNjkZ51iVh8yBj/arcgis/rest/services/Northumbrian_Water_Storm_Overflow_Activity_2_view/FeatureServer/0", None),
    ("Severn Trent Water", "https://services1.arcgis.com/NO7lTIlnxRMMG9Gw/arcgis/rest/services/Severn_Trent_Water_Storm_Overflow_Activity/FeatureServer/0", None),
    ("South West Water", "https://services-eu1.arcgis.com/OMdMOtfhATJPcHe3/arcgis/rest/services/NEH_outlets_PROD/FeatureServer/0", None),
    ("Southern Water", "https://services-eu1.arcgis.com/XxS6FebPX29TRGDJ/arcgis/rest/services/Southern_Water_Storm_Overflow_Activity/FeatureServer/0", None),
    ("Thames Water", "https://services2.arcgis.com/g6o32ZDQ33GpCIu3/arcgis/rest/services/Thames_Water_Storm_Overflow_Activity_(Production)_view/FeatureServer/0", None),
    ("United Utilities", "https://services5.arcgis.com/5eoLvR0f8HKb7HWP/arcgis/rest/services/United_Utilities_Storm_Overflow_Activity/FeatureServer/0", None),
    ("Wessex Water", "https://services.arcgis.com/3SZ6e0uCvPROr4mS/arcgis/rest/services/Wessex_Water_Storm_Overflow_Activity/FeatureServer/0", None),
    ("Yorkshire Water", "https://services-eu1.arcgis.com/1WqkK5cDKUbF0CkH/arcgis/rest/services/Yorkshire_Water_Storm_Overflow_Activity/FeatureServer/0", None),
    # Scotland — different field names
    ("Scottish Water", "https://services3.arcgis.com/Bb8lfThdhugyc4G3/arcgis/rest/services/Scottish_Water_Storm_Overflow_Activity/FeatureServer/0", {
        "id": "ASSET_ID", "company": "COMPANY", "status": "STATUS_NSOH",
        "lat": "DISCHARGE_LOCATION_LATITUDE", "lon": "DISCHARGE_LOCATION_LONGITUDE",
        "receiving_water": "RECEIVING_WATER",
        "event_start": "START_DATETIME", "event_end": "END_DATETIME",
    }),
]
