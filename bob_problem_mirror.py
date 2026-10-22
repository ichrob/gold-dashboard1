"""Public, sanitized problem index built with the watchdog's existing GitHub auth."""
import base64,json
from datetime import datetime,timezone
from urllib.error import HTTPError
from urllib.request import Request,urlopen

BRANCH='bob-status'
PATH='problem-index.json'
URL='https://raw.githubusercontent.com/ichrob/gold-dashboard1/bob-status/problem-index.json'
MAX_AGE=20*60

def publish(*,token,repo,requester=None):
    import bob_issue_watchdog as watchdog
    import bob_problems
    if not token or repo!='ichrob/gold-dashboard1':raise ValueError('Status repository not authorized')
    requester=requester or watchdog.github_request
    rows=watchdog.open_issue_rows(token=token,repo=repo,requester=requester)
    report=bob_problems.from_issues(rows)
    # Only the already allowlisted issue summary. No body, account, quote or log.
    payload=dict(version=1,checkedAt=report['checkedAt'],problems=report['problems'])
    for problem in payload['problems']:
        if problem['code'].startswith('manual-'):problem['message']='Manuelle KI-Hilfeanfrage'
    try:
        previous=requester('GET','/contents/'+PATH+'?ref='+BRANCH,token=token,repo=repo)
    except HTTPError as exc:
        if exc.code!=404:raise
        previous={}
        try:requester('GET','/git/ref/heads/'+BRANCH,token=token,repo=repo)
        except HTTPError as missing:
            if missing.code!=404:raise
            main=requester('GET','/git/ref/heads/main',token=token,repo=repo)
            requester('POST','/git/refs',token=token,repo=repo,data=dict(ref='refs/heads/'+BRANCH,sha=main['object']['sha']))
    data=dict(message='Refresh sanitized Bob problem index',branch=BRANCH,
              content=base64.b64encode(json.dumps(payload,ensure_ascii=False).encode()).decode())
    if previous.get('sha'):data['sha']=previous['sha']
    requester('PUT','/contents/'+PATH,token=token,repo=repo,data=data)
    return len(payload['problems'])

def read(*,opener=urlopen,now=None):
    import bob_problems
    with opener(Request(URL,headers={'User-Agent':'Bob-problem-index/2','Cache-Control':'no-cache'}),timeout=6) as response:
        raw=response.read(200001)
    if len(raw)>200000:raise ValueError('Status snapshot too large')
    data=json.loads(raw)
    if data.get('version')!=1 or not isinstance(data.get('problems'),list) or len(data['problems'])>100:raise ValueError('Status snapshot invalid')
    at=datetime.fromisoformat(data['checkedAt'].replace('Z','+00:00'))
    now=now or datetime.now(timezone.utc)
    if at.tzinfo is None or not -120<=(now-at).total_seconds()<=MAX_AGE:raise ValueError('Status snapshot expired')
    # Rebuild links/titles/status via the existing allowlist. Never trust mirror prose or URLs.
    rows=[]
    for p in data['problems']:
        code=p.get('code');number=p.get('number')
        if code in bob_problems.CODES:title=bob_problems.issue_title(code)
        elif code=='legacy-incident':title=bob_problems.ISSUE_TITLE
        elif code=='manual-'+str(number):title='[Bob KI-Hilfe] '+p.get('message','')
        else:raise ValueError('Status category invalid')
        state=p.get('kiStatus','new')
        if state not in bob_problems.KI_STATUS_LABELS:raise ValueError('Status marker invalid')
        rows.append(dict(number=number,title=title,user={'login':'ichrob'},
            body='<!-- BOB_KI_STATUS:'+state+' -->',created_at=p.get('createdAt'),updated_at=p.get('updatedAt')))
    report=bob_problems.from_issues(rows,now=at)
    report['source']='sanitized-github-watchdog-snapshot'
    return report
