---
name: dbtsnow-operate
description: Build, compile, retry, inspect runs and logs, check freshness, or use baseline state as the operator of an existing native Snowflake DBT PROJECT through this dbtsnow repository. Source deployment and legacy migration belong to dbtsnow-deploy; privilege provisioning belongs to dbtsnow-admin.
---

# Operate a deployed project

Use the user's selected checkout or walk ancestors of this skill to find `pyproject.toml` naming `dbtsnow` and `scripts/dbt_native.py`. Run from that root with the selected configuration. Tutorial account names are examples rather than deployment defaults.

`role`, `connection`, and optional `operator_user` select the operator; deployment fields are reserved for project administration. The generated native profile uses the operator role. Authenticate as that user for two-user validation; administrator role switching does not prove delegated login.

Read only the relevant guide:

| Task | Guide |
| --- | --- |
| Build, compile, retry | [Run and retry](../../../docs/how-to/run-and-retry.md) |
| History, query logs, browser access | [Inspect runs](../../../docs/how-to/inspect-runs.md) |
| Changed models and deferral | [State builds](../../../docs/how-to/state-build.md) |
| Source age | [Source freshness](../../../docs/how-to/check-source-freshness.md) |
| Flags and verification | [Commands](../../../docs/reference/commands.md) |

## Execute the authorized operation

Preview `uv run python scripts/dbt_native.py run --config <config> --command <build|compile|retry|source-freshness>` with the task's flags. Show object/model destination, operator identity/role, runtime, state/selection, and writeback. Read `dbt_version` from the selected configuration if the run preview omits it. Append `--apply` when execution is already authorized. Build/retry can write model relations and tests may query data.

Applied runs verify account/role, optional expected username, empty secondary roles, deployed runtime/profile, and base model database/schema/role/warehouse. Preserve these checks. Do not redeploy merely to execute a project, switch to an administrator role on denial, or broaden privileges automatically. Route source fixes/migration to project administration and access/data provisioning to the appropriate administrator.

Use scoped history/query logs after failure before another write. Service-user CLI tests do not establish human browser sign-in or GitHub OIDC authentication.

## Retry needs failed state

Find an actual failed invocation with compatible persisted `target/run_results.json`. Enabling writeback now cannot recreate missing state. Deployment replaces LIVE files, and intervening writeback may overwrite the failure. Serialize executions with deployment and other runs sharing this path.

Fusion retry explicitly uses configured target/profile; Core inherits recorded arguments. Destination mismatches stop execution; do not bypass them. Retry accepts neither selection nor state. Missing artifacts or a necessary source fix require a separately scoped deploy/new build, rather than an invented retry success. Retry after a successful run is not a validation strategy.

## State, freshness, and jobs

State comparisons need an isolated writable CI model destination, successful build/run artifacts from the last seven days, baseline `MONITOR`, and relation reads for deferral. Use `--state-from DB.SCHEMA.PROJECT --select state:modified+ --no-writeback`, adding `--defer` only with state. Missing state stops execution. Freshness needs defined sources; the included one-view example has none.

`.github/workflows/operate.yml` is manual, main-only, uses `dev-operate` and `SNOWFLAKE_OPERATOR_USER`, and shares `native-dbt-dev` concurrency with deployment. It executes the selected command without deploying source. Follow [GitHub setup](../../../docs/how-to/github-actions.md) for OIDC and allowed input combinations. Dispatch only within the task's authorization and report actual cloud execution separately from offline checks.
