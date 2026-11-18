package ch.bob.degirocompanion

import java.util.Locale

/**
 * Scope-limited, action-free recognition of the visible DEGIRO screen.
 * This standalone policy has no dependency on the unfinished broker prefill PR.
 * It never issues clicks, writes, gestures, network requests or orders.
 */
internal object DegiroStopLossReadOnly {
    internal data class Node(
        val label:String="",
        val selected:Boolean=false,
        val password:Boolean=false,
        val editable:Boolean=false
    )
    internal data class Frame(val packageName:String, val nodes:List<Node>)

    enum class Code {
        NOT_DEGIRO, PROTECTED, INCOMPLETE, MULTIPLE_ISINS,
        NO_PRODUCT, PRODUCT_DETAIL, SELL_FORM, SELL_FORM_UNCLEAR, BUY_OR_UNKNOWN_SIDE
    }
    data class Result(val code:Code) {
        val message:String get()=when(code) {
            Code.NOT_DEGIRO -> "DEGIRO noch nicht sichtbar. Der Leser wartet auf die App."
            Code.PROTECTED -> "Anmeldung oder geschuetzte Ansicht erkannt. Keine Daten gelesen."
            Code.INCOMPLETE -> "Bildschirm unvollstaendig. Kein sicherer Ansichts-Nachweis."
            Code.MULTIPLE_ISINS -> "Mehrere Produktkennungen sichtbar. Pruefung abgebrochen."
            Code.NO_PRODUCT -> "Keine eindeutige DEGIRO-Produktseite erkannt."
            Code.PRODUCT_DETAIL -> "DEGIRO-Produktdetailseite erkannt. Keine Aktion ausgefuehrt."
            Code.SELL_FORM -> "DEGIRO-Verkaufsmaske und Feldbezeichnungen erkannt. Keine Eingaben."
            Code.SELL_FORM_UNCLEAR -> "Verkaufsmaske erkannt, aber Stop-/Anzahlfelder nicht eindeutig."
            Code.BUY_OR_UNKNOWN_SIDE -> "Kaufmaske oder Verkaufsrichtung unklar. Nichts ausgefuehrt."
        }
        val terminal:Boolean get() = code in setOf(
            Code.PROTECTED, Code.MULTIPLE_ISINS, Code.PRODUCT_DETAIL,
            Code.SELL_FORM, Code.SELL_FORM_UNCLEAR, Code.BUY_OR_UNKNOWN_SIDE
        )
    }

    private val isin=Regex("\\b[A-Z]{2}[A-Z0-9]{10}\\b")
    private val protected=Regex(
        "(?i)(passwort|password|passcode|\\bpin\\b|\\btan\\b|fingerabdruck|biometr|anmelden|log.?in|zahlung|bezahlen|verifizieren)"
    )
    private fun norm(s:String)=s.trim().lowercase(Locale.GERMAN).replace(Regex("\\s+")," ")
    private fun has(frame:Frame,label:String)=frame.nodes.any{norm(it.label)==norm(label)}
    fun inspect(frame:Frame):Result {
        if(frame.packageName!="nl.degiro.trader")return Result(Code.NOT_DEGIRO)
        if(frame.nodes.any { it.password || protected.containsMatchIn(it.label) })
            return Result(Code.PROTECTED)
        if(frame.nodes.size !in 4..1200)return Result(Code.INCOMPLETE)
        val count=frame.nodes.flatMap {
            isin.findAll(it.label.uppercase(Locale.ROOT)).map { m->m.value }.toList()
        }.distinct().size
        if(count>1)return Result(Code.MULTIPLE_ISINS)
        if(count==0)return Result(Code.NO_PRODUCT)
        if(!has(frame,"Order platzieren"))return Result(
            if(has(frame,"Uebersicht") || has(frame,"Übersicht")) {
                if(has(frame,"KAUF")&&has(frame,"VERKAUF"))Code.PRODUCT_DETAIL else Code.NO_PRODUCT
            } else Code.NO_PRODUCT)
        val selectedSell=frame.nodes.count { norm(it.label)=="verkauf"&&it.selected }==1
        val selectedBuy=frame.nodes.any{norm(it.label)=="kauf"&&it.selected}
        if(!selectedSell || selectedBuy)return Result(Code.BUY_OR_UNKNOWN_SIDE)
        if(!has(frame,"Ordertyp"))return Result(Code.SELL_FORM_UNCLEAR)
        val stopLabels=frame.nodes.count {
            !it.editable && norm(it.label) in
                setOf("stop","stopp","stop (€)","stopp (€)","stop-kurs","stopp-kurs")
        }
        val quantityLabels=frame.nodes.count {
            !it.editable && norm(it.label) in setOf("anzahl","stückzahl","stueckzahl")
        }
        return Result(if(stopLabels==1 && quantityLabels==1 && has(frame,"Stop Loss"))
            Code.SELL_FORM else Code.SELL_FORM_UNCLEAR)
    }
}

/** Only status codes in memory, never broker text, ISIN, PIN, prices or account data. */
internal object DegiroReadOnlySession {
    private var running=false
    private var deadline=0L
    var onStart:(()->Unit)?=null
    var status="Noch keine DEGIRO-Nur-Lesen-Pruefung gestartet."
        private set
    var lastCode:String="NICHT_GESTARTET"
        private set

    fun start(now:Long):Boolean {
        if(running)return false
        running=true;deadline=now+45_000L;lastCode="LAEUFT"
        status="DEGIRO-Nur-Lesen-Pruefung aktiv (max. 45 Sekunden). Nichts wird angeklickt."
        onStart?.invoke()
        return true
    }
    fun active(now:Long):Boolean {
        if(!running)return false
        if(now>=deadline){finish("ZEITLIMIT");return false}
        return true
    }
    fun note(value:DegiroStopLossReadOnly.Result) {
        if(!running)return
        lastCode=value.code.name
        status=value.message+" Keine Order."
        if(value.terminal)finish("ERKANNT")
    }
    fun finish(reason:String) {
        if(!running)return
        running=false;deadline=0L
        when(reason) {
            "ERKANNT"->status += " Pruefung abgeschlossen."
            "ZEITLIMIT"->{lastCode="ZEITLIMIT";status+=" Zeitlimit erreicht."}
            "STOPP"->{lastCode="STOPP";status="Pruefung von dir beendet. Keine Aktion ausgefuehrt."}
            "BILDSCHIRM_GESPERRT"->{lastCode="BILDSCHIRM_GESPERRT";status="Bildschirm gesperrt. Keine Aktion ausgefuehrt."}
            "PARALLELER_AUFTRAG"->{lastCode="PARALLELER_AUFTRAG";status="Anderer Bob-Leseauftrag aktiv. Nichts ausgefuehrt."}
            "DIENST_GESTOPPT"->{lastCode="DIENST_GESTOPPT";status="DEGIRO-Lesedienst beendet. Keine Aktion."}
            else->{lastCode=reason;status="Pruefung beendet: $reason. Keine Aktion."}
        }
    }
}
