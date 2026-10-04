---
icon: lucide/scan-eye
---

# Preview the example

[Documentation](../index.md) · Next: [Deploy your first project](first-deployment.md)

In this lesson, we will inspect one dbt model and produce its deployment plan. We will use the included configuration without connecting to Snowflake.

## Get the project

You need Git, Python 3.11 or later, and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```sh
git clone https://github.com/MiguelElGallo/dbtsnow.git
cd dbtsnow
uv sync --frozen
```

Run the remaining commands from this repository directory. When synchronization finishes, the project's Python environment is ready.

## Read the model

Open `example/models/deployment_check.sql`:

```sql
select 1 as id, 'Native dbt deployment works' as message
```

This query will become a view with one row. Open `example/models/schema.yml` too: it adds two tests requiring `id` to be present and unique.

## Produce the plan

```sh
uv run python scripts/dbt_native.py deploy --config deployment/example.json
```

The command prints a deployment plan. Find these entries:

| Entry | Value |
| --- | --- |
| Account | `MYORG-MYACCOUNT` |
| Project administrator role | `DBT_PROJECT_ADMIN` |
| Operator/profile role | `DBT_OPERATOR` |
| Native project | `DEV_DBT_PRJ.PROJECTS.NATIVE_DBT_EXAMPLE` |
| Model destination | `DEV_DBT_PRJ.ANALYTICS` |
| Profile / target | `native_dbt_example` / `dev` |
| Runtime | `2.0.0` |
| Automatic compilation / default writeback | Both disabled |

Notice the two destinations: `PROJECTS` holds the native project; `ANALYTICS` receives the model view. The project administrator delivers source, and the operator builds the model later.

## Check the upload list

The list includes the project definition, its model and tests, a generated native profile, and a deployment receipt. The profile carries the model destination and operator role; it contains no login credentials.

The final line should be:

```text
Dry run: no Snowflake connection or cloud writes. Add --apply to deploy.
```

`MYORG-MYACCOUNT` and the expected usernames are placeholders. Keep this configuration for offline previews; it cannot establish authentication, privileges, or runtime availability in your account.

We have inspected what will be uploaded and where it will go. Continue with [your first deployment](first-deployment.md) to prepare a real account and build the view.
