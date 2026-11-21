package ch.bob.degirocompanion

import java.math.BigDecimal
import java.math.RoundingMode
import java.util.Locale

/**
 * Local, one-shot SELL stop-loss form assistant. Never places an order.
 * The clipboard format is UNTRUSTED: it only proposes an owner-reviewed draft.
 */
internal data class StopLossPrefillDraft(
    val isin: String,
    val quantity: Int,
    val stopCents: Long,
    val preparedAtMs: Long
) {
    val stopText: String get() = "%d,%02d".format(Locale.ROOT, stopCents / 100, stopCents % 100)
}

internal object StopLossDraftCodec {
    private val isinPattern = Regex("[A-Z]{2}[A-Z0-9]{10}")
    private val amountPattern = Regex("[0-9]{1,6}(?:\\.[0-9]{1,2})?")
    private const val MAX_AGE_MS = 5 * 60_000L

    fun parse(raw: String, nowMs: Long): StopLossPrefillDraft? {
        val parts = raw.trim().split('|')
        if (parts.size != 6 || parts[0] != "BOB-STOP/1" || parts[2] != "EUR" ||
            !isinPattern.matches(parts[1]) || !SeriesEvidence.validIsin(parts[1]) ||
            !amountPattern.matches(parts[4])) return null
        val quantity = parts[3].toIntOrNull()?.takeIf { it in 1..1_000_000 } ?: return null
        val at = parts[5].toLongOrNull() ?: return null
        if (at > nowMs || nowMs - at > MAX_AGE_MS) return null
        val cents = runCatching {
            BigDecimal(parts[4]).movePointRight(2).setScale(0, RoundingMode.UNNECESSARY).longValueExact()
        }.getOrNull() ?: return null
        if (cents !in 1..100_000_000L) return null
        return StopLossPrefillDraft(parts[1],quantity,cents,at)
    }
}

/** No coordinate taps; only exact visible semantic nodes and unique fields. */
internal object StopLossPrefillPolicy {
    data class Node(
        val label: String,
        val clickable: Boolean = false,
        val editable: Boolean = false,
        val selected: Boolean = false,
        val password: Boolean = false,
        val input: String = "",
        val left: Int = 0,
        val top: Int = 0,
        val right: Int = 0,
        val bottom: Int = 0
    )
    data class Frame(val app: String, val nodes: List<Node>)
    enum class Stage { OPEN_FORM, VERIFY_FORM, ORDER_TYPE, CHOOSE_STOP, WRITE_STOP, VERIFY_STOP, WRITE_QUANTITY, VERIFY_QUANTITY, DONE }
    enum class Kind { CLICK, WRITE, ADVANCE, DONE, BLOCK }
    data class Decision(val kind: Kind, val index: Int = -1, val text: String = "", val next: Stage = Stage.DONE, val code: String = "")

    private val secret = Regex("(?i)(passwort|password|passcode|\\bpin\\b|\\btan\\b|fingerabdruck|biometric|anmelden|log.?in|überweisen|bezahlen|zahlung|verifizieren)")
    private fun norm(s: String) = s.trim().lowercase(Locale.GERMAN).replace(Regex("\\s+")," ")
    private fun exact(f: Frame, label: String, clickable: Boolean = false): Int? =
        f.nodes.indices.filter { norm(f.nodes[it].label) == norm(label) && (!clickable || f.nodes[it].clickable) }.singleOrNull()
    private fun has(f: Frame, label: String) = f.nodes.any { norm(it.label) == norm(label) }
    private fun isSell(f: Frame) = f.nodes.count { norm(it.label) == "verkauf" && it.selected } == 1 &&
        f.nodes.none { norm(it.label) == "kauf" && it.selected }
    private fun base(f: Frame, draft: StopLossPrefillDraft) =
        f.app == "nl.degiro.trader" && f.nodes.size in 4..1200 &&
        f.nodes.none { it.password || secret.containsMatchIn(it.label) } &&
        f.nodes.any { Regex("\\b[A-Z]{2}[A-Z0-9]{10}\\b").containsMatchIn(it.label.uppercase(Locale.ROOT)) &&
            Regex("\\b[A-Z]{2}[A-Z0-9]{10}\\b").findAll(it.label.uppercase(Locale.ROOT)).all { m -> m.value == draft.isin } } &&
        f.nodes.flatMap { Regex("\\b[A-Z]{2}[A-Z0-9]{10}\\b").findAll(it.label.uppercase(Locale.ROOT)).map { m -> m.value }.toList() }
            .distinct() == listOf(draft.isin)

    /** Associate an editable field with the unique nearest caption above it, in the same column. */
    private fun inputFor(f: Frame, caption: Regex): Int? {
        val labels = f.nodes.filter { !it.editable && caption.matches(norm(it.label)) && it.right > it.left }
        if (labels.size != 1) return null
        val label = labels.single()
        val candidates = f.nodes.indices.filter { i ->
            val n = f.nodes[i]
            n.editable && !n.password && n.right > n.left &&
                n.top >= label.bottom && n.top - label.bottom <= 180 &&
                n.left < label.right && n.right > label.left
        }.sortedBy { f.nodes[it].top - label.bottom }
        return candidates.firstOrNull()?.takeIf { first ->
            candidates.size == 1 || f.nodes[candidates[1]].top - label.bottom >
                f.nodes[first].top - label.bottom + 60
        }
    }
    private fun visibleNumber(text: String): String =
        text.replace("€","").replace("\u00a0","").replace(" ","").replace(",",".").trim()

