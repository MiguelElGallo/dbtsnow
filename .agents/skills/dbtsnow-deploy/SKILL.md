---
name: dbtsnow-deploy
description: Configure, preview, deploy, grant operator project access, or migrate native Snowflake DBT PROJECT objects as the project administrator using this dbtsnow repository. Use for reviewed source delivery and the deployment GitHub workflow; platform provisioning belongs to dbtsnow-admin.
---

# Administer and deploy a dbt project

Use the user's selected checkout or walk ancestors of this skill to find `pyproject.toml` naming `dbtsnow` and `scripts/dbt_native.py`. Run from its root with the selected configuration. Tutorial account and role names are examples rather than routing defaults.

Read [project administration](../../../docs/how-to/project-admin.md). Load [configuration](../../../docs/reference/configuration.md) for fields/packaging, [migration](../../../docs/how-to/migrate-to-live.md) for numbered objects, or [GitHub identities](../../../docs/how-to/github-actions.md) for workflow setup. Platform database/role/user creation belongs to [administrator setup](../../../docs/how-to/admin-setup.md).

## Prepare and preview

Reuse the selected JSON. If it is missing, use the wizard with the selected source and a new output path; existing output is refused. Ask only for missing account/context values that cannot be inferred. Named connections must be selected for the intended identity; do not print credential files.

In the corporate setup, `deployment_role`/`deployment_connection`/`deployment_user` select project administration. `role`/`connection`/`operator_user` select operation; the generated profile uses the operator role. Preview `uv run python scripts/dbt_native.py deploy --config <config>` and report both roles, expected identities, account, native/model destinations, runtime, compilation, and writeback. Preview is offline.

Separate roles require `auto_compile: false` and reject `deploy --build`. Do not give the deployment user the operator role to enable compilation. Legacy single-role configs retain optional compilation/build, and only their explicitly authorized model writes may use `--build`.

Preserve packaging checks and the credentials-free generated native profile. Remote dependencies require approved existing integrations; do not embed credentials or bypass supported-file checks.

## Apply and hand off

Append `--apply` when deployment is authorized; do not repeat a resolved permission request. Applied deployment verifies account, current role, optional expected user, no secondary roles, existing-object ownership, runtime, source hashes, and receipt. An existing object owned by another role needs a separately reviewed administrator adoption; never force-replace it or transfer ownership as a workaround.

Once the object exists, preview/apply `uv run python scripts/dbt_native.py project-access --config <config>` within the authorized access handoff. It grants only `USAGE` and `MONITOR` on this exact object to the configured operator and verifies them. Managed-access schemas require schema-owner/grant-administrator action; do not widen the project role's authority.

Report success after readback. LIVE replacement removes prior retry state. A failure may leave changed settings/source; inspect before another mutation rather than blindly redeploying. The operator then runs compile/build through its own identity.

## Migration and jobs

Preview/apply `migrate` only for the selected existing object and authorized migration. It uses the project administrator role, requires ownership, verifies LIVE/preserved metadata, and makes numbered source versions inaccessible. It never enables account behavior bundles or recreates objects.

`.github/workflows/deploy.yml` is manual, main-only, uses `dev-deploy` and `SNOWFLAKE_PROJECT_ADMIN_USER`, and shares concurrency with the separate operator workflow. It always reads a reviewed non-secret `deployment/dev.json`, uses OIDC temporary authentication, deploys without compilation, and applies the operator access handoff. The shipped workflow requires a regular object schema; managed schemas need administrator-owned grants and a reviewed workflow adaptation omitting the owner grant step. The receipt requires the exact clean GitHub SHA.

Publishing, IAM setup, and dispatching a cloud job stay within the user's task authorization. Local/PR checks do not prove cloud OIDC execution; report each validation boundary separately.
