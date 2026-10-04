import hashlib
import hmac
import json
import stat
from pathlib import Path
from typing import Literal

from pydantic import Field

from airp.core.models import Contract, Plan, Target, digest, now

Role = Literal["reader", "planner", "approver", "executor"]


class Forbidden(RuntimeError):
    pass


class Principal(Contract):
    name: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    roles: list[Role]

    def require(self, role: Role) -> None:
        if role not in self.roles:
            raise Forbidden(f"Role required: {role}")


class Policy(Contract):
    version: int = Field(ge=1)
    targets: list[Target] = Field(min_length=1, max_length=10)
    plan_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    approval_ttl_seconds: int = Field(default=300, ge=30, le=900)
    max_replicas: int = Field(default=3, ge=1, le=10)

    @property
    def hash(self) -> str:
        return digest(self.model_dump(mode="json"))

    def check(self, plan: Plan) -> None:
        from airp.remediation.catalog import expected_spec

        if plan.policy_digest != self.hash or plan.expires_at <= now():
            raise Forbidden("Policy changed or plan expired")
        if plan.target not in self.targets or plan.before.target != plan.target:
            raise Forbidden("Target is not allowlisted")
        if not plan.before.healthy or plan.before.spec.get("replicas", 1) > self.max_replicas:
            raise Forbidden("Target health or blast radius precondition failed")
        if plan.before.automount_disabled:
            raise Forbidden("No remediation needed")
        if plan.expected_spec != expected_spec(plan.before):
            raise Forbidden("Plan exceeds the action catalog")


def read_json(path: Path, maximum: int = 1_000_000) -> object:
    with path.open("rb") as stream:
        content = stream.read(maximum + 1)
    if len(content) > maximum:
        raise ValueError("Input exceeds size limit")
    return json.loads(content)


def authenticate(path: Path, token: str | None) -> Principal:
    if token is None or len(token) > 1024:
        raise Forbidden("An operator-issued token is required")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise Forbidden("Identity file must not be accessible to group or other users")
    identities = read_json(path)
    if not isinstance(identities, dict):
        raise Forbidden("Invalid identity configuration")
    presented = hashlib.sha256(token.encode()).hexdigest()
    for expected, identity in identities.items():
        if hmac.compare_digest(presented, expected):
            return Principal.model_validate(identity)
    raise Forbidden("Invalid token")
