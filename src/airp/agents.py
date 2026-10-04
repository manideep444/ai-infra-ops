from datetime import timedelta
from typing import Any

from airp.core.models import (
    Diagnosis,
    Finding,
    Plan,
    Run,
    Snapshot,
    TriageResult,
    ValidationResult,
    digest,
    now,
)
from airp.core.security import Policy
from airp.mcp.client import EvidenceReader
from airp.providers import Provider
from airp.remediation.catalog import RULE, expected_spec


class TriageAgent:
    def __init__(self, provider: Provider) -> None:
        self.provider = provider

    def run(self, finding: Finding) -> TriageResult:
        advice = self.provider.analyze(finding)
        return TriageResult(
            priority={"critical": 0, "high": 1, "medium": 2, "low": 3, "unknown": 4}[
                finding.severity
            ],
            **advice.model_dump(),
        )


class DiagnosticAgent:
    def __init__(self, evidence: EvidenceReader) -> None:
        self.evidence = evidence

    def run(self, finding: Finding) -> Diagnosis:
        if finding.target is None or finding.category != "kubernetes" or finding.rule_id != RULE:
            return Diagnosis(
                root_cause="No executable detector for this finding; manual analysis required",
                evidence_digest=digest(finding.model_dump(mode="json")),
                actionable=False,
            )
        snapshot = self.evidence.snapshot(finding.target)
        return Diagnosis(
            root_cause=(
                "Token automount is not explicitly disabled"
                if not snapshot.automount_disabled
                else "Original finding not reproduced in the supplied snapshot"
            ),
            evidence_digest=digest(snapshot.model_dump(mode="json")),
            snapshot=snapshot,
            actionable=not snapshot.automount_disabled,
        )


class RemediationAgent:
    def run(self, finding: Finding, diagnosis: Diagnosis, policy: Policy) -> Plan | None:
        if not diagnosis.actionable or diagnosis.snapshot is None:
            return None
        snapshot = diagnosis.snapshot
        created = now()
        return Plan(
            finding_id=finding.id,
            action="disable_token_automount",
            target=snapshot.target,
            before=snapshot,
            expected_spec=expected_spec(snapshot),
            policy_digest=policy.hash,
            rationale="Remove unused API credentials; verify rollout and preserve other fields",
            created_at=created,
            expires_at=created + timedelta(seconds=policy.plan_ttl_seconds),
        )


class RiskPolicyAgent:
    def run(self, plan: Plan, policy: Policy) -> str:
        policy.check(plan)
        return (
            "Human approval required: workload restart and credential removal may affect behavior"
        )


class ValidationAgent:
    def run(self, plan: Plan, observed: Snapshot) -> ValidationResult:
        return ValidationResult(
            original_rule_resolved=observed.automount_disabled,
            healthy=observed.healthy,
            no_regression=observed.spec == plan.expected_spec,
            target_identity_matches=observed.uid == plan.before.uid
            and observed.target == plan.target,
            observed=observed,
        )


class ReportingAgent:
    def run(self, run: Run, events: list[dict[str, Any]], checkpoint: str) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "run": run.model_dump(mode="json"),
            "events": events,
            "audit_checkpoint": checkpoint,
            "verified": run.validation is not None
            and run.validation.passed
            and run.state == "succeeded",
            "limitations": [
                "Local hash chain is not external immutable retention",
                "Health and spec checks do not prove application business behavior",
            ],
        }
