# dbtsnow

[Documentation](https://miguelelgallo.github.io/dbtsnow/)

Deploy native Snowflake `DBT PROJECT` objects with separate responsibilities for platform administration, project administration, and daily operation.

| Your responsibility | Start here | Code and job |
| --- | --- | --- |
| Snowflake administrator: databases, schemas, roles, identities, and grants | [Administrator setup](https://miguelelgallo.github.io/dbtsnow/how-to/admin-setup/) | `scripts/dbt_admin.py`; run with your approved administrative connection |
| Project administrator: deploy reviewed source, own the project, and hand it to operators | [Deploy and grant project access](https://miguelelgallo.github.io/dbtsnow/how-to/project-admin/) | `scripts/dbt_native.py deploy` / `project-access`; GitHub `deploy.yml` |
| Operator: compile, build, retry, check freshness, and inspect runs | [Run and retry](https://miguelelgallo.github.io/dbtsnow/how-to/run-and-retry/) · [Inspect runs](https://miguelelgallo.github.io/dbtsnow/how-to/inspect-runs/) | `scripts/dbt_native.py run`; GitHub `operate.yml` |

The project administrator and operator use two independent custom roles. They do not need `ACCOUNTADMIN` for their routine work. [Understand the separation](https://miguelelgallo.github.io/dbtsnow/explanation/role-separation/).

## Try the example

```sh
uv sync --frozen
uv run python scripts/dbt_native.py deploy --config deployment/example.json
```

This preview makes no Snowflake connection. [Deploy your first project](https://miguelelgallo.github.io/dbtsnow/tutorials/first-deployment/) walks through the administrator handoff, two dedicated test users, source deployment, and an operator build.

## Find what you need

| Goal | Documentation |
| --- | --- |
| Prepare corporate access | [Administrator setup](https://miguelelgallo.github.io/dbtsnow/how-to/admin-setup/) · [Role responsibilities](https://miguelelgallo.github.io/dbtsnow/explanation/role-separation/) |
| Learn with a small example | [Preview](https://miguelelgallo.github.io/dbtsnow/tutorials/preview-the-example/) · [First deployment](https://miguelelgallo.github.io/dbtsnow/tutorials/first-deployment/) |
| Deploy or operate from GitHub | [Two workflows and OIDC identities](https://miguelelgallo.github.io/dbtsnow/how-to/github-actions/) |
| Migrate an existing numbered object | [Migrate to LIVE](https://miguelelgallo.github.io/dbtsnow/how-to/migrate-to-live/) |
| Execute or recover a run | [Build and retry](https://miguelelgallo.github.io/dbtsnow/how-to/run-and-retry/) · [Logs](https://miguelelgallo.github.io/dbtsnow/how-to/inspect-runs/) |
| Compare source or check source age | [State builds](https://miguelelgallo.github.io/dbtsnow/how-to/state-build/) · [Source freshness](https://miguelelgallo.github.io/dbtsnow/how-to/check-source-freshness/) |
| Look up a setting or option | [Configuration](https://miguelelgallo.github.io/dbtsnow/reference/configuration/) · [Commands](https://miguelelgallo.github.io/dbtsnow/reference/commands/) |
| Give an agent repository context | [Four repository skills](https://miguelelgallo.github.io/dbtsnow/how-to/use-agent-skills/) |

[Browse the documentation](https://miguelelgallo.github.io/dbtsnow/) for tutorials, task guides, reference, and explanations.

Snowflake CLI **3.28.0** uploads and verifies source. The default native runtime is **dbt Fusion 2.0.0**; Core **1.11.11** is also offered. Account runtime availability is checked before applying; see [configuration](https://miguelelgallo.github.io/dbtsnow/reference/configuration/). New source replaces all LIVE files, including retry artifacts. Existing single-role configurations remain supported; adopting separate roles is an explicit setup change.
