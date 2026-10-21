"""Local callback server used for external resolve integration validation.

This script is intentionally simple and deterministic for docker-based smoke tests.
It accepts POST /resolve and returns tenant-scoped capability snapshots.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

LOG_FILE = "/tmp/external_resolve_callback.log"
API_KEY = "external-resolve-callback-key"
LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 19091


def append_log(message: str) -> None:
    with open(LOG_FILE, "a", encoding="utf-8") as file:
        file.write(f"{datetime.now(timezone.utc).isoformat()} {message}\n")


class ResolveHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/resolve":
            self.send_response(404)
            self.end_headers()
            return

        authorization = self.headers.get("Authorization", "")
        if authorization != f"Bearer {API_KEY}":
            append_log("reject unauthorized request")
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"message":"unauthorized"}')
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_payload = self.rfile.read(content_length)
        payload = json.loads(raw_payload or b"{}")

        external_tenant_id = str(payload.get("external_tenant_id", ""))
        external_user_id = str(payload.get("external_user_id", ""))
        expires_at = (datetime.now(timezone.utc) + timedelta(minutes=30)).replace(microsecond=0)
        expires_at_iso = expires_at.isoformat().replace("+00:00", "Z")

        if external_tenant_id.endswith("tenant-b"):
            response_payload = {
                "source_version": 2026040902,
                "membership_active": True,
                "display_role": "normal",
                "capabilities": ["workspace.view", "workspace.switch"],
                "expires_at": expires_at_iso,
                "management_mode": "external_managed",
                "allow_local_member_override": True,
            }
        else:
            response_payload = {
                "source_version": 2026040901,
                "membership_active": True,
                "display_role": "admin",
                "capabilities": [
                    "workspace.view",
                    "workspace.switch",
                    "workspace.member.list",
                    "workspace.member.invite",
                ],
                "expires_at": expires_at_iso,
                "management_mode": "external_managed",
                "allow_local_member_override": False,
            }

        append_log(
            f"resolve hit tenant={external_tenant_id} user={external_user_id} "
            f"source_version={response_payload['source_version']}"
        )
        body = json.dumps(response_payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


if __name__ == "__main__":
    append_log(f"starting external resolve callback server on {LISTEN_HOST}:{LISTEN_PORT}")
    HTTPServer((LISTEN_HOST, LISTEN_PORT), ResolveHandler).serve_forever()
