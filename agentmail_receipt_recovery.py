"""Bounded read-only recovery of DEGIRO confirmations already in AgentMail.

Webhook remains primary. Never send or forward emails, place broker orders,
persist raw bodies or read another inbox. HTTP requests are restricted to
AgentMail's exact v0 API endpoint and the configured private Bob push service.
"""
import datetime as dt
import json
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import trade_email_import

INBOX = "bob-degiro@agentmail.to"
BASE = "https://api.agentmail.to/v0/inboxes/" + quote(INBOX, safe="") + "/messages"
MAX_LIST = 30
MAX_MESSAGE_BYTES = 130000


def api_json(url, api_key, byte_limit):
    if not isinstance(url,str) or not url.startswith(BASE) or len(url)>1200:
        raise ValueError("AgentMail-Pfad nicht erlaubt")
    request=Request(url,headers={"Authorization":"Bearer "+api_key,
                                 "Accept":"application/json"},method="GET")
    with urlopen(request, timeout=8) as response:
        content=response.read(byte_limit+1)
    if len(content)>byte_limit:
        raise ValueError("AgentMail-Antwort zu groß")
    result=json.loads(content)
    if not isinstance(result,dict):
        raise ValueError("AgentMail-JSON ungültig")
    return result


def recover(api_key, allowed_sender, fetch=api_json, now=None):
    """Return only sanitized, source-labelled receipts, not email bodies."""
    if not api_key or len(api_key)<12 or not allowed_sender:
        return []
    now=now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        raise ValueError("UTC-Zeitbezug fehlt")
    after=(now-dt.timedelta(days=7)).isoformat().replace("+00:00","Z")
    url=BASE+"?"+urlencode({"limit":MAX_LIST,"after":after})
    page=fetch(url,api_key,70000)
    messages=page.get("messages")
    if not isinstance(messages,list) or len(messages)>MAX_LIST:
        raise ValueError("AgentMail-Postfachliste fehlerhaft")
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
        if not str(item.get("subject") or "").lower().startswith(("degiro", "wg: degiro","wg: degiro")):
            continue
        detail=fetch(BASE+"/"+quote(mid,safe=""),api_key,MAX_MESSAGE_BYTES)
        if detail.get("message_id")!=mid or detail.get("inbox_id")!=INBOX:
            continue
        event={"type":"event","event_type":"message.received",
               "message":{**detail,"inbox_id":INBOX}}
        record=trade_email_import.import_event(event,allowed_sender)
        if record.get("status")=="pending-review":
            outputs.append({"messageId":mid,"record":record})
    return outputs


def submit(records,push_base,push_token):
    """Signed Bob internal read-only import, idempotent in the push database."""
    if not (push_base and push_token):
        return 0
    base=push_base.rstrip("/")
    if not base.startswith("https://"):
        raise ValueError("HTTPS für internen Belegimport erforderlich")
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
