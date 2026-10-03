# Configuration reference

[Documentation](../index.md) · [Command reference](commands.md)

The wrapper reads one JSON configuration per deployment destination. The wizard writes this file; `deploy`, `run`, and `migrate` read it. Authentication remains in the selected Snowflake CLI connection or the execution environment.

## Configuration fields

All fields in this table are required strings in the JSON file. Wizard suggestions do not make a field optional in a manually written file.

| Field | Meaning | Wizard suggestion |
| --- | --- | --- |
| `source` | Local dbt project directory. Relative paths start at the configuration file's directory. | `--source`, default `example`, resolved from the current directory when running the wizard. |
| `account` | Expected Snowflake account in `ORGANIZATION-ACCOUNT` form. | Selected local connection, otherwise the dbt profile. |
| `database` | Database containing the native object. | Selected connection, otherwise the dbt profile. |
| `object_schema` | Schema containing the native object. | Selected connection/profile schema, otherwise `PROJECTS`. |
| `project` | Native `DBT PROJECT` object name. | `name` in `dbt_project.yml`. |
| `role` | Explicit deployment and execution role. | Selected connection, otherwise the dbt profile. |
| `warehouse` | Existing warehouse for compilation and execution. | Selected connection, otherwise the dbt profile. |
| `model_database` | Database receiving model tables and views. | Original dbt profile database, otherwise the selected object database. |
| `model_schema` | Base schema receiving model tables and views. | Original dbt profile schema, otherwise the selected object schema. |
| `profile` | Profile name matching the literal `profile` in `dbt_project.yml`. | The project's `profile` value. |
| `target` | Target generated in the native profile. | Original profile target, otherwise `dev`. |

Optional fields have these defaults:

| Field | JSON type | Default | Meaning |
| --- | --- | --- | --- |
| `connection` | String or `null` | `null` | Local named connection. `null` selects a temporary connection; the provided GitHub workflow ignores a saved name. |
| `dbt_version` | String | `2.0.0-preview.210` | Exact native runtime version. Core `1.11.11` is also supported by this template. Apply checks account availability. |
| `external_access_integrations` | Array of strings | `[]` | Existing integrations permitted to download remote packages inside Snowflake. |
| `auto_compile` | Boolean | `true` | Compile on deployment; with an integration, run `deps` first. `false` skips both. |
| `default_writeback` | Boolean | `false` | Default persistence of generated `target` and log files into `LIVE`. |

Use JSON `true` and `false`, not strings such as `"false"` or numbers such as `0`. Unknown keys are rejected.

### Accepted names

Object, role, warehouse, model destination, and integration names must be simple unquoted Snowflake identifiers: start with a letter or `_`, then use letters, digits, `_`, or `$`, with a maximum of 255 characters. Quoted names and dotted names are rejected in these fields.

`profile`, `target`, and a non-null `connection` start with a letter or `_` and may then contain letters, digits, `_`, or `-`. The account uses two components separated by one `-`; each component contains only letters, digits, or `_`. Supply an organization/account identifier, not an account URL.

`dbt_version` must be an exact version such as `1.11.11` or `2.0.0-preview.210`; ranges and `latest` are rejected.

## Two destinations

Given `database: DEV_DBT_PRJ`, `object_schema: PROJECTS`, and `project: NATIVE_DBT_EXAMPLE`, the native object is:

```text
DEV_DBT_PRJ.PROJECTS.NATIVE_DBT_EXAMPLE
```

With `model_database: DEV_DBT_PRJ` and `model_schema: ANALYTICS`, its base model destination is:

```text
DEV_DBT_PRJ.ANALYTICS
```

dbt model settings or custom schema macros can produce other destinations. The native profile's base destination does not override model SQL or those dbt settings. See [first deployment](../tutorials/first-deployment.md).

The complete [example configuration](../../deployment/example.json) uses `"source": "../example"`. Stored at `deployment/example.json`, that path points to the repository's `example` directory, even when a later command runs from another directory.

## Wizard inference and output

Explicit string flags provide suggested values before inference. In interactive mode, Enter accepts the displayed suggestion; another answer replaces it. Explicit boolean flags apply directly without another prompt. `--non-interactive` accepts available suggestions and fails if required values remain missing.

The wizard reads `dbt_project.yml`, then searches for a profile in this order:

1. Project-root `dbt_projects_profiles.yml`.
2. Project-root `profiles.yml`.
3. `~/.dbt/profiles.yml`.

A selected `--connection` is read from `~/.snowflake/config.toml`. Its account, object location, role, and warehouse take precedence over profile suggestions. Model database/schema retain their profile suggestions. Only literal values are inferred; Jinja and environment expressions are not evaluated.

The wizard checks packaging locally, prints the proposed destinations and upload list, and saves JSON. It does not contact Snowflake or save a native profile into your source directory. `--output` defaults to `deployment/dev.json`; existing output files are never overwritten. Edit the existing JSON or choose a new output path.

Real `deployment/*.json` files are ignored by Git, except `deployment/example.json`. Commit a reviewed destination explicitly when configuring GitHub deployment.

## Uploaded files and limits

Each deployment prepares a temporary source directory containing:

- Root `dbt_project.yml`, plus any `packages.yml`, `dependencies.yml`, and `package-lock.yml`.
- `.sql`, `.yml`, `.yaml`, `.csv`, and `.md` files beneath the configured dbt model, macro, seed, test, analysis, snapshot, and documentation directories.
- A generated `dbt_projects_profiles.yml` containing this configuration's single profile and target.
- A generated `deployment_receipt.json` containing settings, provenance, and source hashes. That filename is reserved.

Personal profiles, hidden files, local credentials/configuration files outside the selected dbt paths, and existing `target`, `logs`, and `dbt_packages` directories are excluded. Symlinks and paths escaping the source are rejected.

This baseline rejects Python models, `env.yml`, uploaded `env_var()` references, local packages, cross-project dependencies, and HTTP(S) Git package URLs containing credentials. Remote packages require an existing external access integration; they are downloaded inside Snowflake when `deps` runs.

The file selection is not a general secret scanner. Credentials written directly in an included SQL, YAML, CSV, or Markdown file can still be uploaded. Review those source files before applying.

For artifact settings in practice, see [run and retry](../how-to/run-and-retry.md) and [state-based builds](../how-to/state-build.md). Legacy objects require a separate [migration to LIVE](../how-to/migrate-to-live.md).
