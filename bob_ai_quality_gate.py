"""Read-only repair-PR evidence gate. Does not deploy, run LLMs, or change issues.

Only PRs with an explicit BOB-<issue-number>-<known-code> in their body
must meet this extra gate. Untagged ordinary PRs keep the existing Bob CI.
"""
import json
import os
import re
import sys
from urllib.request import Request, urlopen

from bob_issue_watchdog import CODES, issue_title

REPO = "ichrob/gold-dashboard1"
CASE = re.compile(r"(?<![A-Za-z0-9])BOB-([1-9][0-9]{0,7})-([a-z][a-z0-9-]{2,60})(?![a-z0-9-])")
TEST = re.compile(r"(?:^|/)test_[A-Za-z0-9_.-]+\.(?:py|js|cjs)$")


def api(path, token, opener=urlopen):
    if not re.fullmatch(r"/(?:pulls|issues)/[1-9]\d{0,7}(?:/files\?per_page=100)?", path):
        raise ValueError("invalid-path")
    request = Request("https://api.github.com/repos/" + REPO + path, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "User-Agent": "Bob-repair-evidence-gate/1"})
    with opener(request, timeout=20) as response:
        raw = response.read(200001)
    if len(raw) > 200000:
        raise ValueError("response-too-large")
    return json.loads(raw)


def inspect(pr, issue, files):
    if not isinstance(pr, dict) or pr.get("base", {}).get("repo", {}).get("full_name") != REPO:
        raise ValueError("foreign-base")
    body = pr.get("body") or ""
    if not isinstance(body, str):
        raise ValueError("invalid-pr-body")
    markers = CASE.findall(body[:10000])
    if not markers:
        return "ordinary-pr"
    # One repair issue per PR, to keep clear evidence mapping.
    if len(markers) != 1 or len(set(markers)) != 1:
        raise ValueError("ambiguous-repair-case")
    n, code = markers[0]
    if code not in CODES or not isinstance(issue, dict) or issue.get("number") != int(n):
        raise ValueError("unknown-repair-issue")
    if issue.get("title") != issue_title(code):
        raise ValueError("mismatched-case")
    if not isinstance(files, list) or not files or len(files) >= 100:
        raise ValueError("incomplete-pr-files")
    if not any(isinstance(x, dict) and isinstance(x.get("filename"), str)
               and TEST.search(x["filename"]) for x in files):
        raise ValueError("repair-missing-regression-test")
    return "repair-evidence-present-tests-still-need-to-pass"


def check(*, token, pr_number, reader=api):
    if not token or type(pr_number) is not int or not 1 <= pr_number <= 99999999:
        raise ValueError("bad-configuration")
    pr = reader("/pulls/" + str(pr_number), token)
    if not isinstance(pr, dict):
        raise ValueError("invalid-pr")
    body = pr.get("body") or ""
    if not isinstance(body, str):
        raise ValueError("invalid-body")
    found = CASE.findall(body[:10000])
    if not found:
        return "ordinary-pr"
    if len(found) != 1:
        raise ValueError("ambiguous-repair-case")
    n, code = found[0]
    if code not in CODES:
        raise ValueError("unknown-code")
    issue = reader("/issues/" + n, token)
    files = reader("/pulls/" + str(pr_number) + "/files?per_page=100", token)
    return inspect(pr, issue, files)


def main():
    try:
        number = int(os.environ.get("BOB_PR_NUMBER", "0"))
        result = check(token=os.environ.get("GITHUB_TOKEN"), pr_number=number)
        print("Bob repair evidence gate: " + result)
    except Exception:
        print("Bob repair evidence gate blocked: case/test evidence unavailable.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
