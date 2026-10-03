# Project administrator: deploy and hand off access

[Documentation](../index.md) · [Administrator setup](admin-setup.md)

Use the project administrator's authenticated connection for this guide. The configured `deployment_role` creates and owns the native project. The operator role in `role` owns daily model execution; it stays in the generated profile.

## Check the handoff

The Snowflake administrator has prepared databases, regular schemas, independent roles, warehouse access, and your identity. Your config names the approved destinations, operator role, project administrator role, and selected connections. Set `auto_compile: false` for separated roles.

For dedicated test users, authenticate as the project administrator user with its own key. Checking `CURRENT_ROLE` in an administrator session alone does not demonstrate this handoff. [First-deployment tutorial](../tutorials/first-deployment.md).

## Preview and deploy source

```sh
uv run python scripts/dbt_native.py deploy --config deployment/dev.json
uv run python scripts/dbt_native.py deploy --config deployment/dev.json --apply
```

Review the account, deployment identity/role, project location, and operator model destination before applying. Deployment creates or updates the object, then verifies its runtime, ownership, selected target, receipt, and source hashes.

Split-role deployment skips compilation and dependencies, and rejects `--build`. The [generated operator role](../reference/configuration.md#generated-operator-role) uses a fixed literal Jinja value to avoid the pinned CLI trying to assume the operator role during its deployment validation. Keep the deployment user independent; do not grant it the operator role to pass that client check. Operators compile/build afterward. Remote packages still need an approved external-access integration attached to the object. The project administrator and operator each require the integration's appropriate `USAGE` grant.

An existing project must be owned by the configured project administrator role. If it belongs to another role, ask the platform owner to review adoption separately; this command never transfers ownership or recreates it. Numbered objects require [migration](migrate-to-live.md) first.

## Grant operator access

After the object exists, preview and apply the object-specific handoff:

```sh
uv run python scripts/dbt_native.py project-access --config deployment/dev.json
uv run python scripts/dbt_native.py project-access --config deployment/dev.json --apply
```

The command runs as the project administrator, verifies the object and owner, grants only `USAGE` and `MONITOR` on the configured project to the configured operator role, then reads those grants back. Database/schema/warehouse/data permissions remain the administrator's setup responsibility.

In a managed-access schema, ask the schema owner or an administrator with `MANAGE GRANTS` to apply the [administrator grant path](admin-setup.md#complete-project-and-viewer-access-after-deployment). The project owner alone cannot grant object access there.

The operator can now [build and inspect runs](run-and-retry.md). Service-user CLI acceptance does not verify a person's Snowsight login; perform the separate browser check using an approved human viewer.

## Update or recover source

Deployment replaces all LIVE files, including the failed-run artifacts needed by retry. Coordinate the update with the operator before applying. If a source fix is required, deploy the reviewed fix and ask the operator for a new build; retry cannot recover deleted state.

To restore earlier source, check out the approved earlier revision and deploy it with the same configured owner. Source rollback does not restore model relations changed by earlier executions. A failure can leave settings/source partially changed; inspect before another attempt.

## Use GitHub

The shipped project-administrator workflow requires a regular object schema; it repeats the owner-controlled access handoff after deployment. Existing managed schemas require [administrator-owned grants](admin-setup.md#complete-project-and-viewer-access-after-deployment) and a reviewed workflow adaptation that omits that owner grant step. Administrator pre-grants alone do not make the default workflow's grant step succeed.

The project-administrator workflow uses environment `dev-deploy` and its dedicated OIDC user. It deploys and verifies source, then runs the object access handoff. It does not build models. [Configure the two workflows](github-actions.md).
