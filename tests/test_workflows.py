"""The cloud workflows preserve the deployment/operator identity boundary."""

from __future__ import annotations

import re
import unittest
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]


class CorporateWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflows: dict[str, dict[str, Any]] = {}
        for name in ("deploy", "operate"):
            path = ROOT / ".github" / "workflows" / f"{name}.yml"
            # BaseLoader preserves the GitHub 'on' key and literal strings.
            self.workflows[name] = yaml.load(path.read_text(), Loader=yaml.BaseLoader)

    def test_deployment_and_operation_have_distinct_users_and_environments(self) -> None:
        expected = {
            "deploy": ("dev-deploy", "${{ vars.SNOWFLAKE_PROJECT_ADMIN_USER }}"),
            "operate": ("dev-operate", "${{ vars.SNOWFLAKE_OPERATOR_USER }}"),
        }
        for name, (environment, user) in expected.items():
            with self.subTest(workflow=name):
                job = self.workflows[name]["jobs"][name]
                self.assertEqual(job["environment"], environment)
                self.assertEqual(job["env"]["SNOWFLAKE_USER"], user)
                self.assertEqual(job["env"]["SNOWFLAKE_ACCOUNT"], "${{ vars.SNOWFLAKE_ACCOUNT }}")
                self.assertNotIn("SNOWFLAKE_PASSWORD", job["env"])
                self.assertNotIn("SNOWFLAKE_PRIVATE_KEY", job["env"])

    def test_dispatch_and_protected_main_are_required_for_both_cloud_jobs(self) -> None:
        for name, workflow in self.workflows.items():
            with self.subTest(workflow=name):
                self.assertEqual(set(workflow["on"]), {"workflow_dispatch"})
                self.assertEqual(workflow["jobs"][name]["if"], "github.ref == 'refs/heads/main'")
                self.assertEqual(workflow["permissions"], {"contents": "read"})
                self.assertEqual(
                    workflow["jobs"][name]["permissions"], {"contents": "read", "id-token": "write"}
                )

    def test_shared_non_canceling_lock_serializes_live_artifact_mutations(self) -> None:
        deployment = self.workflows["deploy"]["concurrency"]
        operation = self.workflows["operate"]["concurrency"]
        self.assertEqual(deployment, operation)
        self.assertEqual(deployment["group"], "native-dbt-dev")
        self.assertEqual(deployment["cancel-in-progress"], "false")
        self.assertNotIn("github.workflow", deployment["group"])

    def test_local_gates_and_offline_preview_precede_oidc_for_each_workflow(self) -> None:
        gates = [
            "ruff check .",
            "ruff format --check .",
            "ty check",
            "python -m unittest discover -s tests -v",
        ]
        for name, workflow in self.workflows.items():
            steps = workflow["jobs"][name]["steps"]
            auth_index = next(
                index
                for index, step in enumerate(steps)
                if step.get("uses", "").startswith("snowflakedb/snowflake-actions@")
            )
            before_auth = [step["run"] for step in steps[:auth_index] if "run" in step]
            scripts = "\n".join(before_auth)
            with self.subTest(workflow=name):
                for gate in gates:
                    self.assertIn(gate, scripts)
                self.assertIn("scripts/dbt_native.py", scripts)
                self.assertNotIn("--apply", scripts)
                self.assertNotIn("scripts/dbt_admin.py", scripts)
                auth = steps[auth_index]["with"]
                self.assertEqual(auth["use-oidc"], "true")
                self.assertEqual(
                    auth["default-config-file-path"], ".github/no-local-connection.toml"
                )
                self.assertEqual(auth["cli-version"], "3.28.0")

    def test_deployment_only_deploys_source_and_grants_operator_project_access(self) -> None:
        scripts = "\n".join(
            step.get("run", "") for step in self.workflows["deploy"]["jobs"]["deploy"]["steps"]
        )
        self.assertIn(
            "scripts/dbt_native.py deploy --config deployment/dev.json "
            "--temporary-connection --apply",
            scripts,
        )
        self.assertIn(
            "scripts/dbt_native.py project-access --config deployment/dev.json "
            "--temporary-connection --apply",
            scripts,
        )
        self.assertNotIn("--build", scripts)
        self.assertNotIn("scripts/dbt_native.py run", scripts)
        self.assertNotIn("scripts/dbt_admin.py", scripts)
        self.assertNotIn("ACCOUNTADMIN", scripts)
        self.assertNotIn("GRANT ROLE", scripts)

    def test_operator_inputs_are_environment_values_and_quoted_argument_array(self) -> None:
        workflow = self.workflows["operate"]
        inputs = workflow["on"]["workflow_dispatch"]["inputs"]
        self.assertEqual(
            inputs["command"]["options"], ["build", "compile", "retry", "source-freshness"]
        )
        job = workflow["jobs"]["operate"]
        scripts = "\n".join(step.get("run", "") for step in job["steps"])
        self.assertIn(
            'args=(run --config deployment/dev.json --command "$DBT_COMMAND" '
            "--temporary-connection --apply)",
            scripts,
        )
        self.assertIn('args+=(--state-from "$STATE_FROM")', scripts)
        self.assertIn('args+=(--select "$DBT_SELECTION")', scripts)
        self.assertIn('scripts/dbt_native.py "${args[@]}"', scripts)
        self.assertNotIn("${{ inputs.", scripts)
        self.assertNotIn("scripts/dbt_native.py deploy", scripts)
        self.assertNotIn("project-access", scripts)
        self.assertNotIn("scripts/dbt_admin.py", scripts)
        self.assertNotIn("ACCOUNTADMIN", scripts)
        self.assertNotIn("eval ", scripts)
        self.assertIn("--no-writeback", scripts)
        self.assertEqual(job["env"]["DBT_COMMAND"], "${{ inputs.command }}")
        self.assertEqual(job["env"]["STATE_FROM"], "${{ inputs.state_from }}")
        self.assertEqual(job["env"]["DBT_SELECTION"], "${{ inputs.select }}")

    def test_pinned_actions_and_non_persistent_checkout_credentials(self) -> None:
        for name, workflow in self.workflows.items():
            for step in workflow["jobs"][name]["steps"]:
                if "uses" not in step:
                    continue
                with self.subTest(workflow=name, action=step["uses"]):
                    self.assertRegex(step["uses"], r"^[^@]+@[a-f0-9]{40}$")
                    if step["uses"].startswith("actions/checkout@"):
                        self.assertEqual(step["with"]["persist-credentials"], "false")
            scripts = "\n".join(step.get("run", "") for step in workflow["jobs"][name]["steps"])
            self.assertIsNone(re.search(r"\b(?:snow|dbt)\s+(?:sql|build|run)\b", scripts))


if __name__ == "__main__":
    unittest.main()
