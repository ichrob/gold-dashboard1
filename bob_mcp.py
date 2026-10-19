"""Minimal read-only MCP transport for Bob's private product-audit report.

Uses a dedicated read-only service credential, or the legacy Bob login before
Passkey enrollment. The service credential is accepted only on POST /mcp.
It does not expose the PostgreSQL port, accept browser cookies, or provide write tools.
"""
import base64
import json
import os
import hmac

PROTOCOL = "2025-03-26"
_MAX_RESULT_BYTES = 200_000
_TOOL_NAMES = ("bob_product_audit", "bob_product_gaps")


def service_authenticated(headers):
    """Independent machine identity: never accepted by the browser login layer."""
    expected=os.environ.get('BOB_MCP_SERVICE_TOKEN','')
    authorization=headers.get('Authorization','')
    if len(expected)<32 or len(authorization)>4096:
        return False
    if authorization.startswith('Bearer '):
        candidate=authorization[7:]
    elif authorization.startswith('Basic '):
        try:
            user,candidate=base64.b64decode(authorization[6:],validate=True).decode().split(':',1)
        except (ValueError,UnicodeError):return False
        if user!='bob-readonly':return False
    else:return False
    return hmac.compare_digest(candidate.encode(),expected.encode())



def tool_definitions(diagnostics=False, products=True):
    result = [
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
    if not products:
        result = []
    if diagnostics:
        result.append({
            "name": "bob_diagnostics",
            "description": "Read operational diagnostics: cached market inputs and timestamps, background workers, paper simulation heartbeat, push monitor counts, research and problem index. Missing or stale observations are not healthy. No orders, mutations, raw logs or credentials.",
            "inputSchema": {"type":"object", "properties":{}, "additionalProperties":False},
            "annotations": {"readOnlyHint":True, "destructiveHint":False, "idempotentHint":True, "openWorldHint":False},
        })
    return result



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


def handle(request, report_reader, diagnostics_reader=None, products=True):
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
        return 200, {"jsonrpc":"2.0","id":rid,"result":{"tools":tool_definitions(diagnostics_reader is not None, products)}}
    if method != "tools/call":
        return 200, error(rid, -32601, "Method not found")
    params = request.get("params")
    if not isinstance(params, dict) or params.get("name") not in [t["name"] for t in tool_definitions(diagnostics_reader is not None, products)] or params.get("arguments", {}) != {}:
        return 200, error(rid, -32602, "Invalid tool arguments")
    if params["name"] == "bob_diagnostics":
        data = diagnostics_reader()
    else:
        report = report_reader()
        data = report if params["name"] == "bob_product_audit" else gaps(report)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if len(payload.encode("utf-8")) > _MAX_RESULT_BYTES:
        return 200, {"jsonrpc":"2.0","id":rid,"result":{"content":[
            {"type":"text","text":"Private report too large; use Bob's authenticated app."}],
            "isError":True}}
    return 200, {"jsonrpc":"2.0","id":rid,"result":{"content":[{"type":"text","text":payload}],
        "isError":False}}
