"""Prospective simulation cost debits; assumptions, never broker tariffs."""
import math
from datetime import datetime
from zoneinfo import ZoneInfo
START=int(datetime(2026,10,19,8,tzinfo=ZoneInfo('Europe/Zurich')).timestamp()*1000)
MODEL=dict(version='cash-costs-v1',feeEurPerOrder=1.,slippageBpsPerSide=5.,extraHoldingBpsPerDay=0.)
NOTE='Ab neuen Einstiegen ab 19.10.2026: 1 EUR je Kauf/Verkauf und 0,05 % Slippage je Seite direkt im Spielgeld. Zwei Verkaufsgebühren werden bei der Stückzahlplanung reserviert, aber erst beim Verkauf belastet. Beispielannahmen, keine bestätigten DEGIRO-Tarife. Spread bereits im Brief/Geld enthalten; eingebettete Finanzierung nicht doppelt abziehen. Frühere Fälle bleiben unverändert.'

def units(cash,ask,model):
    # Partial target plus final sale: reserve two fees to avoid spending sale costs.
    return max(0,math.floor((cash-3*model['feeEurPerOrder']+1e-9)/(ask*(1+model['slippageBpsPerSide']/10000))))

def apply(control,case):
    model=case.get('ledgerCostModel')
    if not model or not case.get('quantity'):return
    sales=[e for e in case.get('events',[]) if (e.get('units') or 0)>0 and isinstance(e.get('quote'),dict) and (e['quote'].get('bid') or 0)>0]
    fees=(1+len(sales))*model['feeEurPerOrder']
    slip=(case['allocated']+case.get('cashReleased',0))*model['slippageBpsPerSide']/10000
    total=fees+slip
    previous=case.get('ledgerCostsDebited',0.)
    if total<previous-1e-8:raise ValueError('Kostenprotokoll darf nicht rückwärts laufen')
    delta=max(0,total-previous)
    control['cash']-=delta;control['realizedProfit']-=delta
    control['costsDebitedEur']=control.get('costsDebitedEur',0.)+delta
    case.update(ledgerCostsDebited=total,ledgerFeesEur=fees,ledgerSlippageEur=slip)
    case['ledgerModelNetEur']=(case['cashReleased']-case['allocated']-total if not case.get('remainingUnits') and not case.get('pendingUnits') else None)

def activate(control,now):
    if not control.get('ledgerCostModel'):
        control.update(ledgerCostModel=dict(MODEL),costsStartedAt=now,costsOpeningEquity=control['equity'],costsDebitedEur=0.,costsNote=NOTE)
