# Run a project and retry a failed build

[Documentation](../index.md)

Use a saved configuration for an already deployed LIVE object. The wrapper checks its runtime, project profile, and model destination before execution.

## Run a build

Preview first, then execute:

```sh
uv run python scripts/dbt_native.py run --config deployment/dev.json --command build --writeback
uv run python scripts/dbt_native.py run --config deployment/dev.json --command build --writeback --apply
```

`build` creates or updates model relations and runs tests. `--writeback` saves generated artifacts in LIVE so a later retry can read the failed invocation. On success, the wrapper prints native output and `dbt build completed successfully.`

For compilation alone, use `--command compile`. To check source age, follow [source freshness](check-source-freshness.md).

## Retry an actual failure

Follow these steps only if the previous build **failed** after recording runnable nodes:

1. Use [run history and logs](inspect-runs.md) to find the cause.
2. Correct the cause without redeploying the object. For example, repair a failing source-data row or restore its permissions.
3. Retry the recorded failed invocation:

```sh
uv run python scripts/dbt_native.py run --config deployment/dev.json --command retry --writeback
uv run python scripts/dbt_native.py run --config deployment/dev.json --command retry --writeback --apply
```

Retry requires compatible `target/run_results.json` from the failed run. Enabling writeback only for retry cannot recreate missing earlier artifacts. Avoid intervening executions that overwrite the failed state. Serialize runs sharing LIVE writeback paths.

Fusion receives the configured target and profile explicitly; Core inherits them, so the wrapper checks its recorded arguments. Recorded destination mismatches stop execution. The template accepts no retry selector. [dbt retry behavior](https://docs.getdbt.com/reference/commands/retry).

## Choose retry or a new build

| Situation | Action |
| --- | --- |
| Failed run has compatible persisted artifacts; only data or permissions changed | Retry without redeploying. |
| Source code must change | Fix the code, deploy it, then run a new build. |
| Failed run used `--no-writeback`, or failed before runnable nodes were recorded | Correct the cause and run a new build. |
| Previous invocation succeeded | Run a new build if needed. The pinned Fusion preview returns an error when retry finds no failed nodes. |

Deployment replaces all LIVE files, including generated target/log files. A code deployment therefore deletes the failed state needed by retry. [LIVE file behavior](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-live-version).

To change the default persistence setting, see [configuration](../reference/configuration.md); to compare with a baseline instead, see [state builds](state-build.md).
