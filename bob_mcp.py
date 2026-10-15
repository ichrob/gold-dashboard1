"""Minimal read-only MCP transport for Bob's private product-audit report.

Uses the existing authenticated push service's DB connection, not a public DB
port, browser cookies, broker credentials or GitHub issues. No write tools.
"""
import hashlib
import hmac
import json
import re

PROTOCOL = "2025-03-26"
TOKEN_CONTEXT = b"bob-chatgpt-product-audit-readonly-v1"
_MAX_RESULT_BYTES = 200_000
_TOOL_NAMES = ("bob_product_audit", "bob_product_gaps")


def read_token(service_secret):
    if not isinstance(service_secret, str) or len(service_secret) < 24:
        return None
    return "bob_ro_" + hmac.new(service_secret.encode(), TOKEN_CONTEXT, hashlib.sha256).hexdigest()


def authorized(authorization, service_secret):
    expected = read_token(service_secret)
    if not expected or not isinstance(authorization, str) or not authorization.startswith("Bearer "):
        return False
    candidate = authorization[7:]
    return len(candidate) == len(expected) and hmac.compare_digest(candidate, expected)


def tool_definitions():
    return [
        {
            "name": "bob_product_audit",
            "description": "Read the current private DEGIRO screenshot product audit; contains exact ISINs, missing proof codes, issuer sources and original timestamps. Read-only, never an order or trading permission.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
        },
        {
            "name": "bob_product_gaps",
            "description": "Summarize missing product proof fields by ISIN with original audit status and source; never claim freshness or trade approval.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "annotations": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
        },
    ]


def gaps(report):
    if not isinstance(report, dict):
        return {"status": "unavailable", "total": None, "items": []}
    items = []
    for product in report.get("items", [])[:12]:
        if not isinstance(product, dict):
            continue
        items.append({k: product.get(k) for k in (
            "isin", "direction", "state", "missing", "messages", "source",
            "quoteSourceAt", "leverageSourceAt", "needsKiHelp",
            "autoRecovery", "tradeApproved", "issuerVenue", "venueAction")})
    return {k: report.get(k) for k in (
        "status", "lastCheckedAt", "listUploadedAt", "total", "incomplete",
        "needsHelp", "terminated", "readOnly", "degiroConnected")} | {"items": items}


def error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id,
            "error": {"code": code, "message": message}}


def handle(request, report_reader):
    """Return (HTTP status, JSON-RPC result). Only tool calls read the database."""
    if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
        return 400, error(None, -32600, "Invalid Request")
    method = request.get("method")
    rid = request.get("id")
    if type(rid) not in (str, int) and rid is not None:
        return 400, error(None, -32600, "Invalid Request")
    if method == "notifications/initialized" and "id" not in request:
        return 202, None
    if "id" not in request:
        return 400, error(None, -32600, "Invalid Request")
    if method == "initialize":
        return 200, {"jsonrpc":"2.0","id":rid,"result":{
            "protocolVersion":PROTOCOL,
            "capabilities":{"tools":{"listChanged":False}},
            "serverInfo":{"name":"bob-private-audit","version":"1.0.0"}}}
    if method == "ping":
        return 200, {"jsonrpc":"2.0","id":rid,"result":{}}
    if method == "tools/list":
        return 200, {"jsonrpc":"2.0","id":rid,"result":{"tools":tool_definitions()}}
    if method != "tools/call":
        return 200, error(rid, -32601, "Method not found")
    params = request.get("params")
    if not isinstance(params, dict) or params.get("name") not in _TOOL_NAMES or params.get("arguments", {}) != {}:
        return 200, error(rid, -32602, "Invalid tool arguments")
    report = report_reader()
    data = report if params["name"] == "bob_product_audit" else gaps(report)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if len(payload.encode("utf-8")) > _MAX_RESULT_BYTES:
        return 200, {"jsonrpc":"2.0","id":rid,"result":{"content":[
            {"type":"text","text":"Private report too large; use Bob's authenticated app."}],
            "isError":True}}
    return 200, {"jsonrpc":"2.0","id":rid,"result":{"content":[{"type":"text","text":payload}],
        "isError":False}}
