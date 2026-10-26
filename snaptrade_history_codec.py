"""Lossless column encoding for bounded encrypted activity archives.

Only repeated field names are shared. Observed values, missing fields, ordering,
identifiers and timestamps round-trip exactly. Legacy row lists remain readable.
"""
import json

MAX_ROWS = 20000
MAX_COLUMNS = 32
MAX_SCHEMAS = 256
MAX_EXPANDED_BYTES = 8_000_000


def pack(rows, *, max_rows=MAX_ROWS):
    if not isinstance(rows, list) or len(rows) > max_rows:
        raise ValueError('Invalid activity archive')
    columns, records, indexes = [], [], {}
    for row in rows:
        if not isinstance(row, dict) or not row or len(row) > MAX_COLUMNS:
            raise ValueError('Invalid activity row')
        if any(not isinstance(k, str) or not 0 < len(k) <= 64 for k in row):
            raise ValueError('Invalid activity field')
        keys = tuple(sorted(row))
        if keys not in indexes:
            if len(columns) >= MAX_SCHEMAS:
                raise ValueError('Too many activity schemas')
            indexes[keys] = len(columns)
            columns.append(list(keys))
        records.append([indexes[keys]] + [row[k] for k in keys])
    return {'columnEncoding': 1, 'columns': columns, 'records': records}


def unpack(value):
    if not isinstance(value, dict) or set(value) != {'columnEncoding', 'columns', 'records'} or type(value['columnEncoding']) is not int or value['columnEncoding'] != 1:
        raise ValueError('Invalid activity encoding')
    columns, records = value['columns'], value['records']
    if not isinstance(columns, list) or len(columns) > MAX_SCHEMAS or not isinstance(records, list) or len(records) > MAX_ROWS:
        raise ValueError('Invalid activity archive bounds')
    for names in columns:
        if (not isinstance(names, list) or not 0 < len(names) <= MAX_COLUMNS
                or any(not isinstance(k, str) or not 0 < len(k) <= 64 for k in names)
                or len(set(names)) != len(names)):
            raise ValueError('Invalid activity columns')
    rows, expanded = [], 2
    for record in records:
        if not isinstance(record, list) or not record or type(record[0]) is not int or not 0 <= record[0] < len(columns):
            raise ValueError('Invalid activity record')
        names = columns[record[0]]
        if len(record) != len(names) + 1:
            raise ValueError('Invalid activity record width')
        row = dict(zip(names, record[1:]))
        expanded += len(json.dumps(row, separators=(',', ':'), allow_nan=False).encode()) + 1
        if expanded > MAX_EXPANDED_BYTES:
            raise ValueError('Expanded activity archive too large')
        rows.append(row)
    return rows


def encode_ledger(ledger):
    if len(json.dumps(ledger, separators=(',', ':'), allow_nan=False).encode()) > MAX_EXPANDED_BYTES:
        raise ValueError('Expanded ledger too large')
    result = {**ledger, 'journal': {}}
    for key, journal in ledger.get('journal', {}).items():
        result['journal'][key] = dict(journal)
        activities = journal.get('activities')
        if isinstance(activities, dict) and isinstance(activities.get('rows'), list):
            result['journal'][key]['activities'] = {**activities, 'rows': pack(activities['rows'])}
    return result


def decode_ledger(ledger):
    for journal in ledger.get('journal', {}).values():
        activities = journal.get('activities')
        if isinstance(activities, dict) and isinstance(activities.get('rows'), dict):
            activities['rows'] = unpack(activities['rows'])
    if len(json.dumps(ledger, separators=(',', ':'), allow_nan=False).encode()) > MAX_EXPANDED_BYTES:
        raise ValueError('Expanded ledger too large')
    return ledger
