package ch.bob.degirocompanion

import java.util.Locale

/**
 * Privacy-minimized recognition of a real DEGIRO accessibility VIEW.
 * NO actions are returned: no CLICK, WRITE, gesture, order, login or PIN.
 * No ISIN, quantity, quote, price, text, screenshot or entire tree is retained.
 * The caller must discard the temporary Frame immediately after inspection.
 */
internal object StopLossReadOnlyProbe {
    enum class Code {
        NOT_DEGIRO, SCREEN_PROTECTED, VIEW_INCOMPLETE, AMBIGUOUS_ISIN,
        PRODUCT_NOT_VISIBLE, PRODUCT_DETAIL_VISIBLE, SELL_FORM_VISIBLE,
        SELL_FORM_LABELS_UNCLEAR, BUY_OR_UNCONFIRMED_FORM
    }

    data class Result(
        val code: Code,
        val stopCaptionVisible: Boolean = false,
        val quantityCaptionVisible: Boolean = false,
        val stopLossVisible: Boolean = false
    ) {
        // Code-only summary. Never include raw broker labels, positions or amounts.
        val summary: String get() = when(code) {
            Code.NOT_DEGIRO -> "DEGIRO noch nicht im Vordergrund. Keine Erkennung."
            Code.SCREEN_PROTECTED -> "Geschützte Ansicht / Anmeldung erkannt. Nicht weiter ausgelesen."
            Code.VIEW_INCOMPLETE -> "Ansicht unvollständig. Kein belastbarer Nachweis."
            Code.AMBIGUOUS_ISIN -> "Mehrere Produktkennungen sichtbar. Prüfung gestoppt."
            Code.PRODUCT_NOT_VISIBLE -> "Noch keine eindeutige Produktdetailseite erkennbar."
            Code.PRODUCT_DETAIL_VISIBLE -> "Produktdetailseite erkannt. Keine Verkaufsmaske geöffnet."
            Code.SELL_FORM_VISIBLE -> "Verkaufsmaske erkannt. Stop-Loss-Felder nur gelesen, nichts eingegeben."
            Code.SELL_FORM_LABELS_UNCLEAR -> "Verkaufsmaske erkannt, Feldbezeichnungen unklar. Keine Eingabe."
            Code.BUY_OR_UNCONFIRMED_FORM -> "Kaufmaske oder Verkaufsrichtung nicht eindeutig. Keine Eingabe."
        }
    }

    private val isinPattern=Regex("\\b[A-Z]{2}[A-Z0-9]{10}\\b")
    private val protected=Regex(
        "(?i)(passwort|password|passcode|\\bpin\\b|\\btan\\b|fingerabdruck|biometr|anmelden|log.?in|zahlung|bezahlen|verifizieren)"
    )
    private fun norm(text:String):String =
        text.trim().lowercase(Locale.GERMAN).replace(Regex("\\s+")," ")
    private fun has(f:StopLossPrefillPolicy.Frame,label:String):Boolean =
        f.nodes.any { norm(it.label)==norm(label) }

    fun inspect(f:StopLossPrefillPolicy.Frame):Result {
        if(f.app!="nl.degiro.trader")return Result(Code.NOT_DEGIRO)
        if(f.nodes.any { it.password || protected.containsMatchIn(it.label) })
            return Result(Code.SCREEN_PROTECTED)
        if(f.nodes.size !in 4..1200)return Result(Code.VIEW_INCOMPLETE)
        // Deliberately do not return or persist an ISIN, even if multiple are shown.
        val count=f.nodes.flatMap { node ->
            isinPattern.findAll(node.label.uppercase(Locale.ROOT)).map { it.value }.toList()
        }.distinct().size
        if(count>1)return Result(Code.AMBIGUOUS_ISIN)
        if(count==0)return Result(Code.PRODUCT_NOT_VISIBLE)
        if(!has(f,"Order platzieren")) {
            return if(has(f,"Übersicht") && has(f,"KAUF") && has(f,"VERKAUF"))
                Result(Code.PRODUCT_DETAIL_VISIBLE)
            else Result(Code.PRODUCT_NOT_VISIBLE)
        }
        val sell=f.nodes.count { norm(it.label)=="verkauf" && it.selected }==1
        val buy=f.nodes.any { norm(it.label)=="kauf" && it.selected }
        if(!sell||buy)return Result(Code.BUY_OR_UNCONFIRMED_FORM)
        if(!has(f,"Ordertyp"))return Result(Code.SELL_FORM_LABELS_UNCLEAR)
        val stop=f.nodes.count {
            !it.editable && norm(it.label) in
                setOf("stop","stopp","stop (€)","stopp (€)","stop-kurs","stopp-kurs")
        }==1
        val qty=f.nodes.count {
            !it.editable && norm(it.label) in setOf("anzahl","stückzahl","stueckzahl")
        }==1
        return Result(if(stop&&qty&&has(f,"Stop Loss")) Code.SELL_FORM_VISIBLE
            else Code.SELL_FORM_LABELS_UNCLEAR,stop,qty,has(f,"Stop Loss"))
    }
}

/** At most 45 seconds, foreground-only, RAM-only, explicit device-owner start. */
internal object StopLossReadOnlySession {
    private var deadline=0L
    private var running=false
    var onStarted:(()->Unit)?=null

    var result: StopLossReadOnlyProbe.Result?=null
        private set
    var status="Keine DEGIRO-Oberflächenprüfung gestartet."
        private set

    fun start(nowElapsed:Long):Boolean {
        if(running)return false
        running=true;deadline=nowElapsed+45_000L;result=null
        status="Nur-Lesen-Prüfung gestartet (maximal 45 Sekunden). Keine Eingaben."
        onStarted?.invoke()
        return true
    }
    fun active(nowElapsed:Long):Boolean {
        if(!running)return false
        if(nowElapsed>=deadline){ finish("ZEITLIMIT");return false }
        return true
    }
    fun observe(found:StopLossReadOnlyProbe.Result) {
        if(!running)return
        result=found
        status=found.summary+" Keine Order oder Eingabe."
        if(found.code in setOf(
            StopLossReadOnlyProbe.Code.SELL_FORM_VISIBLE,
            StopLossReadOnlyProbe.Code.PRODUCT_DETAIL_VISIBLE,
            StopLossReadOnlyProbe.Code.SELL_FORM_LABELS_UNCLEAR,
            StopLossReadOnlyProbe.Code.BUY_OR_UNCONFIRMED_FORM,
            StopLossReadOnlyProbe.Code.SCREEN_PROTECTED,
            StopLossReadOnlyProbe.Code.AMBIGUOUS_ISIN
        ))finish("BEENDET")
    }
    fun finish(code:String) {
        if(!running)return
        running=false;deadline=0L
        status=when(code) {
            "BEENDET"->status+" Prüfung beendet."
            "ZEITLIMIT"->status+" Zeitlimit erreicht, beendet."
            "STOPP"->"Nur-Lesen-Prüfung vom Besitzer gestoppt."
            "BILDSCHIRM_GESPERRT"->"Bildschirm gesperrt. Prüfung beendet."
            "ANDERER_AUFTRAG"->"Andere Leseraktion aktiv. Prüfung nicht begonnen."
            "DIENST_STOPP"->"Lesedienst beendet. Prüfung beendet."
            else->"Nur-Lesen-Prüfung beendet: $code."
        }
    }
}
