# dbtsnow

Deploy native Snowflake `DBT PROJECT` objects with separate responsibilities for platform administration, project administration, and daily operation.

| Your responsibility | Start here | Code and job |
| --- | --- | --- |
| Snowflake administrator: databases, schemas, roles, identities, and grants | [Administrator setup](docs/how-to/admin-setup.md) | `scripts/dbt_admin.py`; run with your approved administrative connection |
| Project administrator: deploy reviewed source, own the project, and hand it to operators | [Deploy and grant project access](docs/how-to/project-admin.md) | `scripts/dbt_native.py deploy` / `project-access`; GitHub `deploy.yml` |
| Operator: compile, build, retry, check freshness, and inspect runs | [Run and retry](docs/how-to/run-and-retry.md) · [Inspect runs](docs/how-to/inspect-runs.md) | `scripts/dbt_native.py run`; GitHub `operate.yml` |

The project administrator and operator use two independent custom roles. They do not need `ACCOUNTADMIN` for their routine work. [Understand the separation](docs/explanation/role-separation.md).

## Try the example

```sh
uv sync --frozen
uv run python scripts/dbt_native.py deploy --config deployment/example.json
```

This preview makes no Snowflake connection. [Deploy your first project](docs/tutorials/first-deployment.md) walks through the administrator handoff, two dedicated test users, source deployment, and an operator build.

## Find what you need

| Goal | Documentation |
| --- | --- |
| Prepare corporate access | [Administrator setup](docs/how-to/admin-setup.md) · [Role responsibilities](docs/explanation/role-separation.md) |
| Learn with a small example | [Preview](docs/tutorials/preview-the-example.md) · [First deployment](docs/tutorials/first-deployment.md) |
| Deploy or operate from GitHub | [Two workflows and OIDC identities](docs/how-to/github-actions.md) |
| Migrate an existing numbered object | [Migrate to LIVE](docs/how-to/migrate-to-live.md) |
| Execute or recover a run | [Build and retry](docs/how-to/run-and-retry.md) · [Logs](docs/how-to/inspect-runs.md) |
| Compare source or check source age | [State builds](docs/how-to/state-build.md) · [Source freshness](docs/how-to/check-source-freshness.md) |
| Look up a setting or option | [Configuration](docs/reference/configuration.md) · [Commands](docs/reference/commands.md) |
| Give an agent repository context | [Four repository skills](docs/how-to/use-agent-skills.md) |

[Documentation](docs/index.md) follows Diátaxis. [Earlier screenshots](docs/screenshots/README.md) record the original single-role setup; [validation evidence](docs/validation.md) distinguishes those results from the role-split checks.

Snowflake CLI **3.28.0** uploads and verifies source. The default native runtime is **dbt Fusion 2.0.0**; Core **1.11.11** is also offered. Account runtime availability is checked before applying; see [configuration](docs/reference/configuration.md). New source replaces all LIVE files, including retry artifacts. Existing single-role configurations remain supported; adopting separate roles is an explicit setup change.
