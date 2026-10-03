# dbtsnow

Deploy a native Snowflake `DBT PROJECT` with a small setup wizard and GitHub Actions.

**Recommendation:** use Snowflake CLI with GitHub Actions and OIDC. SQL and Snowsight also support deployment. DCM's current supported entity list does not include `DBT PROJECT`. See the [research and peer review](docs/research.md).

## Try it locally

You need [uv](https://docs.astral.sh/uv/getting-started/installation/), a working Snowflake CLI connection, and an existing database, schemas, warehouse, and suitable role.

If Snowflake CLI is not installed, run `uv tool install snowflake-cli==3.28.0`. Configure and test your connection using [Snowflake's connection guide](https://docs.snowflake.com/en/developer-guide/snowflake-cli/connecting/connect).

```sh
uv run python scripts/dbt_native.py wizard --source example --output deployment/dev.json
uv run python scripts/dbt_native.py deploy --config deployment/dev.json
uv run python scripts/dbt_native.py deploy --config deployment/dev.json --apply
```

The wizard infers the project and connection settings it can find, then asks for missing values. Use the canonical `ORGANIZATION-ACCOUNT` account identifier for identity verification. Review the saved destination before deploying. The second command previews the deployment; `--apply` creates or updates the native object and verifies the result.

**Two locations matter:** the object database/schema stores the deployed project; the model database/schema receives its tables and views. They can be different. The native profile contains runtime settings, without copying credentials from your personal profile. Review your source files too: credentials written directly into SQL or YAML would still be uploaded.

To also build models and run their dbt tests:

```sh
uv run python scripts/dbt_native.py deploy --config deployment/dev.json --apply --build
```

`--build` writes model relations. Deploying the object alone uploads and compiles its project; it does not run a model build.

## Use GitHub Actions

The deployment workflow reads `deployment/dev.json`, targets the GitHub environment `dev`, and runs manually from `main`. Configure its Snowflake OIDC user and GitHub variables using the [short setup guide](docs/github-actions.md). Local connection names are ignored in CI; the workflow uses a temporary connection and OIDC.

The baseline supports one self-contained dbt project. Package downloads need an existing Snowflake external access integration. Projects using `env.yml`, `env_var()` references, or local packages require a separate configuration design and are rejected by this template. Updates preserve the object by avoiding `--force`; rollback means redeploying an earlier known Git commit.

Default versions: Snowflake CLI **3.28.0** and dbt Fusion **2.0.0-preview.210**. The wizard also offers dbt Core **1.11.11**. Snowflake describes Fusion as generally available despite its upstream `preview` version name; check the runtime versions supported by your account.
