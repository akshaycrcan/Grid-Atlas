# Bundled grid reference layers

Downloaded 2026-10-11 as WGS84 GeoJSON from public ArcGIS REST query endpoints.

- grid_regions.geojson: https://services1.arcgis.com/4yjifSiIG17X0gW4/ArcGIS/rest/services/Data_Center_Demand_by_Region/FeatureServer/2 . ORNL/LANL/INL/NGA HSIP/HIFLD-derived published reference, 11 ISO and non-ISO polygons. ISO source date 2020-06-24; validation 2021-05-28. Non-ISO records have no date. Queried NAME,SOURCEDATE,VAL_DATE, maxAllowableOffset=.02, geometryPrecision=3.
- utility_regions.geojson: https://services3.arcgis.com/OYP7N6mAJJCyH6hd/arcgis/rest/services/Electric_Retail_Service_Territories_HIFLD/FeatureServer/0 . Public HIFLD/ORNL/DOE-CESER-derived retail territory mirror. 2,919 USA records. Queried NAME,STATE,SOURCEDATE, maxAllowableOffset=.025, geometryPrecision=3; paginated in OBJECTID order. Dates are preserved per feature.

These historical, simplified, potentially overlapping geometries are display references only. They are not current authoritative service eligibility boundaries, interconnection studies or capacity data. They never enter research evidence or determine a datacenter's utility. Confirm current service areas with the relevant authority.
