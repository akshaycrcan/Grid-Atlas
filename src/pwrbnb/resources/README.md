# City reference points

`us_places.csv` is a reduced copy of the US Census Bureau's 2025 national Places Gazetteer, downloaded October 11, 2026. It contains the state, place name, and internal latitude/longitude for the 50 states and Washington, DC. Puerto Rico is omitted to match the current US site scope.

Source: https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2025_Gazetteer/2025_Gaz_place_national.zip

Documentation: https://www.census.gov/geographies/reference-files/2025/geo/gazetter-file.html

These reference points represent incorporated places and census-designated places. They are approximate city markers, not datacenter coordinates, street addresses, or parcel locations. Matching requires both the city and state; unmatched or ambiguous places receive no pin. City lookup runs locally without an API key, network request, or per-lookup cost.
