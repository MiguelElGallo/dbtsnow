# Corporate role split: plan and review record

## Reviewed plan

The corporate workflow has three actors and two independent custom project roles. A Snowflake administrator provisions fresh databases, standard schemas, roles, and optional service identities. A project administrator owns and deploys the native project and hands its exact-object access to the operator. The operator compiles, builds, retries, checks freshness, and inspects runs through a separate authenticated user.

1. Preserve the existing `role` as the operator/profile role; add deployment role/connection and optional expected users. Keep legacy single-role configuration supported.
2. Force primary-role-only sessions for every Snowflake CLI command; verify account, role, expected user, and secondary-role context.
3. Separate the administrator bootstrap tool from native deployment/execution. Preview offline, reject all resource-name collisions before writes, accept public keys only, and verify exact resources, grants, user defaults, membership, and key fingerprints.
4. Disable automatic compilation in split-role mode and reject combined deployment/build. Preserve ownership, LIVE, runtime, profile, source-hash, and provenance checks.
5. Grant the configured operator only `USAGE` and `MONITOR` on the existing project. Standard schemas allow owner handoff; managed-access schemas require the schema owner or grant administrator.
6. Separate manual deployment and operator jobs, their OIDC users and environments; share one concurrency lock because deployment replaces LIVE retry artifacts.
7. Reorganize documentation and skills by actor with a concrete administrator-to-project-administrator-to-operator handoff. Migration belongs to the project administrator.
8. Create two fresh test users with separate key pairs and one role each. Authenticate independently as each; prove permitted operations and expected permission denials. First probe build with a precreated model schema and no `CREATE SCHEMA` grant.

## Plan peer review pass 1

An independent architecture reviewer checked Snowflake privilege, deployment, execution, and managed-schema documentation. Accepted corrections: move migration to project administration; use exact-project handoff instead of broad future grants; keep managed-schema grants with the administrator; decide runtime schema-creation privilege through a live minimal-grant test; document that service-user CLI acceptance does not prove browser sign-in.

## Plan peer review pass 2

A second reviewer checked identity isolation, privilege collisions, role inheritance, workflow concurrency, and public-key handling. Accepted corrections: use `--secondary-roles NONE` on every invocation rather than a separate SQL session; verify expected authenticated users; refuse existing users/roles/databases before bootstrap writes; verify owner before source replacement; separate OIDC environment subjects; share the deployment/operator lock; account for existing external-access integrations and source-data privileges.

Both plan passes completed before implementation. The separate-role design follows [Snowflake dbt access control](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-access-control), [grant authority](https://docs.snowflake.com/en/sql-reference/sql/grant-privilege), and [CLI secondary-role support](https://docs.snowflake.com/en/release-notes/clients-drivers/snowflake-cli-2026).

## Implementation review and evidence

Both independent implementation reviews covered the entire change: core deployment/execution, bootstrap, regressions, workflows, documentation, all four skills, and the authenticated-user test design. The administrator/workflow tests received independent review from two peers in addition to the author's review; core tests were independently reviewed by the second implementation reviewer and the parent agent.

| Finding | Resolution |
| --- | --- |
| Fresh setup readback was too shallow | Verify exact direct privilege sets, regular schema metadata, service-user defaults, one assigned role, and RSA fingerprint; reject extra or inherited grants. |
| Real `CURRENT_SECONDARY_ROLES()` metadata returned empty strings | Accept the verified `{"roles":"","value":""}` shape as disabled; reject absent/active context before writes. |
| Split config could name elevated built-in roles | Reject built-in elevated roles and `PUBLIC` only in split mode; retain legacy compatibility. |
| Pinned CLI tries `USE ROLE` on a static profile role even with compilation disabled | Two further review passes approved a generated fixed Jinja string literal; exact raw role/profile/hash verification rejects every other expression. Live deployment and operator execution prove resolution without assigning the operator role to the administrator. |
| Workflow owner grants fail in managed schemas | State that shipped jobs require regular schemas; managed schemas use administrator grants and a reviewed workflow adaptation. |
| Preview omitted identity context and tutorials had ambiguous routing | Show role, selected connection, expected user; route provisioning, migration/source, and operation to their respective actors. |
| Administrator capability checks could be misunderstood | Document required creation/grant authority and visibility, and explain that identity/collision checks do not prove every effective privilege or roll back DDL. |

Two realistic skill-behavior passes exercised fresh and existing administrator setup, split deployment, retry, managed-schema handoff, permission-denial diagnosis, migration, and repository review. Offline entrypoints made no cloud connections; read-only and publication constraints were preserved. Discoverability corrections added the fixed-profile helper/test pointers and made operator runtime reporting explicit.

Final code gates passed: **133 unit tests**, full Ruff lint and formatting (39 Python files), ty, and actionlint for all three workflows. Documentation checks parsed 44 wrapper command examples and validated all four skill packages and UI metadata. Offline administrator, deployment, project-access, and operator previews completed without cloud connections. Live test evidence is kept in [role-split validation](role-split-validation.md). The original checkout's concurrent runtime-version edits are preserved; this change is isolated in its own worktree.
