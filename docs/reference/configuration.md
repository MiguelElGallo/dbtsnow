# Configuration reference

[Documentation](../index.md) · [Command reference](commands.md)

One JSON configuration describes the project destination and both delegated identities. The wizard writes it; administrator bootstrap, `deploy`, `project-access`, `run`, and `migrate` read it. Authentication remains in selected Snowflake CLI connections or the execution environment. [Role responsibilities](../explanation/role-separation.md).

## Configuration fields

All fields in this table are required strings in the JSON file. Wizard suggestions do not make a field optional in a manually written file.

| Field | Meaning | Wizard suggestion |
| --- | --- | --- |
| `source` | Local dbt project directory. Relative paths start at the configuration file's directory. | `--source`, default `example`, resolved from the current directory when running the wizard. |
| `account` | Expected Snowflake account in `ORGANIZATION-ACCOUNT` form. | Selected local connection, otherwise the dbt profile. |
| `database` | Database containing the native object. | Selected connection, otherwise the dbt profile. |
| `object_schema` | Schema containing the native object. | Selected connection/profile schema, otherwise `PROJECTS`. |
| `project` | Native `DBT PROJECT` object name. | `name` in `dbt_project.yml`. |
| `role` | Operator calling role and role in the generated native profile. Also the deployment role in legacy single-role configurations. | Selected operator connection, otherwise the dbt profile. |
| `warehouse` | Existing warehouse for compilation and execution. | Selected connection, otherwise the dbt profile. |
| `model_database` | Database receiving model tables and views. | Original dbt profile database, otherwise the selected object database. |
| `model_schema` | Base schema receiving model tables and views. | Original dbt profile schema, otherwise the selected object schema. |
| `profile` | Profile name matching the literal `profile` in `dbt_project.yml`. | The project's `profile` value. |
| `target` | Target generated in the native profile. | Original profile target, otherwise `dev`. |

Optional fields have these defaults:

| Field | JSON type | Default | Meaning |
| --- | --- | --- | --- |
| `connection` | String or `null` | `null` | Operator local connection. No name selects runtime authentication; both GitHub workflows ignore local names. |
| `deployment_role` | String or `null` | `null` | Project administrator calling role for deploy, migration, and project access. `null` uses `role`. |
| `deployment_connection` | String or `null` | `null` | Project administrator connection. `null` falls back to `connection`; `--temporary-connection` ignores both names. |
| `operator_user` | String or `null` | `null` | Expected authenticated `CURRENT_USER()` for operation. |
| `deployment_user` | String or `null` | `null` | Expected authenticated user for project administration. In legacy mode without a separate deployment connection, omission falls back to `operator_user`. |
| `dbt_version` | String | `2.0.0` | Exact native runtime version. Core `1.11.11` is also supported by this template. Apply checks account availability. |
| `external_access_integrations` | Array of strings | `[]` | Existing integrations permitted to download remote packages inside Snowflake. |
| `auto_compile` | Boolean | `true` in manually supplied JSON when omitted | Compile on deployment; with an integration, run `deps` first. `false` skips both. Split-role deployment requires `false`; the wizard suggests `false` for separated roles. |
| `default_writeback` | Boolean | `false` | Default persistence of generated `target` and log files into `LIVE`. |

Use JSON `true` and `false`, not strings such as `"false"` or numbers such as `0`. Unknown keys are rejected.

### Identity selection and split-role mode

| Operation | Calling role | Local connection | Expected user |
| --- | --- | --- | --- |
| Administrator bootstrap | `--admin-role` | `--admin-connection` | Administrator-selected authentication; account/role verified |
| `deploy`, `migrate`, `project-access` | `deployment_role`, otherwise `role` | `deployment_connection`, otherwise `connection` | `deployment_user`, with the legacy fallback described above |
| `run` | `role` | `connection` | `operator_user` |

