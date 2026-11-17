package ch.bob.degirocompanion

import android.app.Activity
import android.graphics.Rect
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

/**
 * An ON-DEVICE fake order screen. This only clicks and writes OUR own Android
 * Views, while the same StopLossPrefillPolicy used by the broker adapter checks
 * the visible labels/locations. It never binds an AccessibilityService, opens
 * DEGIRO, looks at a real portfolio, or touches any actual order.
 */
class StopLossMockOrderActivity : Activity() {
    private val handler=Handler(Looper.getMainLooper())
    private lateinit var form: LinearLayout
    private lateinit var status: TextView
    private lateinit var trace: TextView
    private val screenNodes=mutableListOf<View>()
    private var draft=StopLossPrefillDraft("DE000FB0A490",3,2590,0L)
    private var scenario=StopLossOfflineSimulation.Scenario.HAPPY_PATH
    private var stage=StopLossPrefillPolicy.Stage.OPEN_FORM
    private var viewState="detail"
    private var orderType="Limit"
    private var stopField=""
    private var quantityField=""
    private var running=false
    private var steps=0
    private var log=mutableListOf<String>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val proposal=StopLossPrefillDraft(
            intent.getStringExtra("mock_isin").orEmpty(),
            intent.getIntExtra("mock_quantity",0),
            intent.getLongExtra("mock_stop_cents",0),
            0L
        )
        if(proposal.isin.matches(Regex("[A-Z]{2}[A-Z0-9]{10}")) &&
            proposal.quantity in 1..1_000_000 && proposal.stopCents in 1..100_000_000L)
            draft=proposal
        scenario=runCatching {
            StopLossOfflineSimulation.Scenario.valueOf(
                intent.getStringExtra("mock_scenario") ?: "HAPPY_PATH")
        }.getOrDefault(StopLossOfflineSimulation.Scenario.HAPPY_PATH)

