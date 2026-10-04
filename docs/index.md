---
icon: lucide/house
hide:
  - navigation
  - toc
---

# Native dbt projects on Snowflake

Deploy a native Snowflake dbt project, then build and check your models. Separate users handle account setup, project updates, and daily runs.

[Preview the example](tutorials/preview-the-example.md){ .md-button .md-button--primary }
[Follow the setup lesson](tutorials/first-deployment.md){ .md-button }

## Choose your responsibility

<div class="grid cards role-cards" markdown>

-   :lucide-shield-check:{ .lg .middle } **Snowflake administrator**

    ---

    Prepare databases, schemas, roles, users, and access before the project team starts.

    [Prepare access](how-to/admin-setup.md)

-   :lucide-upload:{ .lg .middle } **Project administrator**

    ---

    Upload reviewed project updates, own the project, and give the operator access.

    [Deploy and hand off access](how-to/project-admin.md)

-   :lucide-play:{ .lg .middle } **Operator**

    ---

    Build models, retry failed runs, and check the results using your own login.

    [Run and retry](how-to/run-and-retry.md)

</div>

## How the setup works

The Snowflake administrator gives the project team access for two separate jobs:

```mermaid
flowchart TD
    A["Snowflake admin<br/>Prepares the setup"] -->|Gives access| P["Project admin<br/>Uploads project updates"]
    A -->|Gives access| O["Operator<br/>Runs the project and checks results"]
```

## Tutorials

Follow these lessons in order to preview a project, deploy it, and build a view.

1. [Preview the example](tutorials/preview-the-example.md) — inspect a model and create an offline deployment plan.
2. [Deploy your first project](tutorials/first-deployment.md) — set up fresh resources and use separate project administrator and operator logins.

## How-to guides

Use a guide to complete a specific task with your selected configuration.

| Task | Guide |
| --- | --- |
| Provision access and identities | [Administrator setup](how-to/admin-setup.md) |
| Deploy source and grant operator access | [Project administration](how-to/project-admin.md) |
| Deploy or run from GitHub | [Separate GitHub workflows and identities](how-to/github-actions.md) |
| Convert a numbered project to LIVE | [Migrate to LIVE](how-to/migrate-to-live.md) |
| Build models or recover a failed run | [Run and retry](how-to/run-and-retry.md) |
| Find execution history and logs | [Inspect runs](how-to/inspect-runs.md) |
| Build only changed models | [Baseline state](how-to/state-build.md) |
| Check source data age | [Source freshness](how-to/check-source-freshness.md) |
| Give an agent task-specific context | [Use the repository skills](how-to/use-agent-skills.md) |

## Reference

Look up exact settings, options, accepted values, and checks.

- [Configuration](reference/configuration.md)
- [Commands](reference/commands.md)

## Explanation

Understand the design and its tradeoffs.

- [Why deployment and operation use different roles](explanation/role-separation.md)
- [Why use Snowflake CLI and GitHub Actions?](explanation/deployment-choice.md)
- [Why LIVE changes deployment and recovery](explanation/live-version.md)
