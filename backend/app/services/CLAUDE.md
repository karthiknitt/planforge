# backend/app/services — conventions

Stateful concerns and outbound integrations: persistence, access control, payments,
external APIs. Pure geometry belongs in `../engine/`.

## The external-service pattern

`render_providers.py` is the reference implementation; `structagent_client.py` follows it.
Any new outbound HTTP service should too:

- A **module-level test transport seam** (`_transport_for_tests`) that tests inject an
  `httpx.MockTransport` into — no network in the test suite.
- A **dedicated exception type** (e.g. `StructuralAPIError`), never a bare `Exception`.
- A **fresh `httpx.AsyncClient` per call**, with an explicit timeout.
- An `is_configured()` predicate so the feature degrades gracefully when unset rather
  than crashing at import.

## Structural integration

`structagent_client.py` → HTTP client for structapi (frozen v1 envelope, `x-api-key`).
`structural_loop.py` → orchestrates a design request end to end.
`structural_store.py` → revision persistence.

The feature is **disabled, not broken**, when `STRUCTURAL_API_KEY` is unset — layout
generation must keep working. Preserve that.

## Gotchas

- **Cold starts run ~20–25s** (Cloud Run `min-instances=0`). Anything called from the
  frontend needs a generous timeout; a 15s abort previously surfaced as "connection
  errors" in the agent chat. Agent tools pass 45s.
- **Never solve inside a read path.** `_load_layout_state` once ran up to 3 CP-SAT solves
  on a store miss; it now returns 409 `{"code": "no_layouts"}` instead.
- **Payments must stay idempotent** — `razorpay_gateway.py` verification is bound to a
  paid order and grants are deduplicated via `consumed_payments`.
