-- One row per scheduled train journey. trip_id is the primary join key to the
-- realtime feed (DATA_FINDINGS §2.7).

select
    trip_id,
    route_id,
    service_id,
    nullif(trip_headsign, '')               as trip_headsign,
    try_cast(nullif(direction_id, '') as integer) as direction_id,
    nullif(shape_id, '')                    as shape_id
from {{ source('raw_gtfs', 'trips') }}
