package ch.bob.degirocompanion

import android.app.Activity
import android.os.Bundle
import android.app.AlertDialog
import android.content.Intent
import android.content.ClipboardManager
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
    private lateinit var draftStatus: TextView
    private var importedModelDraft: StopLossPrefillDraft? = null

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
        draftStatus=label("Modellwerte: Noch nicht übernommen; Standardübung nutzt rein fiktive Zahlen.")
        column.addView(Button(this).apply {
            isAllCaps=false
            text="Frischen Bob-Modellstopp aus Zwischenablage übernehmen"
            setOnClickListener {
                // Clipboard read ONLY after this deliberate tap; the result
                // stays in this activity and never enters live broker controls.
                val clipboard=getSystemService(CLIPBOARD_SERVICE) as ClipboardManager
                val clip=clipboard.primaryClip
                val raw=if(clip!=null && clip.itemCount==1 &&
                    clip.getItemAt(0).uri==null && clip.getItemAt(0).intent==null)
                    clip.getItemAt(0).text?.toString().orEmpty() else ""
                val parsed=StopLossOfflineSimulation.modelDraft(raw,System.currentTimeMillis())
                if(parsed==null) {
                    importedModelDraft=null
                    draftStatus.text="Kein gültiger aktueller Bob-Modellentwurf (max. 5 Minuten). Fiktive Übung bleibt möglich."
                } else {
                    importedModelDraft=parsed
                    draftStatus.text="Modellvorschlag für Simulation: ${parsed.isin} · ${parsed.quantity} Stück · ${parsed.stopText} EUR. Kein Brokerkurs, keine echte Position bestätigt."
                }
            }
        })
        status=label("Noch kein Simulationstest ausgeführt.")
        column.addView(Button(this).apply {
            isAllCaps=false
            text="Simulation starten · ohne echte Position"
            setOnClickListener { runSimulation() }
        })
        column.addView(Button(this).apply {
            isAllCaps=false
            text="Nachgebildete DEGIRO-Ordermaske bedienen · offline"
            setOnClickListener {
                val cases=arrayOf("Normaler Eingabeablauf","Falsche ISIN","Kaufmaske statt Verkauf","Mehrdeutiges Stop-Feld")
                AlertDialog.Builder(this@StopLossSimulationActivity)
                    .setTitle("Nur lokale Testoberfläche, keine DEGIRO-App")
                    .setItems(cases) { _,which ->
                        val d=importedModelDraft ?: StopLossPrefillDraft("DE000FB0A490",3,2590,0L)
                        val scenario=StopLossOfflineSimulation.Scenario.entries[which]
                        startActivity(Intent(this@StopLossSimulationActivity,StopLossMockOrderActivity::class.java)
                            .putExtra("mock_isin",d.isin)
                            .putExtra("mock_quantity",d.quantity)
                            .putExtra("mock_stop_cents",d.stopCents)
                            .putExtra("mock_scenario",scenario.name))
                    }.show()
            }
        })
        column.addView(Button(this).apply {
            isAllCaps=false
            text="Simulation zurücksetzen"
            setOnClickListener {
                status.text="Simulation zurückgesetzt. Keine echte Order oder Brokeränderung."
                results.text=""
                importedModelDraft=null
                draftStatus.text="Modellwerte zurückgesetzt. Fiktive Standardübung."
            }
        })
        results=label("",15f)
        setContentView(ScrollView(this).apply { addView(column) })
    }

    private fun runSimulation() {
        val scenarios=importedModelDraft?.let { StopLossOfflineSimulation.suite(it) }
            ?: StopLossOfflineSimulation.suite()
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
