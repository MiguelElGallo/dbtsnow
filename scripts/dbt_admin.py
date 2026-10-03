#!/usr/bin/env python3
"""Administrator-only provisioning for fresh native dbt project destinations."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import dbt_native as native

ELEVATED_ROLES = {
    "ACCOUNTADMIN",
    "SECURITYADMIN",
    "SYSADMIN",
    "USERADMIN",
    "ORGADMIN",
    "GLOBALORGADMIN",
    "PUBLIC",
}


def identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not native.IDENTIFIER.fullmatch(value):
        raise native.DeploymentError(f"{label}: use a simple unquoted Snowflake identifier.")
    return value.upper()


def public_key(path: str) -> str:
    """Read an RSA public key without accepting or generating private key material."""
    try:
        source = Path(path).read_text(encoding="ascii")
    except (OSError, UnicodeError) as exc:
        raise native.DeploymentError("Cannot read RSA public-key file.") from exc
    if "PRIVATE KEY" in source or not source.startswith("-----BEGIN PUBLIC KEY-----"):
        raise native.DeploymentError("Supply an RSA PUBLIC KEY file, never a private key.")
    try:
        key = subprocess.run(
            ["openssl", "rsa", "-pubin", "-in", path, "-outform", "DER"],
            capture_output=True,
            check=True,
        )
        description = subprocess.run(
            ["openssl", "rsa", "-pubin", "-in", path, "-text", "-noout"],
            capture_output=True,
            check=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise native.DeploymentError(
            "Supply a valid RSA public key; OpenSSL must be installed."
        ) from exc
    size = re.search(r"Public-Key: \((\d+) bit\)", description.stdout)
    if size is None or int(size[1]) < 2048:
        raise native.DeploymentError("RSA public keys must be at least 2048 bits.")
    return base64.b64encode(key.stdout).decode("ascii")


def validate_bootstrap(config: native.Config, users: dict[str, tuple[str, str]]) -> None:
    native.validate_config(config)
    if not config.split_roles:
        raise native.DeploymentError(
            "Bootstrap requires distinct deployment_role and operator role."
        )
    for role in (config.project_admin_role, config.role):
        if identifier(role, "Delegated role") in ELEVATED_ROLES:
            raise native.DeploymentError(
                "Delegated roles must be new custom roles, not built-in roles."
            )
    if (config.database.upper(), config.object_schema.upper()) == (
        config.model_database.upper(),
        config.model_schema.upper(),
    ):
        raise native.DeploymentError("Object and model schemas must be separate.")
    names = []
    if len({role.upper() for role in users}) != len(users):
        raise native.DeploymentError("Each delegated role can have only one bootstrap test user.")
    for role, (user, key) in users.items():
        if role.upper() not in {config.project_admin_role.upper(), config.role.upper()}:
            raise native.DeploymentError(
                "User assignment does not match a configured project role."
            )
        names.append(identifier(user, "Test user"))
        if not re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", key):
            raise native.DeploymentError("Invalid public-key encoding.")
    if len(names) != len(set(names)):
        raise native.DeploymentError("Use separate users for project administration and operation.")
    expected = {
        config.project_admin_role.upper(): config.deployment_user,
        config.role.upper(): config.operator_user,
    }
    for role, (user, _) in users.items():
        expected_user = expected[role.upper()]
        if expected_user and expected_user.upper() != user.upper():
            raise native.DeploymentError(
                "Test user differs from the configuration's expected identity."
            )


def bootstrap_sql(
    config: native.Config,
    users: dict[str, tuple[str, str]],
    *,
    allow_model_schema_creation: bool = False,
) -> list[str]:
    """Generate bounded grants; privileged execution is never part of deployment or operation."""
    validate_bootstrap(config, users)
    project_schema = f"{config.database}.{config.object_schema}"
    model_schema = f"{config.model_database}.{config.model_schema}"
    admin_role = config.project_admin_role
    statements = [
        f"CREATE DATABASE {name}"
        for name in dict.fromkeys([config.database.upper(), config.model_database.upper()])
    ]
    statements.extend(
        [
            f"CREATE SCHEMA IF NOT EXISTS {config.database}.{config.object_schema}",
            f"CREATE SCHEMA IF NOT EXISTS {config.model_database}.{config.model_schema}",
            f"CREATE ROLE {config.project_admin_role}",
            f"CREATE ROLE {config.role}",
            f"GRANT USAGE ON DATABASE {config.database} TO ROLE {config.project_admin_role}",
            f"GRANT USAGE ON SCHEMA {project_schema} TO ROLE {admin_role}",
            f"GRANT CREATE DBT PROJECT ON SCHEMA {project_schema} TO ROLE {admin_role}",
            f"GRANT USAGE ON WAREHOUSE {config.warehouse} TO ROLE {config.project_admin_role}",
        ]
    )
    for name in dict.fromkeys([config.database.upper(), config.model_database.upper()]):
        statements.append(f"GRANT USAGE ON DATABASE {name} TO ROLE {config.role}")
    statements.extend(
        [
            f"GRANT USAGE ON SCHEMA {config.database}.{config.object_schema} TO ROLE {config.role}",
            f"GRANT USAGE ON SCHEMA {model_schema} TO ROLE {config.role}",
            f"GRANT CREATE TABLE, CREATE VIEW ON SCHEMA {model_schema} TO ROLE {config.role}",
            f"GRANT USAGE ON WAREHOUSE {config.warehouse} TO ROLE {config.role}",
        ]
    )
    if allow_model_schema_creation:
        statements.append(
            f"GRANT CREATE SCHEMA ON DATABASE {config.model_database} TO ROLE {config.role}"
        )
    for integration in config.external_access_integrations:
        for role in (config.project_admin_role, config.role):
            statements.append(f"GRANT USAGE ON INTEGRATION {integration} TO ROLE {role}")
    for role, (user, key) in users.items():
        statements.extend(
            [
                f"CREATE USER {user} TYPE = SERVICE DEFAULT_ROLE = {role} "
                f"DEFAULT_SECONDARY_ROLES = () DEFAULT_WAREHOUSE = {config.warehouse} "
                f"RSA_PUBLIC_KEY = '{key}'",
                f"GRANT ROLE {role} TO USER {user}",
            ]
        )
    return statements


def admin_options(config: native.Config, connection: str, role: str) -> list[str]:
    identifier(role, "Administrator role")
    if not native.LABEL.fullmatch(connection):
        raise native.DeploymentError("Use an explicit named administrator connection.")
    return [
        "--connection",
        connection,
        "--account",
        config.account,
        "--role",
        role,
        "--warehouse",
        config.warehouse,
        "--secondary-roles",
        "NONE",
    ]


def check_admin(config: native.Config, options: list[str], role: str) -> dict[str, Any]:
    version = native.run_command(["snow", "--version"])
    if not re.search(rf"(?<![\d.]){re.escape(native.CLI_VERSION)}(?![\d.])", version):
        raise native.DeploymentError(f"Install Snowflake CLI {native.CLI_VERSION} before applying.")
    rows = native.sql_rows(
        "SELECT CURRENT_ORGANIZATION_NAME() AS organization, CURRENT_ACCOUNT_NAME() AS account, "
        "CURRENT_ROLE() AS role, CURRENT_USER() AS user, "
        "CURRENT_SECONDARY_ROLES() AS secondary_roles",
        options,
    )
    if (
        len(rows) != 1
        or f"{rows[0].get('organization')}-{rows[0].get('account')}".upper()
        != config.account.upper()
        or str(rows[0].get("role")).upper() != role.upper()
    ):
        raise native.DeploymentError(
            "Administrator account or role does not match the reviewed plan."
        )
    raw_secondary = rows[0].get("secondary_roles")
    if not isinstance(raw_secondary, str):
        raise native.DeploymentError("Cannot verify administrator secondary roles.")
    try:
        secondary = json.loads(raw_secondary)
    except (TypeError, json.JSONDecodeError) as exc:
        raise native.DeploymentError("Cannot verify administrator secondary roles.") from exc
    if (
        not isinstance(secondary, dict)
        or secondary.get("roles") != ""
        or secondary.get("value") not in {"", "NONE"}
    ):
        raise native.DeploymentError("Administrator secondary roles must be NONE.")
    return rows[0]


def check_collisions(
    config: native.Config, users: dict[str, tuple[str, str]], options: list[str]
) -> None:
    """Check all names before the first write; never adopt users, roles, or databases."""
    resources = [("DATABASES", name) for name in set([config.database, config.model_database])]
    resources += [("ROLES", name) for name in (config.project_admin_role, config.role)]
    resources += [("USERS", user) for user, _ in users.values()]
    for kind, name in resources:
        rows = native.sql_rows(f"SHOW {kind} LIKE '{name}'", options)
        if any(str(row.get("name", "")).upper() == name.upper() for row in rows):
            raise native.DeploymentError(
                f"Bootstrap refuses existing {kind.lower()}: {name}; "
                "use fresh names or administrator-reviewed SQL."
            )
    warehouses = native.sql_rows(f"SHOW WAREHOUSES LIKE '{config.warehouse}'", options)
    if not any(str(row.get("name", "")).upper() == config.warehouse.upper() for row in warehouses):
        raise native.DeploymentError(
            "The configured existing warehouse is not visible to the administrator."
        )


def verify_bootstrap(
    config: native.Config,
    users: dict[str, tuple[str, str]],
    options: list[str],
    *,
    allow_model_schema_creation: bool = False,
) -> None:
    """Read back the exact resource and grant scope, plus newly provisioned identity defaults."""
    admin = config.project_admin_role.upper()
    operator = config.role.upper()
    required: dict[str, set[tuple[str, str, str]]] = {
        admin: {
            ("USAGE", "DATABASE", config.database.upper()),
            ("USAGE", "SCHEMA", f"{config.database}.{config.object_schema}".upper()),
            ("CREATE DBT PROJECT", "SCHEMA", f"{config.database}.{config.object_schema}".upper()),
            ("USAGE", "WAREHOUSE", config.warehouse.upper()),
        },
        operator: {
            ("USAGE", "DATABASE", config.database.upper()),
            ("USAGE", "DATABASE", config.model_database.upper()),
            ("USAGE", "SCHEMA", f"{config.database}.{config.object_schema}".upper()),
            ("USAGE", "SCHEMA", f"{config.model_database}.{config.model_schema}".upper()),
            ("CREATE TABLE", "SCHEMA", f"{config.model_database}.{config.model_schema}".upper()),
            ("CREATE VIEW", "SCHEMA", f"{config.model_database}.{config.model_schema}".upper()),
            ("USAGE", "WAREHOUSE", config.warehouse.upper()),
        },
    }
    if allow_model_schema_creation:
        required[operator].add(("CREATE SCHEMA", "DATABASE", config.model_database.upper()))
    for integration in config.external_access_integrations:
        for role in required:
            required[role].add(("USAGE", "INTEGRATION", integration.upper()))
    for role, expected in required.items():
        rows = native.sql_rows(f"SHOW GRANTS TO ROLE {role}", options)
        actual = {
            (
                str(row.get("privilege", "")).upper(),
                str(row.get("granted_on", "")).upper(),
                str(row.get("name", "")).upper(),
            )
            for row in rows
            if str(row.get("grantee_name", "")).upper() == role
            and str(row.get("granted_to", "")).upper() == "ROLE"
        }
        if actual != expected or len(rows) != len(actual):
            raise native.DeploymentError(
                f"Cannot verify all configured resource grants for {role}."
            )
    schemas = {
        (config.database.upper(), config.object_schema.upper()),
        (config.model_database.upper(), config.model_schema.upper()),
    }
    for database, schema in sorted(schemas):
        rows = native.sql_rows(f"SHOW SCHEMAS LIKE '{schema}' IN DATABASE {database}", options)
        matches = [
            row
            for row in rows
            if str(row.get("name", "")).upper() == schema
            and str(row.get("database_name", "")).upper() == database
        ]
        if (
            len(matches) != 1
            or not isinstance(matches[0].get("options"), str)
            or "MANAGED ACCESS" in matches[0]["options"].upper()
        ):
            raise native.DeploymentError("Cannot verify the new standard project/model schema.")
    for role, (user, key) in users.items():
        rows = native.sql_rows(f"SHOW USERS LIKE '{user}'", options)
        match = [row for row in rows if str(row.get("name", "")).upper() == user.upper()]
        if (
            len(match) != 1
            or str(match[0].get("type", "")).upper() != "SERVICE"
            or str(match[0].get("default_role", "")).upper() != role.upper()
            or str(match[0].get("default_warehouse", "")).upper() != config.warehouse.upper()
        ):
            raise native.DeploymentError(f"Cannot verify new service user {user}.")
        raw_defaults = match[0].get("default_secondary_roles")
        if not isinstance(raw_defaults, str):
            raise native.DeploymentError("Cannot verify new user secondary-role defaults.")
        try:
            defaults = json.loads(raw_defaults)
        except (TypeError, json.JSONDecodeError) as exc:
            raise native.DeploymentError("Cannot verify new user secondary-role defaults.") from exc
        if defaults != []:
            raise native.DeploymentError("New user secondary-role defaults must be empty.")
        grants = native.sql_rows(f"SHOW GRANTS TO USER {user}", options)
        if {str(row.get("role", "")).upper() for row in grants} != {role.upper()}:
            raise native.DeploymentError(
                f"New service user {user} does not have exactly its assigned role."
            )
        properties = native.sql_rows(f"DESC USER {user}", options)
        fingerprint = "SHA256:" + base64.b64encode(
            hashlib.sha256(base64.b64decode(key)).digest()
        ).decode("ascii")
        if not any(
            str(row.get("property", "")).upper() == "RSA_PUBLIC_KEY_FP"
            and row.get("value") == fingerprint
            for row in properties
        ):
            raise native.DeploymentError(f"Cannot verify the public key assigned to {user}.")


def bootstrap(
    config: native.Config,
    *,
    connection: str,
    admin_role: str,
    users: dict[str, tuple[str, str]],
    allow_model_schema_creation: bool = False,
    apply: bool = False,
) -> None:
    statements = bootstrap_sql(
        config, users, allow_model_schema_creation=allow_model_schema_creation
    )
    options = admin_options(config, connection, admin_role)
    print(f"Administrator setup: {config.account}; caller role {admin_role}")
    for statement in statements:
        print(statement + ";")
    print(
        "After deployment, project administrator must grant operator access on "
        f"{config.object_name}."
    )
    if not apply:
        print("Dry run: no Snowflake connection. Add --apply to provision fresh resources.")
        return
    identity = check_admin(config, options, admin_role)
    check_collisions(config, users, options)
    for statement in statements:
        native.sql_rows(statement, options)
    verify_bootstrap(
        config, users, options, allow_model_schema_creation=allow_model_schema_creation
    )
    print(
        f"Verified administrator setup as {identity['user']} / {identity['role']}. "
        "No project deployed or models built."
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    command = commands.add_parser(
        "bootstrap", help="Preview administrator SQL; --apply provisions only fresh resources."
    )
    command.add_argument("--config", required=True)
    command.add_argument("--admin-connection", required=True)
    command.add_argument("--admin-role", required=True)
    command.add_argument("--apply", action="store_true")
    command.add_argument("--allow-model-schema-creation", action="store_true")
    for persona in ("project-admin", "operator"):
        command.add_argument(f"--{persona}-user")
        command.add_argument(f"--{persona}-public-key-file")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        config = native.load_config(args.config)
        users = {}
        for persona, role in (
            ("project_admin", config.project_admin_role),
            ("operator", config.role),
        ):
            user, path = (
                getattr(args, persona + "_user"),
                getattr(args, persona + "_public_key_file"),
            )
            if bool(user) != bool(path):
                raise native.DeploymentError(
                    "Each new service user needs its own public-key file and user name."
                )
            if user and path:
                users[role] = (user, public_key(path))
        bootstrap(
            config,
            connection=args.admin_connection,
            admin_role=args.admin_role,
            users=users,
            allow_model_schema_creation=args.allow_model_schema_creation,
            apply=args.apply,
        )
    except native.DeploymentError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
