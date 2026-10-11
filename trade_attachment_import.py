"""Bounded AgentMail PDF attachment retrieval for DEGIRO email staging.

This is untrusted external material. It is never persisted or executed: only
sanitized results of the existing strict trade_document_import parser survive.
"""
import io
import json
import os
from urllib.parse import quote, urlsplit
from urllib.request import build_opener, HTTPSHandler, HTTPRedirectHandler, Request
import trade_document_import

INBOX = "bob-degiro@agentmail.to"
API_HOST = "api.agentmail.to"
MAX_PDF_SIZE = 3 * 1024 * 1024
MAX_TEXT_SIZE = 160 * 1024
MAX_ATTACHMENTS = 3
MAX_MAIL_ID = 250


class FetchError(Exception):
    """Transient/unconfigured attachment failure. Do not acknowledge silently."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise FetchError("unexpected attachment redirect")


def safe_signed_url(url):
    """Block SSRF, localhost, untrusted ports and redirect abuse."""
    if not isinstance(url, str) or len(url) > 4096:
        raise FetchError("invalid attachment URL")
    try:
        v = urlsplit(url)
        host = (v.hostname or "").lower()
        if (v.scheme != "https" or v.username or v.password or v.port not in (None, 443)
                or v.fragment or not host):
            raise FetchError("invalid attachment URL")
        trusted = (host == "storage.googleapis.com"
                   or host.endswith(".cloudfront.net")
                   or host.endswith(".amazonaws.com")
                   or host.endswith(".agentmail.to")
                   or host.endswith(".agentmail.cc")
                   or host.endswith(".r2.dev"))
        if not trusted:
            raise FetchError("untrusted attachment host")
    except ValueError:
        raise FetchError("invalid attachment URL") from None
    return url


def http_get(url, headers=None, limit=MAX_TEXT_SIZE, timeout=5):
    opener = build_opener(HTTPSHandler(), NoRedirect())
    request = Request(url, headers=headers or {"Accept": "application/json"})
    try:
        with opener.open(request, timeout=timeout) as response:
            data = response.read(limit + 1)
    except Exception as exc:
        raise FetchError("attachment request failed") from exc
    if len(data) > limit:
        raise FetchError("attachment exceeds size limit")
    return data


def pdf_text(pdf_bytes):
    """Local best-effort extraction; AgentMail's text_url is preferred."""
    if not pdf_bytes.startswith(b"%PDF-"):
        raise FetchError("invalid PDF magic")
    try:
        from pypdf import PdfReader  # Optional fallback when installed.
        reader = PdfReader(io.BytesIO(pdf_bytes), strict=True)
        if reader.is_encrypted or not 0 < len(reader.pages) <= 8:
            raise FetchError("encrypted or oversized PDF")
        result = "\n".join((p.extract_text() or "") for p in reader.pages)
        return result[:MAX_TEXT_SIZE] if result else None
    except FetchError:
        raise
    except Exception:
        return None


