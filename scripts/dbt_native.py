#!/usr/bin/env python3
"""Prepare and deploy a native Snowflake DBT PROJECT with explicit destinations."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
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
    if config.connection is not None and (
        not isinstance(config.connection, str) or not LABEL.fullmatch(config.connection)
    ):
        raise DeploymentError("connection must be a simple local connection name or null.")
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


def native_profile(config: Config) -> dict[str, Any]:
    return {
        config.profile: {
            "target": config.target,
            "outputs": {
                config.target: {
                    "type": "snowflake",
                    "database": config.model_database,
                    "schema": config.model_schema,
                    "role": config.role,
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
    integrations = args.external_access_integration or []
    if not args.non_interactive and not integrations:
        response = ask(
            "existing external access integrations (comma-separated, blank for none)", "", False
        )
        integrations = [item.strip() for item in response.split(",") if item.strip()]
    values["external_access_integrations"] = integrations
    config = Config(**values)
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
            "deployment was not verified."
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


def connection_options(config: Config, temporary: bool) -> list[str]:
    auth = (
        ["--temporary-connection"]
        if temporary or not config.connection
        else ["--connection", config.connection]
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
        config.role,
        "--warehouse",
        config.warehouse,
    ]


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


def preflight(config: Config, options: list[str]) -> None:
    version = run_command(["snow", "--version"])
    if not re.search(rf"(?<![\d.]){re.escape(CLI_VERSION)}(?![\d.])", version):
        raise DeploymentError(f"Install pinned Snowflake CLI {CLI_VERSION} before applying.")
    identity = sql_rows(
        "SELECT CURRENT_ORGANIZATION_NAME() AS organization, "
        "CURRENT_ACCOUNT_NAME() AS account, CURRENT_ROLE() AS role",
        options,
    )
    if len(identity) != 1:
        raise DeploymentError("Cannot verify Snowflake session identity.")
    row = identity[0]
    actual = f"{row.get('organization', '')}-{row.get('account', '')}"
    if (
        actual.upper() != config.account.upper()
        or str(row.get("role", "")).upper() != config.role.upper()
    ):
        raise DeploymentError("Authenticated account or role does not match the deployment config.")
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
    objects = sql_rows(
        f"SHOW DBT PROJECTS LIKE '{config.project}' "
        f"IN SCHEMA {config.database}.{config.object_schema}",
        options,
    )
    existing = [
        row for row in objects if str(row.get("name", "")).upper() == config.project.upper()
    ]
    if existing:
        versions = sql_rows(f"SHOW VERSIONS IN DBT PROJECT {config.object_name}", options)
        if not versions or not any(
            row.get("is_live") in (True, "true", "TRUE", "Y") for row in versions
        ):
            raise DeploymentError(
                "Existing object uses legacy numbered versions. Have its owner explicitly "
                "migrate it before deployment; this tool never replaces it."
            )


def show_plan(config: Config, uploaded: list[str]) -> None:
    print(f"Account: {config.account}; role: {config.role}; warehouse: {config.warehouse}")
    print(f"DBT PROJECT: {config.object_name}")
    print(
        f"Model target: {config.model_database}.{config.model_schema}; "
        f"profile/target: {config.profile}/{config.target}"
    )
    print(f"Runtime: {config.dbt_version}; automatic compile: enabled; force replacement: disabled")
    print("Upload files:\n" + "\n".join(f"  {name}" for name in uploaded))


def verify_readback(config: Config, rows: list[dict[str, Any]], metadata: dict[str, str]) -> None:
    if len(rows) != 1:
        raise DeploymentError("Deployment returned no unique DBT PROJECT description.")
    row = rows[0]
    for key, expected_value in (("name", config.project), ("owner", config.role)):
        if key in row and str(row[key]).upper() != expected_value.upper():
            raise DeploymentError(f"Deployment readback {key} does not match the config.")
    expected = {"dbt_version": config.dbt_version, "default_target": config.target}
    if any(str(row.get(key, "")) != value for key, value in expected.items()):
        raise DeploymentError("Deployment readback runtime or target does not match the config.")
    if str(row.get("default_version", "")).upper() != "LIVE":
        raise DeploymentError("Deployment readback did not confirm a mutable LIVE version.")
    if "auto_compile" in row and str(row["auto_compile"]).lower() != "true":
        raise DeploymentError("Deployment readback did not confirm automatic compilation.")
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
        options = connection_options(config, temporary_connection)
        metadata = github_metadata(source_directory(config))
        receipt = write_receipt(config, prepared, uploaded, metadata)
        preflight(config, options)
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
            "--auto-compile",
            "--no-default-writeback",
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
            run_command(
                [
                    "snow",
                    "dbt",
                    "execute",
                    *options,
                    config.object_name,
                    "build",
                    "--target",
                    config.target,
                ]
            )
            print("dbt build completed successfully.")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    setup = commands.add_parser(
        "wizard",
        help="Infer values, ask for missing settings, and save a config without connecting.",
    )
    setup.add_argument("--source", default="example")
    setup.add_argument("--connection")
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
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "wizard":
            wizard(args)
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
