#!/usr/bin/env python3
"""Prepare and deploy a native Snowflake DBT PROJECT with explicit destinations."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

CLI_VERSION = "3.28.0"
DEFAULT_DBT_VERSION = "2.0.0-preview.210"
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_$]{0,254}\Z")
LABEL = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*\Z")
ACCOUNT = re.compile(r"[A-Za-z0-9_]+-[A-Za-z0-9_]+\Z")
RESERVED_PROJECT_ROLES = {
    "ACCOUNTADMIN",
    "SECURITYADMIN",
    "SYSADMIN",
    "USERADMIN",
    "ORGADMIN",
    "GLOBALORGADMIN",
    "PUBLIC",
}
DIR_SETTINGS = {
    "model-paths": ["models"],
    "macro-paths": ["macros"],
    "seed-paths": ["seeds"],
    "test-paths": ["tests"],
    "analysis-paths": ["analyses"],
    "snapshot-paths": ["snapshots"],
    "docs-paths": [],
}
ROOT_FILES = ("dbt_project.yml", "packages.yml", "dependencies.yml", "package-lock.yml")
RECEIPT_FILE = "deployment_receipt.json"
PROFILE_FILES = ("dbt_projects_profiles.yml", "profiles.yml")
SUFFIXES = {".sql", ".yml", ".yaml", ".csv", ".md"}
IGNORED_DIRS = {"target", "logs", "dbt_packages", "__pycache__"}


class DeploymentError(Exception):
    """A configuration, packaging, or deployment requirement was not met."""


@dataclass
class Config:
    source: str
    account: str
    database: str
    object_schema: str
    project: str
    role: str
    warehouse: str
    model_database: str
    model_schema: str
    profile: str
    target: str
    connection: str | None = None
    dbt_version: str = DEFAULT_DBT_VERSION
    external_access_integrations: list[str] = field(default_factory=list)
    default_writeback: bool = False
    auto_compile: bool = True
    deployment_role: str | None = None
    deployment_connection: str | None = None
    operator_user: str | None = None
    deployment_user: str | None = None

    @property
    def project_admin_role(self) -> str:
        return self.deployment_role or self.role

    @property
    def project_admin_connection(self) -> str | None:
        return self.deployment_connection or self.connection

    @property
    def project_admin_user(self) -> str | None:
        if self.deployment_user is not None:
            return self.deployment_user
        if not self.split_roles and self.deployment_connection is None:
            return self.operator_user
        return None

    @property
    def split_roles(self) -> bool:
        return self.project_admin_role.upper() != self.role.upper()

    @property
    def object_name(self) -> str:
        return f"{self.database}.{self.object_schema}.{self.project}"


def read_mapping(path: Path) -> dict[str, Any]:
    """Read literal YAML without evaluating dbt Jinja or constructing objects."""
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise DeploymentError(f"Cannot read YAML: {path}") from exc
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise DeploymentError(f"Expected a YAML mapping: {path}")
    return value


def literal(value: Any) -> str:
    """Only offer static strings as inference; never resolve secret env variables."""
    if isinstance(value, str) and not any(marker in value for marker in ("{{", "{%", "${")):
        return value
    return ""


def validate_config(config: Config) -> None:
    for name in ("default_writeback", "auto_compile"):
        if not isinstance(getattr(config, name), bool):
            raise DeploymentError(f"{name} must be a JSON boolean.")
    for name in (
        "database",
        "object_schema",
        "project",
        "role",
        "warehouse",
        "model_database",
        "model_schema",
    ):
        value = getattr(config, name)
        if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
            raise DeploymentError(f"{name}: use a simple unquoted Snowflake identifier.")
    for name in ("deployment_role", "operator_user", "deployment_user"):
        value = getattr(config, name)
        if value is not None and (not isinstance(value, str) or not IDENTIFIER.fullmatch(value)):
            raise DeploymentError(f"{name}: use a simple unquoted Snowflake identifier or null.")
    if config.split_roles and any(
        role.upper() in RESERVED_PROJECT_ROLES for role in (config.project_admin_role, config.role)
    ):
        raise DeploymentError(
            "Separate project roles must be new custom roles, not built-in roles."
        )
    if (
        config.split_roles
        and config.operator_user is not None
        and config.deployment_user is not None
        and config.operator_user.upper() == config.deployment_user.upper()
    ):
        raise DeploymentError(
            "Separate project roles require different configured user identities."
        )
    for name in ("profile", "target"):
        value = getattr(config, name)
        if not isinstance(value, str) or not LABEL.fullmatch(value):
            raise DeploymentError(f"{name}: use a literal name containing letters, digits, _ or -.")
    if not isinstance(config.account, str) or not ACCOUNT.fullmatch(config.account):
        raise DeploymentError(
            "account: use the organization-account identifier, e.g. MYORG-MYACCOUNT."
        )
    if not isinstance(config.source, str) or not config.source:
        raise DeploymentError("source must name a local dbt project directory.")
    for name in ("connection", "deployment_connection"):
        value = getattr(config, name)
        if value is not None and (not isinstance(value, str) or not LABEL.fullmatch(value)):
            raise DeploymentError(f"{name} must be a simple local connection name or null.")
    if not isinstance(config.dbt_version, str) or not re.fullmatch(
        r"\d+\.\d+\.\d+(?:-[A-Za-z0-9.]+)?", config.dbt_version
    ):
        raise DeploymentError("dbt_version must pin an exact runtime version.")
    if not isinstance(config.external_access_integrations, list) or any(
        not isinstance(value, str) or not IDENTIFIER.fullmatch(value)
        for value in config.external_access_integrations
    ):
        raise DeploymentError("external_access_integrations must be a list of simple identifiers.")


def load_config(path: Path | str) -> Config:
    path = Path(path).resolve()
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeploymentError(f"Cannot read JSON config: {path}") from exc
    allowed = {item.name for item in fields(Config)}
    if not isinstance(values, dict) or set(values) - allowed:
        raise DeploymentError("Config must be an object containing only documented fields.")
    try:
        config = Config(**values)
    except TypeError as exc:
        raise DeploymentError("Config is missing required fields.") from exc
    validate_config(config)
    source = Path(config.source).expanduser()
    config.source = str((path.parent / source).absolute() if not source.is_absolute() else source)
    return config


def profile_role(config: Config) -> str:
    """Use a fixed operator literal to avoid the CLI's deployment-time role switch."""
    if not config.split_roles:
        return config.role
    if not IDENTIFIER.fullmatch(config.role):
        raise DeploymentError("Operator profile role must be a simple Snowflake identifier.")
    return "{{ '" + config.role.upper() + "' }}"


