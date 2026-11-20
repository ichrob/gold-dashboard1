package ch.bob.degirocompanion

/**
 * Standalone offline rehearsal. Only immutable synthetic DEGIRO-shaped Node
 * objects; no AccessibilityService, broker login, network, portfolio or orders.
 * It exercises the SAME StopLossPrefillPolicy decision engine as the device
 * form preparer but NEVER calls the real StopLossPrefillExecutor.
 */
internal object StopLossOfflineSimulation {
    enum class Scenario { HAPPY_PATH, WRONG_ISIN, BUY_SELECTED, AMBIGUOUS_STOP_FIELD }
    /** Each negative scenario must fail at its own safety gate, not at any random gate. */
    data class ExpectedBlock(val stage: StopLossPrefillPolicy.Stage, val code: String)
    fun expectedBlock(scenario: Scenario): ExpectedBlock? = when (scenario) {
        Scenario.HAPPY_PATH -> null
        Scenario.WRONG_ISIN -> ExpectedBlock(StopLossPrefillPolicy.Stage.OPEN_FORM, "PRODUKT_ISIN_NICHT_ERKANNT")
        Scenario.BUY_SELECTED -> ExpectedBlock(StopLossPrefillPolicy.Stage.VERIFY_FORM, "VERKAUF_NICHT_BESTAETIGT")
        Scenario.AMBIGUOUS_STOP_FIELD -> ExpectedBlock(StopLossPrefillPolicy.Stage.WRITE_STOP, "STOP_FELD_NICHT_EINDEUTIG")
    }
    data class Report(val passed: Boolean, val reason: String, val trace: List<String>,
                      val stopText: String = "", val quantityText: String = "",
                      val brokerOpened: Boolean = false, val orderSubmitted: Boolean = false)

    private val defaultDraft=StopLossPrefillDraft("DE000FB0A490",3,2590,0L)
    /** Only the copied Bob model proposal, never an authenticated broker quote. */
    fun modelDraft(raw:String, nowMs:Long):StopLossPrefillDraft? =
        StopLossDraftCodec.parse(raw,nowMs)

