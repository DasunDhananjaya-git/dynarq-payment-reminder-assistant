"""Responsive owner page for the payment reminder assistant (standard library only).

Run from python/: python app.py
Environment: PORT (8000), DATA_DIR (../data), TODAY (real local date by default).
"""

import os
from datetime import date
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from plan import build_plan, read_json

PORT = int(os.environ.get("PORT", "8000"))
DATA_DIR = os.environ.get("DATA_DIR", "../data")
TODAY = os.environ.get("TODAY") or date.today().isoformat()
# The task explicitly permits keeping choices only while the app process runs.
DECISIONS: dict[str, str] = {}
SKIP_LABELS = {
    "duplicate_id": "This invoice ID appears more than once in the file.",
    "invalid_amount": "The amount is missing, not a valid number, or is not greater than zero.",
    "missing_due_date": "The due date is missing.",
    "invalid_due_date": "The due date is not a real date in YYYY-MM-DD format.",
    "invalid_paid_date": "The paid date is invalid or is later than today.",
}


def e(value: object) -> str:
    return escape(str(value), quote=True)


def load_plan():
    invoices = read_json(os.path.join(DATA_DIR, "invoices.json"))
    sent = read_json(os.path.join(DATA_DIR, "sent.json"))
    plan = build_plan(invoices, sent, TODAY)
    lookup = {
        row.get("id"): row for row in invoices
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    return plan, lookup


def layout(content: str, *, title: str = "Payment reminders", status: int = 200) -> tuple[int, bytes]:
    body = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<style>
:root {{ color-scheme: light; --ink:#17212b; --muted:#5d6875; --line:#dbe2e8; --paper:#f5f7f9; --navy:#12324a; --orange:#f07850; --green:#176b4d; --red:#9f2d2d; }}
* {{ box-sizing:border-box; }} body {{ margin:0; background:var(--paper); color:var(--ink); font:16px/1.5 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
header {{ background:var(--navy); color:white; padding:24px max(18px,calc((100vw - 1120px)/2)); }} header h1 {{ margin:0 0 4px; font-size:clamp(1.5rem,4vw,2.1rem); }} header p {{ margin:0; color:#e4edf4; }} main {{ width:min(1120px,100%); margin:24px auto; padding:0 16px 36px; }}
.notice {{ padding:12px 14px; border:1px solid var(--line); border-radius:12px; background:white; margin-bottom:18px; }} .stats {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; margin:18px 0 24px; }} .stat {{ background:white; border:1px solid var(--line); padding:14px; border-radius:12px; }} .stat strong {{ display:block; font-size:1.5rem; }} .stat span {{ color:var(--muted); font-size:.9rem; }} h2 {{ margin:26px 0 12px; font-size:1.25rem; }} .card {{ background:white; border:1px solid var(--line); border-radius:14px; padding:16px; margin:12px 0; min-width:0; }} .card-head {{ display:flex; gap:10px; align-items:flex-start; justify-content:space-between; flex-wrap:wrap; }} .card h3 {{ margin:0; font-size:1.08rem; overflow-wrap:anywhere; }} .meta {{ color:var(--muted); margin:4px 0 12px; overflow-wrap:anywhere; }} .tag {{ display:inline-block; padding:3px 9px; border-radius:999px; background:#eaf0f5; font-weight:650; font-size:.82rem; }} .message {{ margin:12px 0; padding:12px; border-left:3px solid var(--orange); background:#fff8f5; white-space:normal; overflow-wrap:anywhere; }} .decision {{ font-weight:650; margin:10px 0; }} .approved {{ color:var(--green); }} .rejected {{ color:var(--red); }} .actions {{ display:flex; flex-wrap:wrap; gap:10px; }} button {{ min-height:44px; padding:10px 16px; border:0; border-radius:8px; font:inherit; font-weight:650; cursor:pointer; }} .approve {{ background:var(--green); color:white; }} .reject {{ background:#fbe9e9; color:#812222; border:1px solid #e5bebe; }} button:focus-visible {{ outline:3px solid #1b80d4; outline-offset:3px; }} .empty {{ padding:20px; border-radius:12px; background:white; border:1px dashed #aebbc7; }} .skipped .tag {{ background:#fff0dc; }} footer {{ color:var(--muted); font-size:.88rem; padding:16px 0; }}
@media(max-width:520px) {{ header {{ padding:20px 16px; }} main {{ margin:16px auto; padding:0 12px 28px; }} .stats {{ grid-template-columns:1fr; gap:8px; }} .stat {{ padding:10px 13px; }} .stat strong {{ display:inline; margin-right:8px; }} .card {{ padding:13px; }} .actions button {{ flex:1 1 125px; }} }}
</style></head><body>
<header><h1>Payment reminders</h1><p>Owner workspace · {e(TODAY)} · Demo mode: no emails are sent</p></header>
<main>{content}<footer>Reminder levels follow the task rules. Approval decisions stay in memory while this app is running.</footer></main>
</body></html>'''
    return status, body.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def send_html(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path != "/":
            self.send_error(HTTPStatus.NOT_FOUND, "Page not found")
            return
        try:
            plan, invoice_lookup = load_plan()
        except (OSError, ValueError, TypeError) as exc:
            content = (
                '<section class="card"><h2>Invoice data could not be loaded</h2>'
                '<p>Check that DATA_DIR points to a folder containing valid invoices.json '
                'and sent.json files, and that TODAY is a valid YYYY-MM-DD date.</p>'
                f'<p><strong>Details:</strong> {e(exc)}</p></section>'
            )
            status, body = layout(content, title="Data error", status=500)
            self.send_html(status, body)
            return

        actions = plan["actions"]
        skipped = plan["skipped"]
        firm_final = [a for a in actions if a["needs_approval"]]
        content = (
            '<div class="notice"><strong>Today\'s plan</strong> — review each reminder below. '
            'Friendly reminders need no approval; firm and final reminders need your decision.</div>'
            '<div class="stats">'
            f'<div class="stat"><strong>{len(actions)}</strong><span>reminder actions</span></div>'
            f'<div class="stat"><strong>{len(firm_final)}</strong><span>need approval</span></div>'
            f'<div class="stat"><strong>{len(skipped)}</strong><span>invoices skipped</span></div>'
            '</div><h2>Reminder plan</h2>'
        )
        if not actions:
            content += '<div class="empty"><strong>Nothing to remind today.</strong><br>There are no eligible reminders based on the current invoice data and reminder history.</div>'

        for action in actions:
            row = invoice_lookup.get(action["invoice_id"], {})
            customer = e(row.get("customer", "Unknown customer"))
            amount = row.get("amount", 0)
            currency = e(row.get("currency", ""))
            try:
                formatted_amount = f"{currency} {float(amount):,.2f}"
            except (TypeError, ValueError):
                formatted_amount = f"{currency} {e(amount)}"
            step = action["step"]
            card = (
                '<article class="card"><div class="card-head">'
                f'<div><h3>{customer}</h3><p class="meta">Invoice {e(action["invoice_id"])} · '
                f'{formatted_amount} · {e(action["days_overdue"])} days overdue</p></div>'
                f'<span class="tag">{e(step.title())}</span></div>'
                f'<div class="message">{e(action["message"])}</div>'
            )
            if action["needs_approval"]:
                decision = DECISIONS.get(action["invoice_id"])
                if decision:
                    css = "approved" if decision == "Approved" else "rejected"
                    card += f'<p class="decision {css}" role="status">Decision: {e(decision)}</p>'
                else:
                    card += '<p class="decision">Decision needed before this reminder can be used.</p>'
                card += (
                    '<form class="actions" method="post" action="/decision">'
                    f'<input type="hidden" name="invoice_id" value="{e(action["invoice_id"])}">'
                    '<button class="approve" type="submit" name="decision" value="Approved">Approve</button>'
                    '<button class="reject" type="submit" name="decision" value="Rejected">Reject</button>'
                    '</form>'
                )
            else:
                card += '<p class="meta">No approval required.</p>'
            card += '</article>'
            content += card

        content += '<h2>Invoices skipped</h2>'
        if not skipped:
            content += '<div class="empty">No invoices were skipped for data issues.</div>'
        else:
            for item in skipped:
                reason = SKIP_LABELS.get(item["reason"], "The invoice data could not be validated.")
                content += (
                    '<article class="card skipped"><div class="card-head">'
                    f'<h3>Invoice {e(item["invoice_id"])}</h3>'
                    f'<span class="tag">Needs data fix</span></div><p>{e(reason)}</p></article>'
                )

        status, body = layout(content)
        self.send_html(status, body)

    def do_POST(self):
        if self.path != "/decision":
            self.send_error(HTTPStatus.NOT_FOUND, "Page not found")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 10_000:
                raise ValueError("Invalid form length")
            payload = self.rfile.read(length).decode("utf-8")
            form = parse_qs(payload, keep_blank_values=True)
            invoice_id = form.get("invoice_id", [""])[0]
            decision = form.get("decision", [""])[0]
            if decision not in {"Approved", "Rejected"}:
                raise ValueError("Choose approve or reject")
            plan, _ = load_plan()
            valid_ids = {
                action["invoice_id"] for action in plan["actions"]
                if action["needs_approval"]
            }
            if invoice_id not in valid_ids:
                raise ValueError("That invoice is not awaiting approval in today's plan")
            DECISIONS[invoice_id] = decision
        except (OSError, ValueError, TypeError, UnicodeDecodeError) as exc:
            content = (
                '<section class="card"><h2>Decision was not saved</h2>'
                f'<p>{e(exc)}</p><p><a href="/">Return to today\'s plan</a></p></section>'
            )
            status, body = layout(content, title="Decision not saved", status=400)
            self.send_html(status, body)
            return
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/")
        self.end_headers()

    def log_message(self, format, *args):
        # Keep the console readable during a short assessment.
        print("%s - %s" % (self.address_string(), format % args))


def main() -> None:
    server = ThreadingHTTPServer(("", PORT), Handler)
    print(f"Serving on http://localhost:{PORT}/ (data: {DATA_DIR}, today: {TODAY})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping payment reminder app.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
