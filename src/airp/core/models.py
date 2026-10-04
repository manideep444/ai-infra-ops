from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def now() -> datetime:
    return datetime.now(UTC)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Target(Contract):
    namespace: str = Field(pattern=r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$")
    name: str = Field(pattern=r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$")

    @property
    def key(self) -> str:
        return f"{self.namespace}/{self.name}"


class Finding(Contract):
    schema_version: Literal[1] = 1
    id: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9._:/-]+$")
    source: Literal["normalized", "codeql", "dependabot", "trivy", "kubernetes"]
    category: Literal[
        "os", "dependency", "container", "infrastructure", "code", "kubernetes", "compliance"
    ]
    severity: Literal["critical", "high", "medium", "low", "unknown"]
    rule_id: str = Field(min_length=1, max_length=160)
    description: str = Field(max_length=8000)
    target: Target | None = None
    component: str = Field(default="unknown", max_length=300)


class Snapshot(Contract):
    target: Target
    uid: str = Field(min_length=1, max_length=100)
    resource_version: str = Field(min_length=1, max_length=100)
    generation: int = Field(ge=1)
    observed_generation: int = Field(ge=0)
    ready_replicas: int = Field(ge=0)
    updated_replicas: int = Field(ge=0)
    available_replicas: int = Field(ge=0)
    spec: dict[str, Any]

    @property
    def healthy(self) -> bool:
        replicas = self.spec.get("replicas", 1)
        return (
            isinstance(replicas, int)
            and replicas > 0
            and self.observed_generation >= self.generation
            and self.ready_replicas == replicas
            and self.updated_replicas == replicas
            and self.available_replicas == replicas
        )

    @property
    def automount_disabled(self) -> bool:
        return (
            self.spec.get("template", {}).get("spec", {}).get("automountServiceAccountToken")
            is False
        )


class TriageResult(Contract):
    priority: int = Field(ge=0, le=4)
    impact: str = Field(max_length=2000)
    uncertainty: str = Field(max_length=2000)
    possible_false_positive: bool = False


class Diagnosis(Contract):
    root_cause: str = Field(max_length=2000)
    evidence_digest: str
    snapshot: Snapshot | None = None
    actionable: bool


class Plan(Contract):
    schema_version: Literal[1] = 1
    finding_id: str
    action: Literal["disable_token_automount"]
    target: Target
    before: Snapshot
    expected_spec: dict[str, Any]
    policy_digest: str
    rationale: str = Field(max_length=2000)
    created_at: datetime
    expires_at: datetime

    @property
    def hash(self) -> str:
        return digest(self.model_dump(mode="json"))


class Approval(Contract):
    plan_digest: str
    actor: str
    approved_at: datetime
    expires_at: datetime


class ValidationResult(Contract):
    original_rule_resolved: bool
    healthy: bool
    no_regression: bool
    target_identity_matches: bool
    observed: Snapshot

    @property
    def passed(self) -> bool:
        return all(
            (
                self.original_rule_resolved,
                self.healthy,
                self.no_regression,
                self.target_identity_matches,
            )
        )


class State(StrEnum):
    ANALYZING = "analyzing"
    AWAITING_APPROVAL = "awaiting_approval"
    MANUAL_REQUIRED = "manual_required"
    APPROVED = "approved"
    DENIED = "denied"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    NEEDS_INTERVENTION = "needs_intervention"


TRANSITIONS: dict[State, frozenset[State]] = {
    State.ANALYZING: frozenset({State.AWAITING_APPROVAL, State.MANUAL_REQUIRED, State.FAILED}),
    State.AWAITING_APPROVAL: frozenset({State.APPROVED, State.DENIED, State.FAILED}),
    State.APPROVED: frozenset({State.EXECUTING, State.FAILED}),
    State.EXECUTING: frozenset({State.SUCCEEDED, State.FAILED, State.NEEDS_INTERVENTION}),
}


class Run(Contract):
    id: str
    state: State = State.ANALYZING
    version: int = 0
    created_at: datetime
    planner: str
    backend_id: str
    finding: Finding
    triage: TriageResult | None = None
    diagnosis: Diagnosis | None = None
    plan: Plan | None = None
    approval: Approval | None = None
    validation: ValidationResult | None = None
    reason: str = ""
