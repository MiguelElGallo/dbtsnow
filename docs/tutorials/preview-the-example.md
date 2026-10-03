# Preview the example

[Documentation](../index.md) · Next: [Deploy your first project](first-deployment.md)

In this lesson, you will inspect the included dbt model and produce a deployment plan. The preview does not connect to Snowflake or create cloud objects.

## Get the project

You need Git, Python 3.11 or later, and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```sh
git clone https://github.com/MiguelElGallo/dbtsnow.git
cd dbtsnow
uv sync --frozen
```

Run the remaining commands from this repository directory.

## Read the model

Open `example/models/deployment_check.sql`:

```sql
select 1 as id, 'Native dbt deployment works' as message
```

The project builds this query as a view. `example/models/schema.yml` adds two tests: the `id` must be present and unique.

## Preview the deployment

```sh
uv run python scripts/dbt_native.py deploy --config deployment/example.json
```

Confirm these entries in the plan:

| Entry | Example value |
| --- | --- |
| Account | `MYORG-MYACCOUNT`, an offline placeholder |
| Project administrator role | `DBT_PROJECT_ADMIN` |
| Operator/profile role | `DBT_OPERATOR` |
| Native project | `DEV_DBT_PRJ.PROJECTS.NATIVE_DBT_EXAMPLE` |
| Model destination | `DEV_DBT_PRJ.ANALYTICS` |
| Profile / target | `native_dbt_example` / `dev` |
| Runtime | `2.0.0` |
| Automatic compilation / default writeback | Both disabled |

The separate expected users are placeholders for dedicated project-admin/operator identities. They do not authenticate during this preview. The runtime shown comes from the pinned sample configuration; force replacement remains disabled.

The upload list contains the project, its model and tests, a generated native profile, and a deployment receipt. The final line confirms this is a dry run.

`MYORG-MYACCOUNT` is a placeholder in the sample configuration. Keep this lesson as a preview; the next lesson creates a configuration for your own account.

## Check what you learned

The plan names two locations: `PROJECTS` stores the native dbt object, while `ANALYTICS` receives model output. You have inspected what will be uploaded and where it will go.

Continue with [your first live deployment](first-deployment.md).
