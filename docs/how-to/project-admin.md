# Project administrator: deploy and hand off access

[Documentation](../index.md) · [Administrator setup](admin-setup.md)

Deploy a native project using the project administrator's own connection, then grant the operator access to run it. The configured `deployment_role` owns the project; `role` is the operator role used by its dbt profile.

## Check the handoff

Start with the configuration and identities prepared in the [first-deployment tutorial](../tutorials/first-deployment.md). Confirm these values in `deployment/dev.json`:

- The approved account, native project location, and model destination.
- Independent custom `deployment_role` and operator `role` values.
- Your deployment connection and, when configured, `deployment_user`.
- `auto_compile: false` for the separated roles.

Authenticate as the deployment user with its own credentials. Selecting the project administrator role inside a platform administrator's session does not test that user's access.

## Preview and deploy source

```sh
uv run python scripts/dbt_native.py deploy --config deployment/dev.json
```

Check the account, deployment identity/role, native object, and operator model destination in the offline plan. Then apply the same command:

```sh
uv run python scripts/dbt_native.py deploy --config deployment/dev.json --apply
```

A successful command prints `Verified deployment:` with the object, runtime, target, and LIVE version. Before reporting success, the wrapper checks ownership, deployed settings, the deployment receipt, and source hashes.

Split-role deployment skips compilation and dependency installation, and rejects `--build`. The [generated operator role](../reference/configuration.md#generated-operator-role) uses a fixed literal Jinja value so the pinned CLI can validate the profile without assuming the operator role. Keep the deployment user independent; the operator compiles and builds afterward.

For remote packages, arrange an approved external-access integration on the object and its required `USAGE` grants for both roles. An existing project must already be owned by the configured project administrator role. Have the platform owner review a different owner separately; deployment does not transfer ownership or recreate the project. [Migrate numbered objects](migrate-to-live.md) before deploying LIVE source.

## Grant operator access

After deployment, preview the handoff:

```sh
uv run python scripts/dbt_native.py project-access --config deployment/dev.json
```

Confirm the exact project and operator role, then apply it:

```sh
uv run python scripts/dbt_native.py project-access --config deployment/dev.json --apply
```

Expect `Verified project access:` followed by the operator role and project. The command verifies the owner, grants `USAGE` and `MONITOR` on this object, and reads those grants back. The Snowflake administrator supplies database, schema, warehouse, and data access separately.

In a managed-access schema, the schema owner or a role with `MANAGE GRANTS` must use the [administrator grant path](admin-setup.md#complete-project-and-viewer-access-after-deployment). The project owner alone cannot grant access there.

The operator can now [build the project](run-and-retry.md). For Snowsight, use an approved human viewer and [select the correct primary role](inspect-runs.md#set-up-snowsight-access).

## Update or recover source

Coordinate deployments with the operator: replacing LIVE source also removes the artifacts needed by retry. For a source fix, deploy the reviewed change and have the operator run a new build.

To restore earlier source, check out the approved earlier revision and deploy it with the same configured owner. This restores source, not model relations changed by executions. If deployment fails after making changes, inspect the object before another attempt; there is no automatic rollback.

## Use GitHub

The [deployment workflow](github-actions.md) uses environment `dev-deploy` and its dedicated project administrator OIDC user. It deploys and verifies source, then grants operator project access. The operator workflow runs models separately.

The shipped deployment workflow requires a regular object schema. For a managed-access schema, arrange administrator-owned grants and review a workflow adaptation that omits the project-owner `project-access` step. Pre-granting access does not let the project owner repeat that grant.
