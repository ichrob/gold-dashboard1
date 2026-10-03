"""Official economic calendars, informational only; never used for trade gates."""
import calendar
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import html
import re
import threading
import time
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

UTC = timezone.utc
SOURCES = {
    'BLS': 'https://www.bls.gov/schedule/news_release/bls.ics',
    'BEA': 'https://www.bea.gov/news/schedule/ics/online-calendar-subscription.ics',
    'Fed': 'https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm',
}
LABELS = (
    ('Consumer Price Index', 'US-Verbraucherpreise (CPI)', 'hoch'),
    ('Employment Situation', 'US-Arbeitsmarkt (NFP, Löhne, Arbeitslosenquote)', 'hoch'),
    ('Personal Income and Outlays', 'US-Einkommen und Konsum (mit PCE-Inflation)', 'hoch'),
    ('Producer Price Index', 'US-Erzeugerpreise (PPI)', 'mittel'),
    ('Job Openings and Labor Turnover', 'US-Stellenangebote (JOLTS)', 'mittel'),
    ('Gross Domestic Product', 'US-Bruttoinlandsprodukt (BIP)', 'mittel'),
)
_lock = threading.Lock()
_state = {}
_running = False
_last_attempt = 0


def parse_ics(text, source):
    text = re.sub(r'\r?\n[ \t]', '', text)
    if 'BEGIN:VCALENDAR' not in text or 'END:VCALENDAR' not in text:
        raise ValueError('Ungültiger Kalender')
    events = []
    for block in text.split('BEGIN:VEVENT')[1:]:
        fields = {}
        for line in block.split('END:VEVENT')[0].splitlines():
            if ':' in line:
                key, value = line.split(':', 1)
                fields[key] = value
        summary = fields.get('SUMMARY', '')
        match = next((x for x in LABELS if x[0].lower() in summary.lower()), None)
        if not match:
            continue
        start = next(((k, v) for k, v in fields.items() if k.split(';')[0] == 'DTSTART'), None)
        if not start:
            raise ValueError('Termin ohne Zeitangabe')
        key, value = start
        if value.endswith('Z'):
            dt = datetime.strptime(value, '%Y%m%dT%H%M%SZ').replace(tzinfo=UTC)
        else:
            tz = re.search(r'TZID=([^;]+)', key)
            if not tz:
                raise ValueError('Unbekannte Zeitzone')
            zone = tz.group(1).strip('"')
            zone = 'America/New_York' if zone == 'US-Eastern' else zone
            dt = datetime.strptime(value, '%Y%m%dT%H%M%S').replace(tzinfo=ZoneInfo(zone)).astimezone(UTC)
        events.append(dict(title=match[1], importance=match[2], at=dt.isoformat(), dateOnly=False, source=source, url=SOURCES[source]))
    if not events:
        raise ValueError('Keine relevanten Termine erkannt')
    return events


def parse_fed(text):
    # This source confirms meeting dates, not intraday release times.
    # Do not invent a time or countdown for a date-only entry.
    events = []
    sections = re.split(r'(\d{4}) FOMC Meetings', text)
    months = {name: i for i, name in enumerate(calendar.month_name) if name}
    for i in range(1, len(sections), 2):
        year, body = int(sections[i]), sections[i + 1]
        pairs = re.findall(r'fomc-meeting__month[^>]*>(.*?)</div>\s*<div[^>]*fomc-meeting__date[^>]*>(.*?)</div>', body, re.S)
        for raw_month, raw_days in pairs:
            month_text = html.unescape(re.sub('<[^>]+>', '', raw_month)).strip()
            month_name = month_text.split('/')[-1].strip()
            # Cross-month labels sometimes abbreviate the second month.
            month = months.get(month_name) or next((v for k, v in months.items() if k.startswith(month_name)), None)
            days = re.findall(r'\d+', re.sub('<[^>]+>', '', raw_days))
            if month and days:
                day = datetime(year, month, int(days[-1]), tzinfo=UTC).date().isoformat()
                events.append(dict(title='Fed-Zinsentscheid / FOMC (Pressekonferenz separat beachten)', importance='hoch', date=day, dateOnly=True, source='Fed', url=SOURCES['Fed']))
    if not events:
        raise ValueError('Keine Fed-Termine erkannt')
    return events


def _load(source):
    try:
        with urlopen(Request(SOURCES[source], headers={'User-Agent': 'Bob-EconomicCalendar/1.0'}), timeout=12) as response:
            text = response.read(3_000_001)
        if len(text) > 3_000_000:
            raise ValueError('Kalender zu groß')
        events = parse_fed(text.decode('utf-8-sig')) if source == 'Fed' else parse_ics(text.decode('utf-8-sig'), source)
        return source, events, None
    except Exception:
        return source, None, 'Quelle derzeit nicht abrufbar oder Format nicht lesbar'


def _refresh():
    global _running
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            for source, events, error in pool.map(_load, SOURCES):
                with _lock:
                    previous = _state.get(source, {})
                    _state[source] = dict(events=events if events is not None else previous.get('events', []),
                        checkedAt=datetime.now(UTC).isoformat() if events is not None else previous.get('checkedAt'), error=error)
    finally:
        with _lock:
            _running = False


def build_snapshot(state, now):
    events, sources = [], []
    today = now.astimezone(ZoneInfo('Europe/Zurich')).date()
    for name, url in SOURCES.items():
        data = state.get(name, {})
        checked = datetime.fromisoformat(data['checkedAt']) if data.get('checkedAt') else None
        fresh = bool(checked and timedelta(0) <= now - checked <= timedelta(hours=24) and not data.get('error'))
        relevant = []
        for event in data.get('events', []):
            if event['dateOnly']:
                day = datetime.strptime(event['date'], '%Y-%m-%d').date()
                include = today <= day <= today + timedelta(days=90)
            else:
                dt = datetime.fromisoformat(event['at'])
                include = now - timedelta(hours=2) <= dt <= now + timedelta(days=90)
            if include:
                relevant.append({**event, 'sourceFresh': fresh})
        status = 'aktuell' if fresh and relevant else 'keine kommenden Termine bestätigt' if fresh else 'nicht verfügbar' if not checked else 'veraltet / Abruf fehlgeschlagen'
        sources.append(dict(name=name, url=url, checkedAt=data.get('checkedAt'), status=status))
        events.extend(relevant)
    events.sort(key=lambda e: e.get('at', e.get('date', '') + 'T00:00:00+00:00'))
    return dict(mode='information-only', generatedAt=now.isoformat(), timezone='Europe/Zurich',
        complete=all(s['status'] == 'aktuell' for s in sources), sources=sources, events=events,
        note='Nur Terminwarnungen. Keine Änderung an Marktrichtung, Ranking, Produktfreigaben oder Push. Unangekündigte Nachrichten und nicht erfasste Termine bleiben möglich.')


def snapshot():
    global _running, _last_attempt
    with _lock:
        if not _running and time.monotonic() - _last_attempt > 3600:
            _running = True
            _last_attempt = time.monotonic()
            threading.Thread(target=_refresh, daemon=True).start()
        state = {k: dict(v) for k, v in _state.items()}
    return build_snapshot(state, datetime.now(UTC))
