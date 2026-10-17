-- Run after the dbt build in the same model database/schema used by setup.sql.
-- The verification role needs tag metadata visibility and SELECT on all four
-- tables. This verifier expects the unchanged three-row fixture and default
-- source variables. It creates no objects and makes no tag assignments.
USE SECONDARY ROLES NONE;

EXECUTE IMMEDIATE $$
DECLARE
    missing_context EXCEPTION (-20001, 'Select the model database and schema before verification.');
BEGIN
    IF (CURRENT_DATABASE() IS NULL OR CURRENT_SCHEMA() IS NULL) THEN
        RAISE missing_context;
    END IF;
END;
$$;

-- Quote the selected identifiers when passing fully qualified names as strings.
SET tag_prop_namespace = (SELECT '"' || REPLACE(CURRENT_DATABASE(), '"', '""')
    || '"."' || REPLACE(CURRENT_SCHEMA(), '"', '""') || '"');
SET tag_prop_source = (SELECT $tag_prop_namespace || '.TAG_PROP_CONTROL');
SET tag_prop_first = (SELECT $tag_prop_namespace || '.TAG_PROP_01_RENAMED');
SET tag_prop_second = (SELECT $tag_prop_namespace || '.TAG_PROP_02_TRANSFORMED');
SET tag_prop_third = (SELECT $tag_prop_namespace || '.TAG_PROP_03_CONCATENATED');

SHOW TAGS IN SCHEMA;
SET tag_prop_definitions_query_id = (SELECT LAST_QUERY_ID());

