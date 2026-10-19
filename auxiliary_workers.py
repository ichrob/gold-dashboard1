"""Supervise only existing idempotent starts; never replace a live thread."""
CODES=('cfd-worker-stopped','spot-change-worker-stopped','comparison-worker-stopped')

def health():
    import investing_card, spot_daily_change, future_comparison
    return dict(zip(CODES,(investing_card.health(),spot_daily_change.health(),future_comparison.health())))

def maintain(enabled):
    if not enabled:return
    import investing_card, spot_daily_change, future_comparison, bob_self_healing
    states=health()
    for code,starter in zip(CODES,(investing_card.start,spot_daily_change.start,future_comparison.start)):
        bob_self_healing.restart_worker(code,states[code].get('running') is False,starter)
