"""Zero-secret, GitHub OIDC authenticated review through Bob's FREE Cloudflare Worker.

Requires a successful trusted GitHub Actions job, not a Cloudflare token or
private information in the repository. Never merges, deploys or trades.
"""
import json
import os
import re
import sys
import urllib.request
from urllib.parse import urlparse, urlencode

from ai_peer_review import (
    REPO, REVIEW_MARKER, safe_files, review_allowed, check_review_budget,
    request_json, NoRedirect,
)

AUDIENCE = "urn:bob:free-ai-code-review:v1"
WORKER = "https://bob-free-ai-review.robsimon.workers.dev/review"


def github_oidc():
    url = os.getenv("ACTIONS_ID_TOKEN_REQUEST_URL", "")
    temporary = os.getenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "")
    parsed = urlparse(url)
    host = parsed.hostname or ""
    # Actions' runner OIDC endpoints include regional pipelinesghub hosts.
    # Restrict to GitHub's exact actions.githubusercontent.com domain.
    allowed_host = (host == "token.actions.githubusercontent.com"
                    or re.fullmatch(r"pipelines[a-z0-9-]*[.]actions[.]githubusercontent[.]com", host) is not None)
    if (not temporary or parsed.scheme != "https" or not allowed_host
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or parsed.fragment):
        raise ValueError("github-oidc-unavailable")
    separator = "&" if parsed.query else "?"
    req = urllib.request.Request(
        url + separator + urlencode({"audience": AUDIENCE}),
        headers={"Authorization": "Bearer " + temporary, "Accept": "application/json"},
    )
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=12) as response:
        body = response.read(14001)
    if len(body) > 14000:
        raise ValueError("oidc-response-too-large")
    token = json.loads(body).get("value")
    if not isinstance(token, str) or not 100 <= len(token) <= 12000:
        raise ValueError("bad-oidc-token")
    return token


def cloudflare_review(diff, pr, sha, jwt):
    if (not isinstance(diff, str) or not 15 <= len(diff) <= 7000
            or not re.fullmatch(r"[a-f0-9]{40}", sha)
            or type(pr) is not int or not 1 <= pr <= 99999999):
        raise ValueError("review-request-invalid")
    payload = json.dumps({"diff": diff, "pr": pr, "sha": sha}).encode()
    req = urllib.request.Request(WORKER, data=payload, method="POST", headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + jwt})
    with urllib.request.build_opener(NoRedirect()).open(req, timeout=50) as response:
        raw = response.read(7501)
    if len(raw) > 7500:
        raise ValueError("worker-response-too-large")
    response = json.loads(raw)
    answer = response.get("response") if response.get("ok") is True else None
    if not isinstance(answer, str) or not answer.strip() or len(answer) > 5000:
        raise ValueError("unavailable-review")
    return re.sub(r"https?://\S+", "[ungeprüfter Link entfernt]", answer)


def main():
    if os.getenv("BOB_AI_FREE_ONLY") != "confirmed-workers-free":
        raise ValueError("workers-free-unconfirmed")
    github = os.getenv("GITHUB_TOKEN", "")
    pr = os.getenv("BOB_PR_NUMBER", "")
    if not github or not re.fullmatch(r"[1-9]\d{0,7}", pr):
        raise ValueError("github-config-missing")
    base = "https://api.github.com/repos/" + REPO + "/pulls/" + pr
    info = request_json(base, github)
    sha = review_allowed(info, mode=os.getenv("BOB_AI_MODE", "manual"),
                         head_sha=os.getenv("BOB_CI_HEAD_SHA"))
    if not isinstance(sha, str) or not re.fullmatch(r"[a-f0-9]{40}", sha):
        raise ValueError("review-head-unknown")
    comments = request_json("https://api.github.com/repos/" + REPO + "/issues/" + pr
                            + "/comments?per_page=100", github)
    day = check_review_budget(comments, sha)
    diff = safe_files(request_json(base + "/files?per_page=50", github))
    # OIDC is only obtained after local, free, author, SHA and dedup checks pass.
    comment = cloudflare_review(diff, int(pr), sha, github_oidc())
    body = (REVIEW_MARKER + sha + ";utcday=" + day + " -->\n"
            "### Unabhängige Zweit-KI (Cloudflare Workers Free, GitHub OIDC)\n\n"
            + comment + "\n\n"
            "*Vorschlag ohne Codeausführung, Merge oder Handelsfreigabe. "
            "Eine tatsächliche Reparatur erfordert unabhängige Tests und Live-Nachweis.*")
    request_json("https://api.github.com/repos/" + REPO + "/issues/" + pr
                 + "/comments", github, "POST", {"body": body})
    print("Cloudflare free OIDC code review posted for PR #" + pr)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Cloudflare free review blocked; no raw provider errors or credentials logged.",
              file=sys.stderr)
        sys.exit(1)
