# Migrate a numbered project to LIVE

[Documentation](../index.md)

Use this guide for an existing native dbt object whose default version is numbered. Newly opted-in objects use LIVE already. [How LIVE works](../explanation/live-version.md).

## Before you start

- Use a saved configuration naming the **existing** object and its owning role.
- The account must have the `2026_06` bundle or the separate single-live-version feature enabled.
- Back up any numbered source versions you need. Migration makes them inaccessible.

The template never enables an account bundle. Migration preserves the object's identity, grants, task references, and execution history. [Snowflake migration reference](https://docs.snowflake.com/en/sql-reference/functions/system_migrate_dbt_project).

## Review the migration

```sh
uv run python scripts/dbt_native.py migrate --config deployment/dev.json
```

The preview prints the account, role, object, and `SYSTEM$MIGRATE_DBT_PROJECT` statement. It makes no Snowflake connection.

## Apply it to that object

```sh
uv run python scripts/dbt_native.py migrate --config deployment/dev.json --apply
```

The wrapper verifies the account and role, inspects the existing version, then migrates and reads back LIVE plus the previously exposed object metadata. If it is already LIVE, the result is `Already LIVE; no migration performed.`

If ownership or feature prerequisites are missing, resolve the server error with your administrator. If the migration happened but readback failed, inspect the object before retrying; there is no automatic reversal.

After a verified migration, deploy source with the [normal deployment command](../reference/commands.md#deploy). Migration is deliberately separate from the GitHub deployment workflow.
