# Command reference

[Documentation](../index.md) · [Configuration reference](configuration.md)

Run commands from the repository root:

```sh
uv run python scripts/dbt_native.py --help
```

Append `--help` to a subcommand for its parser options. Applied operations require Snowflake CLI `3.28.0` on `PATH` and the configured account, warehouse, and privileges.

## Operation overview

| Command | Default behavior | With `--apply` |
| --- | --- | --- |
| `wizard` | Validate a local upload plan and save JSON. | No `--apply` option. |
| `deploy` | Prepare and display the upload plan without connecting. | Create/update native source and settings, then verify readback. |
| `migrate` | Display migration scope without connecting. | Migrate only the configured legacy object to `LIVE`; an already-LIVE object is a no-op. |
| `run` | Display execution settings without connecting. | Execute the selected native dbt command without redeploying source. |

`wizard` writes a local file. The other previews make no Snowflake connection or cloud changes. A preview does not verify authentication, permissions, or account runtime availability.

## Wizard

```sh
uv run python scripts/dbt_native.py wizard --source example --output deployment/dev.json
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--source PATH` | `example` | dbt source directory, relative to the current directory. |
| `--output PATH` | `deployment/dev.json` | New JSON configuration. Existing files are rejected. |
| `--connection NAME` | Ask interactively | Read a local named connection for suggestions; blank selects a temporary connection. |
| `--non-interactive` | Disabled | Use explicit/inferred values without prompts; fail on missing required values. |
| `--external-access-integration NAME` | None | Existing integration. Repeat the flag for multiple names. |
| `--default-writeback` / `--no-default-writeback` | Disabled | Persist generated run artifacts in `LIVE` by default. |
| `--auto-compile` / `--no-auto-compile` | Enabled | Compile during deployment. |

The remaining value options correspond to [configuration fields](configuration.md): `--account`, `--database`, `--object-schema`, `--project`, `--role`, `--warehouse`, `--model-database`, `--model-schema`, `--profile`, `--target`, and `--dbt-version`.

Interactive boolean answers are `yes`, `no`, `y`, or `n`; Enter accepts the shown default. The wizard prints the saved path and does not modify `dbt_project.yml` or personal profiles.

## Shared operation flags

These flags apply to `deploy`, `migrate`, and `run`:

| Option | Required/default | Meaning |
| --- | --- | --- |
| `--config PATH` | Required | JSON configuration to load. |
| `--apply` | Disabled | Enable the cloud operation. |
| `--temporary-connection` | Disabled | Ignore the saved local connection name and use runtime authentication, such as GitHub OIDC. |

Destination, role, and warehouse remain explicit from the configuration, including with a temporary connection. There is no password or private-key option in this wrapper.

## Deploy

```sh
uv run python scripts/dbt_native.py deploy --config deployment/dev.json --apply
```

`--build` optionally runs `dbt build` after deployment and source verification. It writes model relations and runs tests. Without `--apply`, `--build` only previews that intention.

Compilation and writeback settings come from the configuration. Deployment never uses `--force` and rejects an existing legacy object. Applied deployment verifies identity and runtime support, downloads the source and receipt, checks hashes, and checks the available native metadata. In GitHub, the receipt records the exact clean checked-out commit.

Deployment replaces all `LIVE` files, including prior persisted execution artifacts. It can change object settings before a later failure; a failed model build can leave changed relations. There is no automatic rollback. See [first deployment](../tutorials/first-deployment.md).

## Migrate

```sh
uv run python scripts/dbt_native.py migrate --config deployment/dev.json --apply
```

Migration checks the selected account/role, the existing object's version, and the resulting `LIVE` version, with location and preserved metadata checked where exposed. It never enables account behavior bundles. Numbered source versions become inaccessible after migration; execution history remains. See [migrate to LIVE](../how-to/migrate-to-live.md).

## Run

```sh
uv run python scripts/dbt_native.py run --config deployment/dev.json --command build --apply
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--command` | `build` | One of `build`, `compile`, `retry`, or `source-freshness`. |
| `--writeback` / `--no-writeback` | Configuration default | Override artifact persistence for this execution. |
| `--state-from DB.SCHEMA.PROJECT` | None | Import a fixed artifact path from that project's last successful `build` or `run`. |
| `--select SELECTOR` | None | Pass one literal dbt selector, such as `state:modified+` or `example_model`. |
| `--defer` | Disabled | Resolve unselected references against state; requires `--state-from`. |

Applied runs require an existing `LIVE` object. The wrapper verifies its runtime, downloaded project profile name, and selected profile's base database/schema/role/warehouse against the configuration before executing.

### State and selection

State imports are allowed for `build` and `compile`. The source object name must have exactly three simple identifiers. State must be a populated successful build/run artifact set from the last seven days; the caller needs `MONITOR` on the baseline object. A missing state locator stops execution. The resolved locator is pinned so a concurrent baseline run cannot change the imported path.

Selectors may contain letters, digits, underscores, `.`, `*`, `:`, `+`, `,`, `@`, `/`, and `-`; spaces, shell syntax, and a leading `-` are rejected. The wrapper does not validate whether a selector matches a model.

State and deferral require a separate writable CI model destination when used for validation. See [state-based builds](../how-to/state-build.md).

### Retry and freshness

Retry accepts no selector or state import. It reads the prior `target/run_results.json` in `LIVE`; the failed invocation must have persisted those artifacts. Recorded target/profile mismatches stop execution.

- Fusion `2.*` retry receives the configured `--target` and `--profile` explicitly, including when artifacts omit them.
- Core `1.*` retry inherits its target. A missing/different recorded target is rejected; a recorded profile must match. If its profile is absent, the deployed profile file must contain only the configured profile.

Enabling writeback only on retry cannot recover missing failed-run artifacts. A pinned Fusion retry with no failed nodes returns an error. See [run and retry](../how-to/run-and-retry.md).

`source-freshness` maps to native `source freshness`. It supports selection and writeback overrides, but no state import or deferral. The project must define dbt sources to assess freshness.

## Output and failures

Successful applied runs print native command output. Deployment reports verified source/runtime/target; migration reports a verified migration or already-LIVE no-op.

Wrapper success returns exit code `0`; handled configuration, packaging, connection, or verification failures return `1` and an `Error:` message on stderr. Parser errors return `2`. CLI errors are summarized without echoing potentially sensitive error output. A nonzero exit does not undo an already-applied deployment or model changes.

Failure inspection uses scoped Snowflake execution history and query logs; [inspect runs](../how-to/inspect-runs.md) contains the retrieval commands.
