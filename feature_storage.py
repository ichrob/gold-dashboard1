"""Fixed feature allocation view from existing half-hour catalog samples.

No SQL, payload scans, file access, new collection or deletion. Allocation is
not recoverable disk space; shared dependencies and provider overhead are excluded.
"""
import math

GROUPS = {
    'videoAnalysis': ('bob_youtube_feed_archive', 'bob_research_transcripts',
                      'bob_research_requests', 'bob_research_enhancements',
                      'bob_research_ai_requests'),
    'strategyReplay': ('bob_research_replays',),
    'androidImages': ('bob_android_list_images',),
}


def _integer(value):
    return type(value) is int and 0 <= value <= 10**13


def report(samples, now):
    valid = [s for s in samples if isinstance(s, (tuple, list)) and len(s) >= 3
             and _integer(s[0]) and type(s[2]) is dict]
    latest = max(valid, key=lambda s: s[0]) if valid else None
    return project({'sampleAt': latest[0] if latest else None,
                    'relations': latest[2] if latest else {}}, now)


def project(source, now):
    """Whitelist and validate even when the upstream private report is malformed."""
    source = source if type(source) is dict else {}
    stamp = source.get('sampleAt')
    stamp = stamp if _integer(stamp) else None
    valid_now = type(now) in (int, float) and math.isfinite(now)
    age = now - stamp if valid_now and stamp is not None else None
    state = ('not-observed' if age is None else 'invalid-timestamp' if age < 0
             else 'stale' if age > 3600 else 'observed')
    relations = source.get('relations')
    relations = relations if type(relations) is dict else {}
    safe = {name: relations[name] for names in GROUPS.values() for name in names
            if _integer(relations.get(name))}
    groups = {}
    for name, tables in GROUPS.items():
        complete = all(t in safe for t in tables)
        groups[name] = {
            'status': state if complete else 'incomplete',
            'allocatedBytes': sum(safe[t] for t in tables) if complete else None,
            'missingTables': [t for t in tables if t not in safe],
        }
    return {'sampleAt': stamp, 'status': state, 'relations': safe,
            'groups': groups, 'readOnly': True, 'physicalBytesFreed': None,
            'scope': 'sampled-table-allocation-including-indexes-not-deletion-savings',
            'voice': {'status': 'not-separately-measured', 'allocatedBytes': None,
                      'implementation': 'android-recognizer-and-browser-speech',
                      'scope': 'no-device-cache-or-shared-log-measurement'}}
