import base64
import copy
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

import bob_problems
import bob_problem_mirror
import repair_flow as flow

NOW = datetime(2026, 11, 11, 16, tzinfo=timezone.utc)
VALUE = dict(owner='chatgpt', acceptedAt='2026-11-11T14:00:00Z',
             progressAt='2026-11-11T14:30:00Z', nextCheckAt='2026-11-11T15:00:00Z', phase='awaiting-live')


class RepairFlowTests(unittest.TestCase):
    def issue(self):
        return dict(number=1572, title='[Bob KI-Hilfe] Wächter prüfen', user={'login':'ichrob'},
                    created_at='2026-11-11T13:00:00Z', updated_at='2026-11-11T14:30:00Z',
                    body='PRIVATE DETAILS\n' + flow.marker(VALUE, now=NOW.timestamp()).strip())

    def test_acknowledgement_survives_private_index_and_mirror_without_prose(self):
        report = bob_problems.from_issues([self.issue()], now=NOW)
        self.assertEqual(report['problems'][0]['repairFlow'], VALUE)
        self.assertNotIn('PRIVATE', str(report))
        payload = dict(version=1, checkedAt=report['checkedAt'], problems=report['problems'])
        response=Mock(); response.read.return_value=json.dumps(payload).encode()
        response.__enter__=Mock(return_value=response); response.__exit__=Mock(return_value=False)
        restored=bob_problem_mirror.read(opener=Mock(return_value=response),now=NOW)
        self.assertEqual(restored['problems'][0]['repairFlow'],VALUE)

    def test_untrusted_ambiguous_malformed_future_or_backdated_claim_not_accepted(self):
        source=self.issue()
        variants=[dict(source,user={'login':'outsider'}),dict(source,body=source['body']*2),
                  dict(source,body=source['body'].replace('phase=awaiting-live','phase=verified')),
                  dict(source,body=source['body'].replace('14:30:00','17:00:00')),
                  dict(source,body=source['body'].replace('14:00:00','12:00:00')),
                  dict(source,body=source['body'].replace('15:00:00','13:00:00')),
                  dict(source,body=source['body'].replace('2026-11-11','2026-99-11'))]
        for row in variants:
            with self.subTest(row=row):
                self.assertTrue(all('repairFlow' not in p for p in
                    bob_problems.from_issues([row],now=NOW)['problems']))

    def test_missing_claim_not_inferred_from_testing_or_recent_issue_edit(self):
        row=self.issue(); row['body']='<!-- BOB_KI_STATUS:testing -->'
        index=bob_problems.from_issues([row],now=NOW)
        result=flow.summary(index,now=NOW.timestamp())
        self.assertEqual(result['declaredAccepted'],0)
        self.assertEqual(result['missingAcknowledgement'],1)
        self.assertIsNone(result['verifiedRepairRatePct'])

    def test_overdue_requires_fresh_index_and_does_not_claim_success(self):
        index=bob_problems.from_issues([self.issue()],now=NOW)
        before=copy.deepcopy(index)
        result=flow.summary(index,now=NOW.timestamp())
        self.assertEqual(result['overdueIssueNumbers'],[1572])
        self.assertEqual(result['oldestAcceptedAgeSeconds'],7200)
        self.assertIsNone(result['verifiedRepairDurationSeconds'])
        self.assertEqual(index,before)
        result=flow.summary(index,now=NOW.timestamp()+1201)
        self.assertEqual(result['status'],'stale')
        self.assertIsNone(result['overdueCount'])
        self.assertEqual(result['overdueIssueNumbers'],[])

    def test_unavailable_and_truncated_not_complete_or_zero_success(self):
        self.assertIsNone(flow.summary({},now=NOW.timestamp())['sampledCases'])
        index=bob_problems.from_issues([self.issue()],now=NOW); index['count']=1000
        self.assertTrue(flow.summary(index,now=NOW.timestamp())['truncated'])
        value=dict(VALUE,token='PRIVATE')
        self.assertEqual(flow.sanitize(value,now=NOW.timestamp()),VALUE)


if __name__ == '__main__':
    unittest.main()
