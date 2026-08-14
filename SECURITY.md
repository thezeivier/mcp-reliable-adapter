# Security

## Scope and trust boundary

This repository is a compact, single-host reference implementation. Its default server uses MCP
over local `stdio`, a fictional in-memory SaaS, and a local SQLite database. It is not an
internet-facing service and is not production-ready.

The example intentionally does not implement authentication, authorization, input-size limits,
rate limiting, encrypted storage, PII redaction, tamper-evident audit logs, secret management, or
multi-worker leases. A process with access to the database file can read or alter its contents.
Treat all tool inputs and the SQLite file as sensitive if adapting the code to real data.

Do not expose the server to untrusted clients or replace the fake SaaS with a real API until those
controls, explicit network timeouts, response classification, safe credential injection, schema
migrations, and an environment-specific security review are in place.

## Credentials and data

The repository requires no credentials. `.env` files, SQLite databases, virtual environments,
build artifacts, caches, private keys, and common editor metadata are ignored by Git. The checked-in
`.env.example` contains only a local example path and no secret value.

Never commit real customer payloads, database files, API responses, access tokens, or employer and
client material to issues, tests, fixtures, screenshots, or pull requests.

## Reporting a vulnerability

Until a public repository and maintainer contact are configured, report security concerns privately
to the repository owner. Do not include live credentials, customer data, or exploit traffic in a
report. A public disclosure channel can be added when the repository is published.
