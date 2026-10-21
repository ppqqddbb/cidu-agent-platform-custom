#!/usr/bin/env python
"""生成 external_app_runtime 使用的 context_token（HS256）。"""

from __future__ import annotations

import argparse
import json
import time
import uuid


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate HS256 context_token for external_app_runtime.")
    parser.add_argument("--secret", required=True, help="EXTERNAL_APP_CONTEXT_TOKEN_SECRET")
    parser.add_argument("--tenant-id", required=True, help="tenant_id claim")
    parser.add_argument("--user-id", required=True, help="sub claim")
    parser.add_argument(
        "--capabilities",
        default="",
        help="Comma separated capabilities, e.g. crm.order.read,crm.customer.read",
    )
    parser.add_argument("--issuer", default="", help="iss claim (optional)")
    parser.add_argument("--audience", default="", help="aud claim (optional)")
    parser.add_argument("--ttl-seconds", type=int, default=600, help="Token ttl seconds")
    parser.add_argument("--trace-id", default="", help="trace_id claim (optional)")
    args = parser.parse_args()

    try:
        import jwt  # type: ignore
    except Exception as ex:  # pragma: no cover
        raise SystemExit("missing dependency: pyjwt, try `uv run --project api pip install pyjwt`") from ex

    now = int(time.time())
    capabilities = [item.strip() for item in args.capabilities.split(",") if item.strip()]
    trace_id = args.trace_id.strip() or f"ctx-{uuid.uuid4().hex[:12]}"

    payload: dict[str, object] = {
        "sub": args.user_id,
        "tenant_id": args.tenant_id,
        "capabilities": capabilities,
        "trace_id": trace_id,
        "exp": now + max(60, args.ttl_seconds),
    }
    if args.issuer.strip():
        payload["iss"] = args.issuer.strip()
    if args.audience.strip():
        payload["aud"] = args.audience.strip()

    token = jwt.encode(payload, args.secret, algorithm="HS256")
    print(token)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

