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
| [`dbtsnow-deploy`](../../.agents/skills/dbtsnow-deploy/SKILL.md) | Wizard configuration, offline previews, native deployment, GitHub setup |
| [`dbtsnow-operate`](../../.agents/skills/dbtsnow-operate/SKILL.md) | Existing project runs, retry, logs, state, freshness, migration |
| [`dbtsnow-maintain`](../../.agents/skills/dbtsnow-maintain/SKILL.md) | Code navigation, changes, tests, documentation, review |

For a first offline check, give the agent this prompt:

```text
Use $dbtsnow-deploy to preview deployment/example.json.
Show the native object and model destination. Keep this offline.
```

Expect a deployment plan and an explanation that account permissions and runtime
availability have not been verified. The placeholder account must not become a real destination.

For an existing project, supply your selected configuration:

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
For deployment or operation changes, have an independent agent try an offline
preview and a failure case in an isolated checkout. Check its actual commands and
results, not just whether it repeats the instructions.

Skill metadata and offline agent tests do not verify cloud authentication,
automatic discovery in every client, or a GitHub deployment. See
[validation evidence](../validation.md) for the repository's recorded system tests.
