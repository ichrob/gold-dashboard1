# Original-Spot-Vergleich: Frühwarnung gegen späteres Hauptsignal

Diese isolierte, prospektive Studie ist **kein Handelsmodus**. Sie startet
erst mit einer tatsächlich beobachteten `early-warning-v2`-Warnung
(`active`, LONG oder SHORT) und einer nachweislich geschlossenen
XAU/USD-5m-Kerze. Kurs und Quellzeit müssen mit der Original-Spotquelle
übereinstimmen. Es gibt keinen historischen Einstieg und keinen Ersatz
fehlender Kurse durch einen geschätzten Zwischenwert.

## Zwei Vergleichsarme

* **Früh:** Hypothetischer Spot-Einstieg zum ersten belegten Kurs nach der
  5m-Warnung, ohne Hauptsignal-Freigabe.
* **Bestätigt:** Eintrag erst beim *später* beobachteten Hauptsignal derselben
  Richtung, höchstens 30 Minuten nach dem Frühereignis. Ist keine Bestätigung
  innerhalb der verbleibenden Sitzung da, bleibt das Ergebnis `no-entry` —
  niemals ein erfundener virtueller Kauf.

Beide Arme benutzen für die Modellierung einen beim ersten Signal
eingefrorenen 15m-ATR-Wert: Stopp 1 ATR und Ziel 1,5 ATR vom
jeweiligen Einstieg entfernt. Das verhindert, dass ein späterer
Volatilitätswert rückwirkend das Ergebnis optimiert. Der maximale
Beobachtungszeitraum beträgt 90 Minuten, höchstens bis 21:58 Uhr Zürich
vor Ende des bestehenden Paper-Fensters. Neue Versuche benötigen mindestens
10 Minuten verbleibende Beobachtungszeit.

Ein Ausstieg wird nur beim **später beobachteten** originalen Spotkurs
mit Stopp-, Ziel-, Gegenrichtungs- oder Zeitbedingung dokumentiert.
Ein Sprung über einen Stopp hinweg wird zum tatsächlich beobachteten
Kurs bewertet, nicht zum besseren Schwellenwert. Bei Originaldatenlücken
über 90 Sekunden lautet der Fall `inconclusive`. Unvollständige
Ergebnisse werden nicht als Null-Rendite gewertet.

## Kosten und Grenzen

Die angenommene Rundweg-Spotkostenpauschale von **0,16 %** dient
ausschließlich einem groben Modellvergleich. **Keine** issuerseitigen
Geld-/Briefkurse, Produktkosten, KO-Ereignisse oder Brokergebühren
sind damit nachgewiesen. Ein `pairedSpotDifferencePct` wird nur
berechnet, wenn **beide** Arme anhand eigener Beobachtungen vollständig
geschlossen wurden. Ein ausgebliebenes Hauptsignal zählt als
`mainNeverConfirmed`, nicht als Verlust oder als Produktfill.

Die Studie ergänzt die vorhandene 18-Varianten-Produktstudie, ersetzt
sie nicht. Bob nutzt ausschließlich die bestehenden originalen
Paper-Worker-Eingaben, maximal zwei gleichzeitig offene Fälle, und
speichert **eine Fallzeile pro 5m-Frühwarnung**, kein Ereignis pro Worker-
Durchlauf. Dadurch bleibt die zusätzliche Datenbanklast begrenzt.

Technik: `early_warning_spot_study.py`, integrierter isolierter
Post-Commit-Tick in `paper_simulation.py`. Diagnose:
`shadowStudies.earlyWarningSpotStudy` im privaten vollständigen
Simulationsstatus. Die bewusst auf 2.300 Byte begrenzte Kurzdiagnose
bleibt unvergrößert. Echtgeldorders,
Hauptsignalregeln, Produktauswahl und Push bleiben unverändert.