def fetch_pdf_confirmation(message, api_key, get=http_get):
    """Fetch PDF via AgentMail auth metadata + expiring signed CDN URLs.

    Requires a trusted, verified webhook and exact mailbox/sender checks at
    the caller. No arbitrary webhook-provided URLs are followed.
    """
    if not isinstance(message, dict) or message.get("inbox_id") != INBOX:
        return {"status": "incomplete", "reason": "PDF nicht Bobs Postfach zugeordnet"}
    mid = message.get("message_id")
    if not isinstance(mid, str) or not 1 <= len(mid) <= MAX_MAIL_ID:
        return {"status": "incomplete", "reason": "AgentMail-Nachrichtenkennung fehlt"}
    attachments = message.get("attachments") or []
    if not isinstance(attachments, list) or len(attachments) > 30:
        return {"status": "incomplete", "reason": "Ungültige Anhänge"}
    candidates = []
    for a in attachments:
        if not isinstance(a, dict):
            return {"status": "incomplete", "reason": "Ungültige Anhänge"}
        filename = str(a.get("filename") or "")
        content_type = str(a.get("content_type") or "").lower()
        if not (filename.lower().endswith(".pdf") or content_type == "application/pdf"):
            continue
        size = a.get("size")
        aid = a.get("attachment_id")
        if (type(size) is not int or not 0 < size <= MAX_PDF_SIZE
                or not isinstance(aid, str) or not 1 <= len(aid) <= MAX_MAIL_ID
                or content_type not in ("application/pdf", "application/octet-stream", "")
                or (filename and not filename.lower().endswith(".pdf"))):
            return {"status": "incomplete", "reason": "PDF-Typ oder PDF-Größe unzulässig"}
        candidates.append(a)
    if not candidates:
        return None
    if len(candidates) > MAX_ATTACHMENTS:
        return {"status": "incomplete", "reason": "Zu viele PDF-Anhänge"}
    if not api_key or len(api_key) < 12:
        raise FetchError("AgentMail PDF API access is not configured")

    parsed = []
    for a in candidates:
        aid = a["attachment_id"]
        endpoint = (f"https://{API_HOST}/v0/inboxes/"
                    f"{quote(INBOX,safe='')}/messages/{quote(mid,safe='')}"
                    f"/attachments/{quote(aid,safe='')}")
        body = get(endpoint,
                   {"Authorization": "Bearer " + api_key, "Accept": "application/json"},
                   limit=8192, timeout=5)
        try:
            info = json.loads(body)
        except (ValueError, UnicodeDecodeError) as exc:
            raise FetchError("invalid AgentMail metadata") from exc
        if not isinstance(info, dict) or info.get("attachment_id") != aid:
            raise FetchError("attachment identity mismatch")
        download_url = safe_signed_url(info.get("download_url"))
        raw = get(download_url, {"Accept": "application/pdf"},
                  limit=MAX_PDF_SIZE, timeout=8)
        if not raw.startswith(b"%PDF-"):
            raise FetchError("attachment is not a PDF")
        # If available, use AgentMail's own parsed text for exact table cells.
        # Otherwise attempt the optional local extractor without guessing.
        text = None
        if info.get("text_url"):
            text_url = safe_signed_url(info["text_url"])
            raw_text = get(text_url, {"Accept": "text/plain"},
                           limit=MAX_TEXT_SIZE, timeout=5)
            try:
                text = raw_text.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise FetchError("PDF text encoding unsupported") from exc
        if not text:
            text = pdf_text(raw)
        if not text:
            parsed.append({"status": "incomplete", "reason": "PDF-Text nicht lesbar"})
        else:
            parsed.append(trade_document_import.parse_document_text(text))
    accepted = [x for x in parsed if x.get("status") == "pending-review"]
    if len(accepted) == 1 and len(parsed) == 1:
        result = dict(accepted[0])
        result["attachmentCount"] = 1
        result["sourceKind"] = "AgentMail-DEGIRO-PDF"
        result["reason"] = "Automatisch gelesener PDF-Anhang – nur zur Prüfung, keine aktive Position"
        return result
    if not accepted and len(parsed) == 1:
        return parsed[0]
    return {"status": "incomplete", "reason": "Mehrere/uneindeutige PDF-Handelsbelege"}


def enrich_event(event, record, allowed_sender, api_key, get=http_get):
    """Only fetch for a verified allowed forwarder on the correct inbox."""
    if not isinstance(event, dict) or event.get("event_type") != "message.received":
        return record
    message = event.get("message")
    if not isinstance(message, dict) or message.get("inbox_id") != INBOX:
        return record
    # Reuse the production sender/recipient check; any rejection is terminal.
    import trade_email_import
    allowed = trade_email_import.import_event(event, allowed_sender)
    if allowed["status"] in ("sender-unconfirmed",):
        return allowed
    if allowed["status"] == "ignored" and allowed.get("reason") != "Keine DEGIRO-Bestätigung":
        return allowed
    result = fetch_pdf_confirmation(message, api_key, get=get)
    return result if result is not None else record
