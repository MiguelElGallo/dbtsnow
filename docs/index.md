# Native dbt projects with separate roles

Choose the part of the setup you own. Platform administration happens first; the project administrator and operator then work through separate identities.

| Who you are | Your tasks | Start here |
| --- | --- | --- |
| Snowflake administrator | Provision database, schemas, two roles, user assignments, and authentication | [Administrator setup](how-to/admin-setup.md) |
| dbt project administrator | Deploy and verify source, own the object, grant operator project access, migrate legacy objects | [Project administration](how-to/project-admin.md) |
| dbt operator | Compile/build, retry failed runs, check sources, inspect history and logs | [Run and retry](how-to/run-and-retry.md) · [Inspect runs](how-to/inspect-runs.md) |

## Learn the full handoff

1. [Preview the example](tutorials/preview-the-example.md) without a Snowflake connection.
2. [Deploy your first project](tutorials/first-deployment.md) using administrator setup and two dedicated authenticated test users.
3. [Configure GitHub](how-to/github-actions.md) with separate deployment and operation workflows.

The [role explanation](explanation/role-separation.md) shows what each role can do and why the two delegated roles remain independent.

## Complete a task

| Task | Guide |
| --- | --- |
| Prepare access or additional source/model schemas | [Administrator setup](how-to/admin-setup.md) |
| Update source and hand off access | [Project administration](how-to/project-admin.md) |
| Convert a numbered project | [Migrate to LIVE](how-to/migrate-to-live.md) |
| Build or recover a failed run | [Run and retry](how-to/run-and-retry.md) |
| Find runs and logs | [Inspect runs](how-to/inspect-runs.md) |
| Build only changed models | [Baseline state](how-to/state-build.md) |
| Check source data age | [Source freshness](how-to/check-source-freshness.md) |
| Work with an agent | [Choose the matching skill](how-to/use-agent-skills.md) |

## Reference and explanation

- [Configuration](reference/configuration.md) and [commands](reference/commands.md): exact fields, flags, checks, and compatibility.
- [Roles and identities](explanation/role-separation.md): boundaries and handoff.
- [Deployment choice](explanation/deployment-choice.md): CLI, SQL, Snowsight, and DCM.
- [LIVE behavior](explanation/live-version.md): source replacement, state, migration, and rollback.
- [Validation](validation.md) and [documentation review](documentation-review.md): recorded checks and their limits.

[Historical screenshots](screenshots/README.md) show the earlier combined-role implementation. They are examples rather than current role setup instructions. Tutorials, task guides, reference, and explanation follow [Diátaxis](https://diataxis.fr/start-here/).
