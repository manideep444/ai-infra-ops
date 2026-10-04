from pathlib import Path

import pytest
from test_core import finding

from airp.core.security import Policy, Principal, read_json
from airp.core.store import Store
from airp.mcp.server import EvidenceTools
from airp.providers import MockProvider
from airp.remediation.backends import FixtureBackend, atomic_json
from airp.workflow import OrchestratorAgent


@pytest.fixture
def env(tmp_path):
    tools = EvidenceTools(Path("demo/evidence.json"))
    atomic_json(tmp_path / "workload.json", tools.workload("airp-demo", "demo-web"))
    backend = FixtureBackend(tmp_path / "workload.json")
    policy = Policy.model_validate(read_json(Path("policies/local.json")))
    store = Store(tmp_path / "state.db")

    class Reader:
        def snapshot(self, target):
            return backend.read(target)

    workflow = OrchestratorAgent(store, policy)
    planner = Principal(name="planner", roles=["planner"])
    run = workflow.analyze(finding(), planner, backend.identity, MockProvider(), Reader())
    yield workflow, run, backend, store, Reader()
    store.close()
