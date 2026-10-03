---
name: dbtsnow-deploy
description: Prepare, preview, deploy, or configure GitHub Actions for native Snowflake DBT PROJECT objects using this dbtsnow repository and its setup wizard. Use for dbtsnow deployment configuration, packaging failures, and verified source updates; not general local dbt development.
---

# Deploy with dbtsnow

## Start in the selected checkout

Use the checkout the user selected. Otherwise find the repository root by walking ancestors of this SKILL.md. Require `pyproject.toml` with project name `dbtsnow` and `scripts/dbt_native.py`; if the selected directory fails that check, request its location instead of switching to another checkout. Run wrapper commands from that root.

Read [configuration](../../../docs/reference/configuration.md) for fields or packaging limits. Use [first deployment](../../../docs/tutorials/first-deployment.md) only when setting up an account or role. Account names, tutorial roles, and recorded trial results are examples, not routing defaults.

## Prepare and preview

1. Reuse the user's selected JSON configuration. If missing, use `uv run python scripts/dbt_native.py wizard --source <source> --output <new-config>`; inspect subcommand `--help` for supplied values. The wizard refuses overwrites. Ask for missing account/context values, including the database; never silently choose a trial account or database.
2. Let the wizard infer project/profile/target and selected connection suggestions. Do not print personal credential files. It may read the source profile or `~/.dbt/profiles.yml`; inspect the resulting non-secret settings before accepting them. A named connection must be the user's selected one.
3. Preview with `uv run python scripts/dbt_native.py deploy --config <config>`. This prepares files without a Snowflake connection. Report account, role, warehouse, native object, model database/schema, runtime, compilation, and writeback. Preview does not prove cloud permissions or runtime availability.

Native object and model destinations are independent. The wrapper generates a credential-free native profile. Unsupported source files and dependencies must be resolved using the configuration reference; do not bypass packaging checks or embed credentials. Remote dependencies require appropriate existing external access integrations.

## Apply the authorized change

For a deployment the user authorized, append `--apply` to the reviewed preview command. Do not ask again for the same authorization. Add `--build` only when model writes are included in the task. Creating databases/roles, migration, and workflow dispatch need their own task scope; the skill grants no permissions.

Deployment updates without `--force` and verifies source readback, receipt hashes, runtime, and available native metadata. Report success only after verification. LIVE replacement deletes persisted target/log files, so it also destroys prior retry state. A failed apply can leave changed settings/source or model relations: inspect the failure before another mutation; do not claim automatic rollback or blindly redeploy.

An existing numbered object is rejected. Use the separately scoped migration procedure in [migrate to LIVE](../../../docs/how-to/migrate-to-live.md); do not recreate it or enable account behavior bundles as a workaround.

## GitHub deployment

Read [GitHub Actions](../../../docs/how-to/github-actions.md) before changing or dispatching the workflow. `.github/workflows/deploy.yml` is manual, main-only, uses environment `dev`, serializes deployments, and authenticates through OIDC with a temporary connection. It always reads **`deployment/dev.json`**: commit a reviewed, non-secret configuration for the intended destination. Local ignored configurations alone do not configure CI.

OIDC setup, environment variables, and permissions must be verified for the selected account. The deployment receipt requires the exact clean checked-out GitHub SHA. Passing local gates or PR CI does not establish that OIDC cloud deployment works. Publish or dispatch only within the user's authorization; report repository checks separately from actual cloud execution.
