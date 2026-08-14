# Publication package

This file is preparation only. The repository has not been published.

## GitHub description

> Clean-room Python MCP reference adapter demonstrating a SQLite transactional outbox,
> idempotency-key forwarding, bounded retries, dead-letter handling, restart recovery, and an
> inspectable audit trail.

## Topics

`model-context-protocol`, `mcp-server`, `python`, `sqlite`, `transactional-outbox`, `idempotency`,
`retries`, `dead-letter-queue`, `distributed-systems`, `reliability`, `clean-room`, `portfolio`

## README badges

Add only after the repository URL and default branch exist. Replace `OWNER` and `REPO`; do not use
a coverage, production, exactly-once, package-version, or PyPI badge because none of those claims
is established by the current repository.

```markdown
[![CI](https://github.com/OWNER/REPO/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/REPO/actions/workflows/ci.yml)
![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
```

Place the badges immediately below the H1. The CI badge is the only live quality signal: it runs
Ruff, builds the distributions, reinstalls the wheel, runs the tests, and imports the installed
package.

## LinkedIn post — English

> I built MCP Reliable Adapter, a clean-room portfolio project around one concrete question: how
> can an MCP server accept a request without losing or duplicating it when the downstream SaaS is
> unreliable?
>
> The implementation commits the request, outbox item, and first audit event in one SQLite
> transaction. It then retries with bounded exponential backoff, forwards the original idempotency
> key, recovers claimed work after restart, and exposes exhausted work as dead letter.
>
> It includes two MCP tools and 13 passing test cases. The scope is intentionally compact: it uses
> a fictional SaaS and is not presented as a production-ready help desk. The README also documents
> its limitations and a multi-worker production path.
>
> Repository: [URL]
>
> #MCP #Python #DistributedSystems #BackendEngineering #AIEngineering

## LinkedIn post — Español

> Construí MCP Reliable Adapter, un proyecto de portafolio clean-room para explorar un problema
> concreto: ¿cómo aceptar una solicitud MCP sin perderla ni duplicarla cuando el SaaS de destino
> falla?
>
> La implementación persiste la solicitud, el outbox y el primer evento de auditoría en una sola
> transacción SQLite. Después reintenta con backoff exponencial limitado, conserva la clave de
> idempotencia, recupera trabajo tras un reinicio y hace visibles los fallos agotados en dead letter.
>
> Incluye dos herramientas MCP y 13 casos de prueba aprobados. El alcance es deliberadamente
> compacto: usa un SaaS ficticio y no pretende ser un help desk listo para producción. El README
> documenta también los límites y el camino a una arquitectura multiworker.
>
> Repositorio: [URL]
>
> #MCP #Python #DistributedSystems #BackendEngineering #AIEngineering

## CV bullet

> Built a clean-room Python MCP reference adapter with a SQLite transactional outbox, same-key
> payload conflict detection, idempotency-key forwarding, bounded exponential retries,
> dead-letter handling, restart recovery, and an inspectable audit trail; exposed 2 MCP tools and
> validated 10 reliability scenarios across 13 passing test cases.

## Demo — 60 seconds

1. Explain that an MCP call and an external API cannot share a transaction.
2. Show `submit_support_ticket`: ticket, outbox and audit event commit together.
3. Simulate a transient SaaS failure and show bounded exponential retry.
4. Show delivery with the original idempotency key and the resulting external ID.
5. Show dead-letter and audit history.
6. Run the 13 tests and Ruff.
7. End on Limitations: fictional SaaS, single host; production needs a supervised worker,
   PostgreSQL leases, authentication and observability.

Never claim exactly-once delivery. Downstream creation is effectively-once only when the SaaS
honors the forwarded idempotency key.

### Demo asset recommendation

Record one uncut terminal capture (60–90 seconds) after publication, using synthetic values only:

1. Run the README's local demo and point out the `pending` state after the simulated first failure
   and the `retry_scheduled` audit event.
2. Run `pytest -q` to show the current 13 passing cases.
3. Open the README at **Guarantees and failure semantics**, explicitly highlighting
   **at-least-once delivery attempts** and the conditional downstream idempotency statement.
4. End at **Limitations and production path**.

Do not narrate the demo as exactly-once, production-ready, battle-tested, deployed, multi-worker,
or integrated with a real SaaS. The current README snippet does not wait for the retry deadline and
therefore does not demonstrate successful recovery in that single run; describe it as a scheduled
retry, not a completed retry. A later demo may inject a controllable clock, but that would require
a code change and new validation.

## LinkedIn Featured

- **Type:** link to the GitHub repository (not a package release).
- **Title:** `MCP Reliable Adapter — durable MCP-to-SaaS delivery demo`
- **Description:** `Clean-room Python reference project demonstrating a SQLite transactional
  outbox, idempotency-key forwarding, bounded retries, dead-letter handling, restart recovery, and
  an inspectable audit trail. Fictional SaaS; documented single-host limitations.`
- **Media:** use the repository social preview or the short terminal demo only after its URL is
  public. Do not use employer/client logos or imply a production deployment.

## Publication gates

- [x] `pytest`: 13 passed (10 scenarios; parametrization accounts for the case count).
- [x] `ruff check .`: passed.
- [x] wheel and source distribution build successfully.
- [x] tracked-source scan found no credential-like values, employer/client names, customer data,
  or proprietary identifiers; `.env.example` contains only the local `ADAPTER_DB_PATH` example.
- [x] `PROVENANCE.md` records the clean-room boundary.
- [ ] Create the Git repository and substitute the real `OWNER/REPO` in badges and links.
- [ ] Run the hosted CI before citing the badge or publishing the LinkedIn Featured item.
- [ ] Manually inspect the final staged diff and repository visibility immediately before publish.

The provenance conclusion is limited to the files inspected in this package: there is no Git
metadata here, so commit history and authorship history cannot be independently verified locally.
