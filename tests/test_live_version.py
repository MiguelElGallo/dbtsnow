"""Native LIVE migration and execution contracts without cloud mutation."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

import yaml

from scripts import dbt_native as native


class LiveVersionTests(unittest.TestCase):
    def setUp(self) -> None:
        output = patch("sys.stdout", new_callable=io.StringIO)
        self.stdout = output.start()
        self.addCleanup(output.stop)
        self.config = native.Config(
            source="example",
            account="ORG-ACCOUNT",
            database="CONTROL",
            object_schema="DBT",
            project="PIPELINE",
            role="TRANSFORMER",
            warehouse="COMPUTE",
            model_database="ANALYTICS",
            model_schema="DEV",
            profile="pipeline",
            target="dev",
            dbt_version="1.11.11",
            connection="local",
        )
        self.legacy = {
            "name": "PIPELINE",
            "owner": "TRANSFORMER",
            "created_on": "2026-01-01T00:00:00Z",
            "dbt_version": "1.11.11",
            "default_target": "dev",
            "default_version": "VERSION$1",
            "default_version_name": "v1",
            "default_version_alias": "default",
        }
        self.live = {
            **self.legacy,
            "default_version": "LIVE",
            "default_version_name": None,
            "default_version_alias": None,
            "default_version_location_uri": "snow://dbt/CONTROL.DBT.PIPELINE/versions/live/",
        }

    def test_config_writeback_and_compile_require_real_booleans(self) -> None:
        for field in ("default_writeback", "auto_compile"):
            for value in ("false", "true", 0, 1, None):
                with (
                    self.subTest(field=field, value=value),
                    self.assertRaises(native.DeploymentError),
                ):
                    native.validate_config(replace(self.config, **{field: value}))

    def test_project_lookup_uses_exact_object_within_configured_schema(self) -> None:
        rows = [dict(self.live, name="PIPELINEX"), self.live]
        with patch.object(native, "sql_rows", return_value=rows) as sql:
            found = native.project_row(self.config, ["--connection", "local"])
        self.assertEqual(found, self.live)
        query = sql.call_args.args[0]
        self.assertIn("IN SCHEMA CONTROL.DBT", query.upper())
        self.assertNotIn("IN ACCOUNT", query.upper())

    def test_preflight_accepts_live_despite_deprecated_null_version_columns(self) -> None:
        with (
            patch.object(native, "check_session"),
            patch.object(native, "project_row", return_value=self.live),
            patch.object(
                native, "sql_rows", return_value=[{"versions": [{"dbt_version": "1.11.11"}]}]
            ),
        ):
            self.assertEqual(native.preflight(self.config, []), self.live)

    def test_preflight_rejects_legacy_and_unknown_version_without_migrating(self) -> None:
        for version in ("VERSION$1", None, ""):
            row = dict(self.legacy, default_version=version)
            with (
                self.subTest(version=version),
                patch.object(native, "check_session"),
                patch.object(native, "project_row", return_value=row),
                patch.object(
                    native, "sql_rows", return_value=[{"versions": [{"dbt_version": "1.11.11"}]}]
                ) as sql,
                self.assertRaises(native.DeploymentError),
            ):
                native.preflight(self.config, [])
            self.assertFalse(any("MIGRATE" in call.args[0].upper() for call in sql.call_args_list))

    def test_migration_preview_does_not_connect(self) -> None:
        with patch.object(native.subprocess, "run") as run:
            native.migrate(self.config)
        run.assert_not_called()

    def test_live_migration_is_a_noop(self) -> None:
        with (
            patch.object(native, "check_session"),
            patch.object(native, "project_row", return_value=self.live),
            patch.object(native, "sql_rows", return_value=[]) as sql,
        ):
            native.migrate(self.config, apply=True)
        self.assertFalse(
            any("SYSTEM$MIGRATE_DBT_PROJECT" in call.args[0] for call in sql.call_args_list)
        )

    def test_missing_project_cannot_be_migrated(self) -> None:
        with (
            patch.object(native, "check_session"),
            patch.object(native, "project_row", return_value=None),
            patch.object(native, "sql_rows", return_value=[]) as sql,
            self.assertRaises(native.DeploymentError),
        ):
            native.migrate(self.config, apply=True)
        self.assertFalse(any("MIGRATE" in call.args[0].upper() for call in sql.call_args_list))

    def test_migration_targets_only_the_existing_project_and_preserves_metadata(self) -> None:
        with (
            patch.object(native, "check_session"),
            patch.object(native, "project_row", side_effect=[self.legacy, self.live]),
            patch.object(native, "sql_rows", return_value=[]) as sql,
        ):
            native.migrate(self.config, apply=True)
        queries = [call.args[0] for call in sql.call_args_list]
        migrations = [query for query in queries if "SYSTEM$MIGRATE_DBT_PROJECT" in query]
        self.assertEqual(len(migrations), 1)
        self.assertIn("CONTROL.DBT.PIPELINE", migrations[0])
        self.assertFalse(any("ALTER ACCOUNT" in query.upper() for query in queries))
        self.assertFalse(
            any("SYSTEM$ENABLE_BEHAVIOR_CHANGE_BUNDLE" in query.upper() for query in queries)
        )
        self.assertFalse(any("CREATE OR REPLACE" in query.upper() for query in queries))

    def test_migration_fails_when_preserved_metadata_changes(self) -> None:
        for field in ("name", "owner", "created_on", "dbt_version", "default_target"):
            with (
                self.subTest(field=field),
                patch.object(native, "check_session"),
                patch.object(
                    native,
                    "project_row",
                    side_effect=[self.legacy, dict(self.live, **{field: "CHANGED"})],
                ),
                patch.object(native, "sql_rows", return_value=[]),
                self.assertRaises(native.DeploymentError),
            ):
                native.migrate(self.config, apply=True)

    def test_migration_fails_when_live_or_location_readback_is_wrong(self) -> None:
        for changed in (
            {"default_version": "VERSION$2"},
            {"default_version_location_uri": "snow://dbt/CONTROL.DBT.PIPELINE/versions/v1/"},
        ):
            with (
                self.subTest(changed=changed),
                patch.object(native, "check_session"),
                patch.object(
                    native, "project_row", side_effect=[self.legacy, dict(self.live, **changed)]
                ),
                patch.object(native, "sql_rows", return_value=[]),
                self.assertRaises(native.DeploymentError),
            ):
                native.migrate(self.config, apply=True)

    def test_wrong_account_stops_before_migration(self) -> None:
        with (
            patch.object(
                native, "check_session", side_effect=native.DeploymentError("Wrong account")
            ),
            patch.object(native, "project_row") as lookup,
            patch.object(native, "sql_rows") as sql,
            self.assertRaises(native.DeploymentError),
        ):
            native.migrate(self.config, apply=True)
        lookup.assert_not_called()
        sql.assert_not_called()

    def test_execute_preview_does_not_connect(self) -> None:
        with patch.object(native.subprocess, "run") as run:
            native.execute_project(self.config)
        run.assert_not_called()

    def test_default_execution_skips_writeback_and_does_not_build_elsewhere(self) -> None:
        command = native.execution_command(self.config)
        self.assertIn("--no-writeback", command)
        self.assertNotIn("--writeback", command)
        self.assertIn("CONTROL.DBT.PIPELINE", command)
        self.assertNotIn("ANALYTICS.DEV.PIPELINE", command)
        self.assertLess(command.index("--no-writeback"), command.index("CONTROL.DBT.PIPELINE"))

    def test_configured_writeback_can_be_overridden_per_execution(self) -> None:
        config = replace(self.config, default_writeback=True)
        configured = native.execution_command(config)
        disabled = native.execution_command(config, writeback=False)
        enabled = native.execution_command(self.config, writeback=True)
        self.assertIn("--writeback", configured)
        self.assertIn("--no-writeback", disabled)
        self.assertIn("--writeback", enabled)

    def test_state_build_imports_last_successful_target_before_object(self) -> None:
        command = native.execution_command(
            self.config,
            state_from="CONTROL.DBT.PRODUCTION",
            selection="state:modified+",
            defer=True,
        )
        imported = command[command.index("--import") + 1]
        self.assertIn("SYSTEM$DBT_GET_LAST_SUCCESSFUL_RUN_TARGET", imported)
        self.assertIn("CONTROL.DBT.PRODUCTION", imported)
        self.assertLess(command.index("--import"), command.index("CONTROL.DBT.PIPELINE"))
        self.assertEqual(command[command.index("--state") + 1], "./imports/state")
        self.assertIn("--defer", command)
        self.assertEqual(command[command.index("--select") + 1], "state:modified+")

    def test_invalid_execution_options_are_rejected_before_connecting(self) -> None:
        options: tuple[dict[str, Any], ...] = (
            {"command": "run;DROP DATABASE CONTROL"},
            {"defer": True},
            {"state_from": "CONTROL.DBT.PROD;DROP"},
            {"state_from": "unqualified"},
            {"selection": "one two"},
            {"selection": "model\n--full-refresh"},
            {"command": "retry", "state_from": "CONTROL.DBT.PRODUCTION"},
            {"command": "source-freshness", "state_from": "CONTROL.DBT.PRODUCTION"},
            {"writeback": "false"},
        )
        for option in options:
            with (
                self.subTest(option=option),
                patch.object(native.subprocess, "run") as run,
                self.assertRaises(native.DeploymentError),
            ):
                native.execute_project(self.config, apply=True, **option)
            run.assert_not_called()

    def test_core_retry_preserves_inherited_target_without_state_flags(self) -> None:
        command = native.execution_command(self.config, command="retry")
        self.assertEqual(command[-1], "retry")
        self.assertNotIn("--target", command)
        self.assertNotIn("--state", command)
        self.assertNotIn("--defer", command)

    def test_source_freshness_uses_native_subcommand(self) -> None:
        command = native.execution_command(self.config, command="source-freshness")
        self.assertIn("source", command)
        self.assertIn("freshness", command)
        self.assertEqual(command.index("freshness"), command.index("source") + 1)

    def test_apply_execution_requires_existing_live_object(self) -> None:
        for row in (None, self.legacy):
            with (
                self.subTest(row=row),
                patch.object(native, "preflight", return_value=row),
                patch.object(native, "run_command") as run,
                self.assertRaises(native.DeploymentError),
            ):
                native.execute_project(self.config, apply=True)
            run.assert_not_called()

    def test_apply_execution_prints_native_results_after_live_preflight(self) -> None:
        with (
            patch.object(native, "preflight", return_value=self.live),
            patch.object(native, "verify_execution_target"),
            patch.object(native, "run_command", return_value="native build result") as run,
        ):
            native.execute_project(self.config, apply=True)
        self.assertEqual(run.call_count, 1)
        self.assertIn("native build result", self.stdout.getvalue())

    def test_state_execution_requires_nonempty_immutable_artifact_locator(self) -> None:
        for rows in ([], [{"state": None}], [{"state": ""}], [{"state": 1}]):
            with (
                self.subTest(rows=rows),
                patch.object(native, "preflight", return_value=self.live),
                patch.object(native, "verify_execution_target"),
                patch.object(native, "sql_rows", return_value=rows),
                patch.object(native, "run_command") as run,
                self.assertRaises(native.DeploymentError),
            ):
                native.execute_project(
                    self.config,
                    apply=True,
                    state_from="CONTROL.DBT.PRODUCTION",
                    defer=True,
                )
            run.assert_not_called()

    def test_state_execution_freezes_locator_returned_by_precheck(self) -> None:
        locator = "snow://dbt/CONTROL.DBT.PRODUCTION/artifacts/known-query/target/"
        with (
            patch.object(native, "preflight", return_value=self.live),
            patch.object(native, "verify_execution_target"),
            patch.object(native, "sql_rows", return_value=[{"state": locator}]) as sql,
            patch.object(native, "run_command", return_value="state build result") as run,
        ):
            native.execute_project(
                self.config,
                apply=True,
                state_from="CONTROL.DBT.PRODUCTION",
                selection="state:modified+",
                defer=True,
            )
        self.assertIn("build,run", sql.call_args.args[0])
        invocation = run.call_args.args[0]
        imported = invocation[invocation.index("--import") + 1]
        self.assertIn(locator, imported)
        self.assertNotIn("SYSTEM$DBT_GET_LAST_SUCCESSFUL_RUN_TARGET", imported)
        self.assertEqual(invocation[invocation.index("--state") + 1], "./imports/state")

    def test_noninteractive_wizard_preserves_explicit_boolean_flags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "project"
            source.mkdir()
            (source / "dbt_project.yml").write_text("name: pipeline\nprofile: pipeline\n")
            args = native.parser().parse_args(
                [
                    "wizard",
                    "--source",
                    str(source),
                    "--output",
                    str(root / "deployment.json"),
                    "--non-interactive",
                    "--account",
                    "ORG-ACCOUNT",
                    "--database",
                    "CONTROL",
                    "--object-schema",
                    "DBT",
                    "--project",
                    "PIPELINE",
                    "--role",
                    "TRANSFORMER",
                    "--warehouse",
                    "COMPUTE",
                    "--model-database",
                    "ANALYTICS",
                    "--model-schema",
                    "DEV",
                    "--profile",
                    "pipeline",
                    "--target",
                    "dev",
                    "--dbt-version",
                    "1.11.11",
                    "--default-writeback",
                    "--no-auto-compile",
                ]
            )
            with (
                patch.object(Path, "home", return_value=root),
                patch.object(native.subprocess, "run") as run,
            ):
                config = native.wizard(args)
            run.assert_not_called()
        self.assertIs(config.default_writeback, True)
        self.assertIs(config.auto_compile, False)

    def copy_remote_files(
        self,
        *,
        profiles: dict[str, Any] | None = None,
        project_profile: str = "pipeline",
        retry_args: dict[str, Any] | None = None,
    ) -> tuple[list[list[str]], Any]:
        calls: list[list[str]] = []
        profile_data = profiles if profiles is not None else native.native_profile(self.config)
        inherited = (
            retry_args if retry_args is not None else {"target": "dev", "profile": "pipeline"}
        )

        def copy(command: list[str]) -> str:
            calls.append(command)
            if command[1:3] == ["dbt", "execute"]:
                return "native execution result"
            self.assertEqual(command[1:3], ["dbt", "copy"])
            self.assertTrue(command[3].startswith("snow://dbt/CONTROL.DBT.PIPELINE/versions/live/"))
            filename = command[3].rsplit("/", 1)[-1]
            destination = Path(command[4]) / filename
            if filename == "dbt_project.yml":
                destination.write_text(
                    yaml.safe_dump({"name": "pipeline", "profile": project_profile})
                )
            elif filename == "dbt_projects_profiles.yml":
                destination.write_text(yaml.safe_dump(profile_data))
            elif filename == "run_results.json":
                destination.write_text(json.dumps({"args": inherited}))
            else:
                self.fail(f"Unexpected remote file: {filename}")
            return "[]"

        return calls, copy

    def test_changed_remote_model_destination_blocks_execution(self) -> None:
        for field in ("database", "schema", "role", "warehouse"):
            profiles = native.native_profile(self.config)
            profiles["pipeline"]["outputs"]["dev"][field] = "OTHER_DESTINATION"
            calls, copy = self.copy_remote_files(profiles=profiles)
            with (
                self.subTest(field=field),
                patch.object(native, "preflight", return_value=self.live),
                patch.object(native, "run_command", side_effect=copy),
                self.assertRaises(native.DeploymentError),
            ):
                native.execute_project(self.config, apply=True)
            self.assertFalse(any(command[1:3] == ["dbt", "execute"] for command in calls))

    def test_changed_remote_project_profile_blocks_execution(self) -> None:
        calls, copy = self.copy_remote_files(project_profile="different_profile")
        with (
            patch.object(native, "preflight", return_value=self.live),
            patch.object(native, "run_command", side_effect=copy),
            self.assertRaises(native.DeploymentError),
        ):
            native.execute_project(self.config, apply=True)
        self.assertEqual(len(calls), 1)

    def test_runtime_drift_blocks_before_downloads_or_execution(self) -> None:
        with (
            patch.object(native, "preflight", return_value=dict(self.live, dbt_version="1.9.4")),
            patch.object(native, "verify_execution_target") as verify,
            patch.object(native, "run_command") as run,
            self.assertRaises(native.DeploymentError),
        ):
            native.execute_project(self.config, apply=True)
        verify.assert_not_called()
        run.assert_not_called()

    def test_verified_remote_profile_allows_execution(self) -> None:
        calls, copy = self.copy_remote_files()
        with (
            patch.object(native, "preflight", return_value=self.live),
            patch.object(native, "run_command", side_effect=copy),
        ):
            native.execute_project(self.config, apply=True)
        self.assertEqual(
            [command[1:3] for command in calls],
            [["dbt", "copy"], ["dbt", "copy"], ["dbt", "execute"]],
        )

    def test_core_retry_rejects_missing_or_different_target_and_profile(self) -> None:
        cases = ({}, {"target": "prod"}, {"target": "dev", "profile": "different_profile"})
        for inherited in cases:
            calls, copy = self.copy_remote_files(retry_args=inherited)
            with (
                self.subTest(inherited=inherited),
                patch.object(native, "preflight", return_value=self.live),
                patch.object(native, "run_command", side_effect=copy),
                self.assertRaises(native.DeploymentError),
            ):
                native.execute_project(self.config, command="retry", apply=True)
            self.assertFalse(any(command[1:3] == ["dbt", "execute"] for command in calls))

    def test_core_retry_without_recorded_profile_requires_unique_deployed_profile(self) -> None:
        profiles = native.native_profile(self.config)
        profiles["other_profile"] = {"outputs": {"prod": {"database": "OTHER"}}}
        _, copy = self.copy_remote_files(profiles=profiles, retry_args={"target": "dev"})
        with (
            patch.object(native, "run_command", side_effect=copy),
            self.assertRaises(native.DeploymentError),
        ):
            native.verify_execution_target(self.config, [], "retry")
        _, copy = self.copy_remote_files(retry_args={"target": "dev"})
        with patch.object(native, "run_command", side_effect=copy):
            native.verify_execution_target(self.config, [], "retry")

    def test_fusion_retry_pins_profile_and_target_when_artifacts_omit_them(self) -> None:
        config = replace(self.config, dbt_version="2.0.0-preview.210")
        command = native.execution_command(config, command="retry")
        self.assertEqual(command[command.index("--target") + 1], "dev")
        self.assertEqual(command[command.index("--profile") + 1], "pipeline")
        calls, copy = self.copy_remote_files(retry_args={})
        with (
            patch.object(
                native, "preflight", return_value=dict(self.live, dbt_version=config.dbt_version)
            ),
            patch.object(native, "run_command", side_effect=copy),
        ):
            native.execute_project(config, command="retry", apply=True)
        self.assertTrue(any(command[1:3] == ["dbt", "execute"] for command in calls))

    def test_migration_server_rejection_is_not_reported_as_success(self) -> None:
        def reject(query: str, options: list[str]) -> list[dict[str, Any]]:
            if "SYSTEM$MIGRATE_DBT_PROJECT" in query:
                raise native.DeploymentError("Server rejected migration")
            return [{"status": "ENABLED"}]

        with (
            patch.object(native, "check_session"),
            patch.object(native, "project_row", return_value=self.legacy) as lookup,
            patch.object(native, "sql_rows", side_effect=reject),
            self.assertRaises(native.DeploymentError),
        ):
            native.migrate(self.config, apply=True)
        self.assertEqual(lookup.call_count, 1)
        self.assertNotIn("Verified migration", self.stdout.getvalue())

    def test_main_dispatches_run_without_overwriting_operation_name(self) -> None:
        with (
            patch.object(native, "load_config", return_value=self.config),
            patch.object(native, "execute_project") as execute,
        ):
            result = native.main(
                ["run", "--config", "unused.json", "--command", "compile", "--no-writeback"]
            )
        self.assertEqual(result, 0)
        self.assertEqual(execute.call_args.kwargs["command"], "compile")
        self.assertIs(execute.call_args.kwargs["writeback"], False)

    def test_deployment_settings_readback_rejects_persistence_drift(self) -> None:
        for setting in ("auto_compile", "default_writeback"):
            row = dict(self.live, **{setting: not getattr(self.config, setting)})
            with (
                self.subTest(setting=setting),
                self.assertRaisesRegex(native.DeploymentError, setting),
            ):
                native.verify_readback(self.config, [row], {})

    def test_deploy_transport_applies_explicit_compile_and_writeback_settings(self) -> None:
        for enabled in (True, False):
            config = replace(self.config, auto_compile=enabled, default_writeback=enabled)
            with (
                self.subTest(enabled=enabled),
                patch.object(native, "prepare_source", return_value=[]),
                patch.object(native, "write_receipt", return_value={}),
                patch.object(native, "source_directory", return_value=Path("/private/tmp/project")),
                patch.object(native, "github_metadata", return_value={}),
                patch.object(native, "preflight"),
                patch.object(native, "verify_readback"),
                patch.object(native, "verify_source"),
                patch.object(native, "run_command", return_value="[]") as run,
            ):
                native.deploy(config, apply=True)
            command = next(
                call.args[0]
                for call in run.call_args_list
                if call.args[0][1:3] == ["dbt", "deploy"]
            )
            self.assertIn("--auto-compile" if enabled else "--no-auto-compile", command)
            self.assertIn("--default-writeback" if enabled else "--no-default-writeback", command)


if __name__ == "__main__":
    unittest.main()
