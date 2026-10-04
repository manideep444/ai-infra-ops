import asyncio
from pathlib import Path

import pytest
from test_core import finding

from airp.agents import (
    DiagnosticAgent,
    RemediationAgent,
    RiskPolicyAgent,
    TriageAgent,
    ValidationAgent,
)
from airp.core.models import Snapshot, Target
from airp.core.security import Forbidden, Policy, read_json
from airp.mcp.client import MCPReader
from airp.mcp.server import EvidenceTools
from airp.providers import MockProvider

EVIDENCE = Path("demo/evidence.json")


def test_real_mcp_transport_and_agent_contracts() -> None:
    reader = MCPReader(EVIDENCE)
    item = finding()
    triage = TriageAgent(MockProvider()).run(item)
    assert triage.priority == 1
    diagnosis = DiagnosticAgent(reader).run(item)
    policy = Policy.model_validate(read_json(Path("policies/local.json")))
    plan = RemediationAgent().run(item, diagnosis, policy)
    assert plan is not None
    assert "approval" in RiskPolicyAgent().run(plan, policy)
    observed = plan.before.model_copy(update={"spec": plan.expected_spec})
    assert ValidationAgent().run(plan, observed).passed
    assert not ValidationAgent().run(plan, plan.before).passed


def test_tool_boundaries() -> None:
    tools = EvidenceTools(EVIDENCE)
    with pytest.raises(Forbidden):
        tools.workload("kube-system", "controller")
    with pytest.raises(Forbidden):
        tools.repository("../../etc/passwd")
    with pytest.raises(Forbidden):
        asyncio.run(MCPReader(EVIDENCE).call("shell", {"command": "id"}))
    assert tools.vulnerability("DEMO-2026-001")["fixed_version"] == "2.0.1"
    assert tools.container("airp-demo", "demo-web")["images"]
    assert tools.configuration("airp-demo", "demo-web")["automountServiceAccountToken"]
    assert tools.history("example-run")["events"]
    assert not tools.validation("example-run")["original_rule_resolved"]


def test_mcp_server_rejects_unknown_target() -> None:
    with pytest.raises(ExceptionGroup) as captured:
        MCPReader(EVIDENCE).snapshot(Target(namespace="forbidden", name="secret"))
    assert captured.value.subgroup(Forbidden) is not None


def test_false_positive_is_not_executable() -> None:
    tools = EvidenceTools(EVIDENCE)
    snapshot = Snapshot.model_validate(tools.workload("airp-demo", "demo-web"))
    snapshot.spec["template"]["spec"]["automountServiceAccountToken"] = False

    class Reader:
        def snapshot(self, target: Target) -> Snapshot:
            return snapshot

    assert not DiagnosticAgent(Reader()).run(finding()).actionable
