"""Regressions for the oversize GitHub issue-index failure blocking self-healing."""
import unittest
from urllib.parse import parse_qs, urlsplit

import bob_issue_watchdog as watcher
import bob_ai_coordination as coordinator


class WatchdogGitHubPages(unittest.TestCase):
    def test_oversized_second_page_restarts_with_small_complete_pages(self):
        # Main list needs four pages at 10-per-page, or seven at 5-per-page.
        # The failed 10-item page must not silently skip earlier issue rows.
        rows=[dict(number=i,title="Other",state="open") for i in range(1,33)]
        search=[dict(number=i,title=watcher.issue_title("paper-unhealthy"),
                     state="open") for i in (2,22,33)]
        requested=[]
        def requester(method,path,*,token,repo):
            self.assertEqual(method,"GET")
            self.assertEqual(repo,"ichrob/gold-dashboard1")
            qs=parse_qs(urlsplit(path).query)
            size=int(qs["per_page"][0]);page=int(qs["page"][0])
            requested.append((path.split("?")[0],size,page))
            if path.startswith("/issues?"):
                if size==10 and page==2:
                    raise ValueError("GitHub response too large")
                return rows[(page-1)*size:page*size]
            if path.startswith("/search/issues?"):
                return dict(total_count=len(search),incomplete_results=False,
                            items=search[(page-1)*size:page*size])
            raise AssertionError("unexpected GitHub path")
        actual=watcher.open_issue_rows(token="test",repo="ichrob/gold-dashboard1",
                                       requester=requester)
        self.assertEqual(set(x["number"] for x in actual),set(range(1,34)))
        self.assertIn(("/issues",5,1),requested)
        self.assertIn(("/issues",5,7),requested)
        self.assertIn(("/search/issues",10,1),requested)
        self.assertEqual(next(x for x in actual if x["number"]==22)["title"],
                         watcher.issue_title("paper-unhealthy"))

    def test_search_size_fallback_and_incomplete_search_fail_closed(self):
        search=[dict(number=i,title="Issue",state="open") for i in range(1,14)]
        def req(method,path,*,token,repo):
            qs=parse_qs(urlsplit(path).query)
            size=int(qs["per_page"][0]);page=int(qs["page"][0])
            if path.startswith("/issues?"):return []
            if size==10:
                raise ValueError("GitHub response too large")
            return dict(total_count=len(search),incomplete_results=False,
                        items=search[(page-1)*size:page*size])
        result=watcher.open_issue_rows(token="x",repo="ichrob/gold-dashboard1",
                                       requester=req)
        self.assertEqual(len(result),13)

        def incomplete(method,path,*,token,repo):
            if path.startswith("/issues?"):return []
            return dict(total_count=1,incomplete_results=True,items=[])
        with self.assertRaisesRegex(ValueError,"unvollständig"):
            watcher.open_issue_rows(token="x",repo="ichrob/gold-dashboard1",
                                   requester=incomplete)

        def short_response(method,path,*,token,repo):
            if path.startswith("/issues?"):return []
            return dict(total_count=4,incomplete_results=False,
                        items=[dict(number=1,title="An issue")])
        with self.assertRaisesRegex(ValueError,"unvollständig"):
            watcher.open_issue_rows(token="x",repo="ichrob/gold-dashboard1",
                                   requester=short_response)

    def test_single_oversize_or_unbounded_search_never_creates_issue(self):
        def too_large(method,path,*,token,repo):
            raise ValueError("GitHub response too large")
        with self.assertRaisesRegex(ValueError,"response too large"):
            watcher.open_issue_rows(token="x",repo="ichrob/gold-dashboard1",
                                   requester=too_large)
        def too_many(method,path,*,token,repo):
            if path.startswith("/issues?"):return []
            return dict(total_count=9999,incomplete_results=False,items=[])
        with self.assertRaisesRegex(ValueError,"zu umfangreich"):
            watcher.open_issue_rows(token="x",repo="ichrob/gold-dashboard1",
                                   requester=too_many)

    def test_hand_off_identifies_real_case_for_independent_review_only(self):
        code="study-original-input-degraded"
        body=coordinator.handoff(code,1550)
        self.assertIn("PR-Kennzeichnung",body)
        self.assertIn("BOB-1550-"+code,body)
        self.assertEqual(body.count("BOB-1550-"+code),1)
        self.assertIn("Ohne echten PR kein Review",body)


if __name__=="__main__":
    unittest.main()
