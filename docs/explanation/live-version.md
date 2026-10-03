# Why LIVE changes deployment and recovery

[Documentation](../index.md)

A native dbt object has one mutable LIVE source version under [BCR2362](https://docs.snowflake.com/en/release-notes/bcr-bundles/2026_06/bcr-2362). The behavior change is enabled by default. New opted-in objects use LIVE; existing numbered objects keep their old semantics until explicitly migrated.

## Source versions and execution history differ

The native object stores project files, while each execution creates results and logs. Moving to LIVE removes access to old numbered **source** versions. It preserves object identity, grants, task references, and **execution** history. [Migration semantics](https://docs.snowflake.com/en/sql-reference/functions/system_migrate_dbt_project).

The template checks `default_version = LIVE`. Deprecated version-name and alias columns can be null. Source files live under `snow://dbt/<database>.<schema>.<project>/versions/live/`.

## Compilation and writeback solve different problems

`auto_compile` controls deployment-time compilation. With an external access integration, the CLI also runs `deps` before compiling. Setting it to false skips those deployment-time commands. It does not request a model build.

`default_writeback` controls whether execution artifacts such as `target/` and logs are written into LIVE. This template defaults to **false**, preserving its earlier behavior; Snowflake's native default is **true**. A per-run flag overrides the template's setting. Per-query artifact archives remain available independently of writeback. [Deployment controls](https://docs.snowflake.com/en/developer-guide/snowflake-cli/command-reference/dbt-commands/deploy), [LIVE artifacts](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-live-version).

Persisted failed-run artifacts enable retry. Successful build/run artifacts provide baseline state for comparisons. Automatic compilation alone is not a qualifying baseline. Shared writeback paths can be overwritten by another execution; serialize runs that depend on that state.

## Deployment replaces files

Updating LIVE replaces the entire source directory, including generated target/log files. An old failed invocation cannot be retried from LIVE after that state is removed. Code fixes need a new deployment and build; data or permission fixes can use retry while the original state still exists. [File replacement](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-live-version).

The object location and model location are independent. Updating `DEV_DBT_PRJ.PROJECTS.NATIVE_DBT_EXAMPLE` changes its project files. A subsequent build writes relations under the configured model database/schema, such as `DEV_DBT_PRJ.ANALYTICS`.

## Git becomes the source recovery path

Rollback means deploying source from a known earlier Git revision. This template preserves the object by avoiding `--force`, then verifies source hashes and its receipt. Restoring source does not restore tables or views changed by earlier model executions.

Deployment is not an atomic rollback boundary: CLI can change object settings before a later source or verification failure. A build can change some relations before another model or test fails. The guides therefore keep migration, deployment, and execution as explicit operations.

For practical steps, use [migration](../how-to/migrate-to-live.md), [retry](../how-to/run-and-retry.md), or [state builds](../how-to/state-build.md).
