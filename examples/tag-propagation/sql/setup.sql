-- Select the approved model database, schema, warehouse, and setup role before
-- running this file. The setup role needs the existing tag-administration rights
-- described in the tutorial. This script does not create or grant privileges.
-- Use a fresh schema for the example: existing example names cause an error.
USE SECONDARY ROLES NONE;

EXECUTE IMMEDIATE $$
DECLARE
    missing_context EXCEPTION (-20001, 'Select the model database and schema before setup.');
BEGIN
    IF (CURRENT_DATABASE() IS NULL OR CURRENT_SCHEMA() IS NULL) THEN
        RAISE missing_context;
    END IF;
END;
$$;

SHOW TAGS IN SCHEMA;
SET tag_prop_visible_tags_query_id = (SELECT LAST_QUERY_ID());

EXECUTE IMMEDIATE $$
DECLARE
    collision_count INTEGER;
    name_collision EXCEPTION (-20002, 'Example objects already exist. Choose a fresh schema or review cleanup first.');
BEGIN
    SELECT COUNT(*) INTO :collision_count
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = CURRENT_SCHEMA()
      AND TABLE_NAME IN (
          'TAG_PROP_CONTROL', 'TAG_PROP_01_RENAMED',
          'TAG_PROP_02_TRANSFORMED', 'TAG_PROP_03_CONCATENATED'
      );
    IF (collision_count > 0) THEN
        RAISE name_collision;
    END IF;

    SELECT COUNT(*) INTO :collision_count
    FROM TABLE(RESULT_SCAN($tag_prop_visible_tags_query_id))
    WHERE "database_name" = CURRENT_DATABASE()
      AND "schema_name" = CURRENT_SCHEMA()
      AND "name" IN (
          'TAG_PROP_SOURCE', 'TAG_PROP_PURPOSE',
          'TAG_PROP_ID_LINEAGE', 'TAG_PROP_TIME_LINEAGE'
      );
    IF (collision_count > 0) THEN
        RAISE name_collision;
    END IF;
END;
$$;

CREATE TABLE TAG_PROP_CONTROL (
    ID NUMBER(38, 0) NOT NULL,
    LOADED_AT TIMESTAMP_NTZ NOT NULL
)
COMMENT = 'Synthetic source for the dbtsnow tag propagation example';

INSERT INTO TAG_PROP_CONTROL (ID, LOADED_AT) VALUES
    (1, '2025-01-01 10:00:00'::TIMESTAMP_NTZ),
    (2, '2025-01-02 23:30:00'::TIMESTAMP_NTZ),
    (3, '2025-02-28 23:30:00'::TIMESTAMP_NTZ);

CREATE TAG TAG_PROP_SOURCE
    PROPAGATE = ON_DEPENDENCY_AND_DATA_MOVEMENT
    COMMENT = 'Synthetic source table lineage';
CREATE TAG TAG_PROP_PURPOSE
    PROPAGATE = ON_DEPENDENCY_AND_DATA_MOVEMENT
    COMMENT = 'Purpose of the tag propagation example';
CREATE TAG TAG_PROP_ID_LINEAGE
    PROPAGATE = ON_DEPENDENCY_AND_DATA_MOVEMENT
    COMMENT = 'Lineage of the original ID column';
CREATE TAG TAG_PROP_TIME_LINEAGE
    PROPAGATE = ON_DEPENDENCY_AND_DATA_MOVEMENT
    COMMENT = 'Lineage of the original LOADED_AT column';

-- These are the only explicit assignments in the example. No downstream model
-- has a tag hook, copy macro, or manual tag assignment.
ALTER TABLE TAG_PROP_CONTROL SET TAG
    TAG_PROP_SOURCE = 'tag_prop_control',
    TAG_PROP_PURPOSE = 'tag_propagation_example';
ALTER TABLE TAG_PROP_CONTROL MODIFY COLUMN ID SET TAG
    TAG_PROP_ID_LINEAGE = 'control_id';
ALTER TABLE TAG_PROP_CONTROL MODIFY COLUMN LOADED_AT SET TAG
    TAG_PROP_TIME_LINEAGE = 'loaded_at';
