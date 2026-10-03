# Project administrator: migrate a numbered project to LIVE

[Documentation](../index.md)

Migrate an existing native project's numbered default version to LIVE using its project administrator connection. In a split configuration, `deployment_role`, `deployment_connection`, and optional `deployment_user` select this identity. The configured `role` stays the operator/profile role.

## Before you start

- Use a saved configuration naming the existing object and its owning project administrator role.
- Ask the Snowflake administrator to confirm that the `2026_06` bundle or the separate single-live-version feature is enabled.
- Back up numbered source versions you need; migration makes them inaccessible.

New projects already opted into LIVE do not need migration. The wrapper does not enable account bundles. Migration preserves the object's identity, grants, task references, and execution history. See [how LIVE works](../explanation/live-version.md) and [Snowflake migration](https://docs.snowflake.com/en/sql-reference/functions/system_migrate_dbt_project).

## Review the migration

```sh
uv run python scripts/dbt_native.py migrate --config deployment/dev.json
```

Confirm the account, project administrator identity/role, object, and `SYSTEM$MIGRATE_DBT_PROJECT` statement in this offline plan.

## Apply it to that object

```sh
uv run python scripts/dbt_native.py migrate --config deployment/dev.json --apply
```

The wrapper verifies the caller and configured ownership, inspects the default version, migrates it, then reads back LIVE and the previously exposed object metadata. Expect `Verified migration:` on success. An already migrated project reports `Already LIVE; no migration performed.`

If ownership or feature prerequisites prevent migration, ask the administrator to resolve them. If migration occurred but readback failed, inspect the object before another attempt; there is no automatic reversal.

After verification, use [normal deployment](project-admin.md#preview-and-deploy-source) to update source. Migration is a separate command from the GitHub deployment workflow.
