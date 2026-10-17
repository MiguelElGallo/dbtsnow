-- Table 3: combine both source-column lineages in one derived string.
select
    adjusted_id as final_id,
    concat(
        id_text,
        '@',
        to_char(shifted_loaded_at, 'YYYY-MM-DD"T"HH24:MI:SS')
    ) as record_label,
    to_char(shifted_loaded_at, 'YYYY-MM-DD"T"HH24:MI:SS') as loaded_at_text,
    loaded_date as event_date,
    'constant-only' as constant_marker
from {{ ref('tag_prop_02_transformed') }}
