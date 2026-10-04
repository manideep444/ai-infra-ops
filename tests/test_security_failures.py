from copy import deepcopy
from datetime import timedelta

import pytest
from test_core import finding
from test_workflow import APPROVER, EXECUTOR, PLANNER, approved

from airp.core.models import State, now
from airp.core.security import Forbidden
from airp.core.store import Conflict
from airp.integrations import collect
from airp.providers import MockProvider
from airp.remediation.backends import FixtureBackend, atomic_json


def test_tampered_plan_rejected(env):
    workflow, run, *_ = env
    malicious = deepcopy(run.plan.expected_spec)
    malicious["replicas"] = 9
    with pytest.raises(Forbidden, match="catalog"):
        workflow.policy.check(run.plan.model_copy(update={"expected_spec": malicious}))
    with pytest.raises(Forbidden, match="expired"):
        workflow.policy.check(
            run.plan.model_copy(update={"expires_at": now() - timedelta(seconds=1)})
        )


def test_database_document_tampering(env):
    _, run, _, store, _ = env
    store.connection.execute(
        "UPDATE runs SET document=? WHERE id=?",
        (run.model_copy(update={"reason": "forged"}).model_dump_json(), run.id),
    )
    with pytest.raises(Conflict, match="document"):
        store.verify()


def test_target_lock_rejects_other_run(env):
    workflow, run, backend, store, reader = env
    first = approved(env)
    second = workflow.analyze(finding(), PLANNER, backend.identity, MockProvider(), reader)
    second = workflow.approve(second.id, APPROVER, second.plan.hash)
    store.transition(first, State.EXECUTING, EXECUTOR.name)
    with pytest.raises(Conflict, match="Target"):
        store.transition(second, State.EXECUTING, EXECUTOR.name)
    assert store.get(second.id).state == State.APPROVED
    assert store.verify()


def test_wrong_backend_and_old_rollout(env, tmp_path):
    workflow, run, backend, *_ = env
    approved(env)
    with pytest.raises(Forbidden, match="backend"):
        workflow.execute(run.id, EXECUTOR, FixtureBackend(tmp_path / "other.json"), dry_run=False)
    snapshot = backend.read(run.plan.target)
    assert not snapshot.model_copy(update={"updated_replicas": 0}).healthy
    assert not snapshot.model_copy(update={"observed_generation": 0}).healthy
    assert not snapshot.model_copy(update={"available_replicas": 0}).healthy


def test_conflicting_duplicate_findings_rejected(tmp_path):
    original = finding().model_dump(mode="json")
    atomic_json(tmp_path / "conflict.json", [original, {**original, "severity": "low"}])
    with pytest.raises(ValueError, match="Conflicting"):
        collect(tmp_path / "conflict.json")


def test_crash_before_write_requires_intervention(env):
    workflow, run, backend, store, _ = env
    store.transition(approved(env), State.EXECUTING, EXECUTOR.name)
    result = workflow.reconcile(run.id, EXECUTOR, backend)
    assert result.state == State.NEEDS_INTERVENTION
    assert not backend.read(run.plan.target).automount_disabled
