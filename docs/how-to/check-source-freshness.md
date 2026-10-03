# Operator: check source freshness

Check whether a source table was loaded recently, and fail the run when it exceeds your threshold. [Documentation home](../index.md) · [LIVE and artifacts](../explanation/live-version.md).

## Prepare a source

Use the operator connection with a deployed LIVE project and a saved configuration such as `deployment/dev.json`. The operator role needs warehouse access, `USAGE` on the source database/schema, and `SELECT` on the source table. Creating the optional demonstration table also requires `CREATE TABLE` on its schema. Use your configured role and destinations; these examples assume `DEV_DBT_PRJ.ANALYTICS`.

An authorized role can create this demonstration source:

```sql
CREATE TABLE IF NOT EXISTS DEV_DBT_PRJ.ANALYTICS.FRESHNESS_CONTROL (
  ID INTEGER,
  LOADED_AT TIMESTAMP_NTZ
);

INSERT INTO DEV_DBT_PRJ.ANALYTICS.FRESHNESS_CONTROL
SELECT 1, CONVERT_TIMEZONE('UTC', CURRENT_TIMESTAMP())::TIMESTAMP_NTZ
WHERE NOT EXISTS (
  SELECT 1 FROM DEV_DBT_PRJ.ANALYTICS.FRESHNESS_CONTROL
);
```

If another role owns the source, have its owner/platform administrator provision targeted reads through [administrator setup](admin-setup.md#add-project-specific-data-access). The operator should not switch to an administrator role to grant itself access.

Fusion treats timezone-free `TIMESTAMP_NTZ` values as UTC. Casting a session-local `CURRENT_TIMESTAMP()` directly to NTZ can make fresh data appear stale; the example converts to UTC first.

## Project administrator: declare and deploy the source

Add `models/sources.yml` inside your configured source directory (`example/` in the tutorial):

```yaml
version: 2
sources:
  - name: freshness_demo
    database: DEV_DBT_PRJ
    schema: ANALYTICS
    config:
      loaded_at_field: LOADED_AT
      freshness:
        warn_after: {count: 1, period: hour}
        error_after: {count: 2, period: hour}
    tables:
      - name: control
        identifier: FRESHNESS_CONTROL
```

This layout works with the pinned Fusion and Core runtimes. Have the project administrator review and deploy the updated source definition through its own connection. Commit source changes before authenticated GitHub deployment:

```sh
uv run python scripts/dbt_native.py deploy --config deployment/dev.json
uv run python scripts/dbt_native.py deploy --config deployment/dev.json --apply
```

Source changes need redeployment. Deployment replaces LIVE files, so finish any pending retry first; retry requires its prior run artifacts.

## Operator: run and inspect

```sh
uv run python scripts/dbt_native.py run --config deployment/dev.json --command source-freshness
uv run python scripts/dbt_native.py run --config deployment/dev.json --command source-freshness --no-writeback --apply
```

The first command previews. The second runs Snowflake's supported `source freshness` command. Fresh data produces a passing source result and `sources.json`. Disabling writeback keeps LIVE artifacts unchanged; per-query results remain available.

For an intentional negative check on **this demonstration table**, an authorized role can age the timestamp:

```sql
UPDATE DEV_DBT_PRJ.ANALYTICS.FRESHNESS_CONTROL
SET LOADED_AT = DATEADD(hour, -4,
  CONVERT_TIMEZONE('UTC', CURRENT_TIMESTAMP()))::TIMESTAMP_NTZ;
```

Repeat the execution command: it should return a nonzero exit. [Inspect the run](inspect-runs.md) for its stale-source error and query artifacts. Restore the demonstration timestamp afterward:

```sql
UPDATE DEV_DBT_PRJ.ANALYTICS.FRESHNESS_CONTROL
SET LOADED_AT = CONVERT_TIMEZONE('UTC', CURRENT_TIMESTAMP())::TIMESTAMP_NTZ;
```

Sources: [dbt source configuration](https://docs.getdbt.com/reference/commands/source), [Snowflake supported commands](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-supported-commands), [execution and artifact controls](https://docs.snowflake.com/en/sql-reference/sql/execute-dbt-project).
