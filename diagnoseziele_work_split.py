"""Conservative Sunday/Monday gate classification for 100 Bob diagnostic goals.

This is a strictly static handoff aid. Planning cannot approve a trade,
trigger a market request, prove a delivery, or turn a partial goal verified.
"""
from datetime import date

GROUPS = frozenset((
    "client-provider-schema", "device-local", "market-original-clock",
    "broker-issuer-source", "external-research-media",
    "independent-code-and-runtime",
))
EXPECTED_ACCEPTED = frozenset((2, 7, 8, 13, 18, 69))
SAFE = {"readOnly": True, "realOrders": False,
        "automaticLiveTradeApproval": False,
        "deviceControlWithoutConsent": False,
        "emailsWithoutConsent": False}


def assess(goals, plan):
    invalid = {"status": "unavailable", "readOnly": True, "realOrders": False,
               "reason": "invalid-work-split-planning-only"}
    if (not isinstance(goals, list) or len(goals) != 100
            or not isinstance(plan, dict)
            or plan.get("schemaVersion") != 1
            or plan.get("scope") != "planning-only-not-goal-completion"
            or plan.get("safety") != SAFE):
        return invalid
    try:
        parsed = date.fromisoformat(plan.get("asOf", ""))
        if parsed.year != 2026 or parsed.month != 10:
            return invalid
    except (ValueError, TypeError):
        return invalid
    if any(not isinstance(g, dict) or type(g.get("id")) is not int
           or type(g.get("verified")) is not bool for g in goals):
        return invalid
    ids = [g["id"] for g in goals]
    if sorted(ids) != list(range(1, 101)):
        return invalid
    state = {g["id"]: g["state"] for g in goals}
    accepted = {g["id"] for g in goals if g["verified"]}
    if (accepted != EXPECTED_ACCEPTED
            or state.get(1) != "blocked-client"
            or {n for n in ids if state[n] == "requires-device"}
            != set(range(91, 96))):
        return invalid
    rows = plan.get("groups")
    if not isinstance(rows, list) or len(rows) != len(GROUPS):
        return invalid
    result = []
    seen = set()
    seen_codes = set()
    market = None
    phone = None
    client = None
    for row in rows:
        if not isinstance(row, dict):
            return invalid
        code = row.get("code")
        numbers = row.get("ids")
        if (code not in GROUPS or code in seen_codes
                or not isinstance(numbers, list) or not numbers
                or any(type(n) is not int or n < 1 or n > 100 for n in numbers)
                or len(set(numbers)) != len(numbers)
                or any(n in seen for n in numbers)
                or type(row.get("marketWindowNotRequired")) is not bool
                or row.get("marketWindowNotRequired") != (code not in (
                    "market-original-clock", "broker-issuer-source"))):
            return invalid
        seen.update(numbers)
        seen_codes.add(code)
        if code == "device-local":
            phone = numbers
        elif code == "client-provider-schema":
            client = numbers
        elif code == "market-original-clock":
            market = numbers
        result.append({"code": code, "total": len(numbers),
                       "acceptedHistorically": sum(n in accepted for n in numbers),
                       "notAccepted": sum(n not in accepted for n in numbers)})
    if (seen != set(range(1, 101)) or seen_codes != GROUPS
            or set(phone or ()) != set(range(91, 96))
            or client != [1] or market is None):
        return invalid
    result.sort(key=lambda x: x["code"])
    return {
        "status": "complete-planning-coverage",
        "readOnly": True, "realOrders": False,
        "scope": "planning-only-not-goal-completion",
        "totalGoals": 100,
        "individuallyAcceptedAtDatedSample": len(accepted),
        "notIndividuallyAccepted": 100-len(accepted),
        "weekendReviewCandidateGoals": 94,
        "originalMarketProofContingentGoals": len(market),
        "deviceRequiredGoalIds": [91, 92, 93, 94, 95],
        "clientBlockedGoalIds": [1],
        "groups": result,
        "noMarketDataInferred": True,
        "noPhoneActionsInferred": True,
        "nextCheck": "Use true independently timestamped market observations when "
                     "available, never fabricate 08:00 trade liquidity, trading "
                     "signals or completed device authorization.",
        "note": "Weekend candidate means code, archives or safe source review "
                "can proceed, not that any of those goals is fully satisfied. "
                "Group allocations are only workflow planning; actual live "
                "end-to-end acceptance stays independently gated.",
    }
