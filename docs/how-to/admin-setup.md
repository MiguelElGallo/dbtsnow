# Administrator: prepare databases, roles, and users

[Documentation](../index.md) · [Role responsibilities](../explanation/role-separation.md)

Use an approved Snowflake administrator identity for this guide. After setup, the project administrator deploys source and the operator executes it using their own logins. Routine project work does not use the administrator connection.

## Administrator prerequisites

The selected administrative role needs `CREATE DATABASE` and `CREATE ROLE` on the account, `CREATE USER` when requesting test users, and `MANAGE GRANTS` to apply the warehouse and role grants. It must also have visibility of all targeted databases, roles, and users for collision inspection, and access to the chosen existing warehouse. A custom platform role can supply these capabilities; select your approved role explicitly.

The helper verifies account/role identity, inspects resource collisions, and checks readback. It does not prove every effective privilege before the first DDL statement. A privilege error later in setup can leave earlier resources created; inspect that partial state instead of assuming rollback. [Access-control privileges](https://docs.snowflake.com/en/user-guide/security-access-control-privileges).

The local bootstrap requires OpenSSL when reading public-key files; those files must contain RSA public keys of at least 2048 bits.

## Review the shared configuration

Save a credentials-free configuration for the agreed account and destinations as `deployment/dev.json`. The [configuration reference](../reference/configuration.md) lists every field. For the separated setup:

- `deployment_role` names the project administrator role; `role` names a different operator role.
- `deployment_connection` and `connection` select those identities' local connections.
- `deployment_user` and `operator_user` can bind applied operations to expected usernames.
- `auto_compile` is `false`; the project administrator does not build models.

Use new database, role, and test-user names for the fresh-resource bootstrap. An existing warehouse is reused. Database and model database can differ; never infer a production destination from these examples.

## Create dedicated test credentials

The optional test users use key-pair authentication and `TYPE = SERVICE`. Generate two keys in a **new** directory beneath ignored `.local`. The directory creation guard prevents this block from overwriting an existing set of keys:

```sh
umask 077
mkdir -p .local
mkdir .local/dbt-corporate-keys && (
  set -e
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out .local/dbt-corporate-keys/project-admin.p8
  openssl pkey -in .local/dbt-corporate-keys/project-admin.p8 -pubout -out .local/dbt-corporate-keys/project-admin.pub.pem
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out .local/dbt-corporate-keys/operator.p8
  openssl pkey -in .local/dbt-corporate-keys/operator.p8 -pubout -out .local/dbt-corporate-keys/operator.pub.pem
)
```

The subshell stops if any key-generation command fails. If `.local/dbt-corporate-keys` already exists, preserve it and choose a new directory for a new pair of identities; do not delete or overwrite it to repeat the recipe.

The bootstrap reads only the public-key files. Keep private keys out of configuration, command output, and commits. For ongoing service use, follow your organization's secret storage and key-rotation process. [Snowflake key-pair authentication](https://docs.snowflake.com/en/user-guide/key-pair-auth).

## Preview fresh-resource setup

Replace the administrative connection and test usernames with the approved values. If expected usernames are in the config, use the same usernames here:

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

This preview makes no connection. Review the exact account, databases, schemas, roles, users, warehouse, and grants. `ACCOUNTADMIN` is an example approved admin role; the helper verifies the selected account and active admin role before applying.

Omit both arguments for a test identity if you are not creating that identity. User and public-key arguments must be supplied as a pair. User assignment for existing corporate logins belongs in the reviewed SQL path below.

## Apply and read back

Append `--apply` to the same reviewed command. The helper checks that the targeted databases, delegated roles, and requested test users are fresh before provisioning. It refuses collisions rather than adopting existing permissions, replacing users, or changing their keys.

It provisions object/model databases and regular schemas, the independent project administrator and operator roles, warehouse access, and optional test users with `DEFAULT_SECONDARY_ROLES = ()`. The project role gets `CREATE DBT PROJECT` on the object schema; the operator gets project-parent access and model-schema `USAGE`, `CREATE TABLE`, and `CREATE VIEW`. New users receive only their respective delegated role.

Readback checks the provisioned resources and role/user assignments. A later error does not undo earlier Snowflake DDL; inspect partial setup before deciding how to complete it. The helper does not recreate or force-replace resources.

Model schemas are precreated, and the default operator grants exclude `CREATE SCHEMA`. If a live compile/build demonstrates that the selected native runtime requires it, the administrator can preview and apply a fresh setup with `--allow-model-schema-creation`. This opts into `CREATE SCHEMA` on the configured model database. For a setup already applied, use the separately reviewed grant below instead of rerunning bootstrap.

## Use existing corporate resources

Bootstrap is for fresh resources. For an existing database, warehouse, role, or human login, have the platform owner review the following grant pattern and replace every example name. Verify existing role membership and privileges before reusing a role. Do not transfer ownership or reset authentication as part of onboarding.

```sql
-- Run as the approved administrator after creating/reviewing the two custom roles.
GRANT USAGE ON DATABASE DBT_CORPORATE_DEV TO ROLE DBT_PROJECT_ADMIN;
GRANT USAGE ON SCHEMA DBT_CORPORATE_DEV.PROJECTS TO ROLE DBT_PROJECT_ADMIN;
GRANT CREATE DBT PROJECT ON SCHEMA DBT_CORPORATE_DEV.PROJECTS TO ROLE DBT_PROJECT_ADMIN;
GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE DBT_PROJECT_ADMIN;

GRANT USAGE ON DATABASE DBT_CORPORATE_DEV TO ROLE DBT_OPERATOR;
GRANT USAGE ON SCHEMA DBT_CORPORATE_DEV.PROJECTS TO ROLE DBT_OPERATOR;
GRANT USAGE ON SCHEMA DBT_CORPORATE_DEV.ANALYTICS TO ROLE DBT_OPERATOR;
GRANT CREATE TABLE, CREATE VIEW ON SCHEMA DBT_CORPORATE_DEV.ANALYTICS TO ROLE DBT_OPERATOR;
GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE DBT_OPERATOR;

GRANT ROLE DBT_PROJECT_ADMIN TO USER <EXISTING_PROJECT_ADMIN_USER>;
GRANT ROLE DBT_OPERATOR TO USER <EXISTING_OPERATOR_USER>;
```

Create missing databases/schemas using your platform process. If the model database differs, grant the operator database/schema access there as well. Keep the two delegated roles independent; assigning one to the other would combine their responsibilities.

Only when the runtime requires schema creation, approve this additional model-database scope:

```sql
GRANT CREATE SCHEMA ON DATABASE <MODEL_DATABASE> TO ROLE DBT_OPERATOR;
```

## Add project-specific data access

Provision any additional model schemas and grant the operator only the needed materialization privileges. Custom dbt schemas are separate from the configured base schema. A state comparison using `CI_ANALYTICS`, for example, needs that schema provisioned and the operator's output privileges there.

For source reads or deferral, grant parent `USAGE` and targeted `SELECT` on the intended relations. Replace all placeholders in this example:

```sql
GRANT USAGE ON DATABASE <SOURCE_DATABASE> TO ROLE DBT_OPERATOR;
GRANT USAGE ON SCHEMA <SOURCE_DATABASE>.<SOURCE_SCHEMA> TO ROLE DBT_OPERATOR;
GRANT SELECT ON TABLE <SOURCE_DATABASE>.<SOURCE_SCHEMA>.<SOURCE_TABLE>
  TO ROLE DBT_OPERATOR;
```

Use `ON VIEW` when the relation is a view. The project administrator does not need these data privileges to upload source with automatic compilation disabled.

Remote packages require an existing external-access integration. Its creation and network allowlist belong to the administrator. Grant integration `USAGE` to both the project role that attaches it during deployment and the operator role that executes dependencies. [Dependencies](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-dependencies).

## Validate delegated access

For new test users, authenticate with each user's own key and connection. Check `CURRENT_USER()`, `CURRENT_ROLE()`, and `CURRENT_SECONDARY_ROLES()`; an administrator switching roles does not demonstrate that another user can sign in. The [first-deployment lesson](../tutorials/first-deployment.md#authenticate-as-each-new-user) provides the connection commands.

After project creation and access handoff, confirm a project-administrator deployment and an operator build using those separate logins. To evaluate permission boundaries, use isolated development resources and verify these intended denials:

| Identity | Operations it should lack |
| --- | --- |
| Project administrator | Account-level database/role/user creation; model execution through an operator role not assigned to this user; reads of operator data without separate grants |
| Operator | Account-level database/role/user creation; alteration of another role's project; project grants it has no authority to distribute |

Inspect any unexpected success against direct grants, inherited roles, and grants to `PUBLIC`. The project administrator still has its native object's ownership capabilities; this setup does not remove those. [Role boundaries](../explanation/role-separation.md#what-least-privilege-means-here).

Service-user CLI login, human Snowsight access, and GitHub OIDC are separate authentication paths. Validate only the path you have configured; [GitHub setup](github-actions.md) covers the two workflow identities.

## Complete project and viewer access after deployment

After the project administrator creates the project, that owner runs [the project access handoff](project-admin.md#grant-operator-access). This grants the configured operator `USAGE` and `MONITOR` on that exact object.

In a managed-access schema, the schema owner or an administrator with `MANAGE GRANTS` applies those object grants instead:

```sql
GRANT USAGE, MONITOR ON DBT PROJECT DBT_CORPORATE_DEV.PROJECTS.NATIVE_DBT_EXAMPLE
  TO ROLE DBT_OPERATOR;
SHOW GRANTS ON DBT PROJECT DBT_CORPORATE_DEV.PROJECTS.NATIVE_DBT_EXAMPLE;
```

For a separate browser viewer, grant access to its chosen primary role after the object exists:

```sql
GRANT USAGE ON DATABASE DBT_CORPORATE_DEV TO ROLE <VIEWER_ROLE>;
GRANT USAGE ON SCHEMA DBT_CORPORATE_DEV.PROJECTS TO ROLE <VIEWER_ROLE>;
GRANT MONITOR ON DBT PROJECT DBT_CORPORATE_DEV.PROJECTS.NATIVE_DBT_EXAMPLE
  TO ROLE <VIEWER_ROLE>;
SHOW GRANTS ON DBT PROJECT DBT_CORPORATE_DEV.PROJECTS.NATIVE_DBT_EXAMPLE;
```

An error naming primary role `ACCOUNTADMIN` also needs this explicit project `MONITOR` grant; `MANAGE GRANTS` allows giving access rather than substituting for the project's viewing requirement. Use the approved primary role in [Snowsight](inspect-runs.md#set-up-snowsight-access) and verify its DAG/history.

## Retire a test setup

When a test setup is no longer needed, have the administrator review removal of its native project, test databases, delegated users, and roles. Reuse of an existing warehouse does not make that warehouse part of the cleanup scope. Retire the corresponding local CLI connections and keys when those identities are no longer used. The deployment wrapper does not remove account resources.

Sources: [dbt privileges and deployment/execution phases](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-access-control), [CREATE USER](https://docs.snowflake.com/en/sql-reference/sql/create-user), [managed-access grant authority](https://docs.snowflake.com/en/user-guide/security-access-control-privileges).