def native_profile(config: Config) -> dict[str, Any]:
    return {
        config.profile: {
            "target": config.target,
            "outputs": {
                config.target: {
                    "type": "snowflake",
                    "database": config.model_database,
                    "schema": config.model_schema,
                    "role": profile_role(config),
                    "warehouse": config.warehouse,
                }
            },
        }
    }


def source_directory(config: Config) -> Path:
    source = Path(config.source).expanduser()
    return check_source_path(source)


def check_source_path(source: Path) -> Path:
    for parent in (source, *source.parents):
        if parent.is_symlink():
            raise DeploymentError("The source directory and its parents must not be symlinks.")
    if not source.is_dir():
        raise DeploymentError(f"Source directory does not exist: {source}")
    return source.resolve()


def safe_path(source: Path, relative: str) -> Path:
    path = Path(relative)
    if (
        path.is_absolute()
        or not path.parts
        or any(
            part in {"..", "."} or part.startswith(".") or part in IGNORED_DIRS
            for part in path.parts
        )
    ):
        raise DeploymentError(
            f"Unsafe configured dbt path: {relative!r}; use a dedicated subdirectory."
        )
    candidate = source / path
    for parent in (candidate, *candidate.parents):
        if parent == source:
            break
        if parent.is_symlink():
            raise DeploymentError(f"Symlinks cannot be deployed: {relative}")
    if not candidate.resolve().is_relative_to(source):
        raise DeploymentError(f"Configured path escapes the project: {relative}")
    return candidate


def check_dependencies(source: Path, config: Config) -> None:
    for name in ("packages.yml", "dependencies.yml"):
        path = source / name
        if not path.exists():
            continue
        data = read_mapping(path)
        if data.get("projects"):
            raise DeploymentError(
                "Cross-project dependencies require an explicit extension to this template."
            )
        packages = data.get("packages", [])
        if not isinstance(packages, list) or any(
            not isinstance(package, dict) for package in packages
        ):
            raise DeploymentError(f"Invalid packages list in {name}.")
        if any("local" in package for package in packages):
            raise DeploymentError(
                "Local packages are outside this minimal template; use a remote package and EAI."
            )
        for package in packages:
            git_url = package.get("git")
            if isinstance(git_url, str) and git_url.startswith(("https://", "http://")):
                try:
                    parsed_url = urlsplit(git_url)
                except ValueError as exc:
                    raise DeploymentError("Invalid Git package URL.") from exc
                if parsed_url.username is not None or parsed_url.password is not None:
                    raise DeploymentError(
                        "Git package URLs must not contain credentials. "
                        "Private package authentication needs an explicit native secrets design."
                    )
        if packages and not config.external_access_integrations:
            raise DeploymentError(
                "Remote packages require an existing external_access_integrations entry "
                "for server-side dbt deps."
            )


def prepare_source(config: Config, destination: Path | str) -> list[str]:
    """Build a fresh upload directory from explicit dbt paths, excluding personal profiles."""
    validate_config(config)
    source = source_directory(config)
    if (source / RECEIPT_FILE).exists() or (source / RECEIPT_FILE).is_symlink():
        raise DeploymentError(f"{RECEIPT_FILE} is reserved for generated deployment provenance.")
    destination = Path(destination).resolve()
    if destination == source or destination.is_relative_to(source):
        raise DeploymentError("Prepared source must be outside the dbt source directory.")
    if destination.exists() and any(destination.iterdir()):
        raise DeploymentError("Prepared source destination must be empty.")
    destination.mkdir(parents=True, exist_ok=True)
    for name in ROOT_FILES:
        if (source / name).is_symlink():
            raise DeploymentError(f"Symlinks cannot be deployed: {name}")
    if (source / "env.yml").exists():
        raise DeploymentError(
            "env.yml is outside this minimal template. Extend native environment handling "
            "explicitly before deploying it."
        )
    project = read_mapping(source / "dbt_project.yml")
    if literal(project.get("profile")) != config.profile:
        raise DeploymentError("Config profile must match the literal profile in dbt_project.yml.")
    check_dependencies(source, config)
    candidates: set[Path] = {source / name for name in ROOT_FILES if (source / name).is_file()}
    for setting, defaults in DIR_SETTINGS.items():
        paths = project.get(setting, defaults)
        if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
            raise DeploymentError(f"{setting} must be a list of literal local directories.")
        for relative in paths:
            directory = safe_path(source, relative)
            if not directory.exists():
                continue
            if not directory.is_dir():
                raise DeploymentError(f"{setting} must name a directory: {relative}")
            for base, dirnames, filenames in os.walk(directory, followlinks=False):
                base_path = Path(base)
                for name in dirnames + filenames:
                    if (base_path / name).is_symlink():
                        raise DeploymentError(
                            f"Symlinks cannot be deployed: {(base_path / name).relative_to(source)}"
                        )
                dirnames[:] = [
                    name
                    for name in dirnames
                    if not name.startswith(".") and name not in IGNORED_DIRS
                ]
                for name in filenames:
                    path = base_path / name
                    if name.startswith(".") or name in PROFILE_FILES:
                        continue
                    if path.suffix == ".py":
                        raise DeploymentError(
                            "Python models are not supported by this native deployment template."
                        )
                    if path.suffix.lower() in SUFFIXES:
                        candidates.add(path)
    for path in sorted(candidates):
        if path.suffix.lower() in {".sql", ".yml", ".yaml", ".md"} and re.search(
            r"\benv_var\s*\(", path.read_text(encoding="utf-8")
        ):
            raise DeploymentError(
                "env_var() references need explicit native environment handling. "
                "Extend this template before deploying this project."
            )
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    (destination / PROFILE_FILES[0]).write_text(
        yaml.safe_dump(native_profile(config), sort_keys=False), encoding="utf-8"
    )
    return sorted([str(path.relative_to(source)) for path in candidates] + [PROFILE_FILES[0]])


