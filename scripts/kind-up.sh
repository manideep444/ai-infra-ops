#!/usr/bin/env bash
set -euo pipefail
for tool in docker kind kubectl helm openssl uv; do
  command -v "$tool" >/dev/null || { printf 'Missing prerequisite: %s\n' "$tool"; exit 1; }
done
docker info >/dev/null
if kind get clusters | grep -qx airp; then
  printf 'Existing airp cluster: refreshing one-hour credentials without resetting workloads.\n'
  uv run python scripts/provision-kind.py --credentials-only
  exit 0
fi
kind create cluster --config kubernetes/kind.yaml --image kindest/node:v1.35.0
helm repo add cilium https://helm.cilium.io --force-update
helm upgrade --install cilium cilium/cilium --version 1.18.6 --namespace kube-system \
  --set ipam.mode=kubernetes --kube-context kind-airp --wait --timeout 300s
kubectl --context kind-airp apply -f kubernetes/namespaces.yaml -f kubernetes/rbac.yaml
mkdir -p .state/tls
chmod 700 .state .state/tls
openssl req -x509 -newkey rsa:3072 -nodes -keyout .state/tls/tls.key \
  -out .state/tls/tls.crt -days 7 -subj '/CN=airp-admission.airp-system.svc' \
  -addext 'subjectAltName=DNS:airp-admission.airp-system.svc' 2>/dev/null
chmod 600 .state/tls/tls.key
kubectl --context kind-airp -n airp-system create secret tls admission-tls \
  --cert=.state/tls/tls.crt --key=.state/tls/tls.key
demo_token=$(openssl rand -hex 24)
kubectl --context kind-airp -n airp-demo create secret generic demo-runtime \
  --from-literal="token=$demo_token"
unset demo_token
docker build -t airp:local .
kind load docker-image airp:local --name airp
kubectl --context kind-airp apply -f kubernetes/admission.yaml -f kubernetes/workload.yaml \
  -f kubernetes/network.yaml
kubectl --context kind-airp -n airp-system rollout status deployment/airp-admission --timeout=180s
kubectl --context kind-airp -n airp-demo rollout status deployment/demo-web --timeout=180s
uv run python scripts/provision-kind.py