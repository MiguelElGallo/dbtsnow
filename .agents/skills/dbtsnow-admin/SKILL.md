---
name: dbtsnow-admin
description: Prepare Snowflake databases, schemas, independent project-admin and operator roles, user assignments, and service test users for this dbtsnow repository. Use for administrator bootstrap or corporate access setup before delegated deployment and execution.
---

# Administer dbtsnow access

Use the user's selected checkout or walk ancestors of this skill to find `pyproject.toml` naming `dbtsnow` and `scripts/dbt_admin.py`. Run from that root with the selected project config and approved administrator connection/role. Tutorial account and role names are examples rather than deployment defaults.

Read [administrator setup](../../../docs/how-to/admin-setup.md) for provisioning and [role separation](../../../docs/explanation/role-separation.md) for the handoff. Look up exact fields/flags in [configuration](../../../docs/reference/configuration.md) and [commands](../../../docs/reference/commands.md#administrator-bootstrap).

## Preview the administrator's scope

Use `uv run python scripts/dbt_admin.py bootstrap --config <config> --admin-connection <selected-admin-connection> --admin-role <selected-admin-role>`. Optional dedicated service users require paired username/public-key-file arguments. Private keys and credentials remain outside the project config and tracked artifacts.

The preview is offline. Report exact account, resources, independent delegated roles, requested users, and grant scope. The project administrator creates/owns/deploys the project; the operator executes the profile role. Never assign one delegated role to the other or grant either account administration to make an operation succeed.

## Apply authorized setup

When the user's task authorizes this provisioning, append `--apply` to the reviewed command. Do not ask again for an already-authorized action. Bootstrap verifies account/role, refuses preexisting database/role/requested-user collisions before writes, provisions regular schemas and optional `TYPE = SERVICE` users with empty default secondary roles, then reads back. It never adopts roles, rotates an existing user's key, transfers ownership, or recreates resources.

The selected administrator needs the guide's account creation/grant capabilities and complete target visibility. Identity/collision checks do not prove every effective privilege upfront. For existing corporate resources or human logins, use the administrator-reviewed SQL path in the guide. Inspect partial setup after failure before choosing another mutation; Snowflake DDL is not automatically rolled back. Source privileges, extra model schemas, integrations, and OIDC identities need the selected task's specific scope.

Precreate model schemas. `--allow-model-schema-creation` is an explicit wider operator grant within the configured model database; use it only when justified and authorized, rather than automatically fixing a denied runtime statement. Bootstrap does not grant `CREATE SCHEMA` by default.

## Validate the handoff

Authenticate separately as each new test user, verify current user/primary role and no secondary roles, then use project-admin deployment/access and operator execution. Read [first deployment](../../../docs/tutorials/first-deployment.md) for this sequence. Administrator role switching alone does not validate new user login. Service-user CLI results do not establish human Snowsight sign-in or GitHub OIDC authentication.

Project access grants follow object creation. In a regular schema, the project owner uses `project-access`; managed schemas route grant authority to the schema owner or administrator. Hand subsequent source work to `dbtsnow-deploy` and daily execution to `dbtsnow-operate`. This skill itself adds no cloud/publication authorization.
