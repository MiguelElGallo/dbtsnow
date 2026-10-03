# Operator: inspect runs and logs

[Documentation](../index.md)

Use this guide after a native dbt execution fails, or to confirm which command ran. The wrapper reports a nonzero exit without printing potentially sensitive CLI error output.

## Set up Snowsight access

The project administrator first completes [operator project access](project-admin.md#grant-operator-access), granting the configured operator `USAGE` and `MONITOR` on the exact project. The Snowflake administrator supplies parent database/schema and any separate human viewer assignment in [administrator setup](admin-setup.md#complete-project-and-viewer-access-after-deployment).

For a human Snowsight login, select the intended operator/viewer role as the **primary role**, then open **Transformation → dbt Projects** and check the project **DAG** and **Run History**. A CLI service user cannot replace this human-browser acceptance check.

If the error names `ACCOUNTADMIN`, that primary role also needs explicit project `MONITOR`. Follow the targeted administrator grant path; using a grant-management role does not automatically satisfy Snowsight viewing. Managed schemas require the schema owner or grant administrator for object grants. Do not widen operator permissions to resolve a browser-role mismatch.

`MONITOR` permits viewing project details/history and retrieving recent artifacts. Execution requires project `USAGE`; querying model output requires separate data privileges. [Snowflake dbt access control](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-access-control).

## Find the execution

In Snowsight, open **Transformation → dbt Projects**, select the object, then its run history. The [screenshot walkthrough](../screenshots/README.md) shows this path.

Alternatively, run scoped history SQL using the operator connection/role. Replace the example database, schema, and object with your configuration:

```sql
SELECT QUERY_ID, QUERY_START_TIME, COMMAND, ARGS, STATE, ERROR_MESSAGE
FROM TABLE(DEV_DBT_PRJ.INFORMATION_SCHEMA.DBT_PROJECT_EXECUTION_HISTORY(
  DATABASE => 'DEV_DBT_PRJ', SCHEMA => 'PROJECTS',
  OBJECT_NAME => 'NATIVE_DBT_EXAMPLE'))
ORDER BY QUERY_START_TIME DESC LIMIT 10;
```

Find the execution by time and command. `SUCCESS` confirms completion; `HANDLED_ERROR` contains native failure details. Use the owning role, or have its owner grant `MONITOR` on the object plus the required parent database/schema access to inspect these full history columns. Function arguments filter the history before its result limit. [History reference](https://docs.snowflake.com/en/sql-reference/functions/dbt_project_execution_history).

## Read its log

Copy the chosen `QUERY_ID` into:

```sql
SELECT SYSTEM$GET_DBT_LOG('<QUERY_ID>');
```

Use an owning role, or a role with the required object and parent database/schema access. The log function accepts `OWNERSHIP`, `USAGE`, or `MONITOR` on the object. Logs are available after completion and may be missing when execution fails before files are uploaded. Deployment query IDs are not supported by this function. [Log reference](https://docs.snowflake.com/en/sql-reference/functions/system_get_dbt_log).

## Resolve the failure

| What failed | Next step |
| --- | --- |
| Local configuration or preview | Check the error against the [configuration reference](../reference/configuration.md); no Snowflake write occurred. |
| Account, identity, runtime, or deployed-profile verification | Confirm the selected operator config; have the project administrator correct deployed settings if needed. |
| Deployment readback | Hand source inspection to the project administrator; a deployment may already have changed it. |
| Model or data test | Route code to project administration and data/access to the responsible owner, then choose [retry or a new build](run-and-retry.md#choose-retry-or-a-new-build). |
| Missing state baseline | Refresh a successful baseline and check artifact permissions in the [state guide](state-build.md). |

Neither a failed deployment nor a failed build triggers automatic rollback. Treat logs as potentially sensitive before sharing them.
