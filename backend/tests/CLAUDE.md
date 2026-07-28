# backend/tests — conventions

86 files, 638 tests, run with `cd backend && uv run pytest`. No live network, no live DB.

## Rules

- **Use the `client` fixture** (`conftest.py`) for almost everything — in-memory
  SQLite, `get_db`/`get_current_user_id`/`get_current_user_email` overridden via
  `X-Test-User-Id`/`X-Test-User-Email` headers. Use `client_real_auth` only when the
  test specifically exercises the real `X-Internal-Auth` JWT path, and `client_db`
  when the test needs to seed rows directly through the session factory.
- **`INTERNAL_AUTH_SECRET` is set in `conftest.py`** before any app import
  (`os.environ.setdefault(...)`, 40+ chars) — a pydantic validator rejects anything
  under 32 chars, so don't shorten it or set it per-test.
- **No real outbound HTTP.** `structagent_client.py` and `render_providers.py` expose
  a module-level `_transport_for_tests: httpx.AsyncBaseTransport | None` — tests set
  it to an `httpx.MockTransport` to stub responses. Follow this pattern for any new
  external-service test rather than mocking at the `httpx.AsyncClient` level.
- **CP-SAT is not deterministic** — never re-solve inside a test that needs stable
  output. `tests/helpers/golden.py` loads a frozen layout from
  `tests/fixtures/ccqs_fixture.json` (`golden_config()`/`golden_layout()`) for CCQS
  scoring and similar checks. `tests/helpers/pdf_png.py` holds PDF-to-PNG rendering
  for visual/golden PDF assertions.

## Gotchas

- **`pytest-timeout` is not installed** — `--timeout=N` fails with "unrecognized
  arguments". Don't add it to a command or CI step without adding the dependency.
