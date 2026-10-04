---
icon: lucide/workflow
---

# Deploy and operate with separate GitHub identities

[Documentation](../index.md) · [Role responsibilities](../explanation/role-separation.md)

Configure two manual workflows with separate Snowflake users and GitHub environments. Both read the reviewed `deployment/dev.json`.

| Workflow | GitHub environment | Snowflake identity | Work performed |
| --- | --- | --- | --- |
| `.github/workflows/deploy.yml` | `dev-deploy` | Project administrator | Deploy and verify source, then grant operator project access |
| `.github/workflows/operate.yml` | `dev-operate` | Operator | Compile, build, retry, or check freshness |

The deployment workflow requires a regular object schema. For managed access, arrange [administrator-owned project grants](admin-setup.md#complete-project-and-viewer-access-after-deployment) and adapt the workflow to omit its project-owner `project-access` step. Pre-granted access does not authorize the owner to repeat that grant.

Both workflows share concurrency group `native-dbt-dev` so deployment cannot replace LIVE files during an operation. Coordinate local runs using the same project too.

## Project administrator: review the configuration

Prepare a complete configuration for the approved account and destinations. Use independent custom roles, `auto_compile: false`, and the two OIDC usernames provisioned below. These fields belong in the complete configuration:

```json
{
  "role": "DBT_OPERATOR",
  "deployment_role": "DBT_PROJECT_ADMIN",
  "operator_user": "DBT_OPERATOR_GITHUB",
  "deployment_user": "DBT_PROJECT_ADMIN_GITHUB",
  "auto_compile": false
}
```

Preview the deployment, access handoff, and operator build locally:

```sh
uv run python scripts/dbt_native.py deploy --config deployment/dev.json
uv run python scripts/dbt_native.py project-access --config deployment/dev.json
uv run python scripts/dbt_native.py run --config deployment/dev.json --command build --no-writeback
```

Confirm the same account/project, the two distinct users, and the intended model destination across the plans. These previews make no Snowflake connection. Workflows use `--temporary-connection`, so saved local connection names are ignored. See the [configuration reference](../reference/configuration.md) for the remaining fields.

Destination configurations are ignored by default. Explicitly add the reviewed, credentials-free file for the workflow:

```sh
git add -f deployment/dev.json
```

Commit source and configuration through your normal PR process. Repository checks run locally; dispatching either workflow is the step that deploys or executes in Snowflake.

## Administrator: prepare Snowflake and two OIDC users

Complete [administrator setup](admin-setup.md) for the databases, schemas, and independent roles. Using your approved administrator identity, provision two fresh service users. Replace the usernames and `<OWNER>/<REPO>` with the reviewed values:

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

Review existing users or workload identities separately. Each subject must identify only its intended service user, and the deployment user must have only its project administrator role. Operators execute through the other user.

The [Snowflake OIDC action](https://github.com/snowflakedb/snowflake-actions) obtains the workflow identity used by [workload identity federation](https://docs.snowflake.com/en/user-guide/workload-identity-federation).

## Administrator: configure the GitHub environments

In repository **Settings → Environments**, create **`dev-deploy`** and **`dev-operate`**. Restrict each to **`main`** and add required reviewers according to your platform process. An environment OIDC subject identifies the environment, so the branch restriction belongs in these GitHub settings.

Set these environment variables:

| Environment | Variable | Value |
| --- | --- | --- |
| Both | `SNOWFLAKE_ACCOUNT` | The same `ORGANIZATION-ACCOUNT` as the configuration |
| `dev-deploy` | `SNOWFLAKE_PROJECT_ADMIN_USER` | `DBT_PROJECT_ADMIN_GITHUB`, matching `deployment_user` |
| `dev-operate` | `SNOWFLAKE_OPERATOR_USER` | `DBT_OPERATOR_GITHUB`, matching `operator_user` |

The configuration supplies the roles, warehouse, project, and model destination. Keep passwords and private keys out of it. If a Snowflake network policy restricts access, arrange the approved runner route before dispatching.

## Project administrator: run deployment

Open **Actions**, select **Project administrator - deploy native dbt**, choose **Run workflow**, and select **`main`**.

The job checks the repository, authenticates as the project administrator, deploys without compilation, verifies source, and grants the operator `USAGE`/`MONITOR` on the project. Check for `Verified deployment:` and `Verified project access:` in the deployment step before handing the project to the operator.

Finish pending retry recovery before deployment: replacing LIVE source removes earlier retry artifacts.

## Operator: run the operation workflow

In **Actions**, select **Operator - run native dbt**, choose **Run workflow** on **`main`**, and set the inputs:

| Input | Purpose |
| --- | --- |
| `command` | `build`, `compile`, `retry`, or `source-freshness` |
| `state_from` | Optional successful baseline `DB.SCHEMA.PROJECT` for build/compile |
| `select` | Optional single selector; retry accepts no selection |
| `defer` | Use baseline relations for unselected references; requires `state_from` |
| `writeback` | Persist this run's artifacts in LIVE |

Choose writeback for a build whose failure may need retry. [State comparisons](state-build.md) require a successful baseline, baseline access, and an isolated writable model destination. Retry requires persisted compatible failed artifacts and accepts neither selection nor state inputs. See [run/retry](run-and-retry.md) and [freshness](check-source-freshness.md) for those tasks.

The job authenticates as the operator and checks the deployed runtime, profile, and model destination before execution.

## Check the evidence

Check the operation step for native dbt output and the command's completion message. If it fails, use [run history and logs](inspect-runs.md) to identify the failed invocation. If identity verification fails, compare the environment username with the corresponding configured `deployment_user` or `operator_user`.

For source rollback, restore the reviewed earlier source/configuration through a PR, dispatch deployment, then have the operator validate it. Neither a failed build nor source rollback restores earlier model data.
