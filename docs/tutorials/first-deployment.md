---
icon: lucide/rocket
---

# Deploy your first project through three responsibilities

[Documentation](../index.md) · Previous: [Preview the example](preview-the-example.md)

In this lesson, we will create a development database, deploy one native project, and build a view containing one row. A Snowflake administrator prepares access. Two new service users then deploy and build through separate authenticated CLI connections.

## Before you start

Complete [the preview lesson](preview-the-example.md) and run the commands below from the repository root. You also need:

- OpenSSL and the pinned Snowflake CLI installed below.
- An approved administrator connection named `snowflake_admin` that can use `ACCOUNTADMIN` in your selected account. [Required administrator capabilities](../how-to/admin-setup.md#administrator-prerequisites).
- An existing approved warehouse named `COMPUTE_WH` in that account.
- Unused database `DBT_CORPORATE_DEV`, roles `DBT_PROJECT_ADMIN` and `DBT_OPERATOR`, and users `DBT_PROJECT_ADMIN_SVC` and `DBT_OPERATOR_SVC`.
- No existing `deployment/dev.json`, `.local/dbt-corporate-keys` directory, or CLI connections named `dbt_project_admin` and `dbt_operator`.

This is a fresh-resource exercise. To onboard existing corporate resources, use [administrator setup](../how-to/admin-setup.md#use-existing-corporate-resources).

```sh
uv tool install snowflake-cli==3.28.0
snow --version
```

The version output should report `3.28.0`.

## Administrator: confirm the selected account

Use the approved administrator connection for this read-only check:

```sh
snow sql --connection snowflake_admin --role ACCOUNTADMIN --secondary-roles NONE \
  --query "SELECT CURRENT_ORGANIZATION_NAME() || '-' || CURRENT_ACCOUNT_NAME() AS ACCOUNT, CURRENT_USER() AS USER_NAME, CURRENT_ROLE() AS ROLE_NAME, CURRENT_SECONDARY_ROLES() AS SECONDARY_ROLES"
```

Confirm that `ACCOUNT` is the approved `ORGANIZATION-ACCOUNT`, `ROLE_NAME` is `ACCOUNTADMIN`, and no secondary roles are active. Keep the account value for the next step. If the connection is not ready, complete your organization's administrator authentication setup before continuing.

## Prepare the shared configuration

Create a new local copy without replacing an existing file:

```sh
test ! -e deployment/dev.json && cp deployment/example.json deployment/dev.json
```

Edit this complete copied JSON. Set `account` to the account just checked, and set both `database` and `model_database` to `DBT_CORPORATE_DEV`. Keep `warehouse` as `COMPUTE_WH`. Retain the following settings in the copied file:

```json
{
  "role": "DBT_OPERATOR",
  "deployment_role": "DBT_PROJECT_ADMIN",
  "operator_user": "DBT_OPERATOR_SVC",
  "deployment_user": "DBT_PROJECT_ADMIN_SVC",
  "connection": null,
  "deployment_connection": null,
  "auto_compile": false
}
```

This is a fragment of the copied configuration. Keep its other fields: object schema `PROJECTS`, model schema `ANALYTICS`, project `NATIVE_DBT_EXAMPLE`, profile `native_dbt_example`, target `dev`, and runtime `2.0.0`.

```sh
uv run python scripts/dbt_native.py deploy --config deployment/dev.json
```

Check the plan: native object `DBT_CORPORATE_DEV.PROJECTS.NATIVE_DBT_EXAMPLE`, model destination `DBT_CORPORATE_DEV.ANALYTICS`, deployment role `DBT_PROJECT_ADMIN`, and operator role `DBT_OPERATOR`. The final line confirms no connection was made.

## Administrator: create two test logins

Generate the two key pairs using [the fresh key-directory recipe](../how-to/admin-setup.md#create-dedicated-test-credentials). It creates `.local/dbt-corporate-keys` and keeps each user's private key separate.

Preview the complete setup:

```sh
uv run python scripts/dbt_admin.py bootstrap \
  --config deployment/dev.json \
  --admin-connection snowflake_admin \
  --admin-role ACCOUNTADMIN \
  --project-admin-user DBT_PROJECT_ADMIN_SVC \
  --project-admin-public-key-file .local/dbt-corporate-keys/project-admin.pub.pem \
  --operator-user DBT_OPERATOR_SVC \
  --operator-public-key-file .local/dbt-corporate-keys/operator.pub.pem
```

Check the account, the new database and schemas, both independent roles, and both service users. The operator gets model-schema privileges; neither delegated role gets account administration. The final line confirms no Snowflake connection.

Apply the reviewed setup:

```sh
uv run python scripts/dbt_admin.py bootstrap \
  --config deployment/dev.json \
  --admin-connection snowflake_admin \
  --admin-role ACCOUNTADMIN \
  --project-admin-user DBT_PROJECT_ADMIN_SVC \
  --project-admin-public-key-file .local/dbt-corporate-keys/project-admin.pub.pem \
  --operator-user DBT_OPERATOR_SVC \
  --operator-public-key-file .local/dbt-corporate-keys/operator.pub.pem \
  --apply
```

Wait for `Verified administrator setup`. It confirms the fresh resources and identity assignments; no project has been deployed or model built yet. If setup fails, inspect the error and partial state with the administrator before continuing. [Setup and readback](../how-to/admin-setup.md#apply-and-read-back).

## Authenticate as each new user

Replace `MYORG-MYACCOUNT` in both commands with the same checked account:

```sh
snow connection add --connection-name dbt_project_admin \
  --account MYORG-MYACCOUNT --user DBT_PROJECT_ADMIN_SVC \
  --role DBT_PROJECT_ADMIN --warehouse COMPUTE_WH \
  --authenticator SNOWFLAKE_JWT --private-key .local/dbt-corporate-keys/project-admin.p8 \
  --secondary-roles NONE --no-interactive
snow connection add --connection-name dbt_operator \
  --account MYORG-MYACCOUNT --user DBT_OPERATOR_SVC \
  --role DBT_OPERATOR --warehouse COMPUTE_WH \
  --authenticator SNOWFLAKE_JWT --private-key .local/dbt-corporate-keys/operator.p8 \
  --secondary-roles NONE --no-interactive
```

Set `deployment_connection` to `dbt_project_admin` and `connection` to `dbt_operator` in `deployment/dev.json`. Keep both expected usernames.

Check each login through its own connection:

```sh
snow sql --connection dbt_project_admin --secondary-roles NONE \
  --query 'SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_SECONDARY_ROLES()'
snow sql --connection dbt_operator --secondary-roles NONE \
  --query 'SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_SECONDARY_ROLES()'
```

The first result must name `DBT_PROJECT_ADMIN_SVC` and `DBT_PROJECT_ADMIN`; the second must name `DBT_OPERATOR_SVC` and `DBT_OPERATOR`. Both must have no active secondary roles. We now have two working logins rather than an administrator switching roles.

## Project administrator: deploy source

```sh
uv run python scripts/dbt_native.py deploy --config deployment/dev.json
uv run python scripts/dbt_native.py deploy --config deployment/dev.json --apply
```

The applied command uses the project administrator connection. It skips compilation and verifies the uploaded source. Look for:

```text
Verified deployment: DBT_CORPORATE_DEV.PROJECTS.NATIVE_DBT_EXAMPLE, runtime 2.0.0, target dev, version LIVE, source hashes match.
```

Hand off access to the operator:

```sh
uv run python scripts/dbt_native.py project-access --config deployment/dev.json
uv run python scripts/dbt_native.py project-access --config deployment/dev.json --apply
```

The final message confirms that `DBT_OPERATOR` has `USAGE` and `MONITOR` on this project. The operator is now ready to execute it.

## Operator: build and read the view

```sh
uv run python scripts/dbt_native.py run --config deployment/dev.json --command build
uv run python scripts/dbt_native.py run --config deployment/dev.json --command build --apply
```

This command uses the operator connection. Expect one successful model, two passing tests, and `dbt build completed successfully.` The model creates `DEPLOYMENT_CHECK` in `DBT_CORPORATE_DEV.ANALYTICS`.

Read its row through the same operator login:

```sh
snow sql --connection dbt_operator --secondary-roles NONE \
  --query 'SELECT ID, MESSAGE FROM DBT_CORPORATE_DEV.ANALYTICS.DEPLOYMENT_CHECK'
```

| ID | MESSAGE |
| --- | --- |
| 1 | Native dbt deployment works |

We have completed the administrator-to-project-administrator-to-operator handoff and read the model's output. Next, [inspect a run](../how-to/inspect-runs.md) or [configure the two GitHub workflows](../how-to/github-actions.md). For another project, use the task guides for [administrator setup](../how-to/admin-setup.md), [source deployment](../how-to/project-admin.md), and [build/retry](../how-to/run-and-retry.md).
