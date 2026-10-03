# Operator: build models changed from a baseline

[Documentation](../index.md)

Compare source with a successful baseline using a separate native CI project and writable model schema. The Snowflake administrator prepares access, the project administrator deploys the CI project, and the operator runs the comparison. `--defer` lets unselected references use baseline relations.

## Prepare the baseline and permissions

This example uses `DBT_CORPORATE_DEV.PROJECTS.NATIVE_DBT_EXAMPLE` from the [first-deployment tutorial](../tutorials/first-deployment.md). Substitute your project's baseline when needed.

The baseline needs populated artifacts from a successful `build` or `run` in the last seven days. Deployment-time compilation does not qualify. Preview and refresh it with writeback:

```sh
uv run python scripts/dbt_native.py run --config deployment/dev.json --command build --writeback
uv run python scripts/dbt_native.py run --config deployment/dev.json --command build --writeback --apply
```

Confirm the build succeeded before proceeding. The operator needs project `MONITOR` and parent database/schema access for a baseline it does not own. Deferral also needs `USAGE` on the baseline model database/schema and `SELECT` on the relations used by unselected references. See [Snowflake state and deferral](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-slim-ci-defer-to-prod).

Have the administrator prepare `CI_ANALYTICS` with the operator's model privileges through [project-specific data access](admin-setup.md#add-project-specific-data-access). Keep these grants scoped to the required sources and relations; state access does not require deployment ownership.

## Project administrator: create and deploy the CI configuration

Create a separate `deployment/ci.json` from the approved configuration, choosing a fresh filename if it already exists. Preserve the account, roles, connections, and expected usernames. Change these fields in the complete configuration:

```json
{
  "project": "NATIVE_DBT_CI",
  "model_schema": "CI_ANALYTICS",
  "auto_compile": false,
  "default_writeback": false
}
```

Preview and deploy it, then hand off access:

```sh
uv run python scripts/dbt_native.py deploy --config deployment/ci.json
uv run python scripts/dbt_native.py deploy --config deployment/ci.json --apply
uv run python scripts/dbt_native.py project-access --config deployment/ci.json
uv run python scripts/dbt_native.py project-access --config deployment/ci.json --apply
```

Confirm `Verified deployment:` names `DBT_CORPORATE_DEV.PROJECTS.NATIVE_DBT_CI`, then check `Verified project access:`. The model destination should be `DBT_CORPORATE_DEV.CI_ANALYTICS`. Adjust these example names to your configuration. For a managed object schema, use the [administrator grant path](admin-setup.md#complete-project-and-viewer-access-after-deployment).

## Operator: run with baseline state

Preview the comparison:

```sh
uv run python scripts/dbt_native.py run \
  --config deployment/ci.json \
  --command build \
  --state-from DBT_CORPORATE_DEV.PROJECTS.NATIVE_DBT_EXAMPLE \
  --select state:modified+ \
  --defer \
  --no-writeback
```

Confirm the separate CI project and model destination, then apply the same options:

```sh
uv run python scripts/dbt_native.py run \
  --config deployment/ci.json \
  --command build \
  --state-from DBT_CORPORATE_DEV.PROJECTS.NATIVE_DBT_EXAMPLE \
  --select state:modified+ \
  --defer \
  --no-writeback \
  --apply
```

The wrapper freezes the artifact path from the last successful baseline build/run and imports it at `./imports/state`. Missing state stops execution instead of falling back to a full build. See the [state lookup reference](https://docs.snowflake.com/en/sql-reference/functions/system_dbt_get_last_successful_run_target).

`state:modified+` selects changed nodes and their descendants. If the compared manifests contain no selected changes, expect no nodes to run. After changing a model and redeploying the CI source, check the dbt output for that model and its descendants. Deferral can read baseline relations, so this run need not populate every CI relation.

For GitHub, commit the reviewed CI destination as `deployment/dev.json`, deploy it, then choose **build** with **state_from**, **select**, and optionally **defer** in the [operation workflow](github-actions.md#operator-run-the-operation-workflow). Disable writeback for the comparison. Both workflows use `deployment/dev.json`; `deployment/ci.json` is the local example.
