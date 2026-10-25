import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock
import base64
import json
import bob_problem_mirror as mirror
import bob_issue_watchdog as watchdog
import bob_problems

NOW=datetime(2026,10,25,7,0,tzinfo=timezone.utc)

class TwoWayFeedbackTests(unittest.TestCase):
    def test_review_marker_owner_only_and_not_verified(self):
        from bob_issue_watchdog import issue_title
        sha='a'*40
        row=dict(number=725,title=issue_title('product-quote-evidence-missing'),
                 user={'login':'github-actions[bot]'},
                 body='PRIVATE TEXT\n<!-- BOB_KI_STATUS:testing -->\n'
                      '<!-- BOB_KI_REVIEW:pr=845;sha='+sha+';phase=ci-tested -->')
        result=bob_problems.from_issues([row])['problems'][0]
        self.assertEqual(result['caseId'],'BOB-725-product-quote-evidence-missing')
        self.assertEqual(result['review'],dict(pr=845,commit=sha,phase='ci-tested'))
        self.assertEqual(result['kiStatus'],'testing')
        self.assertNotIn('PRIVATE TEXT',str(result))
        self.assertNotIn('verified',str(result).lower())
        row['user']={'login':'outside-user'}
        self.assertEqual(bob_problems.ki_review(row),None)
        row['user']={'login':'ichrob'}
        row['body']=row['body'].replace('ci-tested','verified')
        self.assertEqual(bob_problems.ki_review(row),None)

    def test_resolutions_strictly_require_two_polls_and_never_product(self):
        current=NOW.isoformat(timespec='seconds')
        examples=[
            dict(number=7,code='scanner-unreachable',verifiedAt=current,proof=mirror.RECOVERY_PROOF),
            dict(number=8,code='product-ko-validity-missing',verifiedAt=current,proof=mirror.RECOVERY_PROOF),
            dict(number=9,code='scanner-degraded',verifiedAt=current,proof='just-an-issue-closure'),
            dict(number=10,code='push-unreachable',verifiedAt=(NOW-timedelta(days=31)).isoformat(),proof=mirror.RECOVERY_PROOF),
            dict(number=11,code='scanner-unreachable',verifiedAt=current,proof=mirror.RECOVERY_PROOF,account='secret'),
            dict(number=12,code='unknown-fault',verifiedAt=current,proof=mirror.RECOVERY_PROOF),
        ]
        accepted=mirror.sanitized_recoveries(examples,now=NOW)
        self.assertEqual([(x['number'],x['code']) for x in accepted],[(7,'scanner-unreachable'),(11,'scanner-unreachable')])
        self.assertNotIn('secret',str(accepted))
        self.assertEqual(mirror.sanitized_recoveries(examples,now=NOW,active_codes={'scanner-unreachable'}),[])

    def test_watchdog_records_only_eligible_confirmed_recoveries(self):
        row=dict(number=23,title=watchdog.issue_title('scanner-unreachable'),
                 state='open')
        def request(method,path,*,token,repo,data=None):
            if method=='GET' and path.startswith('/issues?'):
                return [row]
            if method=='GET' and path.startswith('/search/'):
                return {'items':[row]}
            if method in ('POST','PATCH'):
                return {}
            raise AssertionError((method,path))
        got=[]
        result=watchdog.sync_issue([],token='test',repo='ichrob/gold-dashboard1',
                at=NOW.isoformat(timespec='seconds'),requester=request,
                recovery_codes={'push-unreachable'},verified_resolutions=got)
        self.assertEqual(result,'healthy')
        self.assertEqual(got,[])
        result=watchdog.sync_issue([],token='test',repo='ichrob/gold-dashboard1',
                at=NOW.isoformat(timespec='seconds'),requester=request,
                recovery_codes={'scanner-unreachable'},verified_resolutions=got)
        self.assertEqual(result,'closed-23')
        self.assertEqual(len(got),1)
        self.assertEqual(got[0]['proof'],mirror.RECOVERY_PROOF)

    def test_mirror_publish_preserves_recovery_and_removes_reopened_code(self):
        record=dict(number=27,code='scanner-unreachable',
                    verifiedAt=datetime.now(timezone.utc).isoformat(timespec='seconds'),proof=mirror.RECOVERY_PROOF)
        existing={'version':1,'resolved':[record]}
        calls=[]
        def requester(method,path,*,token,repo,data=None):
            calls.append((method,path,data))
            if method=='GET' and path.startswith('/issues?'):return []
            if method=='GET' and path.startswith('/search/'):return {'items':[]}
            if method=='GET' and path.startswith('/contents/'):
                return {'sha':'hash','content':base64.b64encode(json.dumps(existing).encode()).decode()}
            if method=='PUT' and path.startswith('/contents/'):return {}
            raise AssertionError((method,path))
        # A fresh, authenticated watchdog proof survives a mirror refresh.
        mirror.publish(token='t',repo='ichrob/gold-dashboard1',requester=requester)
        data=[d for method,path,d in calls if method=='PUT'][0]
        published=json.loads(base64.b64decode(data['content']))
        self.assertEqual(published['version'],1)
        self.assertEqual(len(published['resolved']),1)
        self.assertEqual(published['resolved'][0]['number'],27)
        self.assertNotIn('account',published['resolved'][0])

if __name__=='__main__':
    unittest.main()
