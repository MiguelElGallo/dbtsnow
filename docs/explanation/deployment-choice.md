# Why use Snowflake CLI and GitHub Actions?

[Documentation](../index.md)

Researched against official Snowflake documentation on **2026-10-03**. Scope: deploying the native schema-level `DBT PROJECT` object and its source files.

## Recommendation

Use **Snowflake CLI in GitHub Actions**, with OIDC authentication and a pinned runtime. Snowflake recommends this deployment method. GitHub checks out the reviewed commit; CLI uploads its files and creates or updates the native object. A Snowflake Git repository object is not required.

| Method | Native dbt deployment? | Fit for this template |
| --- | --- | --- |
| Snowflake CLI | Yes: `snow dbt deploy` | Best fit: staging, deployment, Git metadata, and CI integration are provided. |
| SQL | Yes: `CREATE DBT PROJECT` and `ALTER DBT PROJECT … DEPLOY` | Useful when a team already manages source staging and SQL delivery. |
| Snowsight | Yes: deploy from a workspace | Useful for interactive development and initial exploration. |
| DCM Projects | No documented `DBT PROJECT` entity | Can manage supported surrounding objects, but cannot replace native dbt deployment here. |

The [supported entity list](https://docs.snowflake.com/en/user-guide/dcm-projects/dcm-projects-supported-entities) does not include dbt projects. This conclusion concerns DCM's managed entities; a task or procedure that invokes dbt is a separate object.

Sources: [deploy dbt objects](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-deploy), [CLI CI/CD](https://docs.snowflake.com/en/developer-guide/snowflake-cli/data-pipelines/dbt-projects).

## Why the template makes these choices

The checked-out files are the deployment source. GitHub supplies the reviewed commit; the generated receipt and downloaded hashes connect that commit to what Snowflake received. Native commit metadata adds evidence when the account exposes it.

Preserving the existing object avoids losing its identity and run history. That is why deployment omits `--force` and refuses numbered objects until a separate migration is reviewed. The CLI can update object properties before source delivery finishes, so successful verification matters beyond a successful upload.

Separate object and model destinations make write scope visible. A credentials-free native profile carries the model context, while the selected CLI connection or OIDC identity supplies authentication. Snowflake prefers `dbt_projects_profiles.yml` over personal `profiles.yml`.

Independent project administrator and operator roles separate delivering source from changing tables and views. Corporate deployment disables automatic compilation and uses its own identity; the operator performs compilation/build through a separate job. See [role separation](role-separation.md). Remote packages need an existing external access integration; explicit handling keeps package access and native environment settings from being inferred from a developer's personal secrets.

Sources: [CLI deploy flags](https://docs.snowflake.com/en/developer-guide/snowflake-cli/command-reference/dbt-commands/deploy), [access control](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-access-control), [DESCRIBE metadata](https://docs.snowflake.com/en/sql-reference/sql/desc-dbt-project), [dependencies](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-dependencies).

## Versions and rollback

Pin Snowflake CLI **3.28.0**, released in September 2026. The default native runtime is **Fusion 2.0.0-preview.210**; **Core 1.11.11** is also offered. Snowflake documents Fusion as generally available despite dbt Labs' version naming. The account's `SYSTEM$SUPPORTED_DBT_VERSIONS()` result is authoritative for availability.

Sources: [CLI release](https://github.com/snowflakedb/snowflake-cli/releases/tag/v3.28.0), [supported runtimes](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-dbt-core-versions).

The `2026_06` behavior change bundle is enabled by default, and new opted-in objects use a single mutable `live` version. Existing objects can still retain legacy numbered versions until migrated. This starter detects the distinction through `default_version`, and offers an explicit, separate `migrate` command for the configured object. Deployment never silently migrates or replaces legacy objects. Migration removes access to numbered source history while preserving execution history. See the [LIVE explanation](live-version.md).

For a live object, rollback means redeploying a known earlier Git commit. Project deployment does not roll back tables or views changed by a subsequent model build. See [the version behavior change](https://docs.snowflake.com/en/release-notes/bcr-bundles/2026_06/bcr-2362).

## Account compatibility

The live trial object reported `LIVE`, its runtime, and its default target, but omitted the documented `last_deployed_from`, `auto_compile`, and `default_writeback` fields. Treat unavailable metadata as an account capability difference; do not enable account features to fill it in automatically.

Snowflake supports downloading files from `snow://dbt/<database>.<schema>.<project>/versions/live/` with [`snow dbt copy`](https://docs.snowflake.com/en/developer-guide/snowflake-cli/command-reference/dbt-commands/copy). This provides a source-content verification path when native commit metadata is unavailable. Compare downloaded source files with the exact prepared deployment snapshot; generated runtime files can be additional output.

## Evidence and limits

CLI uploads through a temporary stage. The template therefore does not add permanent-stage creation privileges just for the upload. Sources: [pinned CLI implementation](https://raw.githubusercontent.com/snowflakedb/snowflake-cli/v3.28.0/src/snowflake/cli/_plugins/dbt/manager.py), [CREATE STAGE permissions](https://docs.snowflake.com/en/sql-reference/sql/create-stage).

The [validation record](../validation.md) describes independent reviews and the live trial tests. The [documentation review](../documentation-review.md) records the separate architecture, clarity, and source-accuracy passes.
