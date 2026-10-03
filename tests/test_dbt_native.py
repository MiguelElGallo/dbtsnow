"""Offline semantic checks for native dbt deployment and packaging boundaries."""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

import yaml

from scripts import dbt_native as native


class NativeDeploymentTests(unittest.TestCase):
    def setUp(self) -> None:
        output = patch("sys.stdout", new_callable=io.StringIO)
        self.stdout = output.start()
        self.addCleanup(output.stop)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "project"
        self.source.mkdir()
        github_environment = patch.dict(native.os.environ, {"GITHUB_SHA": ""})
        github_environment.start()
        self.addCleanup(github_environment.stop)
        self.write(
            "dbt_project.yml",
            "name: tiny\nversion: '1.0'\nconfig-version: 2\n"
            "profile: tiny_profile\nmodel-paths: [models]\n",
        )
        self.write("models/example.sql", "select 1 as id\n")
        self.config = native.Config(
            source=str(self.source),
            connection="dev",
            account="org-account",
            database="CONTROL",
            object_schema="DBT",
            project="TINY",
            role="TRANSFORMER",
            warehouse="COMPUTE",
            model_database="ANALYTICS",
            model_schema="PROD",
            profile="tiny_profile",
            target="prod",
            dbt_version="1.11.11",
            external_access_integrations=[],
        )

    def write(self, relative: str, text: str) -> Path:
        path = self.source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_profile_separates_object_location_from_model_destination(self) -> None:
        profile = native.native_profile(self.config)
        target = profile["tiny_profile"]["outputs"]["prod"]
        self.assertEqual(target["database"], "ANALYTICS")
        self.assertEqual(target["schema"], "PROD")
        self.assertEqual(target["role"], "TRANSFORMER")
        self.assertEqual(target["warehouse"], "COMPUTE")
        self.assertEqual(target["type"], "snowflake")
        for credential in ("account", "user", "password", "private_key", "token"):
            self.assertNotIn(credential, target)

    def test_invalid_identifiers_stop_before_packaging(self) -> None:
        for field in (
            "database",
            "object_schema",
            "project",
            "role",
            "warehouse",
            "model_database",
            "model_schema",
        ):
            for value in (
                "",
                "BAD; DROP DATABASE X",
                "../outside",
                "two words",
                '"quoted"',
                "bad.name",
            ):
                with (
                    self.subTest(field=field, value=value),
                    self.assertRaises(native.DeploymentError),
                ):
                    native.validate_config(replace(self.config, **{field: value}))

    def test_unknown_config_keys_are_rejected(self) -> None:
        payload = asdict(self.config)
        payload["databsae"] = "WRONG"
        config_path = self.root / "deploy.json"
        config_path.write_text(json.dumps(payload))
        with self.assertRaises(native.DeploymentError):
            native.load_config(config_path)

    def test_relative_source_is_resolved_from_config_file(self) -> None:
        payload = asdict(self.config)
        payload["source"] = "project"
        config_path = self.root / "deploy.json"
        config_path.write_text(json.dumps(payload))
        with patch("pathlib.Path.cwd", return_value=Path("/private/tmp")):
            loaded = native.load_config(config_path)
        self.assertEqual(Path(loaded.source).resolve(), self.source.resolve())

    def test_missing_dbt_project_cannot_be_packaged(self) -> None:
        (self.source / "dbt_project.yml").unlink()
        with self.assertRaises(native.DeploymentError):
            native.prepare_source(self.config, self.root / "bundle")

    def test_mismatched_profile_cannot_be_packaged(self) -> None:
        with self.assertRaises(native.DeploymentError):
            native.prepare_source(
                replace(self.config, profile="wrong_profile"), self.root / "bundle"
            )

    def test_bundle_contains_models_and_no_local_credentials_or_artifacts(self) -> None:
        for path in (
            "profiles.yml",
            "dbt_projects_profiles.yml",
            ".env",
            ".git/config",
            "target/manifest.json",
            "logs/dbt.log",
            "private_key.pem",
            "config.toml",
        ):
            self.write(path, "LOCAL_PRIVATE_SECRET\n")
        destination = self.root / "bundle"
        native.prepare_source(self.config, destination)
        self.assertEqual((destination / "models/example.sql").read_text(), "select 1 as id\n")
        self.assertTrue((destination / "dbt_project.yml").exists())
        self.assertTrue((destination / "dbt_projects_profiles.yml").exists())
        generated = yaml.safe_load((destination / "dbt_projects_profiles.yml").read_text())
        self.assertEqual(generated, native.native_profile(self.config))
        for path in destination.rglob("*"):
            if path.is_file():
                self.assertNotIn("LOCAL_PRIVATE_SECRET", path.read_text(), str(path))
        self.assertFalse((destination / "profiles.yml").exists())
        self.assertFalse((destination / "target").exists())
        self.assertFalse((destination / "logs").exists())

    def test_symlink_outside_source_is_rejected(self) -> None:
        secret = self.root / "secret.sql"
        secret.write_text("PRIVATE\n")
        (self.source / "models/linked.sql").symlink_to(secret)
        with self.assertRaises(native.DeploymentError):
            native.prepare_source(self.config, self.root / "bundle")

    def test_loaded_source_cannot_hide_a_symlink(self) -> None:
        link = self.root / "linked-project"
        link.symlink_to(self.source, target_is_directory=True)
        payload = asdict(self.config)
        payload["source"] = str(link)
        path = self.root / "deployment.json"
        path.write_text(json.dumps(payload))
        with self.assertRaises(native.DeploymentError):
            native.prepare_source(native.load_config(path), self.root / "bundle")

    def test_runtime_environment_references_are_not_silently_lost(self) -> None:
        self.write("models/example.sql", "select '{{ env_var(\"DBT_REGION\") }}' as region\n")
        with self.assertRaises(native.DeploymentError):
            native.prepare_source(self.config, self.root / "bundle")

    def test_model_path_cannot_escape_source(self) -> None:
        self.write(
            "dbt_project.yml", "name: tiny\nprofile: tiny_profile\nmodel-paths: ['../private']\n"
        )
        with self.assertRaises(native.DeploymentError):
            native.prepare_source(self.config, self.root / "bundle")

    def test_bundle_destination_cannot_be_inside_source(self) -> None:
        with self.assertRaises(native.DeploymentError):
            native.prepare_source(self.config, self.source / "models/bundle")

    def test_project_yaml_must_be_a_mapping(self) -> None:
        for value in ("[]\n", "null\n", "plain string\n"):
            with self.subTest(value=value):
                self.write("dbt_project.yml", value)
                with self.assertRaises(native.DeploymentError):
                    native.prepare_source(self.config, self.root / "bundle")

    def test_unresolved_remote_dependencies_require_external_access(self) -> None:
        self.write(
            "packages.yml", "packages:\n  - package: dbt-labs/dbt_utils\n    version: 1.3.0\n"
        )
        with self.assertRaises(native.DeploymentError):
            native.prepare_source(self.config, self.root / "bundle")

    def test_remote_packages_are_included_with_explicit_external_access(self) -> None:
        self.write(
            "packages.yml", "packages:\n  - package: dbt-labs/dbt_utils\n    version: 1.3.0\n"
        )
        config = replace(self.config, external_access_integrations=["DBT_PACKAGE_ACCESS"])
        destination = self.root / "bundle"
        native.prepare_source(config, destination)
        self.assertEqual(
            (destination / "packages.yml").read_text(), (self.source / "packages.yml").read_text()
        )
        calls, fake = self.fake_snow()
        with patch.object(native.subprocess, "run", side_effect=fake):
            native.deploy(config, apply=True)
        command = next(call for call in calls if call[1:3] == ["dbt", "deploy"])
        self.assertEqual(
            command[command.index("--external-access-integration") + 1], "DBT_PACKAGE_ACCESS"
        )

    def test_external_access_does_not_allow_embedded_git_credentials(self) -> None:
        self.write(
            "packages.yml",
            "packages:\n  - git: https://PRIVATE_TOKEN@github.com/owner/package.git\n"
            "    revision: pinned\n",
        )
        config = replace(self.config, external_access_integrations=["DBT_PACKAGE_ACCESS"])
        with self.assertRaisesRegex(native.DeploymentError, "credentials"):
            native.prepare_source(config, self.root / "bundle")

    def test_dry_run_does_not_contact_snowflake(self) -> None:
        with patch.object(native.subprocess, "run") as run:
            native.deploy(self.config)
        run.assert_not_called()

    def test_build_preview_does_not_contact_snowflake(self) -> None:
        with patch.object(native.subprocess, "run") as run:
            native.deploy(self.config, build=True)
        run.assert_not_called()

    def fake_snow(
        self,
        *,
        identity_account: str = "account",
        described_target: str = "prod",
        supported_runtime: str = "1.11.11",
        existing_live: bool | None = None,
        checkout_commit: str = "a" * 40,
        described_commit: str | None = "a" * 40,
        copy_fault: str | None = None,
    ) -> tuple[list[list[str]], object]:
        calls: list[list[str]] = []
        deployed_source: Path | None = None

        def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            nonlocal deployed_source
            calls.append(command)
            if command[0] == "git":
                output = checkout_commit if "rev-parse" in command else ""
                return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")
            if command[0] != "snow":
                raise AssertionError(f"Unexpected external command: {command}")
            if "--version" in command:
                output = "Snowflake CLI version: 3.28.0"
            elif "sql" in command:
                flag = "--query" if "--query" in command else "-q"
                query = command[command.index(flag) + 1].upper()
                if "CURRENT_ORGANIZATION_NAME" in query:
                    output = json.dumps(
                        [
                            {
                                "ORGANIZATION": "org",
                                "ACCOUNT": identity_account,
                                "ROLE": "TRANSFORMER",
                                "SECONDARY_ROLES": json.dumps({"roles": "", "value": "NONE"}),
                            }
                        ]
                    )
                elif "SYSTEM$SUPPORTED_DBT_VERSIONS" in query:
                    output = json.dumps(
                        [
                            {
                                "VERSIONS": json.dumps(
                                    [{"dbt_version": supported_runtime, "type": "dbt Core"}]
                                )
                            }
                        ]
                    )
                elif "SHOW DBT PROJECTS" in query:
                    output = (
                        "[]"
                        if existing_live is None
                        else json.dumps(
                            [
                                {
                                    "name": "TINY",
                                    "owner": "TRANSFORMER",
                                    "default_version": "LIVE" if existing_live else "VERSION$1",
                                }
                            ]
                        )
                    )
                elif "SHOW VERSIONS IN DBT PROJECT" in query:
                    output = json.dumps([{"is_live": existing_live}])
                else:
                    raise AssertionError(f"Unexpected SQL: {query}")
            elif command[1:3] == ["dbt", "describe"]:
                row: dict[str, object] = {
                    "name": "TINY",
                    "owner": "TRANSFORMER",
                    "dbt_version": "1.11.11",
                    "default_target": described_target,
                    "default_version": "LIVE",
                    "external_access_integrations": "[]",
                }
                if described_commit is not None:
                    row["last_deployed_from"] = {"git_commit": described_commit}
                output = json.dumps([row])
            elif command[1:3] == ["dbt", "deploy"]:
                deployed_source = Path(command[command.index("--source") + 1])
                output = "[]"
            elif command[1:3] == ["dbt", "copy"]:
                if deployed_source is None:
                    raise AssertionError("Readback happened before deployment")
                cloud_index = next(
                    i for i, value in enumerate(command) if value.startswith("snow://dbt/")
                )
                self.assertEqual(command[cloud_index], "snow://dbt/CONTROL.DBT.TINY/versions/live/")
                self.assertIn("--recursive", command)
                target = Path(command[cloud_index + 1])
                shutil.copytree(deployed_source, target, dirs_exist_ok=True)
                if copy_fault == "receipt":
                    (target / "deployment_receipt.json").write_text("{}")
                elif copy_fault == "missing_receipt":
                    (target / "deployment_receipt.json").unlink()
                elif copy_fault == "model":
                    (target / "models/example.sql").write_text("select 'changed' as id\n")
                elif copy_fault == "missing_model":
                    (target / "models/example.sql").unlink()
                elif copy_fault == "extra_model":
                    (target / "models/rogue.sql").write_text("select 'unexpected' as id\n")
                elif copy_fault == "generated_artifacts":
                    for relative in (
                        "target/manifest.json",
                        "logs/dbt.log",
                        "dbt_packages/utils/macros/util.sql",
                        "dbt_artifacts.zip",
                        "package-lock.yml",
                    ):
                        artifact = target / relative
                        artifact.parent.mkdir(parents=True, exist_ok=True)
                        artifact.write_text("server-generated artifact\n")
                output = "[]"
            elif command[1:3] in (["dbt", "execute"], ["connection", "test"]):
                output = "[]"
            else:
                raise AssertionError(f"Unexpected Snowflake command: {command}")
            return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")

        return calls, run

    def test_wrong_account_fails_before_deployment(self) -> None:
        calls, fake = self.fake_snow(identity_account="other_account")
        with (
            patch.object(native.subprocess, "run", side_effect=fake),
            self.assertRaises(native.DeploymentError),
        ):
            native.deploy(self.config, apply=True)
        self.assertFalse(any(call[1:3] == ["dbt", "deploy"] for call in calls))

    def test_unsupported_runtime_fails_before_deployment(self) -> None:
        calls, fake = self.fake_snow(supported_runtime="1.9.4")
        with (
            patch.object(native.subprocess, "run", side_effect=fake),
            self.assertRaises(native.DeploymentError),
        ):
            native.deploy(self.config, apply=True)
        self.assertFalse(any(call[1:3] == ["dbt", "deploy"] for call in calls))

    def test_existing_legacy_object_is_not_replaced_or_migrated(self) -> None:
        calls, fake = self.fake_snow(existing_live=False)
        with (
            patch.object(native.subprocess, "run", side_effect=fake),
            self.assertRaises(native.DeploymentError),
        ):
            native.deploy(self.config, apply=True)
        self.assertFalse(any(call[1:3] == ["dbt", "deploy"] for call in calls))
        self.assertNotIn("SYSTEM$MIGRATE_DBT_PROJECT", " ".join(" ".join(call) for call in calls))

    def test_existing_live_object_can_be_updated_without_force(self) -> None:
        calls, fake = self.fake_snow(existing_live=True)
        with patch.object(native.subprocess, "run", side_effect=fake):
            native.deploy(self.config, apply=True)
        deployments = [call for call in calls if call[1:3] == ["dbt", "deploy"]]
        self.assertEqual(len(deployments), 1)
        self.assertNotIn("--force", deployments[0])

    def test_github_deployment_records_exact_checked_out_commit(self) -> None:
        calls, fake = self.fake_snow()
        environment = {
            "GITHUB_SHA": "a" * 40,
            "GITHUB_REPOSITORY": "owner/repository",
            "GITHUB_REF_NAME": "main",
            "GITHUB_SERVER_URL": "https://github.com",
        }
        with (
            patch.dict(native.os.environ, environment),
            patch.object(native.subprocess, "run", side_effect=fake),
        ):
            native.deploy(self.config, apply=True)
        command = next(call for call in calls if call[1:3] == ["dbt", "deploy"])
        self.assertEqual(command[command.index("--git-commit") + 1], "a" * 40)
        self.assertEqual(
            command[command.index("--git-url") + 1], "https://github.com/owner/repository"
        )
        self.assertEqual(command[command.index("--git-branch") + 1], "main")

    def test_wrong_checkout_commit_fails_before_deployment(self) -> None:
        calls, fake = self.fake_snow(checkout_commit="b" * 40)
        with (
            patch.dict(native.os.environ, {"GITHUB_SHA": "a" * 40}),
            patch.object(native.subprocess, "run", side_effect=fake),
            self.assertRaises(native.DeploymentError),
        ):
            native.deploy(self.config, apply=True)
        self.assertFalse(any(call[1:3] == ["dbt", "deploy"] for call in calls))

    def test_deployed_commit_mismatch_prevents_requested_build(self) -> None:
        calls, fake = self.fake_snow(described_commit="b" * 40)
        with (
            patch.dict(native.os.environ, {"GITHUB_SHA": "a" * 40}),
            patch.object(native.subprocess, "run", side_effect=fake),
            self.assertRaises(native.DeploymentError),
        ):
            native.deploy(self.config, apply=True, build=True)
        self.assertFalse(any(call[1:3] == ["dbt", "execute"] for call in calls))

    def test_missing_backend_git_metadata_uses_verified_receipt_and_payload(self) -> None:
        calls, fake = self.fake_snow(described_commit=None)
        with (
            patch.dict(native.os.environ, {"GITHUB_SHA": "a" * 40}),
            patch.object(native.subprocess, "run", side_effect=fake),
        ):
            native.deploy(self.config, apply=True, build=True)
        described = next(i for i, call in enumerate(calls) if call[1:3] == ["dbt", "describe"])
        copied = next(i for i, call in enumerate(calls) if call[1:3] == ["dbt", "copy"])
        built = next(i for i, call in enumerate(calls) if call[1:3] == ["dbt", "execute"])
        self.assertLess(described, copied)
        self.assertLess(copied, built)

    def test_corrupt_or_missing_readback_files_prevent_requested_build(self) -> None:
        for fault in ("receipt", "missing_receipt", "model", "missing_model"):
            with self.subTest(fault=fault):
                calls, fake = self.fake_snow(described_commit=None, copy_fault=fault)
                with (
                    patch.dict(native.os.environ, {"GITHUB_SHA": "a" * 40}),
                    patch.object(native.subprocess, "run", side_effect=fake),
                    self.assertRaises(native.DeploymentError),
                ):
                    native.deploy(self.config, apply=True, build=True)
                self.assertTrue(any(call[1:3] == ["dbt", "copy"] for call in calls))
                self.assertFalse(any(call[1:3] == ["dbt", "execute"] for call in calls))

    def test_readback_hashes_are_checked_even_with_backend_git_metadata(self) -> None:
        calls, fake = self.fake_snow(copy_fault="model")
        with (
            patch.dict(native.os.environ, {"GITHUB_SHA": "a" * 40}),
            patch.object(native.subprocess, "run", side_effect=fake),
            self.assertRaises(native.DeploymentError),
        ):
            native.deploy(self.config, apply=True, build=True)
        self.assertFalse(any(call[1:3] == ["dbt", "execute"] for call in calls))

    def test_unexpected_deployed_model_prevents_requested_build(self) -> None:
        calls, fake = self.fake_snow(copy_fault="extra_model")
        with (
            patch.object(native.subprocess, "run", side_effect=fake),
            self.assertRaises(native.DeploymentError),
        ):
            native.deploy(self.config, apply=True, build=True)
        self.assertFalse(any(call[1:3] == ["dbt", "execute"] for call in calls))

    def test_generated_server_artifacts_do_not_invalidate_source_readback(self) -> None:
        calls, fake = self.fake_snow(copy_fault="generated_artifacts")
        with patch.object(native.subprocess, "run", side_effect=fake):
            native.deploy(self.config, apply=True, build=True)
        self.assertTrue(any(call[1:3] == ["dbt", "copy"] for call in calls))
        self.assertTrue(any(call[1:3] == ["dbt", "execute"] for call in calls))

    def test_deployment_uses_native_object_and_preserves_history(self) -> None:
        calls, fake = self.fake_snow()
        with patch.object(native.subprocess, "run", side_effect=fake):
            native.deploy(self.config, apply=True)
        deployments = [call for call in calls if call[1:3] == ["dbt", "deploy"]]
        self.assertEqual(len(deployments), 1)
        self.assertIn("CONTROL.DBT.TINY", deployments[0])
        self.assertNotIn("--force", deployments[0])
        self.assertIn("--dbt-version", deployments[0])
        self.assertTrue(any(call[1:3] == ["dbt", "describe"] for call in calls))
        self.assertFalse(any(call[1:3] == ["dbt", "execute"] for call in calls))

    def test_wizard_infers_distinct_object_and_model_destinations_without_credentials(self) -> None:
        self.write(
            "profiles.yml",
            "tiny_profile:\n  target: prod\n  outputs:\n    prod:\n"
            "      type: snowflake\n      database: ANALYTICS\n      schema: PROD\n"
            "      role: TRANSFORMER\n      warehouse: COMPUTE\n"
            "      user: PRIVATE_USER\n      password: PRIVATE_PASSWORD\n",
        )
        home = self.root / "home"
        snowflake = home / ".snowflake"
        snowflake.mkdir(parents=True)
        (snowflake / "config.toml").write_text(
            '[connections.dev]\naccount="org-account"\ndatabase="CONTROL"\n'
            'schema="DBT"\nrole="TRANSFORMER"\nwarehouse="COMPUTE"\n'
            'password="PRIVATE_CONNECTION_PASSWORD"\n'
        )
        output = self.root / "deployment.json"
        args = native.parser().parse_args(
            [
                "wizard",
                "--source",
                str(self.source),
                "--connection",
                "dev",
                "--output",
                str(output),
                "--non-interactive",
                "--dbt-version",
                "1.11.11",
            ]
        )
        with (
            patch.object(Path, "home", return_value=home),
            patch.object(native.subprocess, "run") as run,
        ):
            config = native.wizard(args)
        run.assert_not_called()
        self.assertEqual((config.database, config.object_schema), ("CONTROL", "DBT"))
        self.assertEqual((config.model_database, config.model_schema), ("ANALYTICS", "PROD"))
        self.assertEqual(
            (config.project, config.profile, config.target), ("tiny", "tiny_profile", "prod")
        )
        saved = output.read_text()
        self.assertNotIn("PRIVATE", saved)
        self.assertNotIn("PRIVATE", self.stdout.getvalue())
        self.assertFalse(Path(json.loads(saved)["source"]).is_absolute())

    def test_requested_build_runs_only_after_successful_readback(self) -> None:
        calls, fake = self.fake_snow()
        with patch.object(native.subprocess, "run", side_effect=fake):
            native.deploy(self.config, apply=True, build=True)
        described = next(i for i, call in enumerate(calls) if call[1:3] == ["dbt", "describe"])
        execution = next(i for i, call in enumerate(calls) if call[1:3] == ["dbt", "execute"])
        self.assertGreater(execution, described)
        self.assertIn("build", calls[execution])
        self.assertIn("prod", calls[execution])

    def test_readback_mismatch_fails_without_build(self) -> None:
        calls, fake = self.fake_snow(described_target="dev")
        with (
            patch.object(native.subprocess, "run", side_effect=fake),
            self.assertRaises(native.DeploymentError),
        ):
            native.deploy(self.config, apply=True, build=True)
        self.assertFalse(any(call[1:3] == ["dbt", "execute"] for call in calls))


if __name__ == "__main__":
    unittest.main()
