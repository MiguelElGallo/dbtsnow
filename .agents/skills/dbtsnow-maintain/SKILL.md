---
name: dbtsnow-maintain
description: Onboard to, navigate, modify, test, document, or review this dbtsnow repository's Python deployment wrapper, native dbt template, and GitHub workflows. Use for repository engineering and documentation work, not for generic dbt analytics projects or cloud execution alone.
---

# Maintain dbtsnow

Use the user's selected checkout, or find the root through ancestors of this SKILL.md. Require `pyproject.toml` naming `dbtsnow` and `scripts/dbt_native.py`. If the selected checkout fails, request its location instead of choosing another repo. Run commands from its root.

Read [README](../../../README.md) and [documentation home](../../../docs/index.md) for orientation; load deeper material only for the affected task. Use `rg` for filenames/text, then symbol-aware navigation such as code-index MCP if available. It is optional, not a runtime dependency.

## Find the change

| Area | Entry points in `scripts/dbt_native.py` |
| --- | --- |
| Configuration/wizard | `Config`, `validate_config`, `load_config`, `infer_values`, `wizard` |
| Packaging/native profile | `profile_role`, `native_profile`, `check_dependencies`, `prepare_source` |
| Identity/runtime/object checks | `connection_options`, `check_session`, `preflight`, `confirm_live` |
| Deployment/readback and access | `validate_deployment`, `deploy`, `project_access`, `verify_readback`, `verify_source`, `write_receipt` |
| Migration | `migrate` |
| Execution/state/retry | `execution_command`, `verify_execution_target`, `execute_project` |
| CLI surface | `parser`, `main` |

`tests/test_dbt_native.py` covers configuration, packaging, wizard, and deployment. `tests/test_live_version.py` covers LIVE migration/execution/state/retry behavior. `tests/test_roles.py` covers separated identities, strict generated operator-role expressions, ownership, and project-access handoff. `scripts/dbt_admin.py` provisions fresh resources; its tests cover offline planning, collisions, least-privilege SQL, and readback. `.github/workflows/checks.yml` runs local checks; `deploy.yml` and `operate.yml` are separately authenticated manual cloud jobs sharing concurrency. `example/` is the small native project; `deployment/example.json` uses placeholders, and real local configs are ignored.

`CLI_VERSION`, `DEFAULT_DBT_VERSION`, `pyproject.toml`, and `uv.lock` are authoritative for pinned versions. Account runtime availability remains a live preflight check. Do not infer current acceptance from screenshots or hardcode historical test counts into new guidance.

## Preserve the contracts

Before changing behavior, inspect its implementation, tests, and [command/configuration reference](../../../docs/reference/commands.md). Keep account/role/user identity, per-invocation secondary-role exclusion, independent project-admin/operator roles and workflows, separate native/model destinations, source restrictions, no-force updates, readback verification, and preview/apply boundaries. Split deployment disables auto compilation/build; administrator bootstrap must refuse collisions before writes. Add meaningful regression coverage for altered failure boundaries rather than weakening checks to satisfy a mock.

Read [role separation](../../../docs/explanation/role-separation.md) for administrator/project-admin/operator boundaries. Native deployment replaces LIVE artifacts. Retry depends on failed persisted state; state imports use a fixed successful-run locator. Core/Fusion retry target behavior differs. Consult [LIVE explanation](../../../docs/explanation/live-version.md) and the relevant how-to before changing those paths.

## Validate and document

Use the existing environment or `uv sync --frozen`, then run:

```sh
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run python -m unittest discover -s tests -v
uv run python scripts/dbt_native.py deploy --config deployment/example.json
```

For workflow edits, run `actionlint` when available. Apply these gates to code/workflow changes; documentation-only changes need relevant links, examples, and skill metadata checks instead of unnecessary cloud runs. Report unavailable checks rather than calling them passed.

Keep documentation in its Diátaxis home: `docs/tutorials/` for learning, `docs/how-to/` for tasks, `docs/reference/` for exact interfaces, `docs/explanation/` for rationale. Use short runnable steps and visible checkpoints as in the existing FastAPI-style guides. Older `docs/research.md`, `docs/live-version.md`, and `docs/github-actions.md` are compatibility links, not duplicate manuals. Request independent review for material behavior or documentation changes when the task calls for it.

For skill edits, validate frontmatter with the available skill-creator validator and independently test realistic agent behavior when deployment/operation instructions change. Keep skills concise and link canonical docs; do not duplicate the wrapper in new helpers.

Publish only when the user authorized it. Verify the configured remote, use a reviewed branch/PR and required checks, and guard a requested merge with the current head SHA. Publication authorization does not imply workflow dispatch or a cloud build. Report local/CI evidence separately from live account tests.
