from copy import deepcopy

import pytest

from airp.admission import EXECUTOR, admit


def request():
    before = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": "demo-web", "uid": "1"},
        "spec": {
            "replicas": 2,
            "template": {
                "spec": {"automountServiceAccountToken": True, "containers": [{"image": "trusted"}]}
            },
        },
    }
    after = deepcopy(before)
    after["spec"]["template"]["spec"]["automountServiceAccountToken"] = False
    return {
        "operation": "UPDATE",
        "namespace": "airp-demo",
        "name": "demo-web",
        "resource": {"group": "apps", "version": "v1", "resource": "deployments"},
        "userInfo": {"username": EXECUTOR},
        "object": after,
        "oldObject": before,
    }


def test_catalog_patch_allowed():
    value = request()
    value["object"]["metadata"]["generation"] = 2
    assert admit(value)


@pytest.mark.parametrize(
    "attack", ["image", "replicas", "annotation", "new_field", "identity", "revert"]
)
def test_extra_mutations_denied(attack):
    value = request()
    after = value["object"]
    if attack == "image":
        after["spec"]["template"]["spec"]["containers"][0]["image"] = "untrusted"
    elif attack == "replicas":
        after["spec"]["replicas"] = 100
    elif attack == "annotation":
        after["metadata"]["annotations"] = {"inject": "yes"}
    elif attack == "new_field":
        after["spec"]["template"]["spec"]["hostNetwork"] = True
    elif attack == "identity":
        after["metadata"]["uid"] = "other"
    else:
        after["spec"]["template"]["spec"]["automountServiceAccountToken"] = True
    assert not admit(value)
