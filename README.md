# dbtsnow

Deploy a native Snowflake `DBT PROJECT` with a setup wizard and GitHub Actions. The wizard asks for the database and execution context; deployment verifies the uploaded source before an optional model build.

## Start with the example

From this repository directory, preview the included project:

```sh
uv sync --frozen
uv run python scripts/dbt_native.py deploy --config deployment/example.json
```

The preview makes no Snowflake connection. For prerequisites, wizard prompts, real deployment, and the expected model result, follow [Deploy your first project](docs/tutorials/first-deployment.md).

## Find what you need

| Goal | Documentation |
| --- | --- |
| Learn with a small example | [Preview](docs/tutorials/preview-the-example.md) · [First deployment](docs/tutorials/first-deployment.md) |
| Deploy from GitHub | [GitHub Actions and OIDC](docs/how-to/github-actions.md) |
| Update an existing numbered object | [Migrate to LIVE](docs/how-to/migrate-to-live.md) |
| Execute or recover a run | [Build and retry](docs/how-to/run-and-retry.md) · [Logs](docs/how-to/inspect-runs.md) |
| Compare source with a baseline | [State builds](docs/how-to/state-build.md) |
| Check source data age | [Source freshness](docs/how-to/check-source-freshness.md) |
| Look up an option | [Configuration](docs/reference/configuration.md) · [Commands](docs/reference/commands.md) |
| Give an agent repository context | [Agent skills](docs/how-to/use-agent-skills.md) |

The [documentation home](docs/index.md) separates tutorials, how-to guides, reference, and explanation. See the [screenshot walkthrough](docs/screenshots/README.md) and [validation evidence](docs/validation.md) for real trial results.

## Deployment approach

Snowflake CLI with GitHub Actions and OIDC is the recommended path. SQL and Snowsight also support native deployment; DCM's documented entity list does not include `DBT PROJECT`. [Read the comparison](docs/explanation/deployment-choice.md).

The template supports LIVE objects and explicit legacy migration. The object destination and model destination are separate settings. Builds write model relations; rollback requires redeploying known source and does not restore those relations. [Understand LIVE](docs/explanation/live-version.md).

Pinned defaults: Snowflake CLI **3.28.0**, dbt Fusion **2.0.0-preview.210**. Core **1.11.11** is also offered. Account runtime availability is checked before applying. See [supported project files and limits](docs/reference/configuration.md#uploaded-files-and-limits).
