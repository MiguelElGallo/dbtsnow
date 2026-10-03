# Deploy your first project

[Documentation](../index.md) · Previous: [Preview the example](preview-the-example.md)

You will deploy the example into `DEV_DBT_PRJ`, build one view, and verify its row. This lesson uses `PROJECTS` for the native object, `ANALYTICS` for model output, and target `dev`.

## Prepare your connection

Complete the [preview lesson](preview-the-example.md) first. You also need a Snowflake account and an existing warehouse. The examples use `COMPUTE_WH`; substitute your warehouse if its name differs.

Install the pinned CLI:

```sh
uv tool install snowflake-cli==3.28.0
snow --version
```

The version must be `3.28.0`. Set up a saved connection using [Snowflake's connection guide](https://docs.snowflake.com/en/developer-guide/snowflake-cli/connecting/connect), then test it. This lesson calls the connection `snowflake_trial`:

```sh
snow connection test --connection snowflake_trial
```

Finish any browser sign-in requested by your connection. Use your own account identifier in `ORGANIZATION-ACCOUNT` form when the wizard asks for it.

## Prepare the development database

Ask a Snowflake administrator to run this SQL. Replace `<YOUR_USER>` with your Snowflake user name and `COMPUTE_WH` with your existing warehouse. These grants stay within the development database and that warehouse.

```sql
CREATE DATABASE IF NOT EXISTS DEV_DBT_PRJ;
CREATE SCHEMA IF NOT EXISTS DEV_DBT_PRJ.PROJECTS;
CREATE SCHEMA IF NOT EXISTS DEV_DBT_PRJ.ANALYTICS;
CREATE ROLE IF NOT EXISTS DEV_DBT_PRJ_DEPLOYER;

GRANT USAGE, CREATE SCHEMA ON DATABASE DEV_DBT_PRJ TO ROLE DEV_DBT_PRJ_DEPLOYER;
GRANT USAGE ON SCHEMA DEV_DBT_PRJ.PROJECTS TO ROLE DEV_DBT_PRJ_DEPLOYER;
GRANT CREATE DBT PROJECT ON SCHEMA DEV_DBT_PRJ.PROJECTS TO ROLE DEV_DBT_PRJ_DEPLOYER;
GRANT USAGE ON SCHEMA DEV_DBT_PRJ.ANALYTICS TO ROLE DEV_DBT_PRJ_DEPLOYER;
GRANT CREATE TABLE, CREATE VIEW ON SCHEMA DEV_DBT_PRJ.ANALYTICS TO ROLE DEV_DBT_PRJ_DEPLOYER;
GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE DEV_DBT_PRJ_DEPLOYER;
GRANT ROLE DEV_DBT_PRJ_DEPLOYER TO USER <YOUR_USER>;
```

The example needs no source tables or external packages. Real projects need permissions on their own sources. [Snowflake access-control reference](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-access-control).

## Save your settings

```sh
uv run python scripts/dbt_native.py wizard --source example --output deployment/dev.json
```

The wizard reads literal project/profile settings and, if selected, your saved connection. Press Enter to accept a suggested value; otherwise type the value you want.

Use these choices for this lesson:

| Prompt | Answer |
| --- | --- |
| Local connection | `snowflake_trial` |
| Account | Your `ORGANIZATION-ACCOUNT` identifier |
| Database | `DEV_DBT_PRJ` |
| Object schema | `PROJECTS` |
| Project | `native_dbt_example` |
| Role | `DEV_DBT_PRJ_DEPLOYER` |
| Warehouse | `COMPUTE_WH`, or your existing warehouse |
| Model database / schema | `DEV_DBT_PRJ` / `ANALYTICS` |
| Profile / target | `native_dbt_example` / `dev` |
| dbt version | `2.0.0-preview.210` |
| External access integrations | Leave blank |
| Persist run artifacts in LIVE | `no` |
| Compile during deployment | `yes` |

You should see `Saved .../deployment/dev.json`. The wizard saves a local file without connecting to Snowflake. It refuses to overwrite an existing configuration; reuse that file or choose a new output name.

## Check the destination

```sh
uv run python scripts/dbt_native.py deploy --config deployment/dev.json
```

Confirm the account, role, warehouse, native object `DEV_DBT_PRJ.PROJECTS.native_dbt_example`, and model destination `DEV_DBT_PRJ.ANALYTICS`. This is still a preview.

## Deploy the object

```sh
uv run python scripts/dbt_native.py deploy --config deployment/dev.json --apply
```

The CLI uploads the files and compiles the project. The wrapper downloads the deployed source and compares it with the upload. On success, you should see:

```text
Verified deployment: DEV_DBT_PRJ.PROJECTS.native_dbt_example, runtime 2.0.0-preview.210, target dev, version LIVE, source hashes match.
```

The account must support the selected runtime and LIVE objects. The wrapper stops before replacing an existing numbered object; use the separate [migration guide](../how-to/migrate-to-live.md) for that situation.

## Complete Snowsight access setup

Select `DEV_DBT_PRJ_DEPLOYER` as your primary role in Snowsight to view the project it owns. If you plan to view it with a different primary role, including `ACCOUNTADMIN`, have an administrator [configure viewer access](../how-to/inspect-runs.md#set-up-snowsight-access) now: grant `MONITOR` on the deployed project and `USAGE` on its parent database and schema to that role.

Open **Transformation → dbt Projects**, select `NATIVE_DBT_EXAMPLE` in `DEV_DBT_PRJ.PROJECTS`, and check that **DAG** and **Run History** load without a privilege error. If you configured a separate viewer role, verify its `MONITOR` grant with the SQL in the access guide. Project ownership belongs to the deployment role; using `ACCOUNTADMIN` in the browser does not automatically satisfy Snowsight's `MONITOR` requirement.

## Build and check the view

```sh
uv run python scripts/dbt_native.py run --config deployment/dev.json --command build --apply
```

This step writes model relations in `ANALYTICS`. Expect one successful model and two passing tests, followed by `dbt build completed successfully.`

In Snowsight, run:

```sql
USE ROLE DEV_DBT_PRJ_DEPLOYER;
USE WAREHOUSE COMPUTE_WH;
SELECT ID, MESSAGE FROM DEV_DBT_PRJ.ANALYTICS.DEPLOYMENT_CHECK;
```

| ID | MESSAGE |
| --- | --- |
| 1 | Native dbt deployment works |

You have deployed a native dbt object and built its model. Find the object under **Transformation → dbt Projects**, or [inspect its execution history and logs](../how-to/inspect-runs.md).

Next, [automate deployment with GitHub Actions](../how-to/github-actions.md). If a step failed, use the [failure guide](../how-to/inspect-runs.md) before repeating it.
