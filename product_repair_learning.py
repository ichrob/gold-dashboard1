"""Private bounded repair memory. Observations never authorize trading."""
import copy
import threading
import time
from datetime import datetime

_LOCK=threading.Lock()
_PLANS={}
GROUPS={
 'quotes':({'quote','quote-time','market-status'},'Datierte Geld-/Briefkurse erneut aus zugelassenen Quellen prüfen'),
 'leverage':({'leverage','leverage-time'},'Originalhebel oder vorhandene Hebelberechnung mit aktuellen Eingaben prüfen'),
 'terms':({'ko','ko-time','strike','ratio','maturity'},'Produktbedingungen aus zugelassenen Quellen erneut abgleichen'),
 'identity':({'identity','list-identity','direction','underlying','currency'},'ISIN, Richtung, Basiswert und Währung abgleichen; Widersprüche nicht überschreiben'),
}
EXCLUDED={'terminated','factor','future','venue','market-closed'}


def clock(value):
 try:
  d=datetime.fromisoformat(str(value).replace('Z','+00:00'))
  return d.timestamp()*1000 if d.tzinfo else None
 except (ValueError,TypeError):return None


def family(source):
 text=str(source or '').lower()
 return next((s for s in ('comdirect','swissquote') if s in text),None)


def update(item, previous, now):
 old=previous.get('repairLearning') or {}
 memory=copy.deepcopy(old.get('sourceSuccesses') or {})
 memory={s:max(0,min(100,int(memory.get(s,0)))) for s in ('comdirect','swissquote')}
 # Penalize a newly failed source once per incident, not on every cached audit.
 failed={family(e.get('stage')) for e in item.get('sourceRecovery',[]) if isinstance(e,dict) and e.get('state') in ('failed','waiting')}
 failed.discard(None)
 before_failed=set(old.get('failedSources') or [])
 for source in failed-before_failed:memory[source]=max(0,memory[source]-1)
 pending=copy.deepcopy(old.get('incidents') or {})
 history=copy.deepcopy(old.get('history') or [])[-12:]
 missing=set(item.get('missing') or [])
 if item.get('state')=='terminated' or missing & EXCLUDED:
  return dict(status='excluded',failedSources=sorted(failed),incidents={},sourceSuccesses=memory,history=history,
              note='Ausschluss oder Handelsplatznachweis; keine automatische Umgehung.')
 for group,(codes,action) in GROUPS.items():
  gaps=sorted(missing & codes)
  if gaps:
   before=pending.get(group) or {}
   pending[group]=dict(state='repairing',missing=gaps,action=action,
                       firstAt=before.get('firstAt',now),checks=0,lastProof=None,goodSince=None)
   continue
  incident=pending.get(group)
  if not incident:continue
  proof=clock(item.get('quoteSourceAt')) if group in ('quotes','identity') else clock(item.get('leverageSourceAt') or (item.get('leverageObservation') or {}).get('at')) if group=='leverage' else None
  if group=='terms':
   observations=(item.get('fieldRecovery') or {}).get('observations') or {}
   dates=[clock(v.get('reviewedAt')) for v in observations.values() if isinstance(v,dict)]
   valid=[d for d in dates if d is not None and 0<=now-d<=8*3600000]
   proof=max(valid) if valid else None
  # Only independently dated, advancing evidence can confirm a repair.
  # Conditions without such evidence remain explicitly awaiting verification.
  if proof is None or not 0<=now-proof<=(8*3600000 if group=='terms' else 90000):
   incident.update(state='awaiting-evidence',checks=0,lastProof=None,goodSince=None)
   continue
  source=family(item.get('dataQuoteSource'))
  if incident.get('source')!=source:
   incident.update(checks=0,lastProof=None,goodSince=None)
  incident['source']=source
  last=incident.get('lastProof')
  if last is None or proof>last or (group=='terms' and now>incident.get('lastCheckAt',now)):
   incident['checks']=incident.get('checks',0)+1
   incident['lastProof']=proof
   incident['lastCheckAt']=now
   if incident.get('goodSince') is None:incident['goodSince']=now
  incident['state']='verifying'
  if incident['checks']>=2 and now-incident['goodSince']>=20000:
   if source and group=='quotes':memory[source]=min(100,memory[source]+1)
   history.append(dict(group=group,at=now,source=source,state='verified',action=incident['action']))
   pending.pop(group)
 return dict(failedSources=sorted(failed),status='repairing' if any(i['state']=='repairing' for i in pending.values()) else 'verifying' if pending else 'ready',
             incidents=pending,sourceSuccesses=memory,history=history[-12:],
             note='Erfolgreiche Nachweisquelle gemerkt; kein Beleg, dass der Reparaturversuch allein die Ursache behoben hat.')


def install(report, now=None):
 global _PLANS
 now=time.time()*1000 if now is None else now
 checked=clock(report.get('lastCheckedAt'))
 # A stale report can retain history, but cannot activate learned priorities.
 with _LOCK:
  _PLANS={i['isin']:copy.deepcopy(i.get('repairLearning') or {}) for i in report.get('items',[])[:12]
          if i.get('isin')} if report.get('status')=='ok' and checked is not None and 0<=now-checked<=180000 else {}


def source_order(isin):
 with _LOCK:scores=(_PLANS.get(isin) or {}).get('sourceSuccesses') or {}
 return sorted(('comdirect','swissquote'),key=lambda source:-scores.get(source,0))


def request_order(isins, active, requested, now):
 """Prioritize overdue/active products, then identified repairs, without starvation.
 No extra requests: the existing four slots and 30-second minimum still apply.
 """
 with _LOCK:
  repair={isin for isin,plan in _PLANS.items() if plan.get('incidents') and plan.get('status')!='excluded'}
 return sorted(isins,key=lambda i:(0 if now-requested.get(i,0)>=90000 else 1,
                                  requested.get(i,0) if now-requested.get(i,0)>=90000 else 0,
                                  i not in active, i not in repair, requested.get(i,0)))
