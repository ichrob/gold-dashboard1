"""Bob Vollautomatisch: safe, simulation-only planning panel.

No broker credentials, no brokerage endpoints, no real-money orders.
The UI is deliberately read-only regarding order execution.
"""
PANEL = r"""
<section id="bob-vollautomatisch" style="margin:18px 0;padding:18px;border:1px solid #475569;border-radius:14px;background:#101d2b;color:#f1f5f9;font-family:inherit">
 <h2 style="margin:0 0 9px">🤖 Vollautomatisch</h2>
 <p style="margin:0 0 14px;color:#cbd5e1">Eigenständiger Gold-Trading-Simulator · Entwicklung · keine echten Orders</p>
 <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px">
  <span style="border:1px solid #eab308;color:#fde68a;border-radius:20px;padding:5px 10px">ENTWICKLUNG</span>
  <span style="border:1px solid #64748b;border-radius:20px;padding:5px 10px">Broker nicht verbunden</span>
  <span style="border:1px solid #22c55e;border-radius:20px;padding:5px 10px">Echtgeldhandel deaktiviert</span>
 </div>
 <details open><summary style="cursor:pointer;font-weight:bold;padding:6px 0">Ziele und Funktionsumfang</summary>
  <p>Bob soll später Einstiege, Positionsgrösse, Stop-Loss, Gewinnmitnahme, Trailing-Stop und Ausstieg selbstständig steuern – zunächst ausschliesslich mit simulierten Orders.</p>
  <p>Die bestehende DEGIRO-Ansicht bleibt unverändert. Es findet keine DEGIRO-Automatisierung statt.</p>
 </details>
 <details><summary style="cursor:pointer;font-weight:bold;padding:6px 0">Sicherheitsregeln</summary>
  <ul><li>Kein Trade bei fehlenden oder veralteten Daten, Marktstatus ABWARTEN oder engen KO-Schwellen</li>
   <li>Keine Doppelorders; maximal eine offene Position je Basiswert/Strategie</li>
   <li>Fester Stop-Loss vor Eröffnung; Stop niemals weiter vom Einstieg entfernen</li>
   <li>Tagesverlustlimit, Maximalverlust pro Position, maximaler Drawdown und Not-Aus</li>
   <li>Broker-API nur nach separater Prüfung, Zulassung und ausdrücklicher Live-Freigabe</li></ul>
 </details>
 <details><summary style="cursor:pointer;font-weight:bold;padding:6px 0">Testplan und Erfolgsmessung</summary>
  <p>1. Historische Simulation mit realistischen Spreads, Gebühren, Slippage und zeitlich korrekten Daten. 2. Mehrwöchiger Live-Paper-Test, auch bei Serverneustarts und Kursausfällen. 3. Unabhängige Prüfung mit bislang ungesehenen Markttagen. 4. Erst danach Brokervergleich.</p>
  <p>Pro Trade: Zeit, Marktsignal, ISIN, Quelle, Kursalter, Einstiegsgrund, Stop/Ziel, Orderereignisse, Kosten und Ergebnis revisionssicher protokollieren.</p>
  <p>Erfolg nicht an Trefferquote allein messen: Nettoergebnis, maximaler Drawdown, Profit-Faktor, Risiko/Ertrag, Regelverstösse und Systemverfügbarkeit.</p>
 </details>
 <div style="padding:12px;border:1px dashed #64748b;border-radius:9px;margin-top:12px">
  <strong>Simulationsstatus:</strong> Noch nicht mit einer eigenständigen Order-Engine verbunden.<p style="margin:5px 0 0;color:#cbd5e1">Keine erfundenen Testresultate. Diese Sparte zeigt bis zur Engine-Anbindung nur Konzept und Prüfkriterien.</p>
 </div>
</section>
"""
