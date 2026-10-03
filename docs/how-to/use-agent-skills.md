# Use the repository's agent skills

[Documentation](../index.md)

Use these skills to give an agent the right starting point for this repository.
They reuse the Python wrapper and canonical docs; no global skill installation is needed.

## Open the checkout

Open a clone of `dbtsnow` as the agent's working directory. Codex discovers
`.agents/skills` from the current directory through its repository ancestors.
Use `/skills` or type `$` to select a skill; restart Codex if a newly added skill
does not appear. [Codex skill discovery](https://learn.chatgpt.com/docs/build-skills).

Other agent tools can read [AGENTS.md](../../AGENTS.md) and the relevant `SKILL.md`
directly. Automatic discovery depends on the client. Keep the skill with this
checkout: its relative links and commands depend on the repository's docs and code.

## Choose one task

| Skill | Use it for |
| --- | --- |
| [`dbtsnow-admin`](../../.agents/skills/dbtsnow-admin/SKILL.md) | Snowflake administrator provisioning, independent roles/users, test-user authentication handoff |
| [`dbtsnow-deploy`](../../.agents/skills/dbtsnow-deploy/SKILL.md) | Project administrator configuration, source delivery, project-access grants, migration, deployment workflow |
| [`dbtsnow-operate`](../../.agents/skills/dbtsnow-operate/SKILL.md) | Operator runs, retry, logs, state, freshness, operation workflow |
| [`dbtsnow-maintain`](../../.agents/skills/dbtsnow-maintain/SKILL.md) | Code navigation, changes, tests, documentation, review |

For administrator setup, supply the selected account/config and administrative connection:

```text
Use $dbtsnow-admin with deployment/dev.json to preview fresh-resource setup.
Use my selected snowflake_admin connection and ACCOUNTADMIN role for the planned apply.
Plan two dedicated test users with separate public keys. Keep this preview offline.
```

The agent should report the exact resources/role/user/grant scope and retain the administrator-to-project-admin-to-operator handoff. It should not create identities during a preview, inherit one delegated role from the other, or accept a private key as bootstrap input.

For a project administrator's first offline check, give the agent this prompt:

```text
Use $dbtsnow-deploy to preview deployment/example.json.
Show both delegated roles and the native object/model destination. Keep this offline.
```

Expect a deployment plan and an explanation that account permissions and runtime
availability have not been verified. The placeholder account must not become a real destination.

For an operator investigation, supply the selected configuration:

```text
Use $dbtsnow-operate with .local/dev.json to investigate my failed build.
Check whether retry is possible. Use read-only inspection; do not execute or redeploy.
```

The agent should inspect failed-run persistence and destination compatibility before
proposing retry. If artifacts are missing, enabling writeback now cannot recover them.

For repository work:

```text
Use $dbtsnow-maintain to find how retry target verification works.
Explain the relevant code, tests, and documentation before changing anything.
```

## Check a skill change

Keep instructions short and link the applicable guide. Validate each skill's YAML
frontmatter and `agents/openai.yaml` metadata with your available skill tooling.
For administrator, deployment, or operation changes, have an independent agent try an offline
preview and a failure case in an isolated checkout. Check its actual commands and
results, not just whether it repeats the instructions.

Skill metadata and offline agent tests do not verify cloud authentication,
automatic discovery in every client, or a GitHub deployment. See
[validation evidence](../validation.md) for the repository's recorded system tests.
