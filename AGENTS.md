# Working in dbtsnow

This repository deploys native Snowflake `DBT PROJECT` objects through
`scripts/dbt_native.py`. Start with [README](README.md) and the
[documentation home](docs/index.md). Native deployment and local dbt execution
have different configuration and artifact behavior.

## Choose the relevant skill

Load only the skill needed for the task:

| Task | Repository skill |
| --- | --- |
| Configure the wizard, preview/deploy source, or set up GitHub deployment | [dbtsnow-deploy](.agents/skills/dbtsnow-deploy/SKILL.md) |
| Build, compile, retry, inspect logs, use state/freshness, or migrate | [dbtsnow-operate](.agents/skills/dbtsnow-operate/SKILL.md) |
| Navigate, change, test, document, or review the repository | [dbtsnow-maintain](.agents/skills/dbtsnow-maintain/SKILL.md) |

For discovery and example prompts, see [Use the agent skills](docs/how-to/use-agent-skills.md).

## Start with explicit context

Run the wrapper from this repository root using the user's selected configuration.
`deployment/example.json` is an offline example with account placeholders.
Tutorial account/database/role names and screenshot results are historical examples,
not deployment defaults. Do not print personal credentials or commit local credential
files. Real local configurations belong in ignored paths; a GitHub deployment needs
a reviewed, non-secret `deployment/dev.json` committed explicitly.

Preview operations without `--apply` make no Snowflake connection. `wizard` writes
a local config; applied commands perform cloud changes. Keep native object and
model destinations separate. A deployment replaces all LIVE files, including
artifacts needed by retry. Use the existing wrapper and preserve its verification.

## Navigate efficiently

`scripts/dbt_native.py` contains configuration, packaging, wizard, deployment,
migration, and execution. Tests live in `tests/test_dbt_native.py` and
`tests/test_live_version.py`; workflows live in `.github/workflows/`.
Use `rg` for text/path lookup and available symbol navigation for focused bodies.
The maintain skill maps symbols and validation commands.

Keep tutorials, task guides, reference, and explanation in their existing Diátaxis
directories. Link canonical docs from skills instead of copying whole manuals.
Skill instructions do not authorize publishing, cloud execution, or privilege changes;
use the task's existing authorization and report offline checks separately from live results.
