"""Tiny zero-dependency server for the three revenue-test microsites.

Run from the repository root:

    python experiments/revenue_tests/server.py

Then open http://127.0.0.1:8788/. Leads and paid-pilot intent are stored in a
local SQLite database. Set ``DSF_EXPERIMENT_DB`` to choose another path.

This server is intentionally small: it is for demand validation, not production
account management or payment processing.
"""

from __future__ import annotations

import csv
import html
import io
import os
import sqlite3
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
SLUGS = ("permit-signal", "sbir-signal", "site-constraint")
DB_PATH = Path(os.environ.get("DSF_EXPERIMENT_DB", ROOT / "revenue_tests.sqlite"))
ADMIN_TOKEN = os.environ.get("DSF_EXPERIMENT_ADMIN_TOKEN")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS revenue_test_leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment TEXT NOT NULL,
            email TEXT NOT NULL,
            company TEXT,
            role TEXT,
            geography TEXT,
            price_intent TEXT,
            request_type TEXT,
            notes TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    return conn


def _page(slug: str) -> bytes:
    path = ROOT / slug / "index.html"
    if not path.is_file():
        raise FileNotFoundError(path)
    return path.read_bytes()


class Handler(BaseHTTPRequestHandler):
    server_version = "DSFRevenueTest/1.0"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path == "/":
            cards = "".join(
                f'<li><a href="/{slug}/">{html.escape(slug)}</a></li>' for slug in SLUGS
            )
            self._html(
                f"<h1>DataSiteForge revenue tests</h1><ul>{cards}</ul>"
                "<p>Each page measures sample requests, calls, and explicit price intent.</p>"
            )
            return
        if path == "/admin/export.csv":
            self._export_csv()
            return
        slug = path.strip("/")
        if slug in SLUGS:
            try:
                body = _page(slug)
            except FileNotFoundError:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        parsed = urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) != 2 or parts[0] != "lead" or parts[1] not in SLUGS:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        slug = parts[1]
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(HTTPStatus.BAD_REQUEST)
            return
        if length <= 0 or length > 20_000:
            self.send_error(HTTPStatus.BAD_REQUEST)
            return
        fields = parse_qs(self.rfile.read(length).decode("utf-8", errors="replace"))
        if (fields.get("website") or [""])[0].strip():  # honeypot
            self._redirect(f"/{slug}/?submitted=1")
            return
        email_value = (fields.get("email") or [""])[0].strip().lower()
        if "@" not in email_value or len(email_value) > 254:
            self.send_error(HTTPStatus.BAD_REQUEST, "A valid email is required")
            return

        def value(name: str, limit: int = 1000) -> str:
            return (fields.get(name) or [""])[0].strip()[:limit]

        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO revenue_test_leads
                    (experiment, email, company, role, geography, price_intent,
                     request_type, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    slug,
                    email_value,
                    value("company", 200),
                    value("role", 120),
                    value("geography", 200),
                    value("price_intent", 120),
                    value("request_type", 120),
                    value("notes", 1200),
                    _now(),
                ),
            )
        self._redirect(f"/{slug}/?submitted=1")

    def _export_csv(self) -> None:
        if not ADMIN_TOKEN or self.headers.get("X-Admin-Token") != ADMIN_TOKEN:
            self.send_error(HTTPStatus.UNAUTHORIZED)
            return
        with _connect() as conn:
            rows = conn.execute(
                "SELECT * FROM revenue_test_leads ORDER BY created_at DESC"
            ).fetchall()
        output = io.StringIO()
        fieldnames = [
            "id", "experiment", "email", "company", "role", "geography",
            "price_intent", "request_type", "notes", "created_at",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))
        body = output.getvalue().encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", 'attachment; filename="revenue-test-leads.csv"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, fragment: str) -> None:
        body = (
            "<!doctype html><meta charset='utf-8'><title>Revenue tests</title>"
            "<style>body{font:17px system-ui;max-width:760px;margin:60px auto;padding:0 20px;line-height:1.5}a{color:#1455d9}</style>"
            + fragment
        ).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.end_headers()

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[{_now()}] {self.address_string()} {fmt % args}")


def main() -> None:
    _connect().close()
    host = os.environ.get("DSF_EXPERIMENT_HOST", "127.0.0.1")
    port = int(os.environ.get("DSF_EXPERIMENT_PORT", "8788"))
    print(f"Revenue tests: http://{host}:{port}/")
    print(f"Lead database: {DB_PATH}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
