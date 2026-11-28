import json
from copy import deepcopy
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from threading import Thread

import pytest

from airp.admission import EXECUTOR, Handler, admit


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


@pytest.fixture
def admission_connection():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever)
    thread.start()
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        yield connection
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("path", ["/validate", "/validate?timeout=5s"])
@pytest.mark.parametrize("mutation", ["catalog", "replicas", "malformed"])
def test_admission_review_response(admission_connection, path, mutation):
    value = request()
    value["uid"] = "review-123"
    if mutation == "replicas":
        value["object"]["spec"]["replicas"] = 9
    elif mutation == "malformed":
        del value["object"]
    admission_connection.request(
        "POST",
        path,
        json.dumps(
            {"apiVersion": "admission.k8s.io/v1", "kind": "AdmissionReview", "request": value}
        ),
        {"Content-Type": "application/json"},
    )
    response = admission_connection.getresponse()
    assert response.status == 200
    review = json.loads(response.read())
    assert review["apiVersion"] == "admission.k8s.io/v1"
    assert review["kind"] == "AdmissionReview"
    assert review["response"]["uid"] == value["uid"]
    allowed = mutation == "catalog"
    assert review["response"]["allowed"] is allowed
    assert review["response"]["status"]["code"] == (200 if allowed else 403)


def test_unknown_admission_path_rejected(admission_connection):
    admission_connection.request("POST", "/other?timeout=5s", "{}")
    response = admission_connection.getresponse()
    assert response.status == 400
    response.read()
