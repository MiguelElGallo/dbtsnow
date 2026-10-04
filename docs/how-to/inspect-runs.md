---
icon: lucide/logs
---

# Operator: inspect runs and logs

[Documentation](../index.md)

Find a native dbt execution, inspect its output, and route the fix to the responsible owner. When the wrapper exits with an error, it suppresses potentially sensitive CLI error output; inspect the Snowflake run for details.

## Set up Snowsight access

The project administrator completes [operator project access](project-admin.md#grant-operator-access). The Snowflake administrator supplies parent database/schema access and assigns a separate human viewer when needed through [administrator setup](admin-setup.md#complete-project-and-viewer-access-after-deployment).

Log in as an approved human user and select the operator/viewer role as the **primary role**. Open **Transformation → dbt Projects** and select the project. Check that its **DAG** and **Run History** open. Service users are for CLI access; use a human login for Snowsight.

If an access error names `ACCOUNTADMIN`, that selected primary role needs explicit project `MONITOR`. Ask the administrator for the targeted viewer grant. In a managed-access schema, the schema owner or a grant administrator must apply it.

`MONITOR` permits viewing project details/history and retrieving recent artifacts. Execution needs project `USAGE`, and querying model output needs separate data privileges. See [Snowflake dbt access control](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-access-control).

## Find the execution

In the project's **Run History**:

1. Select the run matching the execution time and command.
2. Open **Query Details** and check its query ID and status.
3. Inspect the model/test statuses and **dbt Output** to find the failing node or error.

Alternatively, run this scoped history SQL using the operator role. Replace the database, schema, and object with your configuration:

```sql
SELECT QUERY_ID, QUERY_START_TIME, COMMAND, ARGS, STATE, ERROR_MESSAGE
FROM TABLE(DBT_CORPORATE_DEV.INFORMATION_SCHEMA.DBT_PROJECT_EXECUTION_HISTORY(
  DATABASE => 'DBT_CORPORATE_DEV', SCHEMA => 'PROJECTS',
  OBJECT_NAME => 'NATIVE_DBT_EXAMPLE'))
ORDER BY QUERY_START_TIME DESC LIMIT 10;
```

Find the row by time and command. `SUCCESS` confirms completion; `HANDLED_ERROR` records a dbt execution failure. The owning role, or a role with project `MONITOR` and parent database/schema access, can inspect these full history columns. Function arguments filter history before its result limit. See the [history reference](https://docs.snowflake.com/en/sql-reference/functions/dbt_project_execution_history).

## Read its log

Copy the execution's `QUERY_ID` into:

```sql
SELECT SYSTEM$GET_DBT_LOG('<QUERY_ID>');
```

The role needs parent database/schema access and one of project `OWNERSHIP`, `USAGE`, or `MONITOR`. Logs are available after completion; failures before file upload may have no log. Use an execution query ID, because deployment IDs are not supported. See the [log reference](https://docs.snowflake.com/en/sql-reference/functions/system_get_dbt_log).

## Resolve the failure

| What failed | Next step |
| --- | --- |
| Local configuration or preview | Check the [configuration reference](../reference/configuration.md). Preview made no Snowflake change. |
| Account, identity, runtime, or profile verification | Confirm the selected operator config; have the project administrator correct deployed settings when needed. |
| Deployment readback | Hand source inspection to the project administrator; deployment may already have changed it. |
| Model or data test | Route source fixes to the project administrator and data/access fixes to their owner, then choose [retry or a new build](run-and-retry.md#choose-retry-or-a-new-build). |
| Missing state baseline | Refresh a successful baseline and check artifact permissions in the [state guide](state-build.md). |

Inspect changes before another attempt; failures do not trigger automatic rollback. Review logs for sensitive content before sharing them.