def infer_values(source: Path, connection: str | None) -> dict[str, Any]:
    project = read_mapping(source / "dbt_project.yml")
    values: dict[str, Any] = {
        "project": literal(project.get("name")),
        "profile": literal(project.get("profile")),
    }
    profiles = next(
        (source / name for name in PROFILE_FILES if (source / name).is_file()),
        Path.home() / ".dbt/profiles.yml",
    )
    if profiles.is_file():
        profile = read_mapping(profiles).get(values["profile"], {})
        if isinstance(profile, dict):
            values["target"] = literal(profile.get("target"))
            outputs = profile.get("outputs", {})
            target = outputs.get(values.get("target"), {}) if isinstance(outputs, dict) else {}
            if isinstance(target, dict):
                values.update(
                    {
                        key: literal(target.get(key))
                        for key in ("account", "database", "schema", "role", "warehouse")
                    }
                )
                values["model_database"] = literal(target.get("database"))
                values["model_schema"] = literal(target.get("schema"))
    if connection:
        path = Path.home() / ".snowflake/config.toml"
        try:
            settings = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise DeploymentError(f"Cannot read selected local connection from {path}") from exc
        connections = settings.get("connections", {})
        selected = connections.get(connection) if isinstance(connections, dict) else None
        if not isinstance(selected, dict):
            raise DeploymentError(f"Local connection {connection!r} does not exist.")
        values.update(
            {
                key: literal(selected.get(key)) or values.get(key, "")
                for key in ("account", "database", "schema", "role", "warehouse")
            }
        )
    return values


def ask(name: str, default: str, non_interactive: bool) -> str:
    if non_interactive:
        if not default:
            raise DeploymentError(f"Missing {name}; pass --{name.replace('_', '-')}.")
        return default
    hint = f" [{default}]" if default else ""
    try:
        return input(f"{name.replace('_', ' ')}{hint}: ").strip() or default
    except EOFError as exc:
        raise DeploymentError(
            "Wizard input ended; use --non-interactive with explicit values."
        ) from exc


def wizard(args: argparse.Namespace) -> Config:
    source = check_source_path(Path(args.source).expanduser().absolute())
    connection = args.connection
    if not args.non_interactive and connection is None:
        connection = ask("local connection (blank uses temporary connection)", "", False) or None
    inferred = infer_values(source, connection)
    values: dict[str, Any] = {"source": str(source), "connection": connection}
    for name in (
        "account",
        "database",
        "object_schema",
        "project",
        "role",
        "warehouse",
        "model_database",
        "model_schema",
        "profile",
        "target",
        "dbt_version",
    ):
        aliases = {
            "object_schema": "schema",
            "model_database": "database",
            "model_schema": "schema",
        }
        default = getattr(args, name, None) or inferred.get(aliases.get(name, name), "")
        if name == "target":
            default = default or "dev"
        if name == "object_schema":
            default = default or "PROJECTS"
        if name == "model_database":
            default = (
                getattr(args, name, None) or inferred.get("model_database") or values["database"]
            )
        if name == "model_schema":
            default = (
                getattr(args, name, None) or inferred.get("model_schema") or values["object_schema"]
            )
        if name == "dbt_version":
            default = getattr(args, name, None) or DEFAULT_DBT_VERSION
            if not args.non_interactive:
                print(
                    f"Runtime: Fusion {DEFAULT_DBT_VERSION} or Core 1.11.11; "
                    "enter the exact version."
                )
        if name == "account" and default and not ACCOUNT.fullmatch(default):
            default = ""
        values[name] = ask(name, default, args.non_interactive)
    for name in ("deployment_role", "deployment_connection", "operator_user", "deployment_user"):
        value = getattr(args, name, None)
        if not args.non_interactive:
            fallback = values["role"] if name == "deployment_role" else ""
            prompt = {
                "deployment_role": "project administrator role (same role keeps legacy setup)",
                "deployment_connection": "project administrator connection (blank reuses operator)",
                "operator_user": "expected operator user (blank skips user identity check)",
                "deployment_user": "expected project administrator user (blank uses fallback)",
            }[name]
            value = ask(prompt, value or fallback, False)
        values[name] = value or None
    split_roles = (
        str(values.get("deployment_role") or values["role"]).upper() != values["role"].upper()
    )
    integrations = args.external_access_integration or []
    if not args.non_interactive and not integrations:
        response = ask(
            "existing external access integrations (comma-separated, blank for none)", "", False
        )
        integrations = [item.strip() for item in response.split(",") if item.strip()]
    values["external_access_integrations"] = integrations
    for name, fallback in (("default_writeback", False), ("auto_compile", not split_roles)):
        setting = getattr(args, name, None)
        if setting is None and not args.non_interactive:
            if name == "default_writeback":
                print("Writeback saves run artifacts in LIVE for retry; serialize runs using it.")
                prompt = "persist run artifacts in LIVE (writeback)"
            else:
                prompt = "compile during deployment"
            response = ask(prompt, "yes" if fallback else "no", False).lower()
            if response not in ("yes", "no", "y", "n"):
                raise DeploymentError(f"{name}: enter yes or no.")
            setting = response in ("yes", "y")
        values[name] = fallback if setting is None else setting
    config = Config(**values)
    validate_deployment(config)
    with tempfile.TemporaryDirectory(prefix="dbtsnow-plan-") as temp:
        uploaded = prepare_source(config, Path(temp) / "source")
    output = Path(args.output).expanduser().resolve()
    serialized = asdict(config)
    serialized["source"] = os.path.relpath(source, output.parent)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(serialized, indent=2) + "\n")
    except FileExistsError as exc:
        raise DeploymentError(f"Config already exists; choose a new --output: {output}") from exc
    show_plan(config, uploaded)
    print(f"Saved {output}. Review it, then run deploy --config {output} --apply.")
    return config


