# Deployment decision

Researched against official Snowflake documentation on **2026-10-03**. Scope: deploying the native schema-level `DBT PROJECT` object and its source files.

## Recommendation

Use **Snowflake CLI in GitHub Actions**, with OIDC authentication and a pinned runtime. Snowflake recommends this deployment method. GitHub checks out the reviewed commit; CLI uploads its files and creates or updates the native object. A Snowflake Git repository object is not required.

| Method | Native dbt deployment? | Fit for this template |
| --- | --- | --- |
| Snowflake CLI | Yes: `snow dbt deploy` | Best fit: staging, deployment, Git metadata, and CI integration are provided. |
| SQL | Yes: `CREATE DBT PROJECT` and `ALTER DBT PROJECT … DEPLOY` | Useful when a team already manages source staging and SQL delivery. |
| Snowsight | Yes: deploy from a workspace | Useful for interactive development and initial exploration. |
| DCM Projects | No documented `DBT PROJECT` entity | Can manage supported surrounding objects, but cannot replace native dbt deployment here. |

The user’s DCM observation is correct: the [supported entity list](https://docs.snowflake.com/en/user-guide/dcm-projects/dcm-projects-supported-entities) does not include dbt projects. This conclusion concerns DCM's managed entities; a task or procedure that invokes dbt is a separate object.

Sources: [deploy dbt objects](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-deploy), [CLI CI/CD](https://docs.snowflake.com/en/developer-guide/snowflake-cli/data-pipelines/dbt-projects).

## Contract used here

- Deploy checked-out files with `snow dbt deploy`, specifying destination, target, runtime, and source metadata. Never pass `--force`: it recreates the object and can remove run history.
- Keep the native object location separate from model output settings. Generate a dedicated credentials-free `dbt_projects_profiles.yml`; Snowflake prefers that file over `profiles.yml`.
- Use one explicit role for deployment and model execution in this starter. Supply only the permissions needed in the selected database and warehouse.
- Validate the account's supported runtimes and check existing object version semantics before deployment. Read back the deployed settings afterward; validate native commit metadata when the account exposes it.
- Keep model execution optional through `--build`, since it creates or changes model relations.
- Require an existing external access integration for remote package downloads. Reject `env.yml`, `env_var()` references, and local packages in this baseline rather than infer their secrets or source layout.

Sources: [CLI deploy flags](https://docs.snowflake.com/en/developer-guide/snowflake-cli/command-reference/dbt-commands/deploy), [access control](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-access-control), [DESCRIBE metadata](https://docs.snowflake.com/en/sql-reference/sql/desc-dbt-project), [dependencies](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-dependencies).

## Versions and rollback

Pin Snowflake CLI **3.28.0**, released in September 2026. The default native runtime is **Fusion 2.0.0-preview.210**; **Core 1.11.11** is also offered. Snowflake documents Fusion as generally available despite dbt Labs' version naming. The account's `SYSTEM$SUPPORTED_DBT_VERSIONS()` result is authoritative for availability.

Sources: [CLI release](https://github.com/snowflakedb/snowflake-cli/releases/tag/v3.28.0), [supported runtimes](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-dbt-core-versions).

The `2026_06` behavior change bundle is enabled by default, and new opted-in objects use a single mutable `live` version. Existing objects can still retain legacy numbered versions until migrated. This starter detects the distinction; it does not silently migrate or replace legacy objects. Migration removes access to their numbered version history, so treat it as a separate operation.

For a live object, rollback means redeploying a known earlier Git commit. Project deployment does not roll back tables or views changed by a subsequent model build. See [the version behavior change](https://docs.snowflake.com/en/release-notes/bcr-bundles/2026_06/bcr-2362).

## Account compatibility

The live trial object reported `LIVE`, its runtime, and its default target, but omitted the documented `last_deployed_from`, `auto_compile`, and `default_writeback` fields. Treat unavailable metadata as an account capability difference; do not enable account features to fill it in automatically.

Snowflake supports downloading files from `snow://dbt/<database>.<schema>.<project>/versions/live/` with [`snow dbt copy`](https://docs.snowflake.com/en/developer-guide/snowflake-cli/command-reference/dbt-commands/copy). This provides a source-content verification path when native commit metadata is unavailable. Compare downloaded source files with the exact prepared deployment snapshot; generated runtime files can be additional output.

## Peer review

Independent research and architecture review preceded implementation. The review identified four requirements incorporated into the design:

1. CLI is the preferred option, but SQL and Snowsight must remain visible in the comparison.
2. Check live versus legacy object semantics; avoid destructive recreation and automatic migration.
3. Keep personal credentials and production destinations out of inferred project source. Restrict authenticated GitHub deployment to trusted `main` code and an explicitly configured environment.
4. Verify deployment results and do not describe the complete CLI operation as a transaction. CLI can update object properties before updating source files.

Review also confirmed that CLI uploads through a temporary stage. `CREATE STAGE` is required only for permanent stages, so it is not added just for this upload. Sources: [pinned CLI implementation](https://raw.githubusercontent.com/snowflakedb/snowflake-cli/v3.28.0/src/snowflake/cli/_plugins/dbt/manager.py), [CREATE STAGE permissions](https://docs.snowflake.com/en/sql-reference/sql/create-stage).

See [validation evidence](validation.md) for local checks, independent implementation review, and the live trial deployment and execution.
