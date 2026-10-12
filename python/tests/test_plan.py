"""Run from python/: python -m unittest"""

import unittest
from plan import build_plan

TODAY = "2026-10-12"


def invoice(invoice_id="INV-1", **changes):
    row = {
        "id": invoice_id, "customer": "Example Ltd", "email": "accounts@example.test",
        "amount": 1250.0, "currency": "EUR", "due_date": "2026-10-01", "paid_date": None,
    }
    row.update(changes)
    return row


class BuildPlanTests(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(build_plan([], [], TODAY), {"today": TODAY, "actions": [], "skipped": []})

    def test_thresholds_and_only_highest_step(self):
        rows = [
            invoice("INV-03", due_date="2026-10-09"),  # 3 days: friendly
            invoice("INV-10", due_date="2026-10-02"),  # 10 days: firm
            invoice("INV-24", due_date="2026-09-18"),  # 24 days: final
        ]
        plan = build_plan(rows, [], TODAY)
        by_id = {a["invoice_id"]: a for a in plan["actions"]}
        self.assertEqual(by_id["INV-03"]["step"], "friendly")
        self.assertEqual(by_id["INV-10"]["step"], "firm")
        self.assertEqual(by_id["INV-24"]["step"], "final")
        self.assertEqual(by_id["INV-24"]["days_overdue"], 24)

    def test_not_overdue_enough_and_due_today_are_ignored(self):
        rows = [invoice("A", due_date=TODAY), invoice("B", due_date="2026-10-10"), invoice("C", due_date="2026-10-09")]
        self.assertEqual([x["invoice_id"] for x in build_plan(rows, [], TODAY)["actions"]], ["C"])

    def test_sent_current_or_higher_step_suppresses_action(self):
        rows = [invoice("A", due_date="2026-10-09"), invoice("B", due_date="2026-10-02"), invoice("C", due_date="2026-09-18")]
        sent = [
            {"invoice_id": "A", "step": "firm", "sent_on": "2026-10-11"},
            {"invoice_id": "B", "step": "firm", "sent_on": "2026-10-11"},
            {"invoice_id": "C", "step": "firm", "sent_on": "2026-10-11"},
            {"invoice_id": "unknown", "step": "final"},
            {"invoice_id": "A", "step": "not-a-step"},
        ]
        actions = build_plan(rows, sent, TODAY)["actions"]
        self.assertEqual([a["invoice_id"] for a in actions], ["C"])

    def test_duplicate_id_is_reported_once_and_precedes_other_errors(self):
        rows = [invoice("DUP", amount=0), invoice("DUP", due_date=None), invoice("OK", due_date="2026-02-30")]
        skipped = build_plan(rows, [], TODAY)["skipped"]
        self.assertEqual(skipped, [
            {"invoice_id": "DUP", "reason": "duplicate_id"},
            {"invoice_id": "OK", "reason": "invalid_due_date"},
        ])

    def test_invalid_amount_includes_boolean_string_zero_and_negative(self):
        rows = [invoice("A", amount=True), invoice("B", amount="12"), invoice("C", amount=0), invoice("D", amount=-1)]
        self.assertEqual({x["invoice_id"]: x["reason"] for x in build_plan(rows, [], TODAY)["skipped"]},
                         {"A": "invalid_amount", "B": "invalid_amount", "C": "invalid_amount", "D": "invalid_amount"})

    def test_date_validation_and_reason_precedence(self):
        rows = [
            invoice("A", due_date=None, paid_date="bad"),
            invoice("B", due_date=""),
            invoice("C", due_date="2026-02-30"),
            invoice("D", paid_date=""),
            invoice("E", paid_date="2026-10-13"),
            invoice("F", amount="2", due_date="bad"),
        ]
        self.assertEqual({x["invoice_id"]: x["reason"] for x in build_plan(rows, [], TODAY)["skipped"]}, {
            "A": "missing_due_date", "B": "missing_due_date", "C": "invalid_due_date",
            "D": "invalid_paid_date", "E": "invalid_paid_date", "F": "invalid_amount",
        })

    def test_paid_invoice_never_gets_action(self):
        rows = [invoice("PAID", paid_date="2026-10-05", due_date="2026-09-01")]
        self.assertEqual(build_plan(rows, [], TODAY)["actions"], [])

    def test_messages_include_required_fields_and_no_invented_fee(self):
        action = build_plan([invoice("INV-88", amount=1250, due_date="2026-09-18")], [], TODAY)["actions"][0]
        message = action["message"]
        for part in ("Example Ltd", "INV-88", "2026-09-18", "EUR 1,250.00", "24 days overdue"):
            self.assertIn(part, message)
        self.assertNotIn("fee", message.lower())
        self.assertNotIn("interest", message.lower())
        self.assertNotIn("90 days", message.lower())

    def test_plain_text_sort_order(self):
        rows = [invoice("INV-99"), invoice("INV-100")]
        ids = [x["invoice_id"] for x in build_plan(rows, [], TODAY)["actions"]]
        self.assertEqual(ids, ["INV-100", "INV-99"])

    def test_invalid_today_rejected(self):
        with self.assertRaises(ValueError):
            build_plan([], [], "2026-02-30")


if __name__ == "__main__":
    unittest.main()
