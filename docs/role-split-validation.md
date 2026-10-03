# Corporate role split: validation

[Documentation](index.md) · [Plan and peer review](role-split-review.md)

This is historical validation evidence for the corporate-role change on 2026-10-03. Names below identify an isolated test fixture; they are not deployment defaults.

## Review and offline checks

Two independent plan reviews completed before implementation. Two independent implementation passes covered code, tests, administrator setup, deployment/operator jobs, documentation, skills, and user handoffs. The review record lists corrections and final checks. Offline gates passed: 133 unit tests, Ruff lint, formatting of 39 Python files, ty, and actionlint for all three workflows. Documentation validation checked 31 Markdown pages, 219 local links/anchors, 44 CLI examples, four skill packages, and their UI metadata.

## Fresh administrator setup

An explicitly selected administrator connection authenticated as `MIGUELP` / `ACCOUNTADMIN` in account `VAYNIMM-KP67615`. The bootstrap confirmed all requested names were absent before its first write, then created database `DBTSNOW_RBAC_TEST_20261003`, regular schemas `PROJECTS` and `ANALYTICS`, and these independent identities:

| Authenticated user | Its one assigned role | Responsibility |
| --- | --- | --- |
| `DBTSNOW_RBAC_ADMIN_SVC` | `DBTSNOW_RBAC_PROJECT_ADMIN` | Own and deliver native source |
| `DBTSNOW_RBAC_OPERATOR_SVC` | `DBTSNOW_RBAC_OPERATOR` | Execute and inspect models |

Both users are `TYPE = SERVICE`, with distinct RSA key pairs, their respective default role, and empty default secondary roles. Bootstrap readback verified exact grants, schema options, user defaults, one role per user, and public-key fingerprints. Private keys and CLI connections remain in ignored local storage with owner-only permissions.

Each subsequent persona authenticated with its own username and key, independently from the administrator. `CURRENT_USER()`, `CURRENT_ROLE()`, account identity, and `CURRENT_SECONDARY_ROLES()` were verified. With CLI `--secondary-roles NONE`, the account returned `{"roles":"","value":""}`; the checks accept that observed empty state and reject missing or active secondary-role metadata.

The existing `COMPUTE_WH` warehouse was selected. The isolated live config pinned supported runtime `2.0.0`; the original checkout's concurrent runtime edits were preserved. The repository default and sample were subsequently updated to `2.0.0` in this PR.

## Live acceptance

All operations below used the corresponding new user's own key-pair login, with secondary roles disabled. Administrator bootstrap was the only account-administration step.

| Persona | Allowed operation | Verified result |
| --- | --- | --- |
| Project administrator | Deploy the native example with automatic compilation disabled | Owner, runtime `2.0.0`, target `dev`, LIVE version, settings, receipt, and source hashes verified |
| Project administrator | Hand off the existing project | Exact-object operator `USAGE` and `MONITOR` verified |
| Operator | Build the example and query its view | One model and two tests succeeded; output `ID = 1`, `MESSAGE = Native dbt deployment works` |
| Operator | Compile separately | Native compile succeeded |
| Operator | Inspect a failed run | History columns, a nonempty log (10,450 characters), failed-run artifact locator, and persisted `run_results.json` accessible |
| Operator | Repair synthetic input and retry | One synthetic row updated; retry processed only the previously failed test, which passed |

The precreated `ANALYTICS` schema worked with the default bounded model grants. **No `CREATE SCHEMA`, permanent `CREATE STAGE`, extra role membership, or account-management privilege was added** to either delegated role.

### CLI profile compatibility

The first source-deployment attempt exposed a pinned Snowflake CLI validation step: a static profile role caused the CLI to attempt `USE ROLE DBTSNOW_RBAC_OPERATOR` as the project-administrator user even with `--no-auto-compile`. Two further independent reviews approved generating the fixed literal `{{ 'DBTSNOW_RBAC_OPERATOR' }}` in split mode. JSON configuration still accepts only validated identifiers; exact remote-profile and source-hash checks reject other expressions. Deployment then succeeded, and operator build/compile proved the fixed literal resolved to the intended runtime role. The administrator user was never assigned the operator role.

