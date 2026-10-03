# Native dbt deployment, step by step

Deploy a dbt project as a Snowflake object, then build its models when you choose. Start with the included one-view example and use the task guides as your project grows.

## Start here

1. [Preview the example](tutorials/preview-the-example.md). Learn the deployment plan without a Snowflake account.
2. [Deploy your first project](tutorials/first-deployment.md). Use the wizard, deploy, build, and check the result in a development database.
3. [See the screenshot walkthrough](screenshots/README.md). Follow the recorded wizard, Snowsight project, runs, and GitHub checks.

## Complete a task

| I want to… | How-to guide |
| --- | --- |
| Deploy from GitHub Actions | [Configure OIDC and run the workflow](how-to/github-actions.md) |
| Migrate an existing numbered project | [Migrate to LIVE](how-to/migrate-to-live.md) |
| Build models or retry a failed run | [Run and retry](how-to/run-and-retry.md) |
| Build only changed models | [Use baseline state](how-to/state-build.md) |
| Check whether source data is recent | [Check source freshness](how-to/check-source-freshness.md) |
| Find run details and logs | [Inspect runs](how-to/inspect-runs.md) |
| Give an agent the right repository context | [Use the agent skills](how-to/use-agent-skills.md) |

## Look up a setting

- [Configuration](reference/configuration.md): fields, defaults, inference, and supported project files.
- [Commands](reference/commands.md): flags, previews, execution, and failure behavior.

## Understand the design

- [Why CLI and GitHub Actions?](explanation/deployment-choice.md): SQL, Snowsight, and DCM compared.
- [What does LIVE change?](explanation/live-version.md): source updates, artifacts, migration, and rollback.
- [Validation evidence](validation.md): peer reviews, local checks, real trial executions, and their limits.
- [Documentation review](documentation-review.md): independent structure, clarity, and source-accuracy passes.

The documentation separates learning, task instructions, reference, and explanation using [Diátaxis](https://diataxis.fr/start-here/). Its short steps, runnable examples, and visible checkpoints follow the writing approach of [FastAPI's tutorial](https://fastapi.tiangolo.com/tutorial/first-steps/).
