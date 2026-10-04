import os
from pathlib import Path

import pytest
from kubernetes.client.exceptions import ApiException
from test_workflow import APPROVER, EXECUTOR, PLANNER

from airp.core.models import Finding, State, Target
from airp.core.security import Policy, read_json
from airp.core.store import Store
from airp.mcp.client import MCPReader
from airp.mcp.server import EvidenceBundle
from airp.providers import MockProvider
from airp.remediation.backends import KubernetesBackend, atomic_json
from airp.workflow import OrchestratorAgent

pytestmark = [
    pytest.mark.kind,
    pytest.mark.skipif(
        os.environ.get("AIRP_TEST_KIND") != "1", reason="Set AIRP_TEST_KIND=1 after make kind-up"
    ),
]


def test_real_cluster_workflow_and_admission(tmp_path):
    backend = KubernetesBackend(Path(".state/executor.kubeconfig"), "kind-airp")
    target = Target(namespace="airp-demo", name="demo-web")
    before = backend.read(target)
    assert before.healthy and not before.automount_disabled
    with pytest.raises(ApiException) as denied:
        backend.api.patch_namespaced_deployment(
            target.name, target.namespace, {"spec": {"replicas": 9}}
        )
    assert denied.value.status == 403
    with pytest.raises(ApiException) as forbidden:
        backend.api.read_namespaced_deployment("not-allowlisted", target.namespace)
    assert forbidden.value.status == 403
    bundle_path = tmp_path / "evidence.json"
    atomic_json(
        bundle_path,
        EvidenceBundle(backend_id=backend.identity, workloads=[backend.read(target)]).model_dump(
            mode="json"
        ),
    )
    store = Store(tmp_path / "workflow.db")
    workflow = OrchestratorAgent(
        store, Policy.model_validate(read_json(Path("policies/local.json")))
    )
    finding = Finding(
        id="kind-token",
        source="kubernetes",
        category="kubernetes",
        severity="high",
        rule_id="K8S-TOKEN-001",
        description="Real local workload",
        target=target,
    )
    run = workflow.analyze(
        finding, PLANNER, backend.identity, MockProvider(), MCPReader(bundle_path)
    )
    assert run.state == State.AWAITING_APPROVAL
    workflow.execute(run.id, EXECUTOR, backend, dry_run=True)
    assert not backend.read(target).automount_disabled
    workflow.approve(run.id, APPROVER, run.plan.hash)
    result = workflow.execute(run.id, EXECUTOR, backend, dry_run=False)
    assert result.state == State.SUCCEEDED, result.reason
    assert result.validation.passed and store.verify()
    store.close()
