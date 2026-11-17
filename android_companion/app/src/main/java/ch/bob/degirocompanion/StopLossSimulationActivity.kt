package ch.bob.degirocompanion

import android.app.Activity
import android.os.Bundle
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

/**
 * Local non-exported visualization of the policy against fake screen data.
 * Does not start an AccessibilityService, DEGIRO app or any order intent.
 */
class StopLossSimulationActivity : Activity() {
    private lateinit var status: TextView
    private lateinit var results: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val column=LinearLayout(this).apply {
            orientation=LinearLayout.VERTICAL
            setPadding(26,32,26,32)
        }
        fun label(t:String,size:Float=17f)=TextView(this).also {
            it.text=t; it.textSize=size; it.setPadding(0,8,0,12)
            column.addView(it)
        }
        label("BOB · STOP-LOSS-SIMULATION",23f)
        label("Nur Übung: Keine DEGIRO-Verbindung, kein echtes Depot, kein PIN und keine Order. Diese Übung testet Bobs Entscheidungsschritte anhand einer nachgebauten Oberfläche. Sie beweist NICHT die Bedienung der echten DEGIRO-App.")
        label("Fiktive Werte: Beispiel-ISIN DE000FB0A490 · 3 Stück · Stop-Loss 25,90 EUR. Das sind KEINE Livekurse oder Handlungsempfehlungen.")
        status=label("Noch kein Simulationstest ausgeführt.")
        column.addView(Button(this).apply {
            isAllCaps=false
            text="Simulation starten · ohne echte Position"
            setOnClickListener { runSimulation() }
        })
        column.addView(Button(this).apply {
            isAllCaps=false
            text="Simulation zurücksetzen"
            setOnClickListener {
                status.text="Simulation zurückgesetzt. Keine echte Order oder Brokeränderung."
                results.text=""
            }
        })
        results=label("",15f)
        setContentView(ScrollView(this).apply { addView(column) })
    }

    private fun runSimulation() {
        val scenarios=StopLossOfflineSimulation.suite()
        val allOk=scenarios.all { it.second.passed &&
            !it.second.brokerOpened && !it.second.orderSubmitted }
        status.text=if(allOk) "4/4 Simulationen bestanden · 0 Brokerzugriffe · 0 Orders"
            else "Mindestens eine Simulationsprüfung fehlgeschlagen · keine Order"
        results.text=scenarios.joinToString("\n\n") { (scenario, report) ->
            val title=when(scenario) {
                StopLossOfflineSimulation.Scenario.HAPPY_PATH ->
                    "1. Stop-Loss und Stückzahl fiktiv eintragen"
                StopLossOfflineSimulation.Scenario.WRONG_ISIN ->
                    "2. Falsche ISIN verhindern"
                StopLossOfflineSimulation.Scenario.BUY_SELECTED ->
                    "3. Kauf statt Verkauf verhindern"
                StopLossOfflineSimulation.Scenario.AMBIGUOUS_STOP_FIELD ->
                    "4. Mehrdeutiges Stop-Feld verhindern"
            }
            (if(report.passed) "✓ " else "✗ ")+title+
                "\n"+report.reason+
                "\n"+report.trace.joinToString("\n")+
                "\nStop: "+(report.stopText.ifEmpty { "nicht eingegeben" })+
                " · Anzahl: "+(report.quantityText.ifEmpty { "nicht eingegeben" })+
                "\nOrder gesendet: NEIN"
        }
    }
}