The generated native profile always uses `role`, including when another role deploys it. Authenticated invocations specify `--secondary-roles NONE`; account/primary-role and available expected-user checks fail before the requested write if they differ.

Different case-insensitive `deployment_role` and `role` values select split-role mode. Set `auto_compile: false`, use two independent custom roles, and use distinct expected users. Split configurations reject built-in elevated roles and `PUBLIC` for either delegated role at configuration validation; legacy single-role configurations retain their previous role compatibility. If both expected users are provided, configuring the same user in split mode is rejected. Expected usernames are optional for compatibility; the example supplies distinct project administrator and operator usernames.

Without `deployment_role`, the original single-role behavior remains available. It can compile during deployment and use `deploy --build`; adopting new roles or transferring an existing object's ownership is a separate administrator change. The wrapper performs no automatic IAM migration.

### Accepted names

Object, role, warehouse, model destination, and integration names must be simple unquoted Snowflake identifiers: start with a letter or `_`, then use letters, digits, `_`, or `$`, with a maximum of 255 characters. Quoted names and dotted names are rejected in these fields.

`profile`, `target`, and non-null connection names start with a letter or `_` and may then contain letters, digits, `_`, or `-`. The account uses two components separated by one `-`; each component contains only letters, digits, or `_`. Supply an organization/account identifier, not an account URL.

`dbt_version` must be an exact version such as `1.11.11` or `2.0.0`; ranges and `latest` are rejected.

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

The wizard accepts `--deployment-role`, `--deployment-connection`, `--deployment-user`, and `--operator-user` as well as the operator settings. Explicit string flags provide suggested values before inference. In interactive mode, Enter accepts the displayed suggestion; another answer replaces it. Explicit boolean flags apply directly without another prompt. `--non-interactive` accepts available suggestions and fails if required values remain missing.

The wizard reads `dbt_project.yml`, then searches for a profile in this order:

1. Project-root `dbt_projects_profiles.yml`.
2. Project-root `profiles.yml`.
3. `~/.dbt/profiles.yml`.

A selected `--connection` is read from `~/.snowflake/config.toml`. Its account, object location, role, and warehouse take precedence over profile suggestions. Model database/schema retain their profile suggestions. Only literal values are inferred; Jinja and environment expressions are not evaluated.

The wizard checks packaging locally, prints the proposed destinations and upload list, and saves JSON. It does not contact Snowflake or save a native profile into your source directory. `--output` defaults to `deployment/dev.json`; existing output files are never overwritten. Edit the existing JSON or choose a new output path.

Real `deployment/*.json` files are ignored by Git, except `deployment/example.json`. Commit a reviewed destination explicitly when configuring GitHub deployment. The included example selects separate roles with placeholder expected users; it remains an offline example until the account and resource names are replaced and administrator setup is complete.

## Generated operator role

For separate roles, the wrapper writes the operator role as a fixed Jinja string in the generated native profile, for example:

```yaml
role: "{{ 'DBT_OPERATOR' }}"
```

Keep JSON `role` as a simple identifier; the wrapper generates this expression. Snowflake CLI 3.28.0 attempts `USE ROLE` for static profile roles during deployment even when automatic compilation is disabled. Its supported templated-role path skips that client check. The fixed expression preserves the configured operator without assigning its role to the deployment user or reading environment variables. [Pinned CLI implementation](https://github.com/snowflakedb/snowflake-cli/blob/v3.28.0/src/snowflake/cli/_plugins/dbt/manager.py#L624-L634).

In split mode, execution verification requires this exact generated uppercase constant, including its fixed expression syntax; a static role or another expression is rejected. Legacy single-role profiles retain their static role value. Source hashes still verify the uploaded profile. Snowflake documents Jinja-based [profile roles](https://docs.snowflake.com/en/user-guide/data-engineering/dbt-projects-on-snowflake-environment-variables#configure-your-profile-file); this wrapper limits that mechanism to its generated constant.

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
