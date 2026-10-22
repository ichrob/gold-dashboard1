"""Independent, read-only verification of the two published Render build SHAs.

Run separately from the main push release gate; never make Render's
checksPass deployment wait on a smoke job that waits for Render itself.
"""
import json
import re
import sys
from urllib.request import Request, urlopen

HEALTH_URLS = {
    "scanner": "https://bob-private-scanner.onrender.com/health",
    "push": "https://bob-push-service.onrender.com/health",
}
SHA = re.compile(r"^[a-f0-9]{40}$")


def verify(expected, scanner, push):
    """Return verified only if both healthy services expose the exact SHA."""
    if not isinstance(expected, str) or SHA.fullmatch(expected) is None:
        return False, {"expected": "invalid"}
    result = {}
    for name, evidence, ok in (
        ("scanner", scanner, isinstance(scanner, dict) and scanner.get("status") == "ok"),
        ("push", push, isinstance(push, dict) and push.get("ok") is True),
    ):
        actual = evidence.get("build") if isinstance(evidence, dict) else None
        result[name] = ("verified" if ok and actual == expected else
                        "unhealthy" if not ok else "build-mismatch-or-unknown")
    return all(state == "verified" for state in result.values()), result


def read_health(url):
    # Fixed non-sensitive URL only. No credentials, broker data or state change.
    with urlopen(Request(url, headers={"Cache-Control": "no-store",
                                      "User-Agent": "bob-build-verifier"}), timeout=20) as resp:
        raw = resp.read(32769)
        if len(raw) > 32768:
            raise ValueError("Oversized health response")
        body = json.loads(raw)
        if not isinstance(body, dict):
            raise ValueError("Invalid health response")
        return body


def main(args):
    if len(args) != 1 or SHA.fullmatch(args[0]) is None:
        print("Expected an exact 40-character main commit SHA", file=sys.stderr)
        return 2
    evidence = {}
    for name, url in HEALTH_URLS.items():
        try:
            evidence[name] = read_health(url)
        except Exception as exc:
            print(f"{name}: health unavailable ({type(exc).__name__})")
            evidence[name] = None
    verified, statuses = verify(args[0], evidence["scanner"], evidence["push"])
    print(json.dumps({"commit": args[0][:12], "verified": verified,
                      "services": statuses}, sort_keys=True))
    return 0 if verified else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