def run_command(command: list[str]) -> str:
    try:
        completed = subprocess.run(command, check=True, text=True, capture_output=True)
    except FileNotFoundError as exc:
        raise DeploymentError(f"Command not found: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        # Avoid echoing CLI output: it can contain SQL, model data, or credentials.
        raise DeploymentError(
            f"{command[0]} {command[1]} failed (exit {exc.returncode}); "
            "operation did not complete successfully."
        ) from exc
    return completed.stdout


def json_rows(output: str) -> list[dict[str, Any]]:
    try:
        values = json.loads(output)
    except json.JSONDecodeError as exc:
        raise DeploymentError("Snowflake CLI returned invalid JSON.") from exc
    if isinstance(values, dict):
        values = [values]
    if not isinstance(values, list) or any(not isinstance(row, dict) for row in values):
        raise DeploymentError("Snowflake CLI returned an unexpected JSON result.")
    return [{str(key).lower(): value for key, value in row.items()} for row in values]


def sql_rows(query: str, options: list[str]) -> list[dict[str, Any]]:
    return json_rows(run_command(["snow", "sql", "--query", query, "--format", "JSON", *options]))


def connection_options(config: Config, temporary: bool, *, deployment: bool = False) -> list[str]:
    connection = config.project_admin_connection if deployment else config.connection
    role = config.project_admin_role if deployment else config.role
    auth = (
        ["--temporary-connection"] if temporary or not connection else ["--connection", connection]
    )
    return [
        *auth,
        "--account",
        config.account,
        "--database",
        config.database,
        "--schema",
        config.object_schema,
        "--role",
        role,
        "--warehouse",
        config.warehouse,
        "--secondary-roles",
        "NONE",
    ]


def show_identity(config: Config, *, deployment: bool = False) -> None:
    label = "Project administrator" if deployment else "Operator"
    role = config.project_admin_role if deployment else config.role
    connection = config.project_admin_connection if deployment else config.connection
    user = config.project_admin_user if deployment else config.operator_user
    print(
        f"{label} identity: role {role}; connection {connection or 'runtime'}; "
        f"expected user {user or 'unspecified'}"
    )


def github_metadata(source: Path) -> dict[str, str]:
    sha = os.environ.get("GITHUB_SHA")
    if not sha:
        return {}
    actual = run_command(["git", "-C", str(source), "rev-parse", "HEAD"]).strip()
    dirty = run_command(["git", "-C", str(source), "status", "--porcelain"]).strip()
    if actual != sha or dirty:
        raise DeploymentError("GitHub deployment must use the exact clean checked-out GITHUB_SHA.")
    metadata = {"git-commit": sha}
    repository = os.environ.get("GITHUB_REPOSITORY")
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    if repository:
        metadata["git-url"] = f"{server}/{repository}"
    branch = os.environ.get("GITHUB_REF_NAME")
    if branch:
        metadata["git-branch"] = branch
    return metadata


def check_session(config: Config, options: list[str], *, deployment: bool = False) -> None:
    version = run_command(["snow", "--version"])
    if not re.search(rf"(?<![\d.]){re.escape(CLI_VERSION)}(?![\d.])", version):
        raise DeploymentError(f"Install pinned Snowflake CLI {CLI_VERSION} before applying.")
    identity = sql_rows(
        "SELECT CURRENT_ORGANIZATION_NAME() AS organization, "
        "CURRENT_ACCOUNT_NAME() AS account, CURRENT_ROLE() AS role, CURRENT_USER() AS user, "
        "CURRENT_SECONDARY_ROLES() AS secondary_roles",
        options,
    )
    if len(identity) != 1:
        raise DeploymentError("Cannot verify Snowflake session identity.")
    row = identity[0]
    actual = f"{row.get('organization', '')}-{row.get('account', '')}"
    role = config.project_admin_role if deployment else config.role
    user = config.project_admin_user if deployment else config.operator_user
    if actual.upper() != config.account.upper() or str(row.get("role", "")).upper() != role.upper():
        raise DeploymentError("Authenticated account or role does not match the deployment config.")
    if user is not None and str(row.get("user", "")).upper() != user.upper():
        raise DeploymentError("Authenticated user does not match the configured identity.")
    secondary = row.get("secondary_roles")
    if isinstance(secondary, str):
        try:
            secondary = json.loads(secondary)
        except json.JSONDecodeError as exc:
            raise DeploymentError("Cannot verify disabled secondary roles.") from exc
    if (
        not isinstance(secondary, dict)
        or secondary.get("value") not in ("", "NONE")
        or secondary.get("roles") != ""
    ):
        raise DeploymentError("Secondary roles must be disabled for this operation.")


def project_row(config: Config, options: list[str]) -> dict[str, Any] | None:
    rows = sql_rows(
        f"SHOW DBT PROJECTS LIKE '{config.project}' "
        f"IN SCHEMA {config.database}.{config.object_schema}",
        options,
    )
    matches = [row for row in rows if str(row.get("name", "")).upper() == config.project.upper()]
    if len(matches) > 1:
        raise DeploymentError("Cannot identify a unique dbt project object.")
    return matches[0] if matches else None


def confirm_live(row: dict[str, Any]) -> None:
    if str(row.get("default_version", "")).upper() != "LIVE":
        raise DeploymentError(
            "Object does not report a mutable LIVE version. Run migrate --config <config> "
            "to review a separate migration; deployment never replaces legacy objects."
        )
    for key in ("location", "default_version_location_uri"):
        location = row.get(key)
        if location is not None and not str(location).rstrip("/").endswith("/versions/live"):
            raise DeploymentError("LIVE object location does not use /versions/live/.")


def require_project_owner(config: Config, row: dict[str, Any]) -> None:
    if str(row.get("owner", "")).upper() != config.project_admin_role.upper():
        raise DeploymentError(
            "Project ownership does not match the configured project administrator role."
        )


def validate_deployment(config: Config, *, build: bool = False) -> None:
    validate_config(config)
    if config.split_roles and config.auto_compile:
        raise DeploymentError(
            "Separate project roles require auto_compile: false; compile as the operator."
        )
    if config.split_roles and build:
        raise DeploymentError(
            "Separate project roles require a separate run command using the operator identity."
        )


def preflight(
    config: Config, options: list[str], *, deployment: bool = False
) -> dict[str, Any] | None:
    check_session(config, options, deployment=deployment)
    supported = sql_rows("SELECT SYSTEM$SUPPORTED_DBT_VERSIONS() AS versions", options)
    if len(supported) != 1:
        raise DeploymentError("Cannot verify supported dbt runtimes.")
    versions = supported[0].get("versions")
    if isinstance(versions, str):
        try:
            versions = json.loads(versions)
        except json.JSONDecodeError as exc:
            raise DeploymentError("Cannot parse supported dbt runtimes.") from exc
    if not isinstance(versions, list) or not any(
        isinstance(value, dict) and value.get("dbt_version") == config.dbt_version
        for value in versions
    ):
        raise DeploymentError(f"dbt runtime {config.dbt_version} is not supported by this account.")
    existing = project_row(config, options)
    if existing is not None:
        confirm_live(existing)
        if deployment:
            require_project_owner(config, existing)
    return existing


def migrate(config: Config, *, apply: bool = False, temporary_connection: bool = False) -> None:
    validate_config(config)
    query = f"SELECT SYSTEM$MIGRATE_DBT_PROJECT('{config.object_name}')"
    print(
        f"Migration destination: {config.account}, role {config.project_admin_role}, "
        f"{config.object_name}"
    )
    show_identity(config, deployment=True)
    print("Migration preserves object identity, grants, task references, and execution history.")
    print("Numbered source versions become inaccessible. Save needed versions before applying.")
    print(query)
    if not apply:
        print("Dry run: no Snowflake connection or migration. Add --apply to migrate this object.")
        return
    options = connection_options(config, temporary_connection, deployment=True)
    check_session(config, options, deployment=True)
    before = project_row(config, options)
    if before is None:
        raise DeploymentError("Migration target does not exist or is not visible to this role.")
    require_project_owner(config, before)
    if str(before.get("default_version", "")).upper() == "LIVE":
        confirm_live(before)
        print("Already LIVE; no migration performed.")
        return
    version = str(before.get("default_version", "")).upper()
    if version not in ("FIRST", "LAST") and not re.fullmatch(r"VERSION\$\d+", version):
        raise DeploymentError("Cannot verify legacy version semantics; no migration performed.")
    status = sql_rows("SELECT SYSTEM$BEHAVIOR_CHANGE_BUNDLE_STATUS('2026_06') AS status", options)
    print(
        f"2026_06 bundle status: {status}. "
        "The separate live-version feature also permits migration."
    )
    sql_rows(query, options)
    after = project_row(config, options)
    if after is None:
        raise DeploymentError("Migrated object is missing from readback.")
    confirm_live(after)
    for key in (
        "name",
        "database_name",
        "schema_name",
        "owner",
        "created_on",
        "dbt_version",
        "default_target",
    ):
        if key in before and after.get(key) != before[key]:
            raise DeploymentError(f"Migration readback changed {key}; inspect the object.")
    print(f"Verified migration: {config.object_name} is LIVE with existing metadata preserved.")


def execution_command(
    config: Config,
    *,
    command: str = "build",
    state_from: str | None = None,
    selection: str | None = None,
    defer: bool = False,
    writeback: bool | None = None,
    temporary_connection: bool = False,
) -> list[str]:
    validate_config(config)
    if command not in ("build", "compile", "retry", "source-freshness"):
        raise DeploymentError("Unsupported execution command.")
    if writeback is not None and not isinstance(writeback, bool):
        raise DeploymentError("writeback must be a boolean.")
    if state_from is not None and (
        len(state_from.split(".")) != 3
        or not all(IDENTIFIER.fullmatch(part) for part in state_from.split("."))
    ):
        raise DeploymentError("state_from must be database.schema.project with simple identifiers.")
    if selection is not None and (
        not re.fullmatch(r"[A-Za-z0-9_.*:+,@/-]+", selection) or selection.startswith("-")
    ):
        raise DeploymentError(
            "selection must be one literal dbt selector, such as state:modified+."
        )
    if defer and not state_from:
        raise DeploymentError("--defer requires --state-from.")
    if command in ("retry", "source-freshness") and (state_from or defer):
        raise DeploymentError("State imports are supported only for build and compile.")
    if command == "retry" and selection is not None:
        raise DeploymentError("retry reuses the previous invocation; selection is not supported.")
    persist = config.default_writeback if writeback is None else writeback
    options = connection_options(config, temporary_connection)
    result = ["snow", "dbt", "execute", *options, "--writeback" if persist else "--no-writeback"]
    if state_from:
        result.extend(
            [
                "--import",
                f"SYSTEM$DBT_GET_LAST_SUCCESSFUL_RUN_TARGET('{state_from}', "
                "'build,run') AS 'state'",
            ]
        )
    result.append(config.object_name)
    result.extend(["source", "freshness"] if command == "source-freshness" else [command])
    if command != "retry" or config.dbt_version.startswith("2."):
        result.extend(["--target", config.target])
    if command == "retry" and config.dbt_version.startswith("2."):
        result.extend(["--profile", config.profile])
    if state_from:
        result.extend(["--state", "./imports/state"])
    if defer:
        result.append("--defer")
    if selection:
        result.extend(["--select", selection])
    return result


def verify_execution_target(config: Config, options: list[str], command: str) -> None:
    """Check mutable profile destinations and the inherited target before an execution."""
    with tempfile.TemporaryDirectory(prefix="dbtsnow-execution-") as temp:
        downloaded = Path(temp)
        live = f"snow://dbt/{config.object_name}/versions/live/"
        run_command(["snow", "dbt", "copy", live + "dbt_project.yml", str(downloaded), *options])
        project = read_mapping(downloaded / "dbt_project.yml")
        if literal(project.get("profile")) != config.profile:
            raise DeploymentError("Deployed project uses a different profile from the config.")
        run_command(["snow", "dbt", "copy", live + PROFILE_FILES[0], str(downloaded), *options])
        profiles = read_mapping(downloaded / PROFILE_FILES[0])
        profile = profiles.get(config.profile)
        outputs = profile.get("outputs") if isinstance(profile, dict) else None
        target = outputs.get(config.target) if isinstance(outputs, dict) else None
        if not isinstance(target, dict):
            raise DeploymentError("Deployed profile does not contain the configured target.")
        for field_name, expected in (
            ("database", config.model_database),
            ("schema", config.model_schema),
            ("role", profile_role(config)),
            ("warehouse", config.warehouse),
        ):
            actual = target.get(field_name)
            matches = (
                actual == expected
                if field_name == "role" and config.split_roles
                else literal(actual).upper() == expected.upper()
            )
            if not matches:
                raise DeploymentError(
                    f"Deployed model target {field_name} differs from the config."
                )
        if command == "retry":
            run_command(
                ["snow", "dbt", "copy", live + "target/run_results.json", str(downloaded), *options]
            )
            try:
                previous = json.loads((downloaded / "run_results.json").read_text())
                inherited = previous.get("args", {}) if isinstance(previous, dict) else {}
            except (OSError, json.JSONDecodeError) as exc:
                raise DeploymentError(
                    "Retry needs compatible failed-run artifacts in LIVE target/."
                ) from exc
            if not isinstance(inherited, dict):
                raise DeploymentError("Retry artifacts contain invalid invocation arguments.")
            fusion = config.dbt_version.startswith("2.")
            previous_target = inherited.get("target")
            if (previous_target is not None or not fusion) and previous_target != config.target:
                raise DeploymentError(
                    "Retry's inherited target does not match the configured target."
                )
            previous_profile = inherited.get("profile")
            if previous_profile is not None and previous_profile != config.profile:
                raise DeploymentError("Retry's inherited profile differs from the config.")
            if not fusion and previous_profile is None and set(profiles) != {config.profile}:
                raise DeploymentError("Cannot prove Core retry's inherited profile destination.")


def execute_project(
    config: Config,
    *,
    command: str = "build",
    state_from: str | None = None,
    selection: str | None = None,
    defer: bool = False,
    writeback: bool | None = None,
    temporary_connection: bool = False,
    apply: bool = False,
) -> None:
    invocation = execution_command(
        config,
        command=command,
        state_from=state_from,
        selection=selection,
        defer=defer,
        writeback=writeback,
        temporary_connection=temporary_connection,
    )
    print(
        f"Execution destination: {config.account}, {config.object_name}; "
        f"model target {config.model_database}.{config.model_schema}"
    )
    show_identity(config)
    object_index = invocation.index(config.object_name)
    print(f"dbt command: {shlex.join(invocation[object_index + 1 :])}")
    print(f"Artifact writeback: {config.default_writeback if writeback is None else writeback}")
    if state_from:
        print(f"State baseline: last successful build/run from {state_from}")
    if not apply:
        print("Dry run: no Snowflake connection or execution. Add --apply to execute.")
        return
    options = connection_options(config, temporary_connection)
    existing = preflight(config, options)
    if existing is None:
        raise DeploymentError("Execution target does not exist or is not visible to this role.")
    confirm_live(existing)
    if existing.get("dbt_version") != config.dbt_version:
        raise DeploymentError("Deployed runtime differs from the execution config.")
    verify_execution_target(config, options, command)
    if state_from:
        state = sql_rows(
            f"SELECT SYSTEM$DBT_GET_LAST_SUCCESSFUL_RUN_TARGET('{state_from}', "
            "'build,run') AS state",
            options,
        )
        if len(state) != 1 or not isinstance(state[0].get("state"), str) or not state[0]["state"]:
            raise DeploymentError(
                "No successful state artifacts found; run the baseline within the last 7 days "
                "and grant MONITOR."
            )
        # Pin the resolved artifacts so another baseline run cannot change the imported state.
        location = str(state[0]["state"]).replace("'", "''")
        invocation[invocation.index("--import") + 1] = f"'{location}' AS 'state'"
    output = run_command(invocation)
    print(output)
    print(f"dbt {command} completed successfully.")


def show_plan(config: Config, uploaded: list[str]) -> None:
    print(
        f"Account: {config.account}; project administrator role: {config.project_admin_role}; "
        f"warehouse: {config.warehouse}"
    )
    print(f"Operator/profile role: {config.role}")
    print(
        f"Project administrator connection: {config.project_admin_connection or 'temporary'}; "
        f"operator connection: {config.connection or 'temporary'}"
    )
    if config.project_admin_user or config.operator_user:
        print(
            f"Expected project administrator user: {config.project_admin_user or 'unspecified'}; "
            f"operator user: {config.operator_user or 'unspecified'}"
        )
    print(f"DBT PROJECT: {config.object_name}")
    print(
        f"Model target: {config.model_database}.{config.model_schema}; "
        f"profile/target: {config.profile}/{config.target}"
    )
    print(
        f"Runtime: {config.dbt_version}; automatic compile: {config.auto_compile}; "
        "force replacement: disabled"
    )
    print(f"Default artifact writeback: {config.default_writeback}; object version: LIVE")
    print("Upload files:\n" + "\n".join(f"  {name}" for name in uploaded))


def verify_readback(config: Config, rows: list[dict[str, Any]], metadata: dict[str, str]) -> None:
    if len(rows) != 1:
        raise DeploymentError("Deployment returned no unique DBT PROJECT description.")
    row = rows[0]
    require_project_owner(config, row)
    for key, expected_value in (("name", config.project), ("owner", config.project_admin_role)):
        if key in row and str(row[key]).upper() != expected_value.upper():
            raise DeploymentError(f"Deployment readback {key} does not match the config.")
    expected = {"dbt_version": config.dbt_version, "default_target": config.target}
    if any(str(row.get(key, "")) != value for key, value in expected.items()):
        raise DeploymentError("Deployment readback runtime or target does not match the config.")
    confirm_live(row)
    for key in ("auto_compile", "default_writeback"):
        if key in row and str(row[key]).lower() != str(getattr(config, key)).lower():
            raise DeploymentError(f"Deployment readback {key} does not match the config.")
    if "git-commit" in metadata and "last_deployed_from" in row:
        deployed = row.get("last_deployed_from", {})
        if isinstance(deployed, str):
            try:
                deployed = json.loads(deployed)
            except json.JSONDecodeError as exc:
                raise DeploymentError("Deployment metadata is invalid.") from exc
        if not isinstance(deployed, dict) or deployed.get("git_commit") != metadata["git-commit"]:
            raise DeploymentError(
                "Deployment readback Git commit does not match the checked-out commit."
            )


def write_receipt(
    config: Config, prepared: Path, uploaded: list[str], metadata: dict[str, str]
) -> dict[str, Any]:
    receipt = {
        "git_commit": metadata.get("git-commit"),
        "object": config.object_name,
        "dbt_version": config.dbt_version,
        "target": config.target,
        "auto_compile": config.auto_compile,
        "default_writeback": config.default_writeback,
        "files": {
            name: hashlib.sha256((prepared / name).read_bytes()).hexdigest()
            for name in uploaded
            if name != RECEIPT_FILE
        },
    }
    (prepared / RECEIPT_FILE).write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


def verify_source(prepared: Path, downloaded: Path, receipt: dict[str, Any]) -> None:
    try:
        if (downloaded / RECEIPT_FILE).read_bytes() != (prepared / RECEIPT_FILE).read_bytes():
            raise DeploymentError("Deployed provenance receipt does not match this deployment.")
        for name, expected_hash in receipt["files"].items():
            if hashlib.sha256((downloaded / name).read_bytes()).hexdigest() != expected_hash:
                raise DeploymentError(f"Deployed source content does not match: {name}")
        expected_files = set(receipt["files"]) | {RECEIPT_FILE}
        for path in downloaded.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(downloaded)
            # Native compile/deps may persist these artifacts independently of uploaded source.
            if relative.parts[0] in {"target", "logs", "dbt_packages"} or str(relative) in {
                "dbt_artifacts.zip",
                "package-lock.yml",
            }:
                continue
            if str(relative) not in expected_files:
                raise DeploymentError(f"Unexpected file in deployed source: {relative}")
    except OSError as exc:
        raise DeploymentError(
            "Deployed source or provenance receipt is missing from readback."
        ) from exc


def deploy(
    config: Config, *, apply: bool = False, build: bool = False, temporary_connection: bool = False
) -> None:
    validate_deployment(config, build=build)
    with tempfile.TemporaryDirectory(prefix="dbtsnow-deploy-") as temp:
        prepared = Path(temp) / "source"
        uploaded = prepare_source(config, prepared)
        write_receipt(config, prepared, uploaded, {})
        uploaded.append(RECEIPT_FILE)
        show_plan(config, uploaded)
        if build:
            print(
                "Build requested: dbt build will write model relations and run tests "
                "in the configured model target."
            )
        if not apply:
            print("Dry run: no Snowflake connection or cloud writes. Add --apply to deploy.")
            return
        options = connection_options(config, temporary_connection, deployment=True)
        metadata = github_metadata(source_directory(config))
        receipt = write_receipt(config, prepared, uploaded, metadata)
        preflight(config, options, deployment=True)
        command = [
            "snow",
            "dbt",
            "deploy",
            config.object_name,
            "--source",
            str(prepared),
            "--profiles-dir",
            str(prepared),
            "--default-target",
            config.target,
            "--dbt-version",
            config.dbt_version,
            "--no-force",
            "--auto-compile" if config.auto_compile else "--no-auto-compile",
            "--default-writeback" if config.default_writeback else "--no-default-writeback",
            *options,
        ]
        for integration in config.external_access_integrations:
            command.extend(["--external-access-integration", integration])
        for key, value in metadata.items():
            command.extend([f"--{key}", value])
        run_command(command)
        rows = json_rows(
            run_command(
                ["snow", "dbt", "describe", config.object_name, "--format", "JSON", *options]
            )
        )
        verify_readback(config, rows, metadata)
        downloaded = Path(temp) / "readback"
        downloaded.mkdir()
        run_command(
            [
                "snow",
                "dbt",
                "copy",
                f"snow://dbt/{config.object_name}/versions/live/",
                str(downloaded),
                "--recursive",
                *options,
            ]
        )
        verify_source(prepared, downloaded, receipt)
        print(
            f"Verified deployment: {config.object_name}, runtime {config.dbt_version}, "
            f"target {config.target}, version LIVE, source hashes match."
        )
        if build:
            print(run_command(execution_command(config, temporary_connection=temporary_connection)))
            print("dbt build completed successfully.")


def project_access(
    config: Config, *, apply: bool = False, temporary_connection: bool = False
) -> None:
    """Hand one existing project to its operator without account-level grants."""
    validate_config(config)
    query = f"GRANT USAGE, MONITOR ON DBT PROJECT {config.object_name} TO ROLE {config.role}"
    print(
        f"Project access: {config.account}, project administrator role {config.project_admin_role}"
    )
    show_identity(config, deployment=True)
    print(query)
    print("In a managed access schema, its owner or grant administrator must apply these grants.")
    if not apply:
        print("Dry run: no Snowflake connection or grants. Add --apply to grant project access.")
        return
    options = connection_options(config, temporary_connection, deployment=True)
    check_session(config, options, deployment=True)
    existing = project_row(config, options)
    if existing is None:
        raise DeploymentError("Access target does not exist or is not visible to this role.")
    require_project_owner(config, existing)
    sql_rows(query, options)
    grants = sql_rows(f"SHOW GRANTS ON DBT PROJECT {config.object_name}", options)
    privileges = {
        str(row.get("privilege", "")).upper()
        for row in grants
        if str(row.get("granted_to", "")).upper() == "ROLE"
        and str(row.get("granted_on", "")).upper().replace("_", " ") == "DBT PROJECT"
        and str(row.get("grantee_name", "")).upper() == config.role.upper()
        and str(row.get("name", "")).upper() == config.object_name.upper()
    }
    if not {"USAGE", "MONITOR"}.issubset(privileges):
        raise DeploymentError("Project access readback did not confirm both exact-object grants.")
    print(f"Verified project access: {config.role} has USAGE and MONITOR on {config.object_name}.")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    setup = commands.add_parser(
        "wizard",
        help="Infer values, ask for missing settings, and save a config without connecting.",
    )
    setup.add_argument("--source", default="example")
    setup.add_argument("--connection")
    setup.add_argument("--deployment-connection")
    setup.add_argument("--deployment-role")
    setup.add_argument("--operator-user")
    setup.add_argument("--deployment-user")
    setup.add_argument("--output", default="deployment/dev.json")
    setup.add_argument("--non-interactive", action="store_true")
    for name in (
        "account",
        "database",
        "object_schema",
        "project",
        "role",
        "warehouse",
        "model_database",
        "model_schema",
        "profile",
        "target",
        "dbt_version",
    ):
        setup.add_argument(f"--{name.replace('_', '-')}")
    setup.add_argument("--external-access-integration", action="append")
    setup.add_argument(
        "--default-writeback",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Persist generated target/log files in LIVE by default (default: disabled).",
    )
    setup.add_argument(
        "--auto-compile",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Compile during deployment (default: disabled with separate roles).",
    )
    apply = commands.add_parser(
        "deploy", help="Show a local plan; --apply explicitly enables deployment."
    )
    apply.add_argument("--config", required=True)
    apply.add_argument("--apply", action="store_true")
    apply.add_argument(
        "--build",
        action="store_true",
        help="Also run dbt build, writing model relations and running tests.",
    )
    apply.add_argument(
        "--temporary-connection",
        action="store_true",
        help="Use environment authentication instead of a saved local connection.",
    )
    migration = commands.add_parser(
        "migrate", help="Review and explicitly migrate only the configured legacy object to LIVE."
    )
    execution = commands.add_parser(
        "run", help="Execute a deployed LIVE project without redeploying its files."
    )
    access = commands.add_parser(
        "project-access",
        help="Preview or grant operator USAGE and MONITOR on one existing project.",
    )
    for operation in (migration, execution, access):
        operation.add_argument("--config", required=True)
        operation.add_argument("--apply", action="store_true")
        operation.add_argument("--temporary-connection", action="store_true")
    execution.add_argument(
        "--command",
        dest="command_name",
        choices=("build", "compile", "retry", "source-freshness"),
        default="build",
    )
    execution.add_argument("--state-from")
    execution.add_argument("--select", dest="selection")
    execution.add_argument("--defer", action="store_true")
    execution.add_argument(
        "--writeback",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Persist this run's target/log files in LIVE (otherwise use config default).",
    )
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "wizard":
            wizard(args)
        elif args.command == "migrate":
            migrate(
                load_config(args.config),
                apply=args.apply,
                temporary_connection=args.temporary_connection,
            )
        elif args.command == "project-access":
            project_access(
                load_config(args.config),
                apply=args.apply,
                temporary_connection=args.temporary_connection,
            )
        elif args.command == "run":
            execute_project(
                load_config(args.config),
                command=args.command_name,
                apply=args.apply,
                state_from=args.state_from,
                selection=args.selection,
                defer=args.defer,
                writeback=args.writeback,
                temporary_connection=args.temporary_connection,
            )
        else:
            deploy(
                load_config(args.config),
                apply=args.apply,
                build=args.build,
                temporary_connection=args.temporary_connection,
            )
    except DeploymentError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
