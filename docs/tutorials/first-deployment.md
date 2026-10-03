# Deploy your first project through three responsibilities

[Documentation](../index.md) · Previous: [Preview the example](preview-the-example.md)

This lesson provisions a fresh development database, deploys one native project, and builds one view. The administrator performs setup; two dedicated service users demonstrate project administration and operation through separate authenticated CLI sessions.

## Prepare locally

Complete the preview lesson. Use a new output filename if `deployment/dev.json` already exists; keep any existing selected configuration. Install the pinned CLI and use an existing warehouse approved for the test:

```sh
uv tool install snowflake-cli==3.28.0
snow --version
cp deployment/example.json deployment/dev.json
```

Edit the copied, ignored JSON. Set `account` to your actual `ORGANIZATION-ACCOUNT`, `database` and `model_database` to a **new** database such as `DBT_CORPORATE_DEV`, and `warehouse` to your existing warehouse. Use fresh delegated role and user names if the example names already exist. Retain these role settings:

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

This fragment shows fields in the complete copied configuration; it is not a standalone config. Keep `PROJECTS` as the object schema, `ANALYTICS` as model schema, `NATIVE_DBT_EXAMPLE` as the project, and `native_dbt_example` / `dev` as profile/target. The copied configuration pins runtime `2.0.0`; runtime choices come from [configuration](../reference/configuration.md).

Preview the agreed destination:

```sh
uv run python scripts/dbt_native.py deploy --config deployment/dev.json
```

The output should distinguish deployment role `DBT_PROJECT_ADMIN` from operator/profile role `DBT_OPERATOR`. No Snowflake connection is made.

## Administrator: provision the handoff

An administrator follows [administrator setup](../how-to/admin-setup.md#create-dedicated-test-credentials) to generate two separate keys and preview fresh-resource setup. Use the configured usernames:

```sh
uv run python scripts/dbt_admin.py bootstrap \
  --config deployment/dev.json \
  --admin-connection snowflake_admin \
  --admin-role ACCOUNTADMIN \
  --project-admin-user DBT_PROJECT_ADMIN_SVC \
  --project-admin-public-key-file .local/keys/project-admin.pub.pem \
  --operator-user DBT_OPERATOR_SVC \
  --operator-public-key-file .local/keys/operator.pub.pem
```

Review the preview, then append `--apply` to that command. The administrator creates databases/schemas, independent custom roles, and two `TYPE = SERVICE` users, each assigned its respective role. The helper refuses resource collisions before writes. Inspect the readback before continuing.

For an existing corporate database or approved human users, use the [reviewed administrator SQL path](../how-to/admin-setup.md#use-existing-corporate-resources) instead. This tutorial's fresh-resource helper does not adopt an existing database or replace existing credentials.

## Authenticate as each new user

Create two named CLI connections with the private keys generated locally. Replace `MYORG-MYACCOUNT` and `COMPUTE_WH` with the same values in your config:

```sh
snow connection add --connection-name dbt_project_admin \
  --account MYORG-MYACCOUNT --user DBT_PROJECT_ADMIN_SVC \
  --role DBT_PROJECT_ADMIN --warehouse COMPUTE_WH \
  --authenticator SNOWFLAKE_JWT --private-key .local/keys/project-admin.p8 \
  --secondary-roles NONE --no-interactive
snow connection add --connection-name dbt_operator \
  --account MYORG-MYACCOUNT --user DBT_OPERATOR_SVC \
  --role DBT_OPERATOR --warehouse COMPUTE_WH \
  --authenticator SNOWFLAKE_JWT --private-key .local/keys/operator.p8 \
  --secondary-roles NONE --no-interactive
```

Set `deployment_connection` to `dbt_project_admin` and `connection` to `dbt_operator` in `deployment/dev.json`. Keep the two expected usernames. The generated native profile contains no authentication credentials.

Check each login with its own connection:

```sh
snow sql --connection dbt_project_admin --secondary-roles NONE \
  --query 'SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_SECONDARY_ROLES()'
snow sql --connection dbt_operator --secondary-roles NONE \
  --query 'SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_SECONDARY_ROLES()'
```

Expect distinct configured users, their respective roles, and no active secondary roles. The wrapper repeats the identity checks when applying. Switching an administrator's role would not prove these new users can authenticate.

## Project administrator: deploy source

```sh
uv run python scripts/dbt_native.py deploy --config deployment/dev.json
uv run python scripts/dbt_native.py deploy --config deployment/dev.json --apply
```

Deployment uses the project administrator connection. It skips compilation, owns the new object, downloads the deployed source, and verifies source hashes and settings. Expect a `Verified deployment:` message for the configured project and LIVE version.

Now hand off project access:

```sh
uv run python scripts/dbt_native.py project-access --config deployment/dev.json
uv run python scripts/dbt_native.py project-access --config deployment/dev.json --apply
```

Readback confirms `USAGE` and `MONITOR` for `DBT_OPERATOR` on this exact project. The bootstrap creates regular schemas so the object owner can grant this access. Existing managed-access schemas require the administrator grant path.

## Operator: build and check the result

```sh
uv run python scripts/dbt_native.py run --config deployment/dev.json --command build
uv run python scripts/dbt_native.py run --config deployment/dev.json --command build --apply
```

This command uses the operator connection and profile role. It writes the `DEPLOYMENT_CHECK` view in the configured `ANALYTICS` schema and runs two tests. Expect one successful model, two passing tests, and `dbt build completed successfully.`

If the chosen runtime requires database-level schema creation despite precreated schemas, stop and have the administrator review the [explicit additional grant](../how-to/admin-setup.md#use-existing-corporate-resources). The operator should not solve the failure by acquiring an administrator role.

For the example database above, verify the row using the operator connection:

```sh
snow sql --connection dbt_operator --secondary-roles NONE \
  --query 'SELECT ID, MESSAGE FROM DBT_CORPORATE_DEV.ANALYTICS.DEPLOYMENT_CHECK'
```

| ID | MESSAGE |
| --- | --- |
| 1 | Native dbt deployment works |

Continue with [run history and logs](../how-to/inspect-runs.md) or [retry](../how-to/run-and-retry.md). Source changes return to the project administrator; data or access changes return to the appropriate administrator.

## Verify the boundaries

Use the dedicated operator connection to check that this user cannot create a database, grant account privileges, or update the project source. Use the project administrator connection to check that it cannot execute a model build through the operator profile. These negative tests should fail with access-control errors; run them only in the isolated tutorial resources and inspect any unexpected success.

Service users authenticate through CLI; they do not provide a human Snowsight sign-in. For browser acceptance, have the administrator assign an approved human user the intended viewer/operator role, select that **primary role**, and verify project DAG/history separately. [Viewer access](../how-to/admin-setup.md#complete-project-and-viewer-access-after-deployment).

Next, [configure separate GitHub workflows](../how-to/github-actions.md).