### Real failed-test recovery

The project administrator deployed an ignored local copy of the example whose view selects from operator-owned `ANALYTICS.RBAC_CONTROL`. The operator inserted one synthetic row with `ID = NULL`; its writeback build completed the view and uniqueness test but failed exactly the `not_null` test. The operator downloaded and inspected that failed invocation, then changed only the control row's ID to `1`. No deployment or intervening dbt execution occurred between the failed build and retry.

| Run | Query ID | Native state | Node result |
| --- | --- | --- | --- |
| Baseline example build | `01c77d4b-0000-7510-0000-48450003b942` | `SUCCESS` | One model, two tests succeeded |
| Separate compile | `01c77d4c-0000-7510-0000-48450003b9d2` | `SUCCESS` | Compilation succeeded |
| Synthetic failed build | `01c77d4f-0000-7510-0000-48450003bb5e` | `HANDLED_ERROR` | Model and uniqueness passed; one `not_null` failure |
| Retry after data repair | `01c77d53-0000-7510-0000-48450003bbf2` | `SUCCESS` | The one previously failed test passed |

Downloaded retry `run_results.json` contains exactly one node, with the same failed-test unique ID and status `pass`. The view now returns `ID = 1`, `MESSAGE = Synthetic retry validation`. The retained project uses this synthetic retry fixture; the repository's example source remains unchanged.

### Native permission boundaries

Ten distinct expected-denial probes passed with native permission errors, rather than relying only on wrapper refusals:

| Authenticated persona | Denied operations |
| --- | --- |
| Project administrator | Create a database; create a role; create a service user; build through the operator profile; read the existing operator model view |
| Operator | Create a database; create a role; create a service user; alter the existing project's runtime setting; grant project monitoring access |

Account/project mutations returned access-control or insufficient-privilege errors. Administrator execution returned Snowflake `003013 (42501)` because the requested operator role was not assigned to the executing user; data read was denied for the existing operator schema/view. Local regression tests also verify that wrong identity/owner/profile metadata stops before the requested operation.

The ignored local harness recorded 19 distinct SQL probes, including these ten denials and positive data/history/artifact checks. Deployment, access handoff, build, compile, failed build, and retry were separately exercised through the wrappers. Native failure details were inspected before the next mutation.

## Validation limits

The key-pair logins exercise newly created service users through Snowflake CLI. They do not prove human Snowsight login or GitHub OIDC authentication. Workflow linting and static tests validate the two-job boundary; no GitHub job was dispatched. Managed-access schemas use the documented administrator grant path; the shipped jobs and fresh bootstrap use regular schemas.

The fixture is retained for inspection. Future removal of its database, roles, users, and local keys is administrator work; deployments never perform account-resource cleanup.

## Default runtime update

The user requested stable `2.0.0` after the role split. The wrapper default, offline sample, current documentation, and Fusion retry regression now pin that exact version. Omitted-version configurations select stable Fusion; explicit Core pins remain unchanged. Both independent review passes checked this update and preserved the separated identities and historical preview evidence.

Read-only checks on 2026-10-03 confirmed that account `VAYNIMM-KP67615` supports `2.0.0` and both `DEV_DBT_PRJ.PROJECTS.NATIVE_DBT_EXAMPLE` and `DBTSNOW_RBAC_TEST_20261003.PROJECTS.NATIVE_DBT_EXAMPLE` already report runtime `2.0.0`, target `dev`, and `LIVE`. The role fixture was additionally checked through its dedicated project-administrator login. No cloud runtime change or source redeployment was needed.

The updated 134-test suite, Ruff lint/format, ty, workflow lint, documentation examples/links, and offline sample/wizard checks passed. The live build, compile, and real failed-test retry above already exercised `2.0.0`; those artifacts were preserved.
