"""Administrator provisioning must keep delegated identities and privileges separate."""

from __future__ import annotations

import base64
import hashlib
import io
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

from scripts import dbt_admin as admin
from scripts import dbt_native as native


class AdministratorSetupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.keys = tempfile.TemporaryDirectory()
        cls.key_root = Path(cls.keys.name)
        cls.public_files: dict[int, Path] = {}
        for bits in (2048, 1024):
            private = cls.key_root / f"rsa-{bits}.p8"
            public = cls.key_root / f"rsa-{bits}.pub.pem"
            subprocess.run(
                [
                    "openssl",
                    "genpkey",
                    "-algorithm",
                    "RSA",
                    "-pkeyopt",
                    f"rsa_keygen_bits:{bits}",
                    "-out",
                    str(private),
                ],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(public)],
                check=True,
                capture_output=True,
            )
            cls.public_files[bits] = public
        cls.valid_key = admin.public_key(str(cls.public_files[2048]))
        cls.fingerprint = "SHA256:" + base64.b64encode(
            hashlib.sha256(base64.b64decode(cls.valid_key)).digest()
        ).decode("ascii")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.keys.cleanup()

    def setUp(self) -> None:
        output = patch("sys.stdout", new_callable=io.StringIO)
        self.stdout = output.start()
        self.addCleanup(output.stop)
        self.config = native.Config(
            source="example",
            account="ORG-ACCOUNT",
            database="CONTROL_DB",
            object_schema="PROJECTS",
            project="PIPELINE",
            role="DBT_OPERATOR",
            warehouse="COMPUTE",
            model_database="MODEL_DB",
            model_schema="ANALYTICS",
            profile="pipeline",
            target="dev",
            connection="operator",
            deployment_role="DBT_PROJECT_ADMIN",
            deployment_connection="project_admin",
            deployment_user="PROJECT_ADMIN_SVC",
            operator_user="OPERATOR_SVC",
            auto_compile=False,
        )
        self.users = {
            "DBT_PROJECT_ADMIN": ("PROJECT_ADMIN_SVC", self.valid_key),
            "DBT_OPERATOR": ("OPERATOR_SVC", self.valid_key),
        }
        self.options = admin.admin_options(self.config, "approved_admin", "ACCOUNTADMIN")

    def grant_rows(self, role: str, *, allow_schema_creation: bool = False) -> list[dict[str, str]]:
        if role == "DBT_PROJECT_ADMIN":
            triples = [
                ("USAGE", "DATABASE", "CONTROL_DB"),
                ("USAGE", "SCHEMA", "CONTROL_DB.PROJECTS"),
                ("CREATE DBT PROJECT", "SCHEMA", "CONTROL_DB.PROJECTS"),
                ("USAGE", "WAREHOUSE", "COMPUTE"),
            ]
        else:
            triples = [
                ("USAGE", "DATABASE", "CONTROL_DB"),
                ("USAGE", "DATABASE", "MODEL_DB"),
                ("USAGE", "SCHEMA", "CONTROL_DB.PROJECTS"),
                ("USAGE", "SCHEMA", "MODEL_DB.ANALYTICS"),
                ("CREATE TABLE", "SCHEMA", "MODEL_DB.ANALYTICS"),
                ("CREATE VIEW", "SCHEMA", "MODEL_DB.ANALYTICS"),
                ("USAGE", "WAREHOUSE", "COMPUTE"),
            ]
            if allow_schema_creation:
                triples.append(("CREATE SCHEMA", "DATABASE", "MODEL_DB"))
        return [
            {
                "privilege": privilege,
                "granted_on": kind,
                "name": name,
                "granted_to": "ROLE",
                "grantee_name": role,
            }
            for privilege, kind, name in triples
        ]

    def cloud_rows(self, query: str, _: list[str]) -> list[dict[str, Any]]:
        if "CURRENT_ORGANIZATION_NAME" in query:
            return [
                {
                    "organization": "ORG",
                    "account": "ACCOUNT",
                    "role": "ACCOUNTADMIN",
                    "user": "PLATFORM_ADMIN",
                    "secondary_roles": '{"roles":"","value":""}',
                }
            ]
        if query.startswith("SHOW SCHEMAS LIKE "):
            schema = query.split("'")[1]
            database = query.rsplit(" ", 1)[-1]
            return [{"name": schema, "database_name": database, "options": ""}]
        if query.startswith("SHOW GRANTS TO ROLE "):
            return self.grant_rows(query.rsplit(" ", 1)[-1])
        if query.startswith("SHOW GRANTS TO USER "):
            user = query.rsplit(" ", 1)[-1]
            role = "DBT_PROJECT_ADMIN" if user == "PROJECT_ADMIN_SVC" else "DBT_OPERATOR"
            return [{"role": role}]
        if query.startswith("DESC USER ") or query.startswith("DESCRIBE USER "):
            return [{"property": "RSA_PUBLIC_KEY_FP", "value": self.fingerprint}]
        if query.startswith("SHOW USERS LIKE "):
            user = query.split("'")[1]
            role = "DBT_PROJECT_ADMIN" if user == "PROJECT_ADMIN_SVC" else "DBT_OPERATOR"
            return [
                {
                    "name": user,
                    "type": "SERVICE",
                    "default_role": role,
                    "default_warehouse": "COMPUTE",
                    "default_secondary_roles": "[]",
                }
            ]
        if query.startswith("SHOW WAREHOUSES LIKE "):
            return [{"name": "COMPUTE"}]
        return []

    def test_preview_never_connects_or_executes_cloud_commands(self) -> None:
        with patch.object(native, "run_command") as run, patch.object(native, "sql_rows") as sql:
            admin.bootstrap(
                self.config,
                connection="approved_admin",
                admin_role="ACCOUNTADMIN",
                users=self.users,
            )
        run.assert_not_called()
        sql.assert_not_called()
        self.assertIn("Dry run: no Snowflake connection", self.stdout.getvalue())
        self.assertIn("caller role ACCOUNTADMIN", self.stdout.getvalue())
        self.assertNotIn("PRIVATE KEY", self.stdout.getvalue())

    def test_apply_uses_only_explicit_admin_connection_and_no_secondary_roles(self) -> None:
        with (
            patch.object(
                admin,
                "check_admin",
                return_value={"user": "PLATFORM_ADMIN", "role": "ACCOUNTADMIN"},
            ),
            patch.object(admin, "verify_bootstrap"),
            patch.object(
                native,
                "sql_rows",
                side_effect=lambda query, options: (
                    [{"name": "COMPUTE"}] if query.startswith("SHOW WAREHOUSES") else []
                ),
            ) as sql,
        ):
            admin.bootstrap(
                self.config,
                connection="approved_admin",
                admin_role="ACCOUNTADMIN",
                users=self.users,
                apply=True,
            )
        self.assertTrue(sql.call_args_list)
        for call in sql.call_args_list:
            options = call.args[1]
            self.assertEqual(options[options.index("--connection") + 1], "approved_admin")
            self.assertEqual(options[options.index("--role") + 1], "ACCOUNTADMIN")
            self.assertEqual(options[options.index("--secondary-roles") + 1], "NONE")
            self.assertEqual(options[options.index("--account") + 1], "ORG-ACCOUNT")
        queries = [call.args[0] for call in sql.call_args_list]
        self.assertFalse(
            any(
                "DBT PROJECT" in query and not query.startswith("GRANT CREATE DBT PROJECT")
                for query in queries
            )
        )
        self.assertFalse(any("EXECUTE" in query or "CREATE TABLE " in query for query in queries))

    def test_connection_and_admin_role_reject_injection_before_connecting(self) -> None:
        for connection, role in (
            ("admin; DROP DATABASE X", "ACCOUNTADMIN"),
            ("", "ACCOUNTADMIN"),
            ("approved", "ACCOUNTADMIN; GRANT ALL"),
        ):
            with (
                self.subTest(connection=connection, role=role),
                patch.object(native, "sql_rows") as sql,
                self.assertRaises(native.DeploymentError),
            ):
                admin.bootstrap(
                    self.config,
                    connection=connection,
                    admin_role=role,
                    users=self.users,
                    apply=True,
                )
            sql.assert_not_called()

    def test_wrong_account_or_primary_admin_role_blocks_every_write(self) -> None:
        identity = {
            "organization": "ORG",
            "account": "ACCOUNT",
            "role": "ACCOUNTADMIN",
            "user": "PLATFORM_ADMIN",
            "secondary_roles": '{"roles":"","value":""}',
        }
        for field in ("organization", "account", "role"):
            calls: list[str] = []

            def rows(
                query: str, _: list[str], field: str = field, calls: list[str] = calls
            ) -> list[dict[str, Any]]:
                calls.append(query)
                return [dict(identity, **{field: "WRONG"})]

            with (
                self.subTest(field=field),
                patch.object(native, "run_command", return_value="Snowflake CLI 3.28.0"),
                patch.object(native, "sql_rows", side_effect=rows),
                self.assertRaises(native.DeploymentError),
            ):
                admin.bootstrap(
                    self.config,
                    connection="approved_admin",
                    admin_role="ACCOUNTADMIN",
                    users=self.users,
                    apply=True,
                )
            self.assertEqual(len(calls), 1)
            self.assertTrue(calls[0].startswith("SELECT CURRENT_ORGANIZATION_NAME"))

    def test_admin_secondary_role_verification_fails_closed(self) -> None:
        identity = {
            "organization": "ORG",
            "account": "ACCOUNT",
            "role": "ACCOUNTADMIN",
            "user": "PLATFORM_ADMIN",
        }
        for value in (
            None,
            "invalid json",
            "{}",
            '{"roles":["SYSADMIN"],"value":"NONE"}',
            '{"roles":[],"value":"ALL"}',
        ):
            with (
                self.subTest(value=value),
                patch.object(native, "run_command", return_value="3.28.0"),
                patch.object(
                    native, "sql_rows", return_value=[dict(identity, secondary_roles=value)]
                ),
                self.assertRaises(native.DeploymentError),
            ):
                admin.check_admin(self.config, self.options, "ACCOUNTADMIN")
        with (
            patch.object(native, "run_command", return_value="3.28.0"),
            patch.object(native, "sql_rows", return_value=[identity]),
            self.assertRaises(native.DeploymentError),
        ):
            admin.check_admin(self.config, self.options, "ACCOUNTADMIN")

    def test_cli_version_mismatch_blocks_identity_query(self) -> None:
        with (
            patch.object(native, "run_command", return_value="Snowflake CLI 3.27.0"),
            patch.object(native, "sql_rows") as sql,
            self.assertRaises(native.DeploymentError),
        ):
            admin.check_admin(self.config, self.options, "ACCOUNTADMIN")
        sql.assert_not_called()

    def test_exact_resource_collisions_block_before_first_write(self) -> None:
        targets = [
            ("DATABASES", "CONTROL_DB"),
            ("DATABASES", "MODEL_DB"),
            ("ROLES", "DBT_PROJECT_ADMIN"),
            ("ROLES", "DBT_OPERATOR"),
            ("USERS", "PROJECT_ADMIN_SVC"),
            ("USERS", "OPERATOR_SVC"),
        ]
        for kind, name in targets:
            queries: list[str] = []

            def rows(
                query: str,
                _: list[str],
                kind: str = kind,
                name: str = name,
                queries: list[str] = queries,
            ) -> list[dict[str, str]]:
                queries.append(query)
                if query == f"SHOW {kind} LIKE '{name}'":
                    return [{"name": name.lower()}]
                if query.startswith("SHOW WAREHOUSES"):
                    return [{"name": "COMPUTE"}]
                return []

            with (
                self.subTest(kind=kind, name=name),
                patch.object(admin, "check_admin", return_value={}),
                patch.object(native, "sql_rows", side_effect=rows),
                self.assertRaisesRegex(native.DeploymentError, "refuses existing"),
            ):
                admin.bootstrap(
                    self.config,
                    connection="approved_admin",
                    admin_role="ACCOUNTADMIN",
                    users=self.users,
                    apply=True,
                )
            self.assertTrue(queries)
            self.assertTrue(all(query.startswith("SHOW ") for query in queries))

    def test_like_wildcards_do_not_adopt_or_block_similarly_named_resources(self) -> None:
        def rows(query: str, _: list[str]) -> list[dict[str, str]]:
            name = query.split("'")[1]
            if query.startswith("SHOW WAREHOUSES"):
                return [{"name": "COMPUTE"}]
            return [{"name": name.replace("_", "X") + "_OTHER"}]

        with patch.object(native, "sql_rows", side_effect=rows):
            admin.check_collisions(self.config, self.users, self.options)

    def test_missing_warehouse_blocks_before_first_write(self) -> None:
        with (
            patch.object(admin, "check_admin", return_value={}),
            patch.object(native, "sql_rows", return_value=[]) as sql,
            self.assertRaisesRegex(native.DeploymentError, "warehouse"),
        ):
            admin.bootstrap(
                self.config,
                connection="approved_admin",
                admin_role="ACCOUNTADMIN",
                users=self.users,
                apply=True,
            )
        self.assertTrue(all(call.args[0].startswith("SHOW ") for call in sql.call_args_list))

    def test_two_custom_roles_are_required(self) -> None:
        for config in (
            replace(self.config, deployment_role=None),
            replace(self.config, deployment_role="dbt_operator"),
        ):
            with (
                self.subTest(role=config.deployment_role),
                self.assertRaises(native.DeploymentError),
            ):
                admin.bootstrap_sql(config, {})
        for role in admin.ELEVATED_ROLES:
            for field in ("role", "deployment_role"):
                with (
                    self.subTest(role=role, field=field),
                    self.assertRaisesRegex(native.DeploymentError, "custom roles"),
                ):
                    admin.bootstrap_sql(replace(self.config, **{field: role}), {})

    def test_same_schema_and_invalid_resource_identifiers_are_rejected(self) -> None:
        config = replace(self.config, model_database="control_db", model_schema="projects")
        with self.assertRaisesRegex(native.DeploymentError, "separate"):
            admin.bootstrap_sql(config, {})
        for field in (
            "database",
            "object_schema",
            "model_database",
            "model_schema",
            "warehouse",
            "role",
            "deployment_role",
        ):
            with self.subTest(field=field), self.assertRaises(native.DeploymentError):
                admin.bootstrap_sql(
                    replace(self.config, **{field: "X; DROP DATABASE CONTROL_DB"}), {}
                )

    def test_user_names_and_assignments_are_bounded(self) -> None:
        invalid = [
            {"DBT_PROJECT_ADMIN": ("USER; GRANT ROLE ACCOUNTADMIN", self.valid_key)},
            {"ACCOUNTADMIN": ("ADMIN_SVC", self.valid_key)},
            {
                "DBT_PROJECT_ADMIN": ("PROJECT_ADMIN_SVC", self.valid_key),
                "DBT_OPERATOR": ("project_admin_svc", self.valid_key),
            },
            {"DBT_PROJECT_ADMIN": ("WRONG_ADMIN_SVC", self.valid_key)},
            {"DBT_OPERATOR": ("WRONG_OPERATOR_SVC", self.valid_key)},
            {"DBT_OPERATOR": ("OPERATOR_SVC", "key'; GRANT ALL")},
            {
                "DBT_PROJECT_ADMIN": ("PROJECT_ADMIN_SVC", self.valid_key),
                "dbt_project_admin": ("OTHER_ADMIN_SVC", self.valid_key),
            },
        ]
        for users in invalid:
            with self.subTest(users=tuple(users)), self.assertRaises(native.DeploymentError):
                admin.bootstrap_sql(self.config, users)

    def test_cli_requires_user_and_public_key_as_a_pair(self) -> None:
        base = [
            "bootstrap",
            "--config",
            "unused.json",
            "--admin-connection",
            "approved_admin",
            "--admin-role",
            "ACCOUNTADMIN",
        ]
        for option, value in (
            ("--project-admin-user", "PROJECT_ADMIN_SVC"),
            ("--operator-user", "OPERATOR_SVC"),
            ("--project-admin-public-key-file", "unused.pem"),
            ("--operator-public-key-file", "unused.pem"),
        ):
            with (
                self.subTest(option=option),
                patch.object(native, "load_config", return_value=self.config),
                patch.object(admin, "bootstrap") as bootstrap,
                patch("sys.stderr", new_callable=io.StringIO),
            ):
                self.assertEqual(admin.main([*base, option, value]), 1)
            bootstrap.assert_not_called()

    def test_new_users_are_service_logins_with_exactly_one_independent_role(self) -> None:
        statements = admin.bootstrap_sql(self.config, self.users)
        users = [statement for statement in statements if statement.startswith("CREATE USER")]
        self.assertEqual(len(users), 2)
        self.assertTrue(
            all(
                "TYPE = SERVICE" in statement and "DEFAULT_SECONDARY_ROLES = ()" in statement
                for statement in users
            )
        )
        self.assertTrue(
            all("PASSWORD" not in statement and "PRIVATE" not in statement for statement in users)
        )
        role_grants = [statement for statement in statements if statement.startswith("GRANT ROLE")]
        self.assertEqual(
            role_grants,
            [
                "GRANT ROLE DBT_PROJECT_ADMIN TO USER PROJECT_ADMIN_SVC",
                "GRANT ROLE DBT_OPERATOR TO USER OPERATOR_SVC",
            ],
        )
        self.assertFalse(any("TO ROLE" in statement for statement in role_grants))
        self.assertFalse(
            any(
                "OR REPLACE" in statement or "FUTURE" in statement or "ALL PRIVILEGES" in statement
                for statement in statements
            )
        )

    def test_privileges_do_not_combine_project_creation_and_model_operation(self) -> None:
        statements = admin.bootstrap_sql(self.config, {})
        admin_grants = [
            statement for statement in statements if statement.endswith("TO ROLE DBT_PROJECT_ADMIN")
        ]
        operator_grants = [
            statement for statement in statements if statement.endswith("TO ROLE DBT_OPERATOR")
        ]
        self.assertIn(
            "GRANT CREATE DBT PROJECT ON SCHEMA CONTROL_DB.PROJECTS TO ROLE DBT_PROJECT_ADMIN",
            admin_grants,
        )
        self.assertFalse(
            any(
                "MODEL_DB" in statement or "CREATE TABLE" in statement or "CREATE VIEW" in statement
                for statement in admin_grants
            )
        )
        self.assertIn(
            "GRANT CREATE TABLE, CREATE VIEW ON SCHEMA MODEL_DB.ANALYTICS TO ROLE DBT_OPERATOR",
            operator_grants,
        )
        self.assertFalse(
            any(
                "CREATE DBT PROJECT" in statement
                or "OWNERSHIP" in statement
                or "CREATE SCHEMA" in statement
                for statement in operator_grants
            )
        )
        self.assertFalse(
            any(
                "MANAGE GRANTS" in statement
                or "CREATE USER" in statement
                or "CREATE ROLE" in statement
                for statement in admin_grants + operator_grants
            )
        )

    def test_model_schema_creation_is_an_explicit_bounded_opt_in(self) -> None:
        default = admin.bootstrap_sql(self.config, {})
        opted_in = admin.bootstrap_sql(self.config, {}, allow_model_schema_creation=True)
        extra = [statement for statement in opted_in if statement not in default]
        self.assertEqual(extra, ["GRANT CREATE SCHEMA ON DATABASE MODEL_DB TO ROLE DBT_OPERATOR"])
        with (
            patch.object(
                admin,
                "check_admin",
                return_value={"user": "PLATFORM_ADMIN", "role": "ACCOUNTADMIN"},
            ),
            patch.object(admin, "check_collisions"),
            patch.object(admin, "verify_bootstrap") as verify,
            patch.object(native, "sql_rows", return_value=[]),
        ):
            admin.bootstrap(
                self.config,
                connection="approved_admin",
                admin_role="ACCOUNTADMIN",
                users={},
                allow_model_schema_creation=True,
                apply=True,
            )
        self.assertTrue(verify.call_args.kwargs["allow_model_schema_creation"])

    def test_shared_database_is_created_once_and_separate_schemas_remain_scoped(self) -> None:
        config = replace(self.config, model_database="control_db")
        statements = admin.bootstrap_sql(config, {})
        self.assertEqual(
            [statement for statement in statements if statement.startswith("CREATE DATABASE")],
            ["CREATE DATABASE CONTROL_DB"],
        )
        self.assertIn("CREATE SCHEMA IF NOT EXISTS control_db.ANALYTICS", statements)

    def test_public_key_reader_accepts_rsa_2048_and_rejects_private_weak_or_malformed(self) -> None:
        self.assertTrue(base64.b64decode(admin.public_key(str(self.public_files[2048]))))
        private = self.key_root / "rsa-2048.p8"
        with (
            patch.object(admin.subprocess, "run") as run,
            self.assertRaisesRegex(native.DeploymentError, "never a private"),
        ):
            admin.public_key(str(private))
        run.assert_not_called()
        with self.assertRaisesRegex(native.DeploymentError, "2048"):
            admin.public_key(str(self.public_files[1024]))
        with tempfile.TemporaryDirectory() as temporary:
            malformed = Path(temporary) / "invalid.pem"
            malformed.write_text(
                "-----BEGIN PUBLIC KEY-----\ninvalid-key\n-----END PUBLIC KEY-----\n"
            )
            with self.assertRaisesRegex(native.DeploymentError, "valid RSA"):
                admin.public_key(str(malformed))
            with self.assertRaisesRegex(native.DeploymentError, "Cannot read"):
                admin.public_key(str(Path(temporary) / "missing.pem"))

    def test_private_key_rejection_never_prints_private_material(self) -> None:
        private = self.key_root / "rsa-2048.p8"
        args = [
            "bootstrap",
            "--config",
            "unused.json",
            "--admin-connection",
            "approved_admin",
            "--admin-role",
            "ACCOUNTADMIN",
            "--project-admin-user",
            "PROJECT_ADMIN_SVC",
            "--project-admin-public-key-file",
            str(private),
        ]
        with (
            patch.object(native, "load_config", return_value=self.config),
            patch.object(admin, "bootstrap") as bootstrap,
            patch("sys.stderr", new_callable=io.StringIO) as stderr,
        ):
            self.assertEqual(admin.main(args), 1)
        bootstrap.assert_not_called()
        private_text = private.read_text()
        self.assertNotIn(private_text.splitlines()[1], stderr.getvalue() + self.stdout.getvalue())

    def test_readback_checks_both_exact_privilege_sets_and_service_identities(self) -> None:
        with patch.object(native, "sql_rows", side_effect=self.cloud_rows):
            admin.verify_bootstrap(self.config, self.users, self.options)

    def test_missing_or_wrong_scope_grant_never_reports_verified_setup(self) -> None:
        cases = [
            ("DBT_PROJECT_ADMIN", "CREATE DBT PROJECT", "privilege", "USAGE"),
            ("DBT_PROJECT_ADMIN", "USAGE", "granted_on", "TABLE"),
            ("DBT_OPERATOR", "CREATE TABLE", "name", "MODEL_DB.WRONG_SCHEMA"),
            ("DBT_OPERATOR", "CREATE VIEW", "grantee_name", "WRONG_ROLE"),
            ("DBT_OPERATOR", "CREATE VIEW", "granted_to", "USER"),
            ("DBT_OPERATOR", "CREATE VIEW", "privilege", "SELECT"),
        ]
        for role, privilege, field, wrong in cases:

            def rows(
                query: str,
                options: list[str],
                role: str = role,
                privilege: str = privilege,
                field: str = field,
                wrong: str = wrong,
            ) -> list[dict[str, Any]]:
                result = self.cloud_rows(query, options)
                if query == f"SHOW GRANTS TO ROLE {role}":
                    row = next(row for row in result if row["privilege"] == privilege)
                    row[field] = wrong
                return result

            with (
                self.subTest(role=role, privilege=privilege, field=field),
                patch.object(native, "sql_rows", side_effect=rows),
                self.assertRaises(native.DeploymentError),
            ):
                admin.verify_bootstrap(self.config, self.users, self.options)

    def test_each_required_grant_is_verified_before_claiming_success(self) -> None:
        for role in ("DBT_PROJECT_ADMIN", "DBT_OPERATOR"):
            for missing in self.grant_rows(role):

                def rows(
                    query: str,
                    options: list[str],
                    role: str = role,
                    missing: dict[str, str] = missing,
                ) -> list[dict[str, Any]]:
                    result = self.cloud_rows(query, options)
                    if query == f"SHOW GRANTS TO ROLE {role}":
                        result.remove(missing)
                    return result

                with (
                    self.subTest(role=role, missing=missing),
                    patch.object(native, "sql_rows", side_effect=rows),
                    self.assertRaises(native.DeploymentError),
                ):
                    admin.verify_bootstrap(self.config, self.users, self.options)

    def test_extra_privileges_or_inherited_roles_fail_fresh_role_readback(self) -> None:
        for privilege, kind, name in (
            ("CREATE DATABASE", "ACCOUNT", "ORG-ACCOUNT"),
            ("USAGE", "ROLE", "DBT_OPERATOR"),
            ("SELECT", "TABLE", "MODEL_DB.SENSITIVE.DATA"),
        ):

            def rows(
                query: str,
                options: list[str],
                privilege: str = privilege,
                kind: str = kind,
                name: str = name,
            ) -> list[dict[str, Any]]:
                result = self.cloud_rows(query, options)
                if query == "SHOW GRANTS TO ROLE DBT_PROJECT_ADMIN":
                    result.append(
                        {
                            "privilege": privilege,
                            "granted_on": kind,
                            "name": name,
                            "granted_to": "ROLE",
                            "grantee_name": "DBT_PROJECT_ADMIN",
                        }
                    )
                return result

            with (
                self.subTest(privilege=privilege, kind=kind),
                patch.object(native, "sql_rows", side_effect=rows),
                self.assertRaises(native.DeploymentError),
            ):
                admin.verify_bootstrap(self.config, self.users, self.options)

    def test_schema_readback_rejects_managed_foreign_missing_or_duplicate_rows(self) -> None:
        for fault in ("managed", "foreign_database", "missing", "duplicate", "unknown_options"):

            def rows(query: str, options: list[str], fault: str = fault) -> list[dict[str, Any]]:
                result = self.cloud_rows(query, options)
                if query == "SHOW SCHEMAS LIKE 'PROJECTS' IN DATABASE CONTROL_DB":
                    if fault == "managed":
                        result[0]["options"] = "MANAGED ACCESS"
                    elif fault == "foreign_database":
                        result[0]["database_name"] = "WRONG_DATABASE"
                    elif fault == "missing":
                        return []
                    elif fault == "duplicate":
                        return [result[0], dict(result[0])]
                    else:
                        result[0].pop("options")
                return result

            with (
                self.subTest(fault=fault),
                patch.object(native, "sql_rows", side_effect=rows),
                self.assertRaises(native.DeploymentError),
            ):
                admin.verify_bootstrap(self.config, self.users, self.options)

    def test_opted_in_schema_creation_and_external_access_are_verified(self) -> None:
        config = replace(self.config, external_access_integrations=["APPROVED_DBT_PACKAGES"])

        def rows(query: str, options: list[str]) -> list[dict[str, Any]]:
            if query.startswith("SHOW GRANTS TO ROLE "):
                role = query.rsplit(" ", 1)[-1]
                return self.grant_rows(role, allow_schema_creation=True) + [
                    {
                        "privilege": "USAGE",
                        "granted_on": "INTEGRATION",
                        "name": "APPROVED_DBT_PACKAGES",
                        "granted_to": "ROLE",
                        "grantee_name": role,
                    }
                ]
            return self.cloud_rows(query, options)

        with patch.object(native, "sql_rows", side_effect=rows):
            admin.verify_bootstrap(
                config, self.users, self.options, allow_model_schema_creation=True
            )
        with (
            patch.object(native, "sql_rows", side_effect=self.cloud_rows),
            self.assertRaises(native.DeploymentError),
        ):
            admin.verify_bootstrap(config, self.users, self.options)

    def test_missing_optional_schema_creation_grant_fails_opted_in_readback(self) -> None:
        with (
            patch.object(native, "sql_rows", side_effect=self.cloud_rows),
            self.assertRaises(native.DeploymentError),
        ):
            admin.verify_bootstrap(
                self.config, self.users, self.options, allow_model_schema_creation=True
            )

    def test_wrong_service_user_properties_or_extra_role_fail_readback(self) -> None:
        cases = [
            ("type", "PERSON"),
            ("default_role", "ACCOUNTADMIN"),
            ("default_warehouse", "WRONG_WH"),
            ("default_secondary_roles", '["ALL"]'),
        ]
        for field, wrong in cases:

            def rows(
                query: str, options: list[str], field: str = field, wrong: str = wrong
            ) -> list[dict[str, Any]]:
                result = self.cloud_rows(query, options)
                if query == "SHOW USERS LIKE 'PROJECT_ADMIN_SVC'":
                    result[0][field] = wrong
                return result

            with (
                self.subTest(field=field),
                patch.object(native, "sql_rows", side_effect=rows),
                self.assertRaises(native.DeploymentError),
            ):
                admin.verify_bootstrap(self.config, self.users, self.options)

        def extra_role(query: str, options: list[str]) -> list[dict[str, Any]]:
            if query == "SHOW GRANTS TO USER PROJECT_ADMIN_SVC":
                return [{"role": "DBT_PROJECT_ADMIN"}, {"role": "DBT_OPERATOR"}]
            return self.cloud_rows(query, options)

        with (
            patch.object(native, "sql_rows", side_effect=extra_role),
            self.assertRaises(native.DeploymentError),
        ):
            admin.verify_bootstrap(self.config, self.users, self.options)

    def test_missing_or_wrong_public_key_fingerprint_fails_readback(self) -> None:
        for value in (None, "SHA256:wrong-key"):

            def rows(
                query: str, options: list[str], value: str | None = value
            ) -> list[dict[str, Any]]:
                if query in ("DESC USER PROJECT_ADMIN_SVC", "DESCRIBE USER PROJECT_ADMIN_SVC"):
                    return (
                        [] if value is None else [{"property": "RSA_PUBLIC_KEY_FP", "value": value}]
                    )
                return self.cloud_rows(query, options)

            with (
                self.subTest(value=value),
                patch.object(native, "sql_rows", side_effect=rows),
                self.assertRaises(native.DeploymentError),
            ):
                admin.verify_bootstrap(self.config, self.users, self.options)


if __name__ == "__main__":
    unittest.main()
