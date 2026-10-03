# Deploy and operate with separate GitHub identities

[Documentation](../index.md) · [Role responsibilities](../explanation/role-separation.md)

Two manual, main-only workflows share a reviewed `deployment/dev.json` but use different Snowflake users and GitHub environments.

| Workflow | GitHub environment | Snowflake identity | Work performed |
| --- | --- | --- | --- |
| `.github/workflows/deploy.yml` | `dev-deploy` | Project administrator | Deploy/verify source, then grant the configured operator project access |
| `.github/workflows/operate.yml` | `dev-operate` | Operator | Compile, build, retry, or check freshness without redeploying |

The shipped deployment workflow requires a **regular object schema**, matching fresh administrator bootstrap. In a managed-access schema, use the schema-owner/administrator grant path and review an adapted deployment workflow that omits the project-owner `project-access` step. Administrator pre-grants do not give the project owner authority to repeat that grant.

Both use OIDC, temporary connections, and the shared concurrency group `native-dbt-dev`. A deployment cannot replace LIVE files while an operation from these workflows runs. Serialize local executions with the same resources too.

## Project administrator: review the configuration

Create or edit the complete configuration for the selected account and destinations. Set separate custom roles and `auto_compile: false`. For CI, set `deployment_user` and `operator_user` to the distinct OIDC usernames prepared below. Local key-pair test users can have different names; keep their local configuration separate when needed.

Preview locally:

```sh
uv run python scripts/dbt_native.py deploy --config deployment/dev.json
uv run python scripts/dbt_native.py project-access --config deployment/dev.json
uv run python scripts/dbt_native.py run --config deployment/dev.json --command build
```

Each preview is offline. The [configuration reference](../reference/configuration.md) defines role/user/connection selection. Workflows pass `--temporary-connection`, so saved local connection names are ignored.

Actual destination JSON files are ignored by default. After reviewing this exact account and destination, commit the credentials-free workflow configuration explicitly:

```sh
git add -f deployment/dev.json
```

Publishing the workflow/configuration and dispatching either cloud job are separate actions. The repository's normal checks do not deploy or execute dbt.

## Administrator: prepare Snowflake and two OIDC users

Complete [administrator setup](admin-setup.md) for databases/schemas and independent roles. Provision two fresh service users with different OIDC subjects, using your approved admin identity. Replace the usernames and `<OWNER>/<REPO>` with the reviewed values:

```sql
CREATE USER DBT_PROJECT_ADMIN_GITHUB
  TYPE = SERVICE
  WORKLOAD_IDENTITY = (
    TYPE = OIDC
    ISSUER = 'https://token.actions.githubusercontent.com'
    SUBJECT = 'repo:<OWNER>/<REPO>:environment:dev-deploy'
  )
  DEFAULT_ROLE = DBT_PROJECT_ADMIN
  DEFAULT_SECONDARY_ROLES = ();
GRANT ROLE DBT_PROJECT_ADMIN TO USER DBT_PROJECT_ADMIN_GITHUB;

CREATE USER DBT_OPERATOR_GITHUB
  TYPE = SERVICE
  WORKLOAD_IDENTITY = (
    TYPE = OIDC
    ISSUER = 'https://token.actions.githubusercontent.com'
    SUBJECT = 'repo:<OWNER>/<REPO>:environment:dev-operate'
  )
  DEFAULT_ROLE = DBT_OPERATOR
  DEFAULT_SECONDARY_ROLES = ();
GRANT ROLE DBT_OPERATOR TO USER DBT_OPERATOR_GITHUB;
```

Never assign the operator role to the deployment service user just to enable compilation. Deployment disables automatic compilation, and the operator workflow performs execution. Existing users or workload identities need review rather than recreation; each OIDC subject must identify only the intended service user.

The project owner can grant access in a regular schema. For a managed-access schema, arrange the [administrator-controlled project grants](admin-setup.md#complete-project-and-viewer-access-after-deployment) and the reviewed workflow adaptation described above. The default workflow's owner-controlled handoff will otherwise fail even after a successful source deployment.

Sources: [official OIDC action](https://github.com/snowflakedb/snowflake-actions), [workload identity federation](https://docs.snowflake.com/en/user-guide/workload-identity-federation), [dbt role separation](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-access-control).

## Administrator: configure the GitHub environments

Create **`dev-deploy`** and **`dev-operate`** in repository **Settings → Environments**. Restrict each environment to **`main`**; an environment OIDC subject identifies the environment rather than the branch. Add required reviewers according to your platform process.

Set these environment variables:

| Environment | Variable | Value |
| --- | --- | --- |
| Both | `SNOWFLAKE_ACCOUNT` | The same `ORGANIZATION-ACCOUNT` as the JSON configuration |
| `dev-deploy` | `SNOWFLAKE_PROJECT_ADMIN_USER` | `DBT_PROJECT_ADMIN_GITHUB`, matching `deployment_user` |
| `dev-operate` | `SNOWFLAKE_OPERATOR_USER` | `DBT_OPERATOR_GITHUB`, matching `operator_user` |

Roles, warehouse, native object, and model destination come from the reviewed configuration. If Snowflake network policies restrict inbound access, arrange the approved runner route before dispatch. No passwords or private keys belong in the tracked config.

## Project administrator: run deployment

Open **Actions**, select the deployment workflow, choose **Run workflow**, and select **`main`**. It runs local checks, authenticates as the deployment OIDC user, deploys source without compilation, verifies readback, and applies the operator's object-specific `USAGE`/`MONITOR` handoff.

There is no model-build input in this workflow. A successful source deployment is ready for the separately authenticated operator job. Source replacement removes prior LIVE retry artifacts; finish pending recovery before deploying.

## Operator: run the operation workflow

Choose the operation workflow on **`main`** and select a command:

| Input | Purpose |
| --- | --- |
| `command` | `build`, `compile`, `retry`, or `source-freshness` |
| `state_from` | Optional successful baseline `DB.SCHEMA.PROJECT` for build/compile |
| `select` | Optional single selector; not supported by retry |
| `defer` | Resolve unselected references using baseline state; requires `state_from` |
| `writeback` | Choose whether this run persists artifacts in LIVE |

Use writeback for a build whose failed state may need retry. State and deferral need the [baseline prerequisites](state-build.md), appropriate baseline access, and an isolated writable model destination. Retry requires compatible persisted failed artifacts and accepts neither selection nor state inputs. [Run/retry](run-and-retry.md) · [Freshness](check-source-freshness.md).

The operation job verifies deployed runtime/profile/model context before execution. A failed build can leave changed model relations; it does not roll back deployed source or data.

## Check the evidence

A passing PR check establishes repository validation only. An authenticated successful deployment establishes the deployment OIDC path; a separate successful operation establishes the operator OIDC path. Local service-user tests do not establish either GitHub OIDC path or a human browser login.

For source rollback, restore the reviewed earlier source/configuration through a PR, dispatch deployment, then have the operator validate it. This restores project source, not earlier model data.
