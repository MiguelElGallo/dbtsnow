# GitHub Actions setup

The deployment workflow reads `deployment/dev.json` and runs **manually from `main`**, using the GitHub environment **`dev`**. GitHub OIDC supplies a short-lived Snowflake identity; no private key or password is stored in this template.

## 1. Save the deployment settings

Run the wizard locally:

```sh
uv run python scripts/dbt_native.py wizard --source example --output deployment/dev.json
uv run python scripts/dbt_native.py deploy --config deployment/dev.json
```

The configuration records:

| Settings | Purpose |
| --- | --- |
| `account` | Expected account in canonical `ORGANIZATION-ACCOUNT` form, for example `MYORG-MYACCOUNT`. |
| `database`, `object_schema`, `project` | Native object destination. |
| `model_database`, `model_schema` | Tables and views produced by dbt. |
| `role`, `warehouse` | Explicit execution context. |
| `profile`, `target`, `dbt_version` | Native dbt profile, target, and pinned runtime. |
| `source` | Project directory, relative to the configuration file's directory. |
| `external_access_integrations` | Existing integrations for remote packages; empty for the included example. |
| `connection` | Optional local CLI connection; ignored by CI. |

Review the destination and commit the credentials-free configuration when publishing your workflow. The tracked `deployment/example.json` is a reference with placeholders; the workflow always uses `deployment/dev.json`.

Actual configuration files are ignored by Git by default. Once you have reviewed this specific account and destination, explicitly include the workflow's configuration:

```sh
git add -f deployment/dev.json
```

## 2. Prepare Snowflake

An administrator runs the following **after replacing every `<…>` placeholder**. Keep the warehouse, role, and destination consistent with the saved configuration. This example uses a dedicated development database, with `PROJECTS` for the object and `ANALYTICS` for model output.

```sql
CREATE DATABASE IF NOT EXISTS DEV_DBT_PRJ;
CREATE SCHEMA IF NOT EXISTS DEV_DBT_PRJ.PROJECTS;
CREATE SCHEMA IF NOT EXISTS DEV_DBT_PRJ.ANALYTICS;

CREATE ROLE IF NOT EXISTS DBT_DEPLOYER;
GRANT USAGE, CREATE SCHEMA ON DATABASE DEV_DBT_PRJ TO ROLE DBT_DEPLOYER;
GRANT USAGE ON SCHEMA DEV_DBT_PRJ.PROJECTS TO ROLE DBT_DEPLOYER;
GRANT CREATE DBT PROJECT ON SCHEMA DEV_DBT_PRJ.PROJECTS TO ROLE DBT_DEPLOYER;
GRANT USAGE ON SCHEMA DEV_DBT_PRJ.ANALYTICS TO ROLE DBT_DEPLOYER;
GRANT CREATE TABLE, CREATE VIEW ON SCHEMA DEV_DBT_PRJ.ANALYTICS TO ROLE DBT_DEPLOYER;
GRANT USAGE ON WAREHOUSE <YOUR_EXISTING_WAREHOUSE> TO ROLE DBT_DEPLOYER;

CREATE USER <YOUR_GITHUB_SERVICE_USER>
  TYPE = SERVICE
  WORKLOAD_IDENTITY = (
    TYPE = OIDC
    ISSUER = 'https://token.actions.githubusercontent.com'
    SUBJECT = 'repo:<OWNER>/<REPO>:environment:dev'
  )
  DEFAULT_ROLE = DBT_DEPLOYER;

GRANT ROLE DBT_DEPLOYER TO USER <YOUR_GITHUB_SERVICE_USER>;
```

Use the exact GitHub owner/repository name in the subject. The environment name must be exactly `dev`. Each Snowflake OIDC service user needs a unique subject; inspect an existing user before creating another.

The creator owns the native object and can update and monitor it. dbt issues schema-creation statements, so the example grants `CREATE SCHEMA` within the dedicated development database. For an existing object owned by another role, arrange its ownership separately. Real projects also need appropriate source-data privileges; grant `SELECT` only on their intended sources. Custom model schemas need their own permissions. Remote packages additionally need `USAGE` on the selected existing external access integration. The CLI's temporary upload stage does not require a permanent-stage creation grant.

Sources: [official OIDC action](https://github.com/snowflakedb/snowflake-actions), [dbt permissions](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-access-control), [temporary stages](https://docs.snowflake.com/en/sql-reference/sql/create-stage).

## 3. Configure GitHub

In **Settings → Environments**, create **`dev`**:

1. Restrict deployment branches to **`main`**. This is needed because an environment OIDC subject identifies the environment rather than a branch.
2. Add required reviewers if your repository supports them and your team wants a deployment approval.
3. Set these environment variables under **Secrets and variables → Actions**, or directly in the environment:

| Variable | Value |
| --- | --- |
| `SNOWFLAKE_ACCOUNT` | The same account as `account` in the saved configuration. |
| `SNOWFLAKE_USER` | The service user created above. |

Role, warehouse, and both destinations come from the configuration. The workflow uses `--temporary-connection`; it does not load your saved local connection. If Snowflake inbound network rules restrict access, arrange access for the selected runner before deployment. See [Snowflake's CI/CD tutorial](https://docs.snowflake.com/en/user-guide/tutorials/dbt-projects-on-snowflake-ci-cd-tutorial).

## 4. Run the workflow

After the workflow and reviewed configuration are available in your GitHub repository, open **Actions**, choose the native dbt deployment workflow, select **Run workflow**, and select **`main`**.

The workflow runs format checks, Ruff, ty, and unit tests before authenticating and deploying. It pins the CLI version, uses OIDC with limited GitHub permissions, and serializes deployments through concurrency control. The workflow refuses deployment from another branch; the environment branch restriction supplies a second boundary.

Leave **build** disabled to upload and compile the native project only. Enable it to run `dbt build`, which writes tables or views and runs dbt tests against the configured model destination. The workflow verifies the runtime and target, downloads the deployed source, and compares its file hashes and commit receipt with the upload. Native commit metadata is also checked when exposed by the account. A later build failure does not undo deployment or previously changed relations.

The example has no external packages and builds one view with dbt tests. Larger projects should add isolated model-build validation before production promotion. This development starter does not automatically run model builds on incoming pull requests or deploy on every push.

For rollback through GitHub, restore the desired earlier source and configuration through a reviewed PR into `main`, then run the workflow again. Its receipt records the new restore commit. Locally, you can deploy an earlier checked-out revision using the same deployment command.
