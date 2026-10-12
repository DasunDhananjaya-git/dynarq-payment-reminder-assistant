# Dynarq Payment Reminder Assistant

## Run locally (Python 3.11+; standard library only)

1. Open a terminal in `python/`.
2. Run tests: `python -m unittest -v`.
3. Generate today's plan: `python plan.py --invoices ../data/invoices.json --sent ../data/sent.json --today 2026-10-12 --out ../actions.json`.
4. Start the owner page: `python app.py`, then open `http://localhost:8000/`.
5. Optional settings: `PORT`, `DATA_DIR` (folder containing both JSON files), and `TODAY` (`YYYY-MM-DD`).

## Decisions

- Validate dates as real, canonical `YYYY-MM-DD` values and reject boolean, string, non-finite, zero, or negative amounts.
- Check duplicate IDs before other row validation and list each duplicated ID once; show the first applicable data error for other rows.
- Plan one highest eligible step only and suppress it when that step or a higher step is already recorded as sent.
- Use deterministic message templates without invented fees, interest amounts, deadlines, or references to previous reminders.
- Require in-memory approval decisions for firm/final reminders; the page does not send email and does not persist decisions after the process exits.
- The owner page uses the same `build_plan` function as the CLI, escapes displayed invoice content, and adapts to narrow screens and keyboard use.
- Research answers use only the provided source extracts. The current ECB rate is marked as not present in those sources.

## Next with more time

Add persistent decision storage and audit history, improve automated HTTP/page tests, and review legal wording with the business owner before any real reminders are sent.
