"""Explicit administrative closure of the 13 user-reviewed historical paper cases.
Original ledger payloads and unknown outcomes are never rewritten.
"""
import copy
import hashlib
import json
import math

DECISION_AT = "2026-10-26"
STATUS = "closed-unrecoverable"
LABEL = "Geschlossen – mangels historischer Daten nicht rekonstruierbar."
# Fixed, hashed composite identities from the user's reviewed virtual cases.
# No private case times, product identities, date-range rules or future cases.
IDENTITIES = {'f2a5a3a0cadf16eb58578b5d5fdc93dec57592ed17d5c0f064b6b41ed6f9e2a1', 'c8fc23ed4b4bcf4cbae570f9885631352d779414aa25714ba607a2e665beea69', '5fa1641044c1ce7a307fc95e1f288a1943f208d3c6d08738952700ddb03c1e91', 'b99a59707655dff26f8c68cfa904b08d60543c8ac94fb8c8e97ce189e5967777', 'abb06955854bd3ba9e91226868356f0ddcba5076a9654eea6791575ba9c0d7e1', '52e2dd0198dc50b28747c60988a5a509b8fe45aae573ec9a271f16a6821f5a76', 'a62ac234be86cd0d8362f5cfb7dc3acfdebf5f3601f0dd49092c9cc73e5f9153', 'fbeeefc6b8e46d40903555a1d1a443e3965689ebdbcf88e0a9259dbe2e2b4732', '12b8eed3c75a371a14f1f3b11ae9fac000b4f0f8c6aa0b6699c7e0641b63f253', '21a6406d30f557985585cf192e9464495a3e87b658f037a1a0b6d4bc85e4df66', '04d04a759ee8b4e2129ba44ca4373aeccf5c64e31204dbcdf5c15ae7246e0b16', 'ad2cf23e171ec119dfa3283c766d52cafdf51e3715d466609a8d1d05f3ae475e', 'c1777b4aa3454f68a59ac65e003eb9246e38ad44c2e00c0da33d2ca82d0b2aa3'}

def review(case, profile):
    if not isinstance(case, dict) or case.get("status") != "inconclusive":
        return None
    key = (profile, case.get("startedAt"), case.get("closedAt"), case.get("lastAt"))
    if not isinstance(profile, str) or any(type(x) not in (int,float) or not math.isfinite(x) for x in key[1:]):
        return None
    fingerprint = hashlib.sha256(json.dumps(key).encode()).hexdigest()
    if fingerprint not in IDENTITIES:
        return None
    if not any(isinstance(e, dict) and e.get("kind") == "data-gap"
               and e.get("recordedAt") == case.get("closedAt")
               for e in case.get("events", [])):
        return None
    return dict(status=STATUS, label=LABEL, decidedAt=DECISION_AT,
                caseReviewId=fingerprint,
                resultVerified=False, reopenOnlyWithOriginalEvidence=True)

def project_case(case, profile=None):
    result = copy.deepcopy(case)
    closure = review(case, profile)
    if closure:
        result["administrativeReview"] = closure
    if result.get("status") == "inconclusive":
        result["performanceEligible"] = False
        result["performanceExclusionReason"] = "Unbekannter ursprünglicher Ausstieg; spätere Modellverkäufe sind kein Strategieergebnis."
        result["modelSettlementGrossPct"] = result.get("productGrossPct")
        result["productGrossPct"] = None
        result["netReturnKnown"] = False
    return result

def adjust_daily(stats, excluded):
    result = copy.deepcopy(stats)
    # Legacy daily counts may contain later deferred model sales. Future
    # writes count exclusions separately and never increment productKnown.
    if excluded:
        for field, value in zip(("productKnown", "productPositive", "productNegative"), excluded):
            old = result.get(field, 0)
            if type(old) is not int or type(value) is not int or value < 0 or old < value:
                result["performanceCountsValid"] = False
                for name in ("productKnown", "productPositive", "productNegative"):
                    result[name] = None
                return result
            result[field] = old - value
    result["performanceExcluded"] = result.get("inconclusive", 0)
    result["performanceCountsValid"] = True
    return result

def legacy_exclusions(conn):
    # Aggregate only the small paper ledger; no broker accounts or raw quotes.
    return {day: (int(total), int(positive), int(nonpositive))
            for day, total, positive, nonpositive in conn.execute("""SELECT day, count(*),
          count(*) FILTER (WHERE (payload->>'productGrossPct')::numeric > 0),
          count(*) FILTER (WHERE (payload->>'productGrossPct')::numeric <= 0)
        FROM bob_paper_cases
        WHERE payload->>'status' = 'inconclusive'
          AND payload->>'productCounted' = 'true'
          AND NOT (payload ? 'performanceAccountingVersion')
        GROUP BY day""").fetchall()}