WITH
expected_table_tags (tag_name, tag_value) AS (
    SELECT * FROM VALUES
        ('TAG_PROP_SOURCE', 'tag_prop_control'),
        ('TAG_PROP_PURPOSE', 'tag_propagation_example')
),
expected_lineage_tags (tag_name, tag_value) AS (
    SELECT * FROM VALUES
        ('TAG_PROP_ID_LINEAGE', 'control_id'),
        ('TAG_PROP_TIME_LINEAGE', 'loaded_at')
),
expected_models (table_name) AS (
    SELECT * FROM VALUES
        ('TAG_PROP_01_RENAMED'),
        ('TAG_PROP_02_TRANSFORMED'),
        ('TAG_PROP_03_CONCATENATED')
),
expected_columns (table_name, column_name, expects_id, expects_time) AS (
    SELECT * FROM VALUES
        ('TAG_PROP_01_RENAMED', 'RENAMED_ID', TRUE, FALSE),
        ('TAG_PROP_01_RENAMED', 'RENAMED_LOADED_AT', FALSE, TRUE),
        ('TAG_PROP_02_TRANSFORMED', 'ADJUSTED_ID', TRUE, FALSE),
        ('TAG_PROP_02_TRANSFORMED', 'ID_TEXT', TRUE, FALSE),
        ('TAG_PROP_02_TRANSFORMED', 'SHIFTED_LOADED_AT', FALSE, TRUE),
        ('TAG_PROP_02_TRANSFORMED', 'LOADED_DATE', FALSE, TRUE),
        ('TAG_PROP_03_CONCATENATED', 'FINAL_ID', TRUE, FALSE),
        ('TAG_PROP_03_CONCATENATED', 'RECORD_LABEL', TRUE, TRUE),
        ('TAG_PROP_03_CONCATENATED', 'LOADED_AT_TEXT', FALSE, TRUE),
        ('TAG_PROP_03_CONCATENATED', 'EVENT_DATE', FALSE, TRUE),
        ('TAG_PROP_03_CONCATENATED', 'CONSTANT_MARKER', FALSE, FALSE)
),
tag_definitions AS (
    SELECT "name" AS tag_name, "propagate" AS propagation
    FROM TABLE(RESULT_SCAN($tag_prop_definitions_query_id))
    WHERE "database_name" = CURRENT_DATABASE()
      AND "schema_name" = CURRENT_SCHEMA()
),
table_tags AS (
    SELECT * FROM TABLE(INFORMATION_SCHEMA.TAG_REFERENCES($tag_prop_source, 'TABLE'))
    UNION ALL
    SELECT * FROM TABLE(INFORMATION_SCHEMA.TAG_REFERENCES($tag_prop_first, 'TABLE'))
    UNION ALL
    SELECT * FROM TABLE(INFORMATION_SCHEMA.TAG_REFERENCES($tag_prop_second, 'TABLE'))
    UNION ALL
    SELECT * FROM TABLE(INFORMATION_SCHEMA.TAG_REFERENCES($tag_prop_third, 'TABLE'))
),
column_tags AS (
    SELECT * FROM TABLE(INFORMATION_SCHEMA.TAG_REFERENCES_ALL_COLUMNS($tag_prop_source, 'TABLE'))
    UNION ALL
    SELECT * FROM TABLE(INFORMATION_SCHEMA.TAG_REFERENCES_ALL_COLUMNS($tag_prop_first, 'TABLE'))
    UNION ALL
    SELECT * FROM TABLE(INFORMATION_SCHEMA.TAG_REFERENCES_ALL_COLUMNS($tag_prop_second, 'TABLE'))
    UNION ALL
    SELECT * FROM TABLE(INFORMATION_SCHEMA.TAG_REFERENCES_ALL_COLUMNS($tag_prop_third, 'TABLE'))
),
scoped_tags AS (
    -- Match the full tag and object identities, not just their short names.
    SELECT * FROM table_tags
    WHERE TAG_DATABASE = CURRENT_DATABASE()
      AND TAG_SCHEMA = CURRENT_SCHEMA()
      AND OBJECT_DATABASE = CURRENT_DATABASE()
      AND OBJECT_SCHEMA = CURRENT_SCHEMA()
      AND DOMAIN = 'TABLE'
    UNION ALL
    SELECT * FROM column_tags
    WHERE TAG_DATABASE = CURRENT_DATABASE()
      AND TAG_SCHEMA = CURRENT_SCHEMA()
      AND OBJECT_DATABASE = CURRENT_DATABASE()
      AND OBJECT_SCHEMA = CURRENT_SCHEMA()
      AND DOMAIN = 'COLUMN'
),
expected_assignments AS (
    SELECT
        'SOURCE_TAG' AS check_group,
        'TAG_PROP_CONTROL' AS table_name,
        NULL::VARCHAR AS column_name,
        tag_name,
        tag_value,
        'MANUAL' AS apply_method,
        'TABLE' AS tag_level,
        TRUE AS expect_present
    FROM expected_table_tags
    UNION ALL
    SELECT
        'SOURCE_TAG', 'TAG_PROP_CONTROL',
        IFF(tag_name = 'TAG_PROP_ID_LINEAGE', 'ID', 'LOADED_AT'),
        tag_name, tag_value, 'MANUAL', 'COLUMN', TRUE
    FROM expected_lineage_tags
    UNION ALL
    SELECT
        'TABLE_POSITIVE', m.table_name, NULL,
        t.tag_name, t.tag_value, 'PROPAGATED', 'TABLE', TRUE
    FROM expected_models AS m
    CROSS JOIN expected_table_tags AS t
    UNION ALL
    SELECT
        IFF(
            IFF(t.tag_name = 'TAG_PROP_ID_LINEAGE', c.expects_id, c.expects_time),
            'COLUMN_POSITIVE', 'COLUMN_NEGATIVE'
        ),
        c.table_name, c.column_name,
        t.tag_name, t.tag_value, 'PROPAGATED', 'COLUMN',
        IFF(t.tag_name = 'TAG_PROP_ID_LINEAGE', c.expects_id, c.expects_time)
    FROM expected_columns AS c
    CROSS JOIN expected_lineage_tags AS t
),
assignment_checks AS (
    SELECT
        e.check_group,
        e.table_name,
        e.column_name,
        $tag_prop_namespace || '.' || e.tag_name AS tag_name,
        IFF(
            e.expect_present,
            e.tag_value || ' / ' || e.apply_method || ' / ' || e.tag_level,
            'absent'
        ) AS expected,
        COALESCE(NULLIF(LISTAGG(
            a.TAG_VALUE || ' / ' || a.APPLY_METHOD || ' / ' || a.LEVEL,
            '; '
        ) WITHIN GROUP (ORDER BY a.TAG_VALUE, a.APPLY_METHOD, a.LEVEL), ''), 'absent') AS actual,
        IFF(
            e.expect_present,
            COUNT(a.TAG_NAME) = 1 AND COALESCE(COUNT_IF(
                a.TAG_VALUE = e.tag_value
                AND a.APPLY_METHOD = e.apply_method
                AND a.LEVEL = e.tag_level
            ), 0) = 1,
            COUNT(a.TAG_NAME) = 0
        ) AS passed
    FROM expected_assignments AS e
    LEFT JOIN scoped_tags AS a
        ON a.OBJECT_NAME = e.table_name
       AND EQUAL_NULL(a.COLUMN_NAME, e.column_name)
       AND a.TAG_NAME = e.tag_name
    GROUP BY e.check_group, e.table_name, e.column_name, e.tag_name,
             e.tag_value, e.apply_method, e.tag_level, e.expect_present
),
definition_checks AS (
    SELECT
        'TAG_DEFINITION' AS check_group,
        NULL::VARCHAR AS table_name,
        NULL::VARCHAR AS column_name,
        $tag_prop_namespace || '.' || e.tag_name AS tag_name,
        'ON_DEPENDENCY_AND_DATA_MOVEMENT' AS expected,
        COALESCE(d.propagation, 'absent or not visible') AS actual,
        COALESCE(d.propagation = 'ON_DEPENDENCY_AND_DATA_MOVEMENT', FALSE) AS passed
    FROM (
        SELECT tag_name FROM expected_table_tags
        UNION ALL
        SELECT tag_name FROM expected_lineage_tags
    ) AS e
    LEFT JOIN tag_definitions AS d ON d.tag_name = e.tag_name
),
model_columns AS (
    -- In particular, the constant-column negative control must actually exist.
    SELECT e.table_name, COUNT(*) AS expected_count, COUNT(c.COLUMN_NAME) AS actual_count
    FROM expected_columns AS e
    LEFT JOIN INFORMATION_SCHEMA.COLUMNS AS c
        ON c.TABLE_CATALOG = CURRENT_DATABASE()
       AND c.TABLE_SCHEMA = CURRENT_SCHEMA()
       AND c.TABLE_NAME = e.table_name
       AND c.COLUMN_NAME = e.column_name
    GROUP BY e.table_name
),
physical_table_checks AS (
    SELECT
        'PERMANENT_TABLE' AS check_group,
        e.table_name,
        NULL::VARCHAR AS column_name,
        NULL::VARCHAR AS tag_name,
        'BASE TABLE / NO / ' || c.expected_count || ' required columns' AS expected,
        COALESCE(t.TABLE_TYPE || ' / ' || t.IS_TRANSIENT, 'absent or not visible')
            || ' / ' || c.actual_count || ' required columns' AS actual,
        COALESCE(
            t.TABLE_TYPE = 'BASE TABLE' AND t.IS_TRANSIENT = 'NO'
            AND c.actual_count = c.expected_count,
            FALSE
        ) AS passed
    FROM expected_models AS e
    JOIN model_columns AS c ON c.table_name = e.table_name
    LEFT JOIN INFORMATION_SCHEMA.TABLES AS t
        ON t.TABLE_CATALOG = CURRENT_DATABASE()
       AND t.TABLE_SCHEMA = CURRENT_SCHEMA()
       AND t.TABLE_NAME = e.table_name
),
row_counts (table_name, row_count) AS (
    SELECT 'TAG_PROP_CONTROL', COUNT(*) FROM IDENTIFIER($tag_prop_source)
    UNION ALL
    SELECT 'TAG_PROP_01_RENAMED', COUNT(*) FROM IDENTIFIER($tag_prop_first)
    UNION ALL
    SELECT 'TAG_PROP_02_TRANSFORMED', COUNT(*) FROM IDENTIFIER($tag_prop_second)
    UNION ALL
    SELECT 'TAG_PROP_03_CONCATENATED', COUNT(*) FROM IDENTIFIER($tag_prop_third)
),
row_count_checks AS (
    SELECT
        'ROW_COUNT' AS check_group,
        table_name,
        NULL::VARCHAR AS column_name,
        NULL::VARCHAR AS tag_name,
        '3' AS expected,
        TO_VARCHAR(row_count) AS actual,
        row_count = 3 AS passed
    FROM row_counts
),
all_checks AS (
    SELECT * FROM assignment_checks
    UNION ALL
    SELECT * FROM definition_checks
    UNION ALL
    SELECT * FROM physical_table_checks
    UNION ALL
    SELECT * FROM row_count_checks
)
SELECT check_group, table_name, column_name, tag_name, expected, actual, passed
FROM all_checks
ORDER BY check_group, table_name, column_name, tag_name;

-- Fail the SQL command if the matrix contains any failure or an unexpected
-- number of checks. Inspect the preceding result set to diagnose a failure.
SET tag_prop_checks_query_id = (SELECT LAST_QUERY_ID());
EXECUTE IMMEDIATE $$
DECLARE
    total_checks INTEGER;
    failed_checks INTEGER;
    verification_failed EXCEPTION (-20003, 'Tag propagation verification failed. Inspect the preceding check rows.');
BEGIN
    SELECT COUNT(*), COALESCE(COUNT_IF(NOT COALESCE(PASSED, FALSE)), 0)
    INTO :total_checks, :failed_checks
    FROM TABLE(RESULT_SCAN($tag_prop_checks_query_id));
    IF (total_checks <> 43 OR failed_checks <> 0) THEN
        RAISE verification_failed;
    END IF;
    RETURN 'PASS: 43 checks (8 prerequisites, 28 downstream tags, 3 permanent tables, 4 row counts).';
END;
$$;
