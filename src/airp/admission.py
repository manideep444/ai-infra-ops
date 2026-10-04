import json
import ssl
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

EXECUTOR = "system:serviceaccount:airp-system:airp-executor"


def admit(request: dict[str, Any]) -> bool:
    if request.get("userInfo", {}).get("username") != EXECUTOR:
        return True
    if (
        request.get("operation") != "UPDATE"
        or request.get("namespace") != "airp-demo"
        or request.get("name") != "demo-web"
        or request.get("subResource")
        or request.get("resource") != {"group": "apps", "version": "v1", "resource": "deployments"}
    ):
        return False
    before = deepcopy(request["oldObject"])
    after = deepcopy(request["object"])
    pod_before = before["spec"]["template"]["spec"]
    pod_after = after["spec"]["template"]["spec"]
    if pod_after.get("automountServiceAccountToken") is not False:
        return False
    pod_before.pop("automountServiceAccountToken", None)
    pod_after.pop("automountServiceAccountToken", None)
    for item in (before, after):
        for generated in ("generation", "managedFields", "resourceVersion"):
            item["metadata"].pop(generated, None)
    return bool(before == after)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200 if self.path == "/healthz" else 404)
        self.end_headers()

    def do_POST(self) -> None:
        self.connection.settimeout(5)
        length = int(self.headers.get("Content-Length", "0"))
        if self.path != "/validate" or not 0 < length <= 256_000:
            self.send_error(400)
            return
        uid = ""
        allowed = False
        try:
            review = json.loads(self.rfile.read(length))
            request = review["request"]
            uid = request["uid"]
            allowed = admit(request)
        except (KeyError, TypeError, ValueError):
            allowed = False
        response = json.dumps(
            {
                "apiVersion": "admission.k8s.io/v1",
                "kind": "AdmissionReview",
                "response": {
                    "uid": uid,
                    "allowed": allowed,
                    "status": {
                        "message": "Catalog-only mutation" if allowed else "Mutation denied"
                    },
                },
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain("/tls/tls.crt", "/tls/tls.key")
    server = ThreadingHTTPServer(("0.0.0.0", 8443), Handler)  # noqa: S104
    server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
