import json
import os
import subprocess
from pathlib import Path

import pytest
from pydantic import SecretStr

from airp.cli import demo, execute_command, init_demo, parser
from airp.core.config import Settings
from airp.core.security import Forbidden, authenticate
from airp.integrations import collect
from airp.remediation.backends import atomic_json


def test_complete_fixture_demo(tmp_path, capsys):
    settings = Settings(state_dir=tmp_path)
    init_demo(settings)
    assert demo(settings, auto_approve=True) == 0
    reports = [json.loads(path.read_text()) for path in (tmp_path / "reports").glob("*.json")]
    assert len(reports) == 7
    assert sum(item["verified"] for item in reports) == 1
    assert "SIMULATED" in capsys.readouterr().out
    assert "airp_remediations_total" in (tmp_path / "telemetry" / "metrics.prom").read_text()


def test_cli_missing_token_fails_closed(tmp_path):
    result = subprocess.run(
        ["airp", "verify-audit"],
        capture_output=True,
        text=True,
        env={**os.environ, "AIRP_STATE_DIR": str(tmp_path), "AIRP_TOKEN": ""},
        timeout=15,
        check=False,
    )
    assert result.returncode == 1


@pytest.mark.parametrize(
    "format,data,source",
    [
        (
            "sarif",
            {"runs": [{"results": [{"ruleId": "rule-1", "message": {"text": "finding"}}]}]},
            "codeql",
        ),
        (
            "dependabot",
            [
                {
                    "security_advisory": {
                        "ghsa_id": "DEMO-1",
                        "summary": "fictional",
                        "severity": "high",
                    },
                    "dependency": {"package": {"name": "demo"}},
                }
            ],
            "dependabot",
        ),
        (
            "trivy",
            {"Results": [{"Class": "os-pkgs", "Vulnerabilities": [{"VulnerabilityID": "DEMO-2"}]}]},
            "trivy",
        ),
    ],
)
def test_scanner_adapters(tmp_path, format, data, source):
    path = tmp_path / "input.json"
    atomic_json(path, data)
    result = collect(path, format)
    assert len(result) == 1 and result[0].source == source and result[0].target is None


def test_all_categories_and_priority():
    findings = collect(Path("demo/findings.json"))
    assert len({finding.category for finding in findings}) == 7
    assert findings[0].severity == "critical"


def test_identity_file_permissions(tmp_path):
    path = tmp_path / "identities.json"
    atomic_json(path, {})
    path.chmod(0o644)
    with pytest.raises(Forbidden, match="accessible"):
        authenticate(path, "fake")


def test_separate_operator_cli_workflow(tmp_path, capsys):
    from test_core import finding

    settings = Settings(state_dir=tmp_path)
    init_demo(settings)
    capsys.readouterr()
    source = tmp_path / "finding.json"
    atomic_json(source, [finding().model_dump(mode="json")])

    def invoke(role, arguments):
        token = json.loads((tmp_path / f"{role}.token.json").read_text())["token"]
        configured = settings.model_copy(update={"token": SecretStr(token)})
        assert execute_command(parser().parse_args(arguments), configured) == 0
        return capsys.readouterr().out

    planned = json.loads(invoke("planner", ["plan", str(source)]))
    run_id, plan_digest = planned["run_id"], planned["plan_digest"]
    assert len(plan_digest) == 64
    assert json.loads(invoke("planner", ["inspect", run_id]))["plan_digest"] == plan_digest
    invoke("executor", ["execute", run_id])
    invoke("approver", ["approve", run_id, "--digest", plan_digest])
    executed = json.loads(invoke("executor", ["execute", run_id, "--apply"]))
    assert executed["run"]["state"] == "succeeded"
    invoke("executor", ["report", run_id])
    assert len(invoke("executor", ["verify-audit"]).strip()) == 64
