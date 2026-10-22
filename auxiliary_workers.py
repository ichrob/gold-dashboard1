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

def start_initial(enabled):
    """Start the same three auxiliary workers once, without duplicating loops.

    This is only startup orchestration. The existing repair supervisor retains
    its 30-minute retry budgets and must independently verify recovery.
    No network quotes, broker actions or risk settings are changed here.
    """
    if not enabled:
        return {code: 'disabled' for code in CODES}
    import investing_card, spot_daily_change, future_comparison
    components = ((CODES[0], investing_card.health, investing_card.start),
                  (CODES[1], spot_daily_change.health, spot_daily_change.start),
                  (CODES[2], future_comparison.health, future_comparison.start))
    statuses = {}
    for code, check, start in components:
        try:
            running = check().get('running')
            if running is True:
                statuses[code] = 'already-running'
                continue
            start()
            statuses[code] = 'start-attempted'
        except Exception as exc:
            statuses[code] = 'start-failed'
            print('BOB_AUX_START code=' + code + ' error=' + type(exc).__name__, flush=True)
    return statuses
