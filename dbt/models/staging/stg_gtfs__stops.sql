-- Stations and platforms. GTFS uses a two-level hierarchy: a parent "station"
-- and child "platform" stops (DATA_FINDINGS §2.5). Both static stop_times and the
-- realtime feed reference the CHILD (platform) stop_id; we join up to the parent
-- for readable station names downstream.
-- Gotcha: parent stops carry parent_station = '' (empty string), not NULL (§5).

select
    stop_id,
    stop_name,
    -- normalise the empty-string-means-no-parent gotcha to a real NULL
    nullif(parent_station, '')                as parent_station,
    nullif(location_type, '')                 as location_type,
    (nullif(parent_station, '') is null)      as is_parent_station,
    try_cast(nullif(stop_lat, '') as double)  as stop_lat,
    try_cast(nullif(stop_lon, '') as double)  as stop_lon
from {{ source('raw_gtfs', 'stops') }}
