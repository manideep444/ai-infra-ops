import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from uuid import uuid4

from airp import observability as telemetry
from airp.agents import (
    DiagnosticAgent,
    RemediationAgent,
    RiskPolicyAgent,
    TriageAgent,
    ValidationAgent,
)
from airp.core.models import Approval, Finding, Run, State, now
from airp.core.security import Forbidden, Policy, Principal
from airp.core.store import Conflict, Store
from airp.mcp.client import EvidenceReader
from airp.providers import Provider
from airp.remediation.backends import Backend


class OrchestratorAgent:
    def __init__(self, store: Store, policy: Policy) -> None:
        self.store, self.policy = store, policy

    @contextmanager
    def stage(self, name: str, run: Run, actor: Principal) -> Iterator[None]:
        self.store.record(run.id, actor.name, f"{name}_started")
        with telemetry.agent_span(name, run.id):
            try:
                yield
            except Exception:
                self.store.record(run.id, actor.name, f"{name}_failed")
                raise
            else:
                self.store.record(run.id, actor.name, f"{name}_completed")

    def analyze(
        self,
        finding: Finding,
        actor: Principal,
        backend_id: str,
        provider: Provider,
        evidence: EvidenceReader,
    ) -> Run:
        actor.require("planner")
        run = Run(
            id=str(uuid4()),
            created_at=now(),
            planner=actor.name,
            backend_id=backend_id,
            finding=finding,
        )
        self.store.create(run)
        try:
            with self.stage("triage", run, actor):
                triage = TriageAgent(provider).run(finding)
            with self.stage("diagnostic", run, actor):
                diagnosis = DiagnosticAgent(evidence).run(finding)
            with self.stage("remediation", run, actor):
                plan = RemediationAgent().run(finding, diagnosis, self.policy)
            if plan is None:
                result = self.store.transition(
                    run,
                    State.MANUAL_REQUIRED,
                    actor.name,
                    triage=triage,
                    diagnosis=diagnosis,
                    reason=diagnosis.root_cause,
                )
                telemetry.WORKFLOWS.labels(result.state).inc()
                return result
            with self.stage("risk_policy", run, actor):
                reason = RiskPolicyAgent().run(plan, self.policy)
            return self.store.transition(
                run,
                State.AWAITING_APPROVAL,
                actor.name,
                triage=triage,
                diagnosis=diagnosis,
                plan=plan,
                reason=reason,
            )
        except Exception as error:
            telemetry.WORKFLOWS.labels("failed").inc()
            return self.store.transition(
                run, State.FAILED, actor.name, reason=f"Analysis blocked: {type(error).__name__}"
            )

    def approve(self, run_id: str, actor: Principal, plan_digest: str, deny: bool = False) -> Run:
        actor.require("approver")
        self.store.verify()
        run = self.store.get(run_id)
        if run.state != State.AWAITING_APPROVAL or run.plan is None:
            raise Conflict("Run is not awaiting approval")
        if actor.name == run.planner:
            raise Forbidden("Planner cannot approve their own plan")
        if plan_digest != run.plan.hash:
            raise Forbidden("Approval digest does not match the reviewed plan")
        if deny:
            return self.store.transition(
                run, State.DENIED, actor.name, reason="Human approval denied"
            )
        self.policy.check(run.plan)
        approval = Approval(
            plan_digest=plan_digest,
            actor=actor.name,
            approved_at=now(),
            expires_at=min(
                run.plan.expires_at, now() + timedelta(seconds=self.policy.approval_ttl_seconds)
            ),
        )
        return self.store.transition(run, State.APPROVED, actor.name, approval=approval)

    def execute(self, run_id: str, actor: Principal, backend: Backend, dry_run: bool = True) -> Run:
        actor.require("executor")
        self.store.verify()
        run = self.store.get(run_id)
        if run.plan is None or run.state not in {State.APPROVED, State.AWAITING_APPROVAL}:
            raise Conflict("Run has no executable pending plan")
        self.policy.check(run.plan)
        if backend.identity != run.backend_id:
            raise Forbidden("Execution backend differs from the planned backend")
        current = backend.read(run.plan.target)
        if (
            current.uid != run.plan.before.uid
            or current.resource_version != run.plan.before.resource_version
            or current.spec != run.plan.before.spec
            or not current.healthy
        ):
            raise Forbidden("Target drift or unhealthy target; collect fresh evidence and re-plan")
        if dry_run:
            backend.apply(run.plan, dry_run=True)
            return run
        if (
            run.state != State.APPROVED
            or run.approval is None
            or run.approval.plan_digest != run.plan.hash
            or run.approval.expires_at <= now()
        ):
            raise Forbidden("A current approval for this exact plan is required")
        if actor.name in {run.planner, run.approval.actor}:
            raise Forbidden("Executor must be separate from planner and approver")
        run = self.store.transition(run, State.EXECUTING, actor.name)
        assert run.plan is not None
        started = time.monotonic()
        try:
            with self.stage("executor", run, actor):
                backend.apply(run.plan)
            with self.stage("validation", run, actor):
                result = ValidationAgent().run(run.plan, backend.observe(run.plan.target))
            state = State.SUCCEEDED if result.passed else State.NEEDS_INTERVENTION
            run = self.store.transition(
                run,
                state,
                actor.name,
                validation=result,
                reason="Verified" if result.passed else "Required validation failed",
            )
        except Exception as error:
            run = self.store.transition(
                run,
                State.NEEDS_INTERVENTION,
                actor.name,
                reason=f"Execution outcome requires inspection: {type(error).__name__}",
            )
        telemetry.REMEDIATIONS.labels(run.state).inc()
        telemetry.WORKFLOWS.labels(run.state).inc()
        telemetry.EXECUTION.observe(time.monotonic() - started)
        return run

    def reconcile(self, run_id: str, actor: Principal, backend: Backend) -> Run:
        actor.require("executor")
        self.store.verify()
        run = self.store.get(run_id)
        if run.state != State.EXECUTING or run.plan is None or backend.identity != run.backend_id:
            raise Conflict(
                "Only an interrupted executing run on its original backend can reconcile"
            )
        try:
            validation = ValidationAgent().run(run.plan, backend.observe(run.plan.target))
            return self.store.transition(
                run,
                State.SUCCEEDED if validation.passed else State.NEEDS_INTERVENTION,
                actor.name,
                validation=validation,
                reason="Read-only reconciliation; no mutation replayed",
            )
        except Exception as error:
            return self.store.transition(
                run,
                State.NEEDS_INTERVENTION,
                actor.name,
                reason=f"Reconciliation blocked: {type(error).__name__}",
            )
