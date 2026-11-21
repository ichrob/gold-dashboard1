package ch.bob.degirocompanion

import java.util.Locale

/**
 * One-shot, owner-approved broker action. This policy cannot give approval:
 * only the non-exported Android Activity can authorize the matching RAM draft.
 * Never accept an arbitrary remote command, coordinate tap, or confirmation page.
 */
internal object StopLossOrderSubmitPolicy {
    private fun norm(value: String) =
        value.trim().lowercase(Locale.GERMAN).replace(Regex("\\s+"), " ")

    fun decide(
        frame: StopLossPrefillPolicy.Frame,
        draft: StopLossPrefillDraft
    ): StopLossPrefillPolicy.Decision {
        val p = StopLossPrefillPolicy
        fun block(code: String) = p.Decision(p.Kind.BLOCK, code = code)

        // Both fields must still match after the owner switched from Bob to
        // DEGIRO. The prefill policy also verifies SELL, ISIN, stop type,
        // field geometry, protected surfaces, and the broker package.
        val verifiedStop = p.decide(p.Stage.VERIFY_STOP, frame, draft)
        if (verifiedStop.kind != p.Kind.ADVANCE ||
            verifiedStop.next != p.Stage.WRITE_QUANTITY)
            return block("ORDER_STOP_NICHT_VERIFIZIERT")
        val verifiedQuantity = p.decide(p.Stage.VERIFY_QUANTITY, frame, draft)
        if (verifiedQuantity.kind != p.Kind.DONE)
            return block("ORDER_STUECKZAHL_NICHT_VERIFIZIERT")

        // Never act on a summary / second confirmation screen; those
        // require the owner to review any new broker-specific information.
        val buttons = frame.nodes.indices.filter {
            norm(frame.nodes[it].label) == "order platzieren" &&
                frame.nodes[it].clickable && !frame.nodes[it].password
        }
        if (frame.nodes.any { norm(it.label) in setOf(
                "order bestätigen", "confirm order", "orderübersicht",
                "orderzusammenfassung", "orderdetails") })
            return block("ORDER_BESTAETIGUNG_MANUELL")
        val unique = buttons.singleOrNull() ?: return block("ORDER_BUTTON_UNEINDEUTIG")
        if (frame.nodes.count { norm(it.label) == "order platzieren" } != 1)
            return block("ORDER_BUTTON_MEHRFACH")
        return p.Decision(p.Kind.CLICK, unique, next = p.Stage.DONE)
    }
}