    fun run(scenario: Scenario, draft: StopLossPrefillDraft = defaultDraft): Report {
        if(!draft.isin.matches(Regex("[A-Z]{2}[A-Z0-9]{10}")) ||
            draft.quantity !in 1..1_000_000 || draft.stopCents !in 1..100_000_000L)
            return Report(false,"Ungültiger Modell-Entwurf",listOf("SIMULATION blockiert; kein Brokerzugriff"))
        val alteredIsin=if(draft.isin=="DE000FB0A490") "DE000FB0A491" else "DE000FB0A490"
        val trace=mutableListOf<String>("SIMULATION · offline · keine DEGIRO-Verbindung")
        var stage=StopLossPrefillPolicy.Stage.OPEN_FORM
        var orderType="Limit"
        var stopInput=""
        var quantityInput=""
        var sellOpen=false
        var menuOpen=false
        var intendedBlock=false

        fun frame(): StopLossPrefillPolicy.Frame {
            val n=mutableListOf<StopLossPrefillPolicy.Node>()
            if(menuOpen) {
                n.addAll(listOf("Limit","Market","Stop Loss","Stop Limit")
                    .map { StopLossPrefillPolicy.Node(it,clickable=true) })
            } else if(!sellOpen) {
                n.addAll(listOf(
                    StopLossPrefillPolicy.Node(if(scenario==Scenario.WRONG_ISIN) alteredIsin else draft.isin),
                    StopLossPrefillPolicy.Node("Übersicht"),
                    StopLossPrefillPolicy.Node("KAUF",clickable=true),
                    StopLossPrefillPolicy.Node("VERKAUF",clickable=true)
                ))
            } else {
                n.addAll(listOf(
                    StopLossPrefillPolicy.Node(draft.isin),
                    // This is deliberately NEVER clickable in the simulator.
                    StopLossPrefillPolicy.Node("Order platzieren",clickable=false),
                    StopLossPrefillPolicy.Node("Kauf",selected=scenario==Scenario.BUY_SELECTED),
                    StopLossPrefillPolicy.Node("Verkauf",selected=scenario!=Scenario.BUY_SELECTED),
                    StopLossPrefillPolicy.Node("Ordertyp"),
                    StopLossPrefillPolicy.Node(orderType,clickable=true)
                ))
                if(orderType=="Stop Loss") {
                    n.add(StopLossPrefillPolicy.Node("Stop (€)",left=380,top=500,right=600,bottom=525))
                    n.add(StopLossPrefillPolicy.Node("",editable=true,input=stopInput,
                        left=380,top=555,right=620,bottom=600))
                    if(scenario==Scenario.AMBIGUOUS_STOP_FIELD) {
                        n.add(StopLossPrefillPolicy.Node("Stop (€)",left=380,top=500,right=600,bottom=525))
                    }
                    n.add(StopLossPrefillPolicy.Node("Anzahl",left=30,top=650,right=180,bottom=675))
                    n.add(StopLossPrefillPolicy.Node("",editable=true,input=quantityInput,
                        left=30,top=700,right=270,bottom=745))
                }
            }
            // This is a test-only model identifier, NEVER an actual Android app.
            return StopLossPrefillPolicy.Frame("nl.degiro.trader",n)
        }

        for(i in 0 until 14) {
            val snapshot=frame()
            val decision=StopLossPrefillPolicy.decide(stage,snapshot,draft)
            when(decision.kind) {
                StopLossPrefillPolicy.Kind.BLOCK -> {
                    trace.add("Sicherheitssperre in $stage: "+decision.code)
                    val expected=expectedBlock(scenario)
                    intendedBlock=expected != null && expected.stage==stage &&
                        expected.code==decision.code &&
                        stopInput.isEmpty() && quantityInput.isEmpty()
                    return Report(intendedBlock,
                        if(intendedBlock) "Sperre wie erwartet: "+decision.code
                        else "Unerwartete Sperre: "+decision.code+" in "+stage,
                        trace,stopInput,quantityInput)
                }
                StopLossPrefillPolicy.Kind.DONE -> {
                    val ok=scenario==Scenario.HAPPY_PATH &&
                        stopInput==draft.stopText && quantityInput==draft.quantity.toString()
                    trace.add(if(ok) "Werte kontrolliert; keine Order gesendet." else "Unerwarteter Abschluss")
                    return Report(ok,if(ok) "Eingabefelder simuliert und verifiziert" else "Abschluss fehlerhaft",
                        trace,stopInput,quantityInput)
                }
                StopLossPrefillPolicy.Kind.ADVANCE -> {
                    trace.add("Ansicht bestätigt: "+stage+" → "+decision.next)
                    stage=decision.next
                }
                StopLossPrefillPolicy.Kind.CLICK -> {
                    val label=snapshot.nodes.getOrNull(decision.index)?.label.orEmpty()
                    if(label !in setOf("VERKAUF","Limit","Stop Loss")) {
                        trace.add("Unerlaubtes Bedienelement gesperrt")
                        return Report(false,"Unerlaubtes Bedienelement",trace)
                    }
                    when(label) {
                        "VERKAUF" -> sellOpen=true
                        "Limit" -> menuOpen=true
                        "Stop Loss" -> { menuOpen=false; orderType="Stop Loss" }
                    }
                    trace.add("Nur simuliert: "+label+" auswählen")
                    stage=decision.next
                }
                StopLossPrefillPolicy.Kind.WRITE -> {
                    if(decision.text !in setOf(draft.stopText,draft.quantity.toString())) {
                        trace.add("Unerlaubter Eingabewert")
                        return Report(false,"Wert nicht im Entwurf",trace)
                    }
                    when(stage) {
                        StopLossPrefillPolicy.Stage.WRITE_STOP -> stopInput=decision.text
                        StopLossPrefillPolicy.Stage.WRITE_QUANTITY -> quantityInput=decision.text
                        else -> return Report(false,"Schreiben in falscher Phase",trace)
                    }
                    trace.add("Nur simuliert: "+(if(stage==StopLossPrefillPolicy.Stage.WRITE_STOP)
                        "Stop (€)" else "Anzahl")+" = "+decision.text)
                    stage=decision.next
                }
            }
        }
        return Report(false,"Simulationsschrittgrenze überschritten",trace,stopInput,quantityInput)
    }

    fun suite(draft: StopLossPrefillDraft = defaultDraft): List<Pair<Scenario,Report>> =
        Scenario.entries.map { it to run(it,draft) }
}