        val page=LinearLayout(this).apply {
            orientation=LinearLayout.VERTICAL; setPadding(20,24,20,20)
        }
        fun header(txt:String)=TextView(this).also {
            it.text=txt; it.textSize=16f; it.setPadding(0,3,0,7)
            page.addView(it)
        }
        header("TESTMASKE · NUR SIMULATION · KEINE DEGIRO-VERBINDUNG")
        header("Bob-Modellwert: ${draft.isin} · ${draft.stopText} EUR · ${draft.quantity} Stück")
        status=header("Noch keine simulierten Eingaben.").also { it.tag="mock_status" }
        page.addView(Button(this).apply {
            text="Testoberfläche automatisch bedienen"; isAllCaps=false
            tag="mock_start"
            setOnClickListener { begin() }
        })
        page.addView(Button(this).apply {
            text="Simulation stoppen / zurücksetzen"; isAllCaps=false
            setOnClickListener {
                running=false;handler.removeCallbacksAndMessages(null)
                stage=StopLossPrefillPolicy.Stage.OPEN_FORM
                viewState="detail";orderType="Limit";stopField="";quantityField=""
                status.text="Zurückgesetzt. Keine Order ausgelöst."
                log.clear();trace.text="";render()
            }
        })
        form=LinearLayout(this).apply {
            orientation=LinearLayout.VERTICAL; setPadding(8,8,8,8)
            page.addView(this)
        }
        trace=header("Start: simulierte Produktdetailseite")
        setContentView(ScrollView(this).apply { addView(page) })
        render()
    }

    private fun addText(value:String,selected:Boolean=false):TextView =
        TextView(this).also {
            it.text=value;it.textSize=17f;it.isSelected=selected
            it.setPadding(8,6,8,6);form.addView(it);screenNodes.add(it)
        }

    private fun addButton(value:String, click:()->Unit):Button =
        Button(this).also {
            it.text=value;it.isAllCaps=false
            it.minHeight=48;it.setOnClickListener { click() }
            form.addView(it);screenNodes.add(it)
        }

    private fun addField():EditText =
        EditText(this).also {
            it.isSingleLine=true;it.showSoftInputOnFocus=false
            it.inputType=android.text.InputType.TYPE_CLASS_TEXT
            it.setPadding(8,4,8,4)
            form.addView(it);screenNodes.add(it)
        }

    private fun render() {
        form.removeAllViews();screenNodes.clear()
        when(viewState) {
            "detail" -> {
                addText(if(scenario==StopLossOfflineSimulation.Scenario.WRONG_ISIN)
                    (if(draft.isin=="DE000FB0A490") "DE000FB0A491" else "DE000FB0A490")
                    else draft.isin)
                addText("Übersicht")
                addButton("KAUF") {} // Mock only: no trading functionality
                addButton("VERKAUF") { viewState="form";render() }
            }
            "menu" -> listOf("Limit","Market","Stop Loss","Stop Limit").forEach { choice ->
                addButton(choice) {
                    if(choice=="Stop Loss") {
                        orderType="Stop Loss";viewState="form";render()
                    }
                }
            }
            else -> {
                addText(draft.isin)
                addText("Kauf",scenario==StopLossOfflineSimulation.Scenario.BUY_SELECTED)
                addText("Verkauf",scenario!=StopLossOfflineSimulation.Scenario.BUY_SELECTED)
                addText("Ordertyp")
                addButton(orderType) { viewState="menu";render() }
                if(orderType=="Stop Loss") {
                    addText("Stop (€)")
                    addField().apply {
                        setText(stopField)
                        addTextChangedListener(object : android.text.TextWatcher {
                            override fun beforeTextChanged(s:CharSequence?,start:Int,count:Int,after:Int) {}
                            override fun onTextChanged(s:CharSequence?,start:Int,before:Int,count:Int) {
                                stopField=s?.toString().orEmpty()
                            }
                            override fun afterTextChanged(s:android.text.Editable?) {}
                        })
                    }
                    if(scenario==StopLossOfflineSimulation.Scenario.AMBIGUOUS_STOP_FIELD)
                        addText("Stop (€)")
                    addText("Anzahl")
                    addField().apply {
                        setText(quantityField)
                        addTextChangedListener(object : android.text.TextWatcher {
                            override fun beforeTextChanged(s:CharSequence?,start:Int,count:Int,after:Int) {}
                            override fun onTextChanged(s:CharSequence?,start:Int,before:Int,count:Int) {
                                quantityField=s?.toString().orEmpty()
                            }
                            override fun afterTextChanged(s:android.text.Editable?) {}
                        })
                    }
                }
                // Readable in simulated nodes, but permanently NOT CLICKABLE.
                addText("Order platzieren (SIMULATION · DEAKTIVIERT)")
                // The production policy requires this exact label as an
                // observation. The matching TextView has NO click listener.
                addText("Order platzieren")
            }
        }
    }

    /** Snapshot OUR actual View bounds rather than hard-coded synthetic coords. */
    private fun capture():Pair<StopLossPrefillPolicy.Frame,List<View>> {
        val nodes=screenNodes.toList()
        val frame=StopLossPrefillPolicy.Frame("nl.degiro.trader",nodes.map { view ->
            // Use actual laid-out View geometry, including fields below the
            // visible ScrollView fold. No guessed screen coordinates.
            val pos=IntArray(2);view.getLocationOnScreen(pos)
            val rect=Rect(pos[0],pos[1],pos[0]+view.width,pos[1]+view.height)
            val edit=view as? EditText
            StopLossPrefillPolicy.Node(
                label=if(edit!=null) "" else (view as? TextView)?.text?.toString().orEmpty(),
                clickable=view is Button && view.isEnabled,
                editable=edit!=null && view.isEnabled,
                selected=view.isSelected,
                input=edit?.text?.toString().orEmpty(),
                left=rect.left,top=rect.top,right=rect.right,bottom=rect.bottom
            )
        })
        return frame to nodes
    }

    private fun begin() {
        if(running)return
        running=true;steps=0
        stage=StopLossPrefillPolicy.Stage.OPEN_FORM
        viewState="detail";orderType="Limit";stopField="";quantityField="";log.clear()
        render();status.text="Prüfe sichtbare Testfelder ..."
        form.postDelayed({ step() },200)
    }

    private fun record(message:String) {
        log.add(message);trace.text=log.joinToString("\n")
    }
    private fun stop(reason:String,passed:Boolean=false) {
        running=false;handler.removeCallbacksAndMessages(null)
        status.text=if(passed) "TEST BESTANDEN · 0 Brokerzugriffe · 0 Orders"
            else "TEST ANGEHALTEN: $reason · 0 Brokerzugriffe · 0 Orders"
        record(reason)
    }
    private fun step() {
        if(!running)return
        if(++steps>18) { stop("Schrittgrenze");return }
        val (frame,views)=capture()
        val decision=StopLossPrefillPolicy.decide(stage,frame,draft)
        when(decision.kind) {
            StopLossPrefillPolicy.Kind.BLOCK -> {
                val expected=scenario!=StopLossOfflineSimulation.Scenario.HAPPY_PATH
                stop("Sperre: "+decision.code,passed=expected)
            }
            StopLossPrefillPolicy.Kind.DONE -> {
                stop(if(stopField==draft.stopText &&
                        quantityField==draft.quantity.toString() &&
                        scenario==StopLossOfflineSimulation.Scenario.HAPPY_PATH)
                        "Werte kontrolliert: Stop $stopField EUR · Anzahl $quantityField"
                    else "Abschlussdaten stimmen nicht",
                    passed=stopField==draft.stopText &&
                        quantityField==draft.quantity.toString() &&
                        scenario==StopLossOfflineSimulation.Scenario.HAPPY_PATH)
            }
            StopLossPrefillPolicy.Kind.ADVANCE -> {
                record("Erkannt: $stage → ${decision.next}")
                stage=decision.next;form.postDelayed({step()},170)
            }
            StopLossPrefillPolicy.Kind.CLICK -> {
                val target=views.getOrNull(decision.index) as? Button
                val label=target?.text?.toString().orEmpty()
                val permitted=when(stage) {
                    StopLossPrefillPolicy.Stage.OPEN_FORM -> label=="VERKAUF"
                    StopLossPrefillPolicy.Stage.ORDER_TYPE -> label=="Limit"
                    StopLossPrefillPolicy.Stage.CHOOSE_STOP -> label=="Stop Loss"
                    else -> false
                }
                if(!permitted || target==null) {stop("Nicht erlaubter Klick");return}
                record("Testklick: $label")
                stage=decision.next
                target.performClick() // Only our non-exported fake Activity
                form.postDelayed({step()},180)
            }
            StopLossPrefillPolicy.Kind.WRITE -> {
                val target=views.getOrNull(decision.index) as? EditText
                val allowed=when(stage) {
                    StopLossPrefillPolicy.Stage.WRITE_STOP -> decision.text==draft.stopText
                    StopLossPrefillPolicy.Stage.WRITE_QUANTITY ->
                        decision.text==draft.quantity.toString()
                    else -> false
                }
                if(target==null || !allowed){stop("Nicht erlaubtes Eingabefeld");return}
                record("Testeingabe $stage: ${decision.text}")
                target.setText(decision.text) // no accessibility / no broker
                stage=decision.next
                form.postDelayed({step()},180)
            }
        }
    }

    override fun onDestroy() {
        running=false;handler.removeCallbacksAndMessages(null)
        super.onDestroy()
    }
}
