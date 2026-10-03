---
name: dbtsnow-operate
description: Build, compile, retry, inspect logs, check freshness, use baseline state, or migrate an existing native Snowflake DBT PROJECT through this dbtsnow repository. Use for operating and diagnosing deployed dbtsnow objects, especially LIVE artifact and target constraints.
---

# Operate a deployed project

Use the user-selected checkout, or walk ancestors of this SKILL.md to find `pyproject.toml` naming `dbtsnow` and `scripts/dbt_native.py`. If an explicitly selected checkout is invalid, request its location; do not substitute another repository. Run from its root with the user's configuration. Never reuse the historical trial account as a default.

Read only the guide relevant to the task:

| Task | Guide |
| --- | --- |
| Build, compile, retry | [Run and retry](../../../docs/how-to/run-and-retry.md) |
| Find execution/query logs | [Inspect runs](../../../docs/how-to/inspect-runs.md) |
| Select changed models or defer references | [State builds](../../../docs/how-to/state-build.md) |
| Check source age | [Source freshness](../../../docs/how-to/check-source-freshness.md) |
| Convert a numbered object | [Migrate to LIVE](../../../docs/how-to/migrate-to-live.md) |
| Look up flags/verification behavior | [Commands](../../../docs/reference/commands.md) |

## Execute the selected task

Preview `uv run python scripts/dbt_native.py run --config <config> --command <build|compile|retry|source-freshness>` with any required task flags. Show the native object, model destination, runtime, selection/state, and writeback. Append `--apply` when the user has authorized that execution; do not repeat permission requests already resolved. Build writes model relations and runs tests. Do not redeploy merely to execute an existing project.

Applied runs verify deployed runtime, project profile, and the selected profile's base database/schema/role/warehouse. Keep those checks intact. Preview does not connect or verify the deployed target. On failure, use scoped execution history/query logs and the wrapper's error to diagnose the cause before any further mutation. Data repairs, privilege changes, and further executions must stay within the task’s existing authorization; do not broaden access or blindly retry.

## Retry requires preserved failed state

Locate an actual failed invocation that persisted compatible `target/run_results.json` using writeback. Enabling writeback now cannot recreate missing artifacts. Redeployment replaces all LIVE files; intervening writeback can overwrite the failed state. Serialize runs that share it.

Fusion retry explicitly receives the configured target/profile. Core inherits recorded arguments, so missing/different targets or incompatible profiles are rejected. Do not bypass a destination mismatch. Retry accepts no selector/state import. If artifacts are missing or source needs fixing, explain why retry cannot work and propose the separately scoped fix/deploy/new build; do not apply that alternative without task authorization. Retry after a successful invocation is not a validation strategy.

## State and freshness

State validation uses a separate deployed CI object and writable model schema. The baseline needs populated successful build/run artifacts from the last seven days; deployment compilation is insufficient. Roles need baseline `MONITOR`, destination permissions, and baseline relation read access for deferral.

Use `--state-from DB.SCHEMA.PROJECT --select state:modified+ --no-writeback`, adding `--defer` only when requested and using state. The wrapper freezes the baseline locator and imports it at `./imports/state`; missing state stops execution rather than falling back to a full build. A changed-node run need not populate the entire CI schema.

Freshness requires defined dbt sources; the included one-view example has none. Follow the freshness guide for UTC timestamp handling. Use isolated source-data fixtures only when the task includes them; do not alter source tables outside its existing authorization.

## Migration

Use the `migrate` preview/apply path only for the configured legacy object and an authorized migration. It requires appropriate ownership/feature availability and verifies LIVE readback. Numbered source versions become inaccessible; execution history is preserved. Do not enable account bundles, recreate objects, or promise restoration of previous model relations.
