"""Separate authenticated project-administrator and operator boundaries."""

from __future__ import annotations

import io
import json
import shutil
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

import yaml

from scripts import dbt_native as native


class RoleSeparationTests(unittest.TestCase):
    def setUp(self) -> None:
        output = patch("sys.stdout", new_callable=io.StringIO)
        self.stdout = output.start()
        self.addCleanup(output.stop)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / "source"
        (self.source / "models").mkdir(parents=True)
        (self.source / "dbt_project.yml").write_text("name: pipeline\nprofile: pipeline\n")
        (self.source / "models/check.sql").write_text("select 1 as id\n")
        self.config = native.Config(
            source=str(self.source),
            account="ORG-ACCOUNT",
            database="CONTROL",
            object_schema="PROJECTS",
            project="PIPELINE",
            role="DBT_OPERATOR",
            warehouse="COMPUTE",
            model_database="MODELS",
            model_schema="ANALYTICS",
            profile="pipeline",
            target="dev",
            dbt_version="2.0.0",
            connection="operator",
            deployment_role="DBT_PROJECT_ADMIN",
            deployment_connection="project_admin",
            operator_user="OPERATOR_SVC",
            deployment_user="ADMIN_SVC",
            auto_compile=False,
        )
        self.live = {
            "name": "PIPELINE",
            "owner": "DBT_PROJECT_ADMIN",
            "dbt_version": "2.0.0",
            "default_target": "dev",
            "default_version": "LIVE",
            "auto_compile": False,
            "default_writeback": False,
        }

    def fake_cloud(
        self,
        *,
        owner: str | None = "DBT_PROJECT_ADMIN",
        corrupt_profile: bool = False,
        corrupt_source: bool = False,
        remote_role: Any = None,
    ) -> tuple[list[list[str]], Any]:
        calls: list[list[str]] = []
        deployed: Path | None = None

        def run(command: list[str]) -> str:
            nonlocal deployed
            calls.append(command)
            if command == ["snow", "--version"]:
                return "Snowflake CLI version: 3.28.0"
            if command[1] == "sql":
                query = command[command.index("--query") + 1]
                if "CURRENT_ORGANIZATION_NAME" in query:
                    role = command[command.index("--role") + 1]
                    user = "ADMIN_SVC" if role == "DBT_PROJECT_ADMIN" else "OPERATOR_SVC"
                    return json.dumps(
                        [
                            {
                                "organization": "ORG",
                                "account": "ACCOUNT",
                                "role": role,
                                "user": user,
                                "secondary_roles": json.dumps({"roles": "", "value": ""}),
                            }
                        ]
                    )
                if "SYSTEM$SUPPORTED_DBT_VERSIONS" in query:
                    return json.dumps([{"versions": [{"dbt_version": "2.0.0"}]}])
                if "SHOW DBT PROJECTS" in query:
                    row = dict(self.live, owner=owner)
                    return json.dumps([row])
                raise AssertionError(query)
            if command[1:3] == ["dbt", "deploy"]:
                deployed = Path(command[command.index("--source") + 1])
                return "[]"
            if command[1:3] == ["dbt", "describe"]:
                return json.dumps([self.live])
            if command[1:3] == ["dbt", "copy"]:
                location = command[3]
                destination = Path(command[4])
                if "--recursive" in command:
                    assert deployed is not None
                    shutil.copytree(deployed, destination, dirs_exist_ok=True)
                    if corrupt_source:
                        (destination / "models/check.sql").write_text("select 9 as id\n")
                elif location.endswith("dbt_project.yml"):
                    shutil.copy(self.source / "dbt_project.yml", destination)
                elif location.endswith(native.PROFILE_FILES[0]):
                    profiles = native.native_profile(self.config)
                    if corrupt_profile:
                        profiles["pipeline"]["outputs"]["dev"]["role"] = "DBT_PROJECT_ADMIN"
                    if remote_role is not None:
                        profiles["pipeline"]["outputs"]["dev"]["role"] = remote_role
                    (destination / native.PROFILE_FILES[0]).write_text(yaml.safe_dump(profiles))
                else:
                    raise AssertionError(location)
                return "[]"
            if command[1:3] == ["dbt", "execute"]:
                return "successful operator execution"
            raise AssertionError(command)

        return calls, run

    def test_legacy_config_keeps_one_identity(self) -> None:
        config = replace(
            self.config, deployment_role=None, deployment_connection=None, deployment_user=None
        )
        self.assertFalse(config.split_roles)
        self.assertEqual(config.project_admin_role, config.role)
        self.assertEqual(config.project_admin_user, config.operator_user)
        self.assertEqual(
            native.connection_options(config, False),
            native.connection_options(config, False, deployment=True),
        )

    def test_separate_identity_does_not_inherit_operator_user(self) -> None:
        for config in (
            replace(self.config, deployment_user=None),
            replace(self.config, deployment_user=None, deployment_connection=None),
            replace(self.config, deployment_user=None, deployment_role=None),
        ):
            with self.subTest(config=config):
                self.assertIsNone(config.project_admin_user)

    def test_split_roles_reject_built_in_delegated_roles(self) -> None:
        for role in native.RESERVED_PROJECT_ROLES:
            for field in ("role", "deployment_role"):
                with (
                    self.subTest(role=role, field=field),
                    self.assertRaisesRegex(native.DeploymentError, "custom roles"),
                ):
                    native.validate_config(replace(self.config, **{field: role.lower()}))

    def test_legacy_same_role_keeps_built_in_role_compatibility(self) -> None:
        for role in native.RESERVED_PROJECT_ROLES:
            for deployment_role in (None, role.lower()):
                with self.subTest(role=role, deployment_role=deployment_role):
                    native.validate_config(
                        replace(self.config, role=role, deployment_role=deployment_role)
                    )

    def test_split_roles_cannot_claim_the_same_expected_user(self) -> None:
        with self.assertRaisesRegex(native.DeploymentError, "different configured user"):
            native.validate_config(replace(self.config, deployment_user=self.config.operator_user))

    def test_secondary_role_readback_requires_none_with_no_active_roles(self) -> None:
        identity = {
            "organization": "ORG",
            "account": "ACCOUNT",
            "role": "DBT_OPERATOR",
            "user": "OPERATOR_SVC",
        }
        for secondary in (
            {"roles": "DBT_PROJECT_ADMIN", "value": "ALL"},
            {"roles": "", "value": "ALL"},
            {"value": "NONE"},
            {"roles": ""},
            [],
            None,
            "invalid json",
        ):
            with (
                self.subTest(secondary=secondary),
                patch.object(
                    native,
                    "run_command",
                    side_effect=["3.28.0", json.dumps([dict(identity, secondary_roles=secondary)])],
                ),
                self.assertRaises(native.DeploymentError),
            ):
                native.check_session(self.config, [])
        for secondary in (
            {"roles": "", "value": "NONE"},
            {"roles": "", "value": ""},
            json.dumps({"roles": "", "value": "NONE"}),
            json.dumps({"roles": "", "value": ""}),
        ):
            with (
                self.subTest(secondary=secondary),
                patch.object(
                    native,
                    "run_command",
                    side_effect=["3.28.0", json.dumps([dict(identity, secondary_roles=secondary)])],
                ),
            ):
                native.check_session(self.config, [])

    def test_config_load_preserves_separate_identities_and_relative_source(self) -> None:
        payload = asdict(self.config)
        payload["source"] = "source"
        path = self.root / "config.json"
        path.write_text(json.dumps(payload))
        loaded = native.load_config(path)
        self.assertEqual(loaded, self.config)

    def test_optional_identity_fields_reject_sql_and_connection_injection(self) -> None:
        for field in (
            "deployment_role",
            "operator_user",
            "deployment_user",
            "deployment_connection",
        ):
            for value in ("", "bad.name", "ROLE; GRANT ALL", "two words", 1):
                with (
                    self.subTest(field=field, value=value),
                    self.assertRaises(native.DeploymentError),
                ):
                    native.validate_config(replace(self.config, **{field: value}))

    def test_missing_secondary_role_readback_fails_closed(self) -> None:
        identity = {
            "organization": "ORG",
            "account": "ACCOUNT",
            "role": "DBT_OPERATOR",
            "user": "OPERATOR_SVC",
        }
        with (
            patch.object(native, "run_command", side_effect=["3.28.0", json.dumps([identity])]),
            self.assertRaisesRegex(native.DeploymentError, "Secondary roles"),
        ):
            native.check_session(self.config, [])

    def test_connections_route_roles_and_disable_secondary_roles(self) -> None:
        for deployment, connection, role in (
            (False, "operator", "DBT_OPERATOR"),
            (True, "project_admin", "DBT_PROJECT_ADMIN"),
        ):
            options = native.connection_options(self.config, False, deployment=deployment)
            self.assertEqual(options[options.index("--connection") + 1], connection)
            self.assertEqual(options[options.index("--role") + 1], role)
            self.assertEqual(options[options.index("--secondary-roles") + 1], "NONE")
            temporary = native.connection_options(self.config, True, deployment=deployment)
            self.assertIn("--temporary-connection", temporary)
            self.assertNotIn("--connection", temporary)

    def test_profile_never_uses_deployment_role_or_authentication(self) -> None:
        target = native.native_profile(self.config)["pipeline"]["outputs"]["dev"]
        self.assertEqual(target["role"], "{{ 'DBT_OPERATOR' }}")
        self.assertNotIn("user", target)
        self.assertNotIn("connection", target)

    def test_split_profile_role_is_a_fixed_canonical_literal(self) -> None:
        config = replace(self.config, role="dbt_operator")
        self.assertEqual(native.profile_role(config), "{{ 'DBT_OPERATOR' }}")
        legacy = replace(config, deployment_role=None)
        self.assertEqual(native.profile_role(legacy), "dbt_operator")
        with self.assertRaises(native.DeploymentError):
            native.profile_role(replace(self.config, role="bad' }}{{ env_var('ROLE')"))

    def test_session_rejects_wrong_account_role_or_user_for_each_persona(self) -> None:
        for deployment, expected_role, expected_user in (
            (False, "DBT_OPERATOR", "OPERATOR_SVC"),
            (True, "DBT_PROJECT_ADMIN", "ADMIN_SVC"),
        ):
            identity = {
                "organization": "ORG",
                "account": "ACCOUNT",
                "role": expected_role,
                "user": expected_user,
                "secondary_roles": {"roles": "", "value": "NONE"},
            }
            for field in ("account", "role", "user"):
                with (
                    self.subTest(deployment=deployment, field=field),
                    patch.object(
                        native,
                        "run_command",
                        side_effect=["3.28.0", json.dumps([dict(identity, **{field: "WRONG"})])],
                    ),
                    self.assertRaises(native.DeploymentError),
                ):
                    native.check_session(self.config, [], deployment=deployment)

    def test_identity_mismatch_blocks_execution_before_object_lookup(self) -> None:
        identity = {
            "organization": "ORG",
            "account": "ACCOUNT",
            "role": "DBT_OPERATOR",
            "user": "ADMIN_SVC",
            "secondary_roles": {"roles": "", "value": "NONE"},
        }
        with (
            patch.object(native, "run_command", side_effect=["3.28.0", json.dumps([identity])]),
            patch.object(native, "project_row") as lookup,
            self.assertRaisesRegex(native.DeploymentError, "user"),
        ):
            native.execute_project(self.config, apply=True)
        lookup.assert_not_called()

    def test_split_compile_and_combined_build_fail_before_packaging_or_connection(self) -> None:
        for config, build in (
            (replace(self.config, auto_compile=True), False),
            (self.config, True),
        ):
            for apply in (False, True):
                with (
                    self.subTest(build=build, apply=apply),
                    patch.object(native, "prepare_source") as package,
                    patch.object(native, "run_command") as run,
                    self.assertRaises(native.DeploymentError),
                ):
                    native.deploy(config, build=build, apply=apply)
                package.assert_not_called()
                run.assert_not_called()

    def test_administrator_deployment_verifies_operator_profile_and_source(self) -> None:
        calls, run = self.fake_cloud()
        with (
            patch.object(native, "run_command", side_effect=run),
            patch.dict("os.environ", {}, clear=True),
        ):
            native.deploy(self.config, apply=True)
        cloud_calls = [command for command in calls if "--role" in command]
        self.assertTrue(cloud_calls)
        self.assertTrue(
            all(
                command[command.index("--role") + 1] == "DBT_PROJECT_ADMIN"
                for command in cloud_calls
            )
        )
        self.assertTrue(
            all(
                command[command.index("--connection") + 1] == "project_admin"
                for command in cloud_calls
            )
        )
        deployed = next(command for command in calls if command[1:3] == ["dbt", "deploy"])
        self.assertIn("--no-auto-compile", deployed)
        self.assertFalse(any(command[1:3] == ["dbt", "execute"] for command in calls))
        self.assertIn("source hashes match", self.stdout.getvalue())

    def test_administrator_cannot_replace_project_owned_by_different_role(self) -> None:
        for owner in ("DBT_OPERATOR", None):
            calls, run = self.fake_cloud(owner=owner)
            with (
                self.subTest(owner=owner),
                patch.object(native, "run_command", side_effect=run),
                patch.dict("os.environ", {}, clear=True),
                self.assertRaisesRegex(native.DeploymentError, "ownership"),
            ):
                native.deploy(self.config, apply=True)
            self.assertFalse(any(command[1:3] == ["dbt", "deploy"] for command in calls))

    def test_source_readback_corruption_still_fails_separate_deployment(self) -> None:
        _, run = self.fake_cloud(corrupt_source=True)
        with (
            patch.object(native, "run_command", side_effect=run),
            patch.dict("os.environ", {}, clear=True),
            self.assertRaisesRegex(native.DeploymentError, "source content"),
        ):
            native.deploy(self.config, apply=True)
        self.assertNotIn("Verified deployment", self.stdout.getvalue())

    def test_operator_can_execute_project_owned_by_project_administrator(self) -> None:
        calls, run = self.fake_cloud()
        with patch.object(native, "run_command", side_effect=run):
            native.execute_project(self.config, apply=True)
        cloud_calls = [command for command in calls if "--role" in command]
        self.assertTrue(
            all(command[command.index("--role") + 1] == "DBT_OPERATOR" for command in cloud_calls)
        )
        self.assertTrue(
            all(command[command.index("--connection") + 1] == "operator" for command in cloud_calls)
        )
        self.assertTrue(any(command[1:3] == ["dbt", "execute"] for command in calls))

    def test_remote_role_drift_prevents_operator_execution(self) -> None:
        calls, run = self.fake_cloud(corrupt_profile=True)
        with (
            patch.object(native, "run_command", side_effect=run),
            self.assertRaisesRegex(native.DeploymentError, "target role"),
        ):
            native.execute_project(self.config, apply=True)
        self.assertFalse(any(command[1:3] == ["dbt", "execute"] for command in calls))

    def test_split_execution_requires_the_exact_generated_role_expression(self) -> None:
        for role in (
            "DBT_OPERATOR",
            "{{ 'DBT_PROJECT_ADMIN' }}",
            "{{ env_var('DBT_CURRENT_ROLE') }}",
            "{{ 'dbt_operator' }}",
            "{{'DBT_OPERATOR'}}",
            "{{ 'DBT_OPERATOR' | upper }}",
            "{{ 'DBT_OPERATOR' }} ",
            1,
        ):
            calls, run = self.fake_cloud(remote_role=role)
            with (
                self.subTest(role=role),
                patch.object(native, "run_command", side_effect=run),
                self.assertRaisesRegex(native.DeploymentError, "target role"),
            ):
                native.execute_project(self.config, apply=True)
            self.assertFalse(any(command[1:3] == ["dbt", "execute"] for command in calls))

    def test_migration_uses_administrator_identity_and_requires_owner(self) -> None:
        legacy = dict(self.live, default_version="VERSION$1")
        with (
            patch.object(native, "check_session") as session,
            patch.object(native, "project_row", side_effect=[legacy, self.live]),
            patch.object(native, "sql_rows", return_value=[]) as sql,
        ):
            native.migrate(self.config, apply=True)
        self.assertTrue(session.call_args.kwargs["deployment"])
        options = session.call_args.args[1]
        self.assertEqual(options[options.index("--role") + 1], "DBT_PROJECT_ADMIN")
        self.assertTrue(
            any("SYSTEM$MIGRATE_DBT_PROJECT" in call.args[0] for call in sql.call_args_list)
        )
        with (
            patch.object(native, "check_session"),
            patch.object(native, "project_row", return_value=dict(legacy, owner="DBT_OPERATOR")),
            patch.object(native, "sql_rows") as sql,
            self.assertRaisesRegex(native.DeploymentError, "ownership"),
        ):
            native.migrate(self.config, apply=True)
        sql.assert_not_called()

    def test_operator_preview_names_only_the_operator_identity(self) -> None:
        with patch.object(native, "run_command") as run:
            native.execute_project(self.config)
        run.assert_not_called()
        preview = self.stdout.getvalue()
        self.assertIn("role DBT_OPERATOR; connection operator; expected user OPERATOR_SVC", preview)
        self.assertNotIn("ADMIN_SVC", preview)
        self.assertNotIn("role DBT_PROJECT_ADMIN", preview)

    def test_access_preview_is_offline_and_scoped_to_one_object(self) -> None:
        with patch.object(native, "run_command") as run:
            native.project_access(self.config)
        run.assert_not_called()
        self.assertIn(
            "GRANT USAGE, MONITOR ON DBT PROJECT CONTROL.PROJECTS.PIPELINE TO ROLE DBT_OPERATOR",
            self.stdout.getvalue(),
        )
        self.assertNotIn("FUTURE", self.stdout.getvalue())

    def grant_rows(self) -> list[dict[str, str]]:
        return [
            {
                "privilege": privilege,
                "granted_to": "ROLE",
                "granted_on": "DBT_PROJECT",
                "grantee_name": "DBT_OPERATOR",
                "name": self.config.object_name,
            }
            for privilege in ("USAGE", "MONITOR")
        ]

    def test_access_apply_uses_administrator_and_verifies_both_exact_object_grants(self) -> None:
        with (
            patch.object(native, "check_session") as session,
            patch.object(native, "project_row", return_value=self.live),
            patch.object(native, "sql_rows", side_effect=[[], self.grant_rows()]) as sql,
        ):
            native.project_access(self.config, apply=True)
        self.assertTrue(session.call_args.kwargs["deployment"])
        self.assertEqual(
            sql.call_args_list[0].args[0],
            "GRANT USAGE, MONITOR ON DBT PROJECT CONTROL.PROJECTS.PIPELINE TO ROLE DBT_OPERATOR",
        )
        self.assertEqual(
            sql.call_args_list[1].args[0], "SHOW GRANTS ON DBT PROJECT CONTROL.PROJECTS.PIPELINE"
        )
        self.assertIn("Verified project access", self.stdout.getvalue())

    def test_access_requires_exact_object_role_type_and_both_privileges(self) -> None:
        for field, wrong in (
            ("name", "OTHER.PROJECTS.PIPELINE"),
            ("grantee_name", "OTHER_ROLE"),
            ("granted_on", "TABLE"),
            ("granted_to", "USER"),
            ("privilege", "SELECT"),
        ):
            rows = self.grant_rows()
            rows[1][field] = wrong
            with (
                self.subTest(field=field),
                patch.object(native, "check_session"),
                patch.object(native, "project_row", return_value=self.live),
                patch.object(native, "sql_rows", side_effect=[[], rows]),
                self.assertRaisesRegex(native.DeploymentError, "exact-object"),
            ):
                native.project_access(self.config, apply=True)

    def test_access_missing_or_foreign_owner_prevents_grants(self) -> None:
        for row in (None, dict(self.live, owner="OTHER")):
            with (
                self.subTest(row=row),
                patch.object(native, "check_session"),
                patch.object(native, "project_row", return_value=row),
                patch.object(native, "sql_rows") as sql,
                self.assertRaises(native.DeploymentError),
            ):
                native.project_access(self.config, apply=True)
            sql.assert_not_called()

    def test_access_server_rejection_is_not_success(self) -> None:
        with (
            patch.object(native, "check_session"),
            patch.object(native, "project_row", return_value=self.live),
            patch.object(
                native, "sql_rows", side_effect=native.DeploymentError("Server rejected grant")
            ),
            self.assertRaises(native.DeploymentError),
        ):
            native.project_access(self.config, apply=True)
        self.assertNotIn("Verified project access", self.stdout.getvalue())

    def test_wizard_defaults_split_to_no_compile_and_preserves_user_checks(self) -> None:
        output = self.root / "new.json"
        args = native.parser().parse_args(
            [
                "wizard",
                "--source",
                str(self.source),
                "--output",
                str(output),
                "--non-interactive",
                "--account",
                "ORG-ACCOUNT",
                "--database",
                "CONTROL",
                "--role",
                "DBT_OPERATOR",
                "--warehouse",
                "COMPUTE",
                "--deployment-role",
                "DBT_PROJECT_ADMIN",
                "--deployment-connection",
                "project_admin",
                "--operator-user",
                "OPERATOR_SVC",
                "--deployment-user",
                "ADMIN_SVC",
            ]
        )
        with (
            patch.object(native, "run_command") as run,
            patch.object(
                native, "infer_values", return_value={"project": "pipeline", "profile": "pipeline"}
            ),
        ):
            config = native.wizard(args)
        run.assert_not_called()
        self.assertFalse(config.auto_compile)
        self.assertEqual(config.project_admin_user, "ADMIN_SVC")
        self.assertEqual(native.load_config(output), config)

    def test_main_dispatches_project_access(self) -> None:
        with (
            patch.object(native, "load_config", return_value=self.config),
            patch.object(native, "project_access") as grant,
        ):
            result = native.main(["project-access", "--config", "unused.json", "--apply"])
        self.assertEqual(result, 0)
        self.assertTrue(grant.call_args.kwargs["apply"])


if __name__ == "__main__":
    unittest.main()
