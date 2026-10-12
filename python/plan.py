"""Payment reminder rules engine.

Run from this directory, for example:
    python plan.py --invoices ../data/invoices.json --sent ../data/sent.json \
      --today 2026-10-12 --out ../actions.json
"""

import argparse
import json
import math
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

STEPS = ((24, "final", True), (10, "firm", True), (3, "friendly", False))
STEP_RANK = {"friendly": 1, "firm": 2, "final": 3}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_date(value: Any) -> date | None:
    """Return a real, canonical YYYY-MM-DD date, or None."""
    if not isinstance(value, str) or not DATE_RE.fullmatch(value):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def is_valid_amount(amount: Any) -> bool:
    """Amounts must be positive finite JSON numbers; booleans are not numbers here."""
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        return False
    try:
        numeric = float(amount)
    except (OverflowError, ValueError):
        return False
    return math.isfinite(numeric) and numeric > 0


def reminder_message(invoice: dict[str, Any], step: str, days_overdue: int) -> str:
    """Create a self-contained message without adding fees or made-up deadlines."""
    customer = str(invoice.get("customer", "Customer"))
    invoice_id = str(invoice.get("id", ""))
    due_date = str(invoice.get("due_date", ""))
    currency = str(invoice.get("currency", ""))
    amount = float(invoice["amount"])
    formatted_amount = f"{currency} {amount:,.2f}"

    if step == "friendly":
        return (
            f"Hello {customer}, this is a friendly reminder that invoice {invoice_id} "
            f"for {formatted_amount}, due on {due_date}, is {days_overdue} days overdue. "
            "Please arrange payment when convenient. Thank you."
        )
    if step == "firm":
        return (
            f"Dear {customer}, our records show that invoice {invoice_id} for "
            f"{formatted_amount}, due on {due_date}, is {days_overdue} days overdue. "
            "Please arrange payment promptly. Kind regards."
        )
    return (
        f"Dear {customer}, invoice {invoice_id} for {formatted_amount}, due on "
        f"{due_date}, is {days_overdue} days overdue. Please treat this as our final "
        "payment reminder. Kind regards."
    )


def build_plan(invoices: list[dict[str, Any]], sent: list[dict[str, Any]], today: str) -> dict[str, Any]:
    """Build today's reminder plan and skipped-data list using the task rules."""
    today_date = parse_date(today)
    if today_date is None:
        raise ValueError("--today must be a real date in YYYY-MM-DD format")
    if not isinstance(invoices, list):
        raise ValueError("Invoices file must contain a JSON list")
    if not isinstance(sent, list):
        raise ValueError("Sent reminders file must contain a JSON list")

    # IDs are specified as text in the input contract. Count them before other
    # validation so duplicate_id takes precedence over every other data error.
    id_counts = Counter(
        invoice.get("id")
        for invoice in invoices
        if isinstance(invoice, dict) and isinstance(invoice.get("id"), str)
    )
    duplicate_ids = {invoice_id for invoice_id, count in id_counts.items() if count > 1}

    sent_ranks: dict[str, int] = {}
    for item in sent:
        if not isinstance(item, dict):
            continue
        invoice_id = item.get("invoice_id")
        step = item.get("step")
        if isinstance(invoice_id, str) and isinstance(step, str) and step in STEP_RANK:
            sent_ranks[invoice_id] = max(sent_ranks.get(invoice_id, 0), STEP_RANK[step])

    actions: list[dict[str, Any]] = []
    skipped_by_id: dict[str, dict[str, str]] = {}

    for index, invoice in enumerate(invoices):
        if not isinstance(invoice, dict):
            # The input contract specifies invoice objects with text IDs. Keep
            # unexpected rows from crashing the entire run while making the
            # problem visible in the skipped list.
            skipped_by_id[f"~invalid-row-{index:06d}"] = {
                "invoice_id": f"(row {index + 1})", "reason": "invalid_due_date"
            }
            continue

        raw_id = invoice.get("id")
        invoice_id = raw_id if isinstance(raw_id, str) else str(raw_id or "")
        if invoice_id in duplicate_ids:
            skipped_by_id[invoice_id] = {"invoice_id": invoice_id, "reason": "duplicate_id"}
            continue

        amount = invoice.get("amount")
        if not is_valid_amount(amount):
            skipped_by_id[invoice_id] = {"invoice_id": invoice_id, "reason": "invalid_amount"}
            continue

        raw_due = invoice.get("due_date")
        if raw_due is None or raw_due == "":
            skipped_by_id[invoice_id] = {"invoice_id": invoice_id, "reason": "missing_due_date"}
            continue
        due_date = parse_date(raw_due)
        if due_date is None:
            skipped_by_id[invoice_id] = {"invoice_id": invoice_id, "reason": "invalid_due_date"}
            continue

        raw_paid = invoice.get("paid_date")
        paid_date = None
        if raw_paid is not None:
            paid_date = parse_date(raw_paid)
            if paid_date is None or paid_date > today_date:
                skipped_by_id[invoice_id] = {"invoice_id": invoice_id, "reason": "invalid_paid_date"}
                continue
        if paid_date is not None:
            continue

        days_overdue = (today_date - due_date).days
        if days_overdue < 3:
            continue

        eligible_step = next(
            (step for threshold, step, needs_approval in STEPS if days_overdue >= threshold),
            None,
        )
        if eligible_step is None:
            continue
        if sent_ranks.get(invoice_id, 0) >= STEP_RANK[eligible_step]:
            continue

        needs_approval = eligible_step in ("firm", "final")
        actions.append({
            "invoice_id": invoice_id,
            "step": eligible_step,
            "needs_approval": needs_approval,
            "days_overdue": days_overdue,
            "message": reminder_message(invoice, eligible_step, days_overdue),
        })

    actions.sort(key=lambda item: item["invoice_id"])
    skipped = sorted(skipped_by_id.values(), key=lambda item: item["invoice_id"])
    return {"today": today, "actions": actions, "skipped": skipped}


def read_json(path: str) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan today's payment reminders.")
    parser.add_argument("--invoices", required=True, help="path to invoices.json")
    parser.add_argument("--sent", required=True, help="path to sent.json")
    parser.add_argument("--today", required=True, help="date as YYYY-MM-DD")
    parser.add_argument("--out", required=True, help="path to write the plan JSON")
    args = parser.parse_args()

    try:
        invoices = read_json(args.invoices)
        sent = read_json(args.sent)
        plan = build_plan(invoices, sent, args.today)
        output_path = Path(args.out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(plan, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
