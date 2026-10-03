# Working in dbtsnow

This repository deploys native Snowflake `DBT PROJECT` objects through
`scripts/dbt_native.py`; `scripts/dbt_admin.py` provisions fresh administrator-owned
resources. Start with [README](README.md) and [documentation](docs/index.md).
Native deployment and local dbt execution have different configuration and artifacts.

## Choose the responsibility and skill

| Responsibility or task | Repository skill |
| --- | --- |
| Snowflake administrator: database/schema/role/user setup and authentication handoff | [dbtsnow-admin](.agents/skills/dbtsnow-admin/SKILL.md) |
| Project administrator: wizard, source deployment, project access, legacy migration, deployment job | [dbtsnow-deploy](.agents/skills/dbtsnow-deploy/SKILL.md) |
| Operator: build, compile, retry, history/logs, state/freshness, operation job | [dbtsnow-operate](.agents/skills/dbtsnow-operate/SKILL.md) |
| Repository engineering: navigation, changes, tests, documentation, review | [dbtsnow-maintain](.agents/skills/dbtsnow-maintain/SKILL.md) |

Load only the skill needed. [Agent examples](docs/how-to/use-agent-skills.md) show
how to keep the administrator, project administrator, and operator tasks scoped.

## Use the selected context

Run from this repository root with the user's selected configuration.
`deployment/example.json` is an offline corporate example with placeholders.
Tutorial names and screenshot results are examples, not deployment defaults.
Do not print credentials or commit local authentication files. Real local settings
belong in ignored paths; GitHub needs a reviewed non-secret `deployment/dev.json`
committed explicitly.

In split-role mode, `deployment_role`/`deployment_connection`/`deployment_user`
select project administration. `role`/`connection`/`operator_user` select operation
and the native profile. Keep the two custom roles independent. Source deployment
requires `auto_compile: false` and refuses `--build`; operator execution follows.
Administrator provisioning and ownership adoption are separate actions rather than
runtime error workarounds.

Previews without `--apply` make no Snowflake connection. `wizard` writes a local
config. Applied commands perform cloud changes and verify readback. All authenticated
CLI invocations disable secondary roles. New service-user validation must use those
users' own logins; changing an administrator's active role is insufficient.

Keep native and model destinations separate. Deployment replaces LIVE files,
including retry artifacts. Use the existing wrappers and preserve their checks.
Both GitHub jobs share concurrency; coordinate local writes to the same resources.

## Navigate and maintain

`scripts/dbt_native.py` contains configuration, packaging, wizard, project access,
deployment, migration, and execution. `scripts/dbt_admin.py` contains provisioning.
Tests are under `tests/`; workflows are under `.github/workflows/`. Use `rg` for
text/path lookup and available symbol navigation for focused bodies. The maintain
skill maps entrypoints and validation commands.

Keep tutorials, task guides, reference, and explanation in their Diátaxis directories.
Link canonical administrator setup instead of copying database/role/user grant SQL
into operating guides. Skills do not authorize publication, cloud execution, or
privilege changes; use the existing task authorization and distinguish offline,
dedicated-user CLI, GitHub OIDC, and human-browser results.