    fun decide(stage: Stage, f: Frame, draft: StopLossPrefillDraft): Decision {
        fun block(code: String) = Decision(Kind.BLOCK, code = code)
        // A real broker confirmation page is never part of prefill.
        // This check applies before even a harmless dropdown click/write.
        if(f.nodes.any { norm(it.label) in setOf("order bestätigen","confirm order",
                    "orderzusammenfassung","orderübersicht","orderdetails") })
            return block("ORDER_BESTAETIGUNG_GESCHUETZT")
        if(stage==Stage.OPEN_FORM) {
            if(!base(f,draft)) return block("PRODUKT_ISIN_NICHT_ERKANNT")
            if(has(f,"Order platzieren")) {
                return if(isSell(f) && has(f,"Ordertyp"))
                    Decision(Kind.ADVANCE,next=Stage.ORDER_TYPE) else block("VERKAUF_NICHT_BESTAETIGT")
            }
            // The verified DEGIRO product detail shown by the owner has a
            // distinct SELL entry button. This can only OPEN an order form;
            // the broker's final "Order platzieren" control is never called.
            if(!has(f,"Übersicht") || has(f,"Ordertyp") ||
                !has(f,"KAUF") || !has(f,"VERKAUF")) return block("PRODUKT_DETAIL_NICHT_ERKANNT")
            return exact(f,"VERKAUF",clickable=true)?.let {
                Decision(Kind.CLICK,it,next=Stage.VERIFY_FORM)
            } ?: block("VERKAUF_BUTTON_NICHT_EINDEUTIG")
        }
        if(stage==Stage.CHOOSE_STOP) {
            // Android dialogs can expose only the four options, not the
            // original order background. Never mistake an unrelated popup:
            // accept exactly the known DEGIRO order-type choice menu.
            if(f.app!="nl.degiro.trader" || f.nodes.any { it.password || secret.containsMatchIn(it.label) } ||
                listOf("Limit","Market","Stop Loss","Stop Limit").any { !has(f,it) })
                return block("ORDERTYP_DIALOG_NICHT_ERKANNT")
            return exact(f,"Stop Loss",clickable=true)?.let {
                Decision(Kind.CLICK,it,next=Stage.WRITE_STOP)
            } ?: block("STOP_LOSS_OPTION_FEHLT")
        }
        if (!base(f,draft)) return block("ISIN_ODER_ANSICHT_NICHT_EINDEUTIG")
        if (!isSell(f)) return block("VERKAUF_NICHT_BESTAETIGT")
        if (!has(f,"Order platzieren")) return block("ORDERMASKE_NICHT_ERKANNT")
        return when(stage) {
            Stage.OPEN_FORM -> block("PRODUKT_DETAIL_NICHT_ERKANNT")
            Stage.VERIFY_FORM -> if(has(f,"Ordertyp"))
                Decision(Kind.ADVANCE,next=Stage.ORDER_TYPE) else block("VERKAUFSFORM_NICHT_ERKANNT")
            Stage.ORDER_TYPE -> {
                if (has(f,"Stop Loss") && f.nodes.none { norm(it.label) == "market" && it.clickable })
                    Decision(Kind.ADVANCE, next=Stage.WRITE_STOP)
                else if (!has(f,"Ordertyp")) block("ORDERTYP_FEHLT")
                else exact(f,"Limit",clickable=true)?.let { Decision(Kind.CLICK,it,next=Stage.CHOOSE_STOP) }
                    ?: block("ORDERTYP_UNKLAR")
            }
            Stage.CHOOSE_STOP -> exact(f,"Stop Loss",clickable=true)?.let {
                Decision(Kind.CLICK,it,next=Stage.WRITE_STOP)
            } ?: block("STOP_LOSS_OPTION_FEHLT")
            Stage.WRITE_STOP, Stage.VERIFY_STOP -> {
                if (!has(f,"Stop Loss")) block("STOP_LOSS_NICHT_AUSGEWAEHLT")
                else {
                    val index = inputFor(f,Regex("(stop|stopp|stop[- ]?kurs|stopp[- ]?kurs|stop \\(€\\)|stopp \\(€\\)|stop[- ]?preis \\(€\\))"))
                        ?: return block("STOP_FELD_NICHT_EINDEUTIG")
                    if(stage==Stage.WRITE_STOP) Decision(Kind.WRITE,index,draft.stopText,Stage.VERIFY_STOP)
                    else if (visibleNumber(f.nodes[index].input) ==
                        visibleNumber(draft.stopText)) Decision(Kind.ADVANCE,next=Stage.WRITE_QUANTITY)
                    else block("STOP_EINGABE_NICHT_BESTAETIGT")
                }
            }
            Stage.WRITE_QUANTITY, Stage.VERIFY_QUANTITY -> {
                val index=inputFor(f,Regex("(anzahl|stückzahl|stueckzahl)"))
                    ?: return block("ANZAHL_FELD_NICHT_EINDEUTIG")
                if(stage==Stage.WRITE_QUANTITY) Decision(Kind.WRITE,index,draft.quantity.toString(),Stage.VERIFY_QUANTITY)
                else if (visibleNumber(f.nodes[index].input) == draft.quantity.toString())
                    Decision(Kind.DONE,next=Stage.DONE)
                else block("ANZAHL_EINGABE_NICHT_BESTAETIGT")
            }
            Stage.DONE -> Decision(Kind.DONE,next=Stage.DONE)
        }
    }
}
