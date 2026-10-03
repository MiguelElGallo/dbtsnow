# Validation

Validated on **2026-10-03**. Research and the implementation plan were reviewed independently before coding; separate implementation and test reviews followed.

## Local checks

- Ruff lint and formatting: pass.
- ty type checks: pass.
- **34 unit tests pass**, covering wizard inference, separate object/model destinations, credential exclusion, invalid configurations, paths and symlinks, package requirements, legacy version rejection, account/runtime checks, Git provenance, source readback, unexpected source files, and build failure boundaries.
- GitHub workflow syntax: passes `actionlint`.
- The sample deployment preview succeeds without contacting Snowflake.

## Live trial test

The user selected the trial account and database **`DEV_DBT_PRJ`**. The test created schemas `PROJECTS` and `ANALYTICS` and role `DEV_DBT_PRJ_DEPLOYER`, confined to that database and the existing `COMPUTE_WH` warehouse.

| Check | Result |
| --- | --- |
| Wizard infers the account/project/profile and saves the selected destination | Pass |
| First native deployment | Pass |
| Native object | `DEV_DBT_PRJ.PROJECTS.NATIVE_DBT_EXAMPLE` |
| Runtime / target / version | Fusion `2.0.0-preview.210` / `dev` / `LIVE` |
| Native `dbt build` | Pass: one view and two dbt data tests |
| Independent model query | `ID = 1`, `MESSAGE = Native dbt deployment works` |
| Redeploy a clean local Git fixture without `--force` | Pass |
| Download deployed receipt and compare every uploaded source hash | Pass |
| Native build after verified redeployment | Pass |

The first build was independently confirmed through `DBT_PROJECT_EXECUTION_HISTORY` as `SUCCESS`, query `01c77c63-0000-7510-0000-4845000344b2`. The trial database and example remain available. Trial-specific configuration and readback artifacts are ignored under `.local/`.

The trial's `DESCRIBE` output omitted newer commit-metadata properties. Source and receipt verification therefore run independently of those properties. GitHub uses its actual checked-out SHA; the live local fixture test used its own clean Git commit and did not claim to run inside GitHub Actions.

## Scope

Remote-package behavior is covered by offline contract tests; the live example has no dependencies. OIDC requires the documented GitHub environment and Snowflake service-user setup. Deployment can change object settings before a later failure, and failed model builds can leave changed relations; there is no automatic rollback.
