# Validation

Validated on **2026-10-03**. Research and the implementation plan were reviewed independently before coding; separate implementation and test reviews followed.

## Local checks

- Ruff lint and formatting: pass.
- ty type checks: pass.
- **68 unit tests pass**, covering wizard inference, separate destinations, credential exclusion, paths and symlinks, package requirements, migration and LIVE metadata, account/runtime/profile drift, Git provenance, source readback, compilation/writeback controls, state artifacts, Core/Fusion retry, freshness, and failure boundaries.
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

## BCR2362 verification

Independent plan and implementation reviews covered migration, mutable profile destinations, artifact persistence, state selection, runtime-specific retry behavior, and quoted GitHub inputs. See the [usage guide](live-version.md).

The existing trial object already reports `default_version = LIVE`, with nullable deprecated version labels. Applying `migrate` correctly returned a no-op. Legacy migration, metadata preservation, server failure, and invalid readback are covered offline; no object was demigrated and no account bundle was changed to manufacture a legacy fixture.

A native build with explicit writeback succeeded (`01c77cad-0000-7510-0000-484500034a16`). Downloaded `target/manifest.json` and `target/run_results.json` were valid, with one successful model and two passing tests. State compilation imported a fixed last-successful-build artifact path and correctly selected zero models because the source was unchanged (`01c77cae-0000-7510-0000-484500034ad6`). The final wrapper also passed this check after remote project/profile destination validation was added.

A separate `DEV_DBT_PRJ.PROJECTS.BCR2362_CHECK` fixture tested actual failures and recovery using Fusion `2.0.0-preview.210`. Its only source is the dedicated `DEV_DBT_PRJ.ANALYTICS.BCR2362_CONTROL` table; source timestamps are stored as UTC. The main example was not redeployed for these tests.

| Fixture check | Execution history evidence |
| --- | --- |
| Deliberately fail a not-null test with one null row | `01c77cbb-0000-7510-0000-484500034e5a`, `HANDLED_ERROR` |
| Repair that row and run wrapper retry without redeploying | `01c77cbc-0000-7510-0000-484500034eca`, `SUCCESS`; only the failed test was retried |
| Source freshness with a current UTC timestamp | `01c77cba-0000-7510-0000-484500034db6`, `SUCCESS` |
| Source freshness with a deliberately four-hour-old timestamp | `01c77cba-0000-7510-0000-484500034e0a`, `HANDLED_ERROR` |

Downloaded retry artifacts contained only the previously failed test, now passing with zero failures. The archived freshness `sources.json` reported `Pass` with an age of 22 seconds, despite `--no-writeback`; this confirms per-query artifacts remain accessible independently of LIVE persistence.

The fixture was restored to a non-null row and fresh timestamp. Both negative cases returned a nonzero wrapper exit, with native error details retained in scoped execution history. Evidence is ignored under `.local/bcr2362-fixture/`.

Fusion artifacts omit the target name, so retry supplies explicit target/profile flags after verifying the deployed destination. Core inherits these values and requires compatible recorded arguments; Core retry is covered offline. On this pinned Fusion preview, retry after an already successful invocation returns an error saying there are no failed nodes, rather than a successful no-op.

The GitHub deployment workflow passes local `actionlint`. Cloud deployment through GitHub OIDC has not been dispatched; live tests used the authorized local OAuth connection. The separate **Check template** workflow validates the code offline on pushes and pull requests.

## Repository skill checks

The three [repository skills](how-to/use-agent-skills.md) passed skill-creator
frontmatter validation, UI metadata checks, and local Markdown link checks on
2026-10-03. Independent review checked routing, source accuracy, and guide clarity;
its wording suggestions were incorporated.

Fresh agents tried the skills in an isolated copy of the checkout:

| Trial | Observed result |
| --- | --- |
| Deploy from a nested working directory | Found the selected root and produced the offline example plan. |
| Select an invalid checkout | Stopped without switching repositories or running deployment. |
| Retry a failed build without writeback | Explained missing retry state and previewed a new build without executing it. |
| Retry Core artifacts with a different target | Rejected the mismatch in an offline fixture; no native execution occurred. |
| Locate and test Core retry verification | Found implementation, regression coverage, and canonical docs; the focused regression passed. |

The existing 68 tests, Ruff, formatting, ty, and sample preview also passed after
the skill additions. These trials used an installed Python environment and
explicit skill files; they did not test automatic discovery across clients,
OIDC, or a new cloud deployment.

## Scope

Remote-package behavior is covered by offline contract tests; the live example has no dependencies. OIDC requires the documented GitHub environment and Snowflake service-user setup. Deployment can change object settings before a later failure, and failed model builds can leave changed relations; there is no automatic rollback.
