"""Owner-triggered Gemini DRAFT PR: untrusted public patch as inert text only."""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.error import HTTPError, URLError

from ai_peer_review import REPO, request_json
from gemini_mobile_developer import (
    BASE, NUMBER, PRIVATE_CONTENT, checked_path, enabled,
    model_proposal, public_file, public_issue,
)

STAGE = "preflight"
MAX_PATCH_BYTES = 5000


def strict_patch(reply, target):
    target = checked_path(target)
    if (not isinstance(reply, str) or not reply or len(reply) > 5500
            or PRIVATE_CONTENT.search(reply) or "\x00" in reply):
        raise ValueError("unsafe-patch")
    lines = reply.strip().splitlines()
    fence = chr(96) * 3
    if len(lines) > 2 and lines[0] == fence + "diff" and lines[-1] == fence:
        lines = lines[1:-1]
    if len(lines) < 4 or lines[:2] != ["--- a/" + target, "+++ b/" + target]:
        raise ValueError("unsafe-patch")
    if lines.count(lines[0]) != 1 or lines.count(lines[1]) != 1:
        raise ValueError("unsafe-patch")
    hunks = sum(line.startswith("@@ -") for line in lines[2:])
    changes = sum(line.startswith(("+", "-")) for line in lines[2:])
    if not 1 <= hunks <= 6 or not 1 <= changes <= 160:
        raise ValueError("unsafe-patch")
    for line in lines[2:]:
        if (line.startswith(("diff --git", "GIT binary patch", "Binary files",
                             "new file mode", "deleted file mode", "rename ",
                             "copy ", "index ", "---", "+++"))
                or not line.startswith((" ", "+", "-", "@@", "\\ No newline"))):
            raise ValueError("unsafe-patch")
    patch = "\n".join(lines).rstrip() + "\n"
    if len(patch.encode()) > MAX_PATCH_BYTES:
        raise ValueError("unsafe-patch")
    return patch


def draft_branch(issue, target, sha):
    if (not NUMBER.fullmatch(str(issue)) or not re.fullmatch(r"[a-f0-9]{40}", sha)
            or not isinstance(target, str)):
        raise ValueError("invalid-branch-input")
    return ("gemini/draft-" + str(issue) + "-" + sha[:10] + "-"
            + hashlib.sha256(target.encode()).hexdigest()[:8])


def git_run(*args, input=None):
    result = subprocess.run(["git", *args], input=input, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=20)
    if result.returncode:
        raise ValueError("safe-git-operation-failed")
    return result.stdout.rstrip("\n")


def run():
    global STAGE
    if not enabled() or os.getenv("BOB_GEMINI_DRAFT_PR_ENABLED") != "1":
        print("Gemini draft PR disabled: free-only owner opt-in required.")
        return
    if (os.getenv("GITHUB_ACTOR") != "ichrob" or
            os.getenv("GITHUB_REPOSITORY") != REPO or
            os.getenv("GITHUB_REF") != "refs/heads/main"):
        raise ValueError("owner-workflow-only")
    number = os.getenv("BOB_GEMINI_DEV_ISSUE", "")
    target = checked_path(os.getenv("BOB_GEMINI_DEV_FILE", ""))
    token, key = os.getenv("GITHUB_TOKEN"), os.getenv("GEMINI_API_KEY")
    if not NUMBER.fullmatch(number) or not token or not key:
        raise ValueError("missing-authorization")
    STAGE = "verify-public-input"
    issue = public_issue(request_json(BASE + "/issues/" + number, token))
    file_info = request_json(BASE + "/contents/" + target + "?ref=main", token)
    source = public_file(file_info)
    branch = draft_branch(number, target, file_info["sha"])
    STAGE = "deduplicate-before-model"
    try:
        request_json(BASE + "/git/ref/heads/" + branch, token)
    except HTTPError as err:
        if err.code != 404:
            raise ValueError("github-branch-check-failed") from None
    else:
        print("Gemini draft branch already exists; skipped before model call.")
        return
    if git_run("rev-parse", "--abbrev-ref", "HEAD") != "main":
        raise ValueError("checkout-not-main")
    if git_run("status", "--porcelain"):
        raise ValueError("checkout-not-clean")
    if git_run("show", "HEAD:" + target) != source.rstrip("\n"):
        raise ValueError("source-version-mismatch")
    STAGE = "model-public-patch"
    patch = strict_patch(model_proposal(issue, target, source, key), target)
    STAGE = "check-patch-no-execution"
    git_run("apply", "--check", "--whitespace=error", "-", input=patch)
    STAGE = "create-inert-draft"
    git_run("switch", "-c", branch)
    folder = Path("gemini_proposals")
    folder.mkdir(exist_ok=True)
    path = folder / (str(number) + "-" + file_info["sha"][:10] + "-"
                     + branch.rsplit("-", 1)[-1] + ".patch")
    if path.exists():
        raise ValueError("proposal-already-present")
    path.write_text(patch, encoding="utf-8")
    git_run("add", "--", str(path))
    git_run("config", "user.name", "github-actions[bot]")
    git_run("config", "user.email", "github-actions[bot]@users.noreply.github.com")
    git_run("commit", "-m", "Gemini inert patch proposal for issue #" + number)
    git_run("push", "--set-upstream", "origin", branch)
    STAGE = "open-github-draft-pr"
    body = ("Source: public Bob issue #" + number + "; suggested target: "
            + target + ".\n\nThis DRAFT contains an **untrusted patch file as text only**. "
            "No model-generated code was applied or executed. Independently review "
            "and test any adopted changes in a separate PR. No auto merge/deploy, "
            "private diagnostics, broker actions or paid fallback.")
    result = request_json(BASE + "/pulls", token, "POST",
                          {"title": "Gemini inert code proposal for Bob #" + number,
                           "head": branch, "base": "main",
                           "draft": True, "body": body})
    if not isinstance(result, dict) or type(result.get("number")) is not int:
        raise ValueError("github-pr-response-invalid")
    print("Gemini independent draft proposal PR #" + str(result["number"]))


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        if isinstance(e, HTTPError):
            kind = "provider-http-" + str(e.code)
        elif isinstance(e, URLError):
            kind = "network-unavailable"
        elif isinstance(e, ValueError) and str(e) in {
            "unsafe-patch", "invalid-branch-input", "missing-authorization",
            "owner-workflow-only", "checkout-not-main", "checkout-not-clean",
            "source-version-mismatch", "github-branch-check-failed",
        }:
            kind = str(e)
        else:
            kind = "validation-failed"
        print("Gemini draft unavailable at " + STAGE + ": " + kind,
              file=sys.stderr)
        sys.exit(1)
