# Inspect runs and logs

[Documentation](../index.md)

Use this guide after a native dbt execution fails, or to confirm which command ran. The wrapper reports a nonzero exit without printing potentially sensitive CLI error output.

## Set up Snowsight access

After the first deployment, configure access for the primary role you use in Snowsight. The deployment role owns the project and can monitor it. If you use another role, grant it `MONITOR` on the project and `USAGE` on its parent database and schema. The wizard saves configuration locally; it does not apply these grants.

Ask a Snowflake administrator with `MANAGE GRANTS` to run the following SQL. Replace `<YOUR_VIEWER_ROLE>` with an existing role assigned to your user, and replace the object destination with your configured database, object schema, and project:

```sql
GRANT USAGE ON DATABASE DEV_DBT_PRJ TO ROLE <YOUR_VIEWER_ROLE>;
GRANT USAGE ON SCHEMA DEV_DBT_PRJ.PROJECTS TO ROLE <YOUR_VIEWER_ROLE>;
GRANT MONITOR ON DBT PROJECT DEV_DBT_PRJ.PROJECTS.NATIVE_DBT_EXAMPLE
  TO ROLE <YOUR_VIEWER_ROLE>;

SHOW GRANTS ON DBT PROJECT DEV_DBT_PRJ.PROJECTS.NATIVE_DBT_EXAMPLE;
```

Expect a row with `privilege = MONITOR` and `grantee_name` equal to your selected viewer role. Select that role as your **primary role** in Snowsight, then open **Transformation → dbt Projects** and select the project. Check that its **DAG** and **Run History** tabs load without a privilege error.

If the error specifically names primary role `ACCOUNTADMIN` and this example object, run this targeted repair with the object owner or a role with `MANAGE GRANTS`. In a managed access schema, use the schema owner or a role with `MANAGE GRANTS`:

```sql
GRANT MONITOR ON DBT PROJECT DEV_DBT_PRJ.PROJECTS.NATIVE_DBT_EXAMPLE
  TO ROLE ACCOUNTADMIN;
```

Refresh the project page. Having `MANAGE GRANTS` lets an administrator grant access; it does not replace the project's required `MONITOR` privilege. You can also select the owning deployment role as your primary role if it is assigned to your user. Check access again if the object is dropped and recreated.

`MONITOR` permits viewing project definitions, lineage, history, and run artifacts. Executing the project requires `USAGE` on the project, and querying its model output requires separate data privileges. [Snowflake dbt access control](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-access-control) · [Grant authority](https://docs.snowflake.com/en/sql-reference/sql/grant-privilege) · [Monitoring and data access](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-best-practices).

## Find the execution

In Snowsight, open **Transformation → dbt Projects**, select the object, then its run history. The [screenshot walkthrough](../screenshots/README.md) shows this path.

Alternatively, run scoped history SQL. Replace the example database, schema, and object with your configuration:

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
| Account, runtime, or deployed-profile verification | Correct the destination or deployed settings before executing. |
| Deployment readback | Inspect the object and uploaded source; a deployment may already have changed it. |
| Model or data test | Correct the source/data/permissions, then choose [retry or a new build](run-and-retry.md#choose-retry-or-a-new-build). |
| Missing state baseline | Refresh a successful baseline and check artifact permissions in the [state guide](state-build.md). |

Neither a failed deployment nor a failed build triggers automatic rollback. Treat logs as potentially sensitive before sharing them.
