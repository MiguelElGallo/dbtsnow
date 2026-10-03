# Operator: build models changed from a baseline

[Documentation](../index.md)

Use the operator identity for a separate native CI project and writable model schema to compare checked-out source with a successful baseline. The administrator prepares the schema/access, and the project administrator deploys the CI object first. State comparison decides which nodes changed; `--defer` lets unchanged upstream references use baseline relations.

## Prepare the baseline and permissions

This development example uses baseline `DBT_CORPORATE_DEV.PROJECTS.NATIVE_DBT_EXAMPLE` from the [first-deployment tutorial](../tutorials/first-deployment.md). Replace it with your own baseline for a real project.

The baseline needs a successful `build` or `run` with populated artifacts in the last seven days. Deployment-time compilation does not qualify. Refresh the example baseline with:

```sh
uv run python scripts/dbt_native.py run --config deployment/dev.json --command build --writeback --apply
```

The executing role needs `MONITOR` on a baseline it does not own, plus access to the native CI object and its writable model destination. Deferral also needs `USAGE` on the baseline model database/schema and `SELECT` on relations used by unchanged references. Grant access only to the relevant sources and relations. [Snowflake state/deferral guide](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-slim-ci-defer-to-prod).

Have the Snowflake administrator prepare `CI_ANALYTICS` and the operator's model privileges through [administrator setup](admin-setup.md#add-project-specific-data-access). Different baseline/CI operator roles need explicit baseline parent access, `MONITOR`, and relation reads. Do not grant deployment ownership merely to retrieve state.

## Project administrator: create and deploy the CI configuration

Make a separate local configuration for the same approved account and identities. Change `project` to `NATIVE_DBT_CI` and `model_schema` to `CI_ANALYTICS`; preserve `deployment_role`, the operator `role`, both connections, and expected usernames. Set `auto_compile: false` and `default_writeback: false`. Store it at `deployment/ci.json`, choosing a new filename if it already exists.

```sh
uv run python scripts/dbt_native.py deploy --config deployment/ci.json
uv run python scripts/dbt_native.py deploy --config deployment/ci.json --apply
uv run python scripts/dbt_native.py project-access --config deployment/ci.json
uv run python scripts/dbt_native.py project-access --config deployment/ci.json --apply
```

Review native object `DBT_CORPORATE_DEV.PROJECTS.NATIVE_DBT_CI` and model destination `DBT_CORPORATE_DEV.CI_ANALYTICS`, replacing these example names with the selected configuration. The project administrator deploys without compilation and grants only this CI object's operator access.

## Operator: run with baseline state

```sh
uv run python scripts/dbt_native.py run \
  --config deployment/ci.json \
  --command build \
  --state-from DBT_CORPORATE_DEV.PROJECTS.NATIVE_DBT_EXAMPLE \
  --select state:modified+ \
  --defer \
  --no-writeback
uv run python scripts/dbt_native.py run \
  --config deployment/ci.json \
  --command build \
  --state-from DBT_CORPORATE_DEV.PROJECTS.NATIVE_DBT_EXAMPLE \
  --select state:modified+ \
  --defer \
  --no-writeback \
  --apply
```

The wrapper resolves the last successful build/run target, freezes that artifact path, and imports it at `./imports/state`. Missing state stops execution; it does not fall back to a full build. [State lookup reference](https://docs.snowflake.com/en/sql-reference/functions/system_dbt_get_last_successful_run_target).

If no model source changed, expect no selected nodes. After a model change and another CI deployment, expect the changed model and its dependent nodes to run. State selection does not guarantee a fully populated CI schema; deferral can still read baseline relations.

For GitHub, commit the reviewed CI destination as `deployment/dev.json`, have the project administrator run deployment, then have the operator choose **build**, set **state_from** and **select**, and optionally **defer** in the [operation workflow](github-actions.md#operator-run-the-operation-workflow). Disable writeback for state comparisons. Both workflows read `deployment/dev.json`; `deployment/ci.json` is the local example.
