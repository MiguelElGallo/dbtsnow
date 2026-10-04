---
icon: lucide/bot
---

# Use the repository's agent skills

[Documentation](../index.md)

Choose a repository skill to give an agent the right starting point. The skills use the Python wrapper and canonical docs; they need no global installation.

## Open the checkout

Open a clone of `dbtsnow` as the agent's working directory. Codex discovers `.agents/skills` from the current directory through its repository ancestors. Use `/skills` or type `$` to select a skill; restart Codex if a newly added skill does not appear. See [Codex skill discovery](https://learn.chatgpt.com/docs/build-skills).

Other agent tools can read [AGENTS.md](https://github.com/MiguelElGallo/dbtsnow/blob/main/AGENTS.md) and the relevant `SKILL.md` directly. Automatic discovery depends on the client. Keep the skills with this checkout because their links and commands depend on its docs and code.

## Choose one task

| Skill | Use it for |
| --- | --- |
| [`dbtsnow-admin`](https://github.com/MiguelElGallo/dbtsnow/blob/main/.agents/skills/dbtsnow-admin/SKILL.md) | Administrator provisioning, independent roles/users, authentication handoff |
| [`dbtsnow-deploy`](https://github.com/MiguelElGallo/dbtsnow/blob/main/.agents/skills/dbtsnow-deploy/SKILL.md) | Project administrator configuration, source delivery, project access, migration, deployment workflow |
| [`dbtsnow-operate`](https://github.com/MiguelElGallo/dbtsnow/blob/main/.agents/skills/dbtsnow-operate/SKILL.md) | Operator runs, retry, logs, state, freshness, operation workflow |
| [`dbtsnow-maintain`](https://github.com/MiguelElGallo/dbtsnow/blob/main/.agents/skills/dbtsnow-maintain/SKILL.md) | Code navigation, changes, tests, documentation, review |

For an administrator setup preview, supply the selected configuration and the connection intended for a later apply:

```text
Use $dbtsnow-admin with deployment/dev.json to preview fresh-resource setup.
Plan two service users with separate public keys and independent roles.
My administrator connection is snowflake_admin with role ACCOUNTADMIN.
Keep this preview offline.
```

Expect the exact resources, roles, users, and grants in the plan. Bootstrap accepts public keys; keep private keys outside its input. Authenticate as each provisioned user for the [role handoff](admin-setup.md#validate-delegated-access).

For a first deployment preview:

```text
Use $dbtsnow-deploy to preview deployment/example.json.
Show both delegated roles and the native object/model destination. Keep this offline.
```

Expect an offline deployment plan. The sample has account placeholders; use a reviewed configuration for a real deployment. An offline preview cannot confirm account permissions or available runtimes.

For an operator investigation:

```text
Use $dbtsnow-operate with deployment/dev.json to investigate my failed build.
Check whether retry is possible. Use read-only inspection; do not execute or redeploy.
```

Expect the agent to check persisted failed artifacts and destination compatibility before proposing retry. Enabling writeback now cannot recover missing artifacts from the earlier failure.

For repository work:

```text
Use $dbtsnow-maintain to find how retry target verification works.
Explain the relevant code, tests, and documentation before changing anything.
```

Choose the skill for the next task when responsibility changes: administrator setup, project administrator deployment, then operator execution. The skill guides the work; your request determines which actions the agent may perform.
