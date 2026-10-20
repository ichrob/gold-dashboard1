"""Bounded original evaluator context; descriptive evidence, never trade approval."""
import math

VERSION = 'decision-context-v1'
INDICATORS = {k:'number' for k in ('score','rsi','macd','signal','hist','atr','adx','ema20','ema50','ema200','bbPos')}
INDICATORS.update(timeframe='text',barAt='number')
SCHEMA = dict(version='text',ready='bool',priceFresh='bool',indicators=INDICATORS,
    entryTiming=dict(allowed='bool',reason='text',status='text'),
    session=dict(entryAllowed='bool',reason='text',phase='text'),
    dmi=dict(available='bool',mode='text',direction='text',reason='text'))


def project(value,schema):
    value=value if isinstance(value,dict) else {}
    result={}
    for key,kind in schema.items():
        item=value.get(key)
        if isinstance(kind,dict):result[key]=project(item,kind)
        elif kind=='number':result[key]=item if type(item) in (int,float) and math.isfinite(item) else None
        elif kind=='bool':result[key]=item if type(item) is bool else None
        else:result[key]=item[:500] if isinstance(item,str) else None
    return result


def freeze(value):
    if not isinstance(value,dict) or value.get('version')!=VERSION:return None
    return project(value,SCHEMA)


def capture(market):
    source=market.get('analysisSnapshot') or {}
    if not isinstance(source,dict):source={}
    # The evaluator's native A uses R/at/e20; preserve these as named values,
    # without recomputing or filling missing indicators from later observations.
    indicators={key:source.get(key) for key in INDICATORS}
    for target,original in [('rsi','R'),('atr','at'),('ema20','e20'),('ema50','e50'),('ema200','e200'),('signal','sig'),('bbPos','bbp')]:
        if indicators.get(target) is None:indicators[target]=source.get(original)
    indicators['barAt']=market.get('analysisBarAt')
    return freeze(dict(version=VERSION,ready=market.get('ready'),priceFresh=market.get('priceFresh'),
        indicators=indicators,entryTiming=market.get('entryTimingGate'),session=market.get('session'),dmi=market.get('dmi')))
