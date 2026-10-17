-- Table 2: arithmetic, text conversion, and date transformations.
select
    renamed_id + 1000 as adjusted_id,
    upper(concat('control-', to_varchar(renamed_id))) as id_text,
    dateadd('hour', 1, renamed_loaded_at) as shifted_loaded_at,
    to_date(renamed_loaded_at) as loaded_date
from {{ ref('tag_prop_01_renamed') }}
