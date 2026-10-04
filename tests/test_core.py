from datetime import timedelta

import pytest
from pydantic import ValidationError

from airp.core.models import Finding, Run, State, Target, now
from airp.core.store import Conflict, Store


def finding() -> Finding:
    return Finding(
        id="demo-1",
        source="kubernetes",
        category="kubernetes",
        severity="high",
        rule_id="K8S-TOKEN-001",
        description="Unnecessary API token",
        target=Target(namespace="airp-demo", name="demo-web"),
    )


def test_strict_contracts() -> None:
    with pytest.raises(ValidationError):
        Target(namespace="../escape", name="demo")
    with pytest.raises(ValidationError):
        Finding.model_validate({**finding().model_dump(), "command": "arbitrary"})
    with pytest.raises(ValidationError):
        Finding.model_validate({**finding().model_dump(), "description": "x" * 8001})


def test_state_and_audit(tmp_path) -> None:
    store = Store(tmp_path / "state.db")
    run = Run(
        id="run-1", created_at=now(), planner="planner", backend_id="fixture", finding=finding()
    )
    store.create(run)
    updated = store.transition(run, State.MANUAL_REQUIRED, "planner", reason="unsupported")
    assert store.get(run.id) == updated
    assert len(store.verify()) == 64
    with pytest.raises(Conflict):
        store.transition(run, State.FAILED, "planner")
    with pytest.raises(Conflict):
        store.transition(updated, State.SUCCEEDED, "planner")
    store.connection.execute("UPDATE events SET payload='{}' WHERE sequence=1")
    with pytest.raises(Conflict, match="chain"):
        store.verify()
    store.close()


def test_utc_clock() -> None:
    assert now().utcoffset() == timedelta(0)
