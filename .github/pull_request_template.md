## What and why

<!-- One or two sentences. Link the issue if there is one. -->

## Java parity

<!-- Which Java classes/tests this ports (paths + the Java commit). List any Java test not ported and why, and any intentional behaviour difference. -->

## Checklist

- [ ] `uv run ruff check`, `uv run ruff format --check`, `uv run mypy` pass
- [ ] Tests added or ported; every behaviour change has a test that fails without it
- [ ] Coverage ≥ 95% (`uv run pytest`); if not, what is uncovered and why: …
- [ ] Golden/parity tests pass for every external contract touched
- [ ] Timeouts on outbound calls; retries only on recoverable, idempotent calls; limits on services
- [ ] No secrets or PII in code, logs, errors or fixtures
- [ ] Design doc / system diagram updated if behaviour, APIs, data or architecture changed
