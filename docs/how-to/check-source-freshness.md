# Operator: check source freshness

[Documentation](../index.md)

Check whether a source table was loaded recently and fail the run when its loading time exceeds the configured threshold.

## Prepare a source

Use an existing source table with a column that records its loading time. This example assumes `DBT_CORPORATE_DEV.RAW.ORDERS` has a `LOADED_AT` column; replace those names with your source.

The operator needs warehouse access, `USAGE` on the source database/schema, and `SELECT` on the table. Have its owner or the Snowflake administrator grant the required reads through [project-specific data access](admin-setup.md#add-project-specific-data-access).

For a `TIMESTAMP_NTZ` loading column, keep values in UTC. A direct cast of a session-local timestamp can make fresh data appear stale. Convert loading timestamps to UTC before storing them, for example with `CONVERT_TIMEZONE('UTC', CURRENT_TIMESTAMP())::TIMESTAMP_NTZ`.

## Project administrator: declare and deploy the source

Add this definition to `models/sources.yml` inside the configured source directory (`example/` in the tutorial):

```yaml
version: 2
sources:
  - name: raw
    database: DBT_CORPORATE_DEV
    schema: RAW
    config:
      loaded_at_field: LOADED_AT
      freshness:
        warn_after: {count: 1, period: hour}
        error_after: {count: 2, period: hour}
    tables:
      - name: orders
        identifier: ORDERS
```

The `config` layout works with the configured Fusion `2.0.0` and supported Core runtime. Choose thresholds that match your source's loading schedule. See the [dbt source configuration](https://docs.getdbt.com/reference/commands/source).

Using the project administrator connection, review and deploy the definition:

```sh
uv run python scripts/dbt_native.py deploy --config deployment/dev.json
uv run python scripts/dbt_native.py deploy --config deployment/dev.json --apply
```

Check for `Verified deployment:` before switching to the operator. Finish pending retries first: deployment replaces LIVE files, including their failed-run artifacts. Commit the source change before using the GitHub deployment workflow.

## Operator: run and inspect

Preview a freshness check that leaves LIVE artifacts unchanged:

```sh
uv run python scripts/dbt_native.py run --config deployment/dev.json --command source-freshness --no-writeback
```

Confirm the operator identity, project, and writeback choice, then execute:

```sh
uv run python scripts/dbt_native.py run --config deployment/dev.json --command source-freshness --no-writeback --apply
```

The wrapper runs Snowflake's supported `source freshness` command. Fresh data produces a passing source result and `sources.json` in the query artifacts. With the example thresholds, a source older than one hour warns; a source older than two hours fails and returns a nonzero exit. Use [run history and logs](inspect-runs.md) to inspect the source result and loading time.

`--no-writeback` preserves LIVE artifacts. Use `--writeback` in both preview and execution if you need to persist this check's artifacts in LIVE. See [supported native commands](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-supported-commands) and [execution artifact controls](https://docs.snowflake.com/en/sql-reference/sql/execute-dbt-project).
