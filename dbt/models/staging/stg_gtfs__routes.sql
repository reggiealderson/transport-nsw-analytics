-- Train lines on the network map (DATA_FINDINGS §2.3). route_type = 2 is rail.

select
    route_id,
    nullif(route_short_name, '')             as route_short_name,
    nullif(route_long_name, '')              as route_long_name,
    try_cast(nullif(route_type, '') as integer) as route_type,
    agency_id
from {{ source('raw_gtfs', 'routes') }}
