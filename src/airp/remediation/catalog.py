from copy import deepcopy
from typing import Any

from airp.core.models import Plan, Snapshot

RULE = "K8S-TOKEN-001"


def expected_spec(before: Snapshot) -> dict[str, Any]:
    result = deepcopy(before.spec)
    result["template"]["spec"]["automountServiceAccountToken"] = False
    return result


def json_patch(plan: Plan) -> list[dict[str, Any]]:
    return [
        {"op": "test", "path": "/metadata/uid", "value": plan.before.uid},
        {"op": "test", "path": "/metadata/resourceVersion", "value": plan.before.resource_version},
        {"op": "add", "path": "/spec/template/spec/automountServiceAccountToken", "value": False},
    ]
