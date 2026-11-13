"""Bounded read-only recovery of DEGIRO confirmations already in AgentMail.

Webhook remains primary. Never send or forward emails, place broker orders,
persist raw bodies or read another inbox. HTTP requests are restricted to
AgentMail's exact v0 API endpoint and the configured private Bob push service.
"""
import datetime as dt
import json
import time
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import trade_email_import
import trade_attachment_import

INBOX = "bob-degiro@agentmail.to"
BASE = "https://api.agentmail.to/v0/inboxes/" + quote(INBOX, safe="") + "/messages"
MAX_LIST = 30
PAGE_SIZE = 5
MAX_PAGES = 6
MAX_MESSAGE_BYTES = 130000
_message_cache = {}


def _read_error(code, byte_limit, observed_bytes):
    # Fixed diagnostic fields only: no URL, message ID, body or exception text.
    print("BOB_EMAIL_RECOVERY_READ code="+code+" cap="+str(byte_limit)+
          " observedBytes="+str(observed_bytes), flush=True)
    return ValueError("AgentMail-Antwort nicht lesbar")


def api_json(url, api_key, byte_limit):
    if not isinstance(url,str) or not url.startswith(BASE) or len(url)>1200:
        raise ValueError("AgentMail-Pfad nicht erlaubt")
    request=Request(url,headers={"Authorization":"Bearer "+api_key,
                                 "Accept":"application/json"},method="GET")
    with urlopen(request, timeout=8) as response:
        content=response.read(byte_limit+1)
    if len(content)>byte_limit:
        raise _read_error("response-size-limit", byte_limit, len(content))
    try:
        result=json.loads(content)
    except (ValueError, UnicodeDecodeError):
        raise _read_error("invalid-json", byte_limit, len(content)) from None
    if not isinstance(result,dict):
        raise _read_error("invalid-json-shape", byte_limit, len(content))
    return result


def recover(api_key, allowed_sender, fetch=api_json, now=None, lookback_days=7):
    """Return only sanitized, source-labelled receipts, not email bodies."""
    if not api_key or len(api_key)<12 or not allowed_sender:
        return []
    now=now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        raise ValueError("UTC-Zeitbezug fehlt")
    if type(lookback_days) is not int or not 1 <= lookback_days <= 45:
        raise ValueError("Beleg-Zeitfenster muss zwischen 1 und 45 Tagen liegen")
    after=(now-dt.timedelta(days=lookback_days)).isoformat().replace("+00:00","Z")
    # A 30-message archive response exceeded the production 70 KB cap.
    # Keep that cap, but read small pages using the provider's opaque cursor.
    # Both total messages and request count remain bounded.
    messages=[]
    page_token=None
    seen_tokens=set()
    for _ in range(MAX_PAGES):
        params={"limit": min(PAGE_SIZE, MAX_LIST-len(messages)), "after": after}
        if page_token:
            params["page_token"]=page_token
        page=fetch(BASE+"?"+urlencode(params),api_key,70000)
        batch=page.get("messages")
        if not isinstance(batch,list) or len(batch)>params["limit"]:
            raise _read_error("invalid-message-list", params["limit"],
                              len(batch) if isinstance(batch,list) else 0)
        messages.extend(batch)
        page_token=page.get("next_page_token")
        if not page_token:
            break
        if (not isinstance(page_token,str) or len(page_token)>500
                or page_token in seen_tokens):
            raise _read_error("invalid-page-token", MAX_PAGES, len(seen_tokens))
        seen_tokens.add(page_token)
        if len(messages)>=MAX_LIST:
            break
    if page_token:
        # Do not imply that a bounded archive window covered the entire inbox.
        print("BOB_EMAIL_RECOVERY_READ code=archive-window-limited", flush=True)
    outputs=[]
    seen=set()
    for item in messages:
        if not isinstance(item,dict) or item.get("inbox_id")!=INBOX:
            continue
        mid=item.get("message_id")
        if not isinstance(mid,str) or not 1<=len(mid)<=200 or mid in seen:
            continue
        seen.add(mid)
        if "received" not in (item.get("labels") or []):
            continue
        attachments=item.get("attachments") or []
        has_pdf=isinstance(attachments,list) and any(
            isinstance(a,dict) and (str(a.get("filename") or "").lower().endswith(".pdf")
            or a.get("content_type")=="application/pdf") for a in attachments)
        if not has_pdf and not str(item.get("subject") or "").lower().startswith(("degiro", "wg: degiro","wg: degiro")):
            continue
        cache_key=(mid,item.get('updated_at'),item.get('size'))
        cached=_message_cache.get(cache_key) if fetch is api_json else None
        if cached and time.monotonic()-cached[0]<300:
            outputs.append(cached[1]);continue
        detail=fetch(BASE+"/"+quote(mid,safe=""),api_key,MAX_MESSAGE_BYTES)
        if detail.get("message_id")!=mid or detail.get("inbox_id")!=INBOX:
            continue
        event={"type":"event","event_type":"message.received",
               "message":{**detail,"inbox_id":INBOX}}
        record=trade_email_import.import_event(event,allowed_sender)
        # Reuse the webhook's bounded, sender-checked PDF path, including
        # historical attachments whose subject does not name the broker.
        record=trade_attachment_import.enrich_event(event,record,allowed_sender,api_key)
        if record.get("status")=="pending-review":
            parsed={"messageId":mid,"record":record}
            outputs.append(parsed)
            if fetch is api_json:
                if len(_message_cache)>60:_message_cache.clear()
                _message_cache[cache_key]=(time.monotonic(),parsed)
    return outputs


def submit(records,push_base,push_token):
    """Signed Bob internal read-only import, idempotent in the push database."""
    if not (push_base and push_token):
        return 0
    base=push_base.rstrip("/")
    if not base.startswith(("https://","http://")):
        base="http://"+base  # Bob's existing Render-private service configuration.
    done=0
    for payload in records:
        data=json.dumps(payload,separators=(",",":")).encode()
        if len(data)>7000:raise ValueError("Belegdaten zu groß")
        request=Request(base+"/email-import/receive",data=data,method="POST",
            headers={"Content-Type":"application/json","X-Bob-Push-Token":push_token})
        with urlopen(request,timeout=10) as response:
            response.read(4096)
        done+=1
    return done
