# Security Policy

This reference is not approved for unattended production remediation. Read the
[threat model](docs/security.md) before granting infrastructure credentials.

Before publishing, enable GitHub private vulnerability reporting in the repository
security settings. Use that channel for exploitable findings. If it is unavailable,
open a public issue requesting a private reporting channel without including exploit
details, credentials or confidential data.

Do not submit real infrastructure snapshots, tokens, kubeconfigs, Terraform state,
private model endpoints or employer data in issues. Provide a reproduction using
the fictional fixtures where possible. There is no guaranteed support SLA.

Dependency, image and infrastructure scanners must remain enabled. A newly disclosed
issue may make a previously passing release fail; resolve it or document a narrowly
scoped, time-bounded exception rather than disabling the gate.