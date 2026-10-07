"""Observed product terms accepted under Bob's declared series policy.

The retrieval time is provenance, never an issuer effective date. Call only
when the term and product identity were read in the same successful request
series, and preserve this timestamp through caches and fallback responses.
"""
def observed_condition(value, source, isin, observed_at):
    return dict(value=value, at=None, source=source, reviewedAt=observed_at,
                conditionVerified=False, validityUnconfirmed=True,
                validitySeries=dict(isin=isin, source=source, observedAt=observed_at,
                                    origin='automatic', policy='declared-series-v1'))
