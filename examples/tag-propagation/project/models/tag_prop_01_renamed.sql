-- Table 1: preserve each source row while changing both column names.
select
    id as renamed_id,
    loaded_at as renamed_loaded_at
from {{ source('tag_propagation_fixture', 'control') }}
