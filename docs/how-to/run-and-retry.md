# Operator: run a project and retry a failed build

[Documentation](../index.md)

Use the operator's own authenticated connection and a saved configuration for an already deployed LIVE project. The configured `role`, `connection`, and optional `operator_user` select this identity. Start after the project administrator has [granted project access](project-admin.md#grant-operator-access) and the Snowflake administrator has supplied model/source privileges.

## Run a build

Preview the build with artifact persistence enabled:

```sh
uv run python scripts/dbt_native.py run --config deployment/dev.json --command build --writeback
```

Confirm the operator identity, project, model destination, and writeback choice. Execute the same plan:

```sh
uv run python scripts/dbt_native.py run --config deployment/dev.json --command build --writeback --apply
```

The wrapper verifies identity, runtime, deployed profile, and model destination before running. `build` creates or updates model relations and runs tests. On success, expect native dbt output followed by `dbt build completed successfully.`

`--writeback` saves generated artifacts in LIVE so a later retry can use a failed invocation. Use `--no-writeback` when you want to leave LIVE artifacts unchanged. For compilation, replace `--command build` with `--command compile` in both commands. To check loading times, follow [source freshness](check-source-freshness.md).

## Retry an actual failure

Use retry after a build failed and saved runnable nodes:

1. Find the cause in [run history and logs](inspect-runs.md).
2. Have the responsible owner repair data or permissions without redeploying source. An operator can change only data it is authorized to change.
3. Preview and retry the recorded invocation:

```sh
uv run python scripts/dbt_native.py run --config deployment/dev.json --command retry --writeback
uv run python scripts/dbt_native.py run --config deployment/dev.json --command retry --writeback --apply
```

Expect the failed nodes to run, followed by `dbt retry completed successfully.` on success.

Retry needs compatible `target/run_results.json` from the failed run. Turning on writeback only for retry cannot recreate missing earlier artifacts. Avoid intervening executions that overwrite the failed state, and coordinate all runs and deployments sharing LIVE files. The two GitHub workflows share a lock; coordinate local executions too.

Fusion receives the configured target and profile explicitly. Core inherits them from the failed invocation, so the wrapper verifies its recorded arguments. A destination mismatch stops execution. Retry accepts no selector. See [dbt retry behavior](https://docs.getdbt.com/reference/commands/retry).

## Choose retry or a new build

| Situation | Action |
| --- | --- |
| Compatible failed artifacts exist; only data or permissions changed | Retry without redeploying. |
| Source code must change | Have the project administrator deploy the reviewed fix, then run a new build. |
| Failed run used `--no-writeback`, or saved no runnable nodes | Correct the cause and run a new build. |
| Previous invocation succeeded | Run a new build when needed; retry is for failed invocations. |

Deployment replaces all LIVE files, including the target/log files needed by retry. See [LIVE file behavior](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-live-version).

Use the [configuration reference](../reference/configuration.md) to change default artifact persistence, or [state builds](state-build.md) to compare with a successful baseline.
