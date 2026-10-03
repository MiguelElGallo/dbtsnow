# Build models changed from a baseline

[Documentation](../index.md)

Use a separate native CI project and model schema to compare checked-out source with a successful baseline. State comparison decides which nodes changed; `--defer` lets unchanged upstream references use baseline relations.

## Prepare the baseline and permissions

This development example uses baseline `DEV_DBT_PRJ.PROJECTS.NATIVE_DBT_EXAMPLE` from the [first-deployment tutorial](../tutorials/first-deployment.md). Replace it with your own baseline for a real project.

The baseline needs a successful `build` or `run` with populated artifacts in the last seven days. Deployment-time compilation does not qualify. Refresh the example baseline with:

```sh
uv run python scripts/dbt_native.py run --config deployment/dev.json --command build --writeback --apply
```

The executing role needs `MONITOR` on a baseline it does not own, plus access to the native CI object and its writable model destination. Deferral also needs `USAGE` on the baseline model database/schema and `SELECT` on relations used by unchanged references. Grant access only to the relevant sources and relations. [Snowflake state/deferral guide](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-slim-ci-defer-to-prod).

For this example, ask an administrator to prepare the separate model schema:

```sql
CREATE SCHEMA IF NOT EXISTS DEV_DBT_PRJ.CI_ANALYTICS;
GRANT USAGE ON SCHEMA DEV_DBT_PRJ.CI_ANALYTICS TO ROLE DEV_DBT_PRJ_DEPLOYER;
GRANT CREATE TABLE, CREATE VIEW ON SCHEMA DEV_DBT_PRJ.CI_ANALYTICS TO ROLE DEV_DBT_PRJ_DEPLOYER;
```

The tutorial role already owns the baseline and its example view. Different baseline and CI roles need the explicit read grants described above.

## Create the CI configuration

```sh
uv run python scripts/dbt_native.py wizard \
  --source example \
  --output deployment/ci.json \
  --database DEV_DBT_PRJ \
  --object-schema PROJECTS \
  --project NATIVE_DBT_CI \
  --role DEV_DBT_PRJ_DEPLOYER \
  --model-database DEV_DBT_PRJ \
  --model-schema CI_ANALYTICS \
  --no-auto-compile \
  --no-default-writeback
```

Answer the account, connection, warehouse, and remaining prompts. Keep `native_dbt_example` as the profile and `dev` as the target. Review every proposed value, particularly the separate model schema. String flags supply editable wizard suggestions; explicit boolean flags apply directly without another prompt.

`auto_compile: false` skips full compilation during deployment, leaving the selected state-based run to do its work.

## Deploy the CI object

```sh
uv run python scripts/dbt_native.py deploy --config deployment/ci.json
uv run python scripts/dbt_native.py deploy --config deployment/ci.json --apply
```

Confirm the object is `DEV_DBT_PRJ.PROJECTS.NATIVE_DBT_CI` and the model destination is `DEV_DBT_PRJ.CI_ANALYTICS` before applying.

## Run with baseline state

```sh
uv run python scripts/dbt_native.py run \
  --config deployment/ci.json \
  --command build \
  --state-from DEV_DBT_PRJ.PROJECTS.NATIVE_DBT_EXAMPLE \
  --select state:modified+ \
  --defer \
  --no-writeback
uv run python scripts/dbt_native.py run \
  --config deployment/ci.json \
  --command build \
  --state-from DEV_DBT_PRJ.PROJECTS.NATIVE_DBT_EXAMPLE \
  --select state:modified+ \
  --defer \
  --no-writeback \
  --apply
```

The wrapper resolves the last successful build/run target, freezes that artifact path, and imports it at `./imports/state`. Missing state stops execution; it does not fall back to a full build. [State lookup reference](https://docs.snowflake.com/en/sql-reference/functions/system_dbt_get_last_successful_run_target).

If no model source changed, expect no selected nodes. After a model change and another CI deployment, expect the changed model and its dependent nodes to run. State selection does not guarantee a fully populated CI schema; deferral can still read baseline relations.

For GitHub, commit a reviewed configuration for this CI destination as `deployment/dev.json`, then enable **build**, set **state_from** and **select**, and optionally **defer** in the [deployment workflow](github-actions.md). The workflow always reads `deployment/dev.json`; `deployment/ci.json` is the local example.
