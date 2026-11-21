package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

/** Tests NEVER access a broker. Real Android/DEGIRO compatibility is unverified. */
class StopLossOrderSubmitPolicyTest {
    private val draft = StopLossPrefillDraft("DE000FB0A490", 3, 2690L, 1_800_000_000_000L)

    private fun frame(
        isin: String = draft.isin,
        sell: Boolean = true,
        stop: String = "26,90",
        quantity: String = "3",
        type: String = "Stop Loss",
        duplicateButton: Boolean = false
    ): StopLossPrefillPolicy.Frame {
        val n = mutableListOf(
            StopLossPrefillPolicy.Node(isin),
            StopLossPrefillPolicy.Node("Order platzieren", clickable = true),
            StopLossPrefillPolicy.Node("Kauf", selected = !sell),
            StopLossPrefillPolicy.Node("Verkauf", selected = sell),
            StopLossPrefillPolicy.Node("Ordertyp"),
            StopLossPrefillPolicy.Node(type),
            StopLossPrefillPolicy.Node("Stop (€)", left=380, top=500, right=600, bottom=525),
            StopLossPrefillPolicy.Node("", editable=true, input=stop, left=380, top=555, right=620, bottom=600),
            StopLossPrefillPolicy.Node("Anzahl", left=30, top=650, right=180, bottom=675),
            StopLossPrefillPolicy.Node("", editable=true, input=quantity, left=30, top=700, right=270, bottom=745)
        )
        if (duplicateButton) n.add(StopLossPrefillPolicy.Node("Order platzieren", clickable=true))
        return StopLossPrefillPolicy.Frame("nl.degiro.trader", n)
    }

    @Test fun exactSellStopLossMayOfferOnlyOneSubmitButton() {
        val r=StopLossOrderSubmitPolicy.decide(frame(), draft)
        assertEquals(StopLossPrefillPolicy.Kind.CLICK, r.kind)
        assertEquals(StopLossPrefillPolicy.Stage.DONE, r.next)
        assertEquals("Order platzieren", frame().nodes[r.index].label)
    }

    @Test fun cannotSubmitWrongPriceQuantityProductOrBuy() {
        val bad=listOf(
            frame(stop="26,91"), frame(quantity="2"), frame(isin="DE000FB0A491"),
            frame(sell=false), frame(type="Market"),
            frame(duplicateButton=true), frame().copy(app="com.attacker.other")
        )
        for(f in bad) assertEquals(
            StopLossPrefillPolicy.Kind.BLOCK,
            StopLossOrderSubmitPolicy.decide(f,draft).kind)
    }

    @Test fun noConfirmationPagePasswordOrUnexpectedIsin() {
        val confirmation=frame().copy(nodes=frame().nodes+
            StopLossPrefillPolicy.Node("Order bestätigen", clickable=true))
        val password=frame().copy(nodes=frame().nodes+
            StopLossPrefillPolicy.Node("PIN eingeben",password=true))
        val twoProducts=frame().copy(nodes=frame().nodes+
            StopLossPrefillPolicy.Node("DE000FC1CHB7"))
        for(f in listOf(confirmation,password,twoProducts))
            assertEquals(StopLossPrefillPolicy.Kind.BLOCK,
                StopLossOrderSubmitPolicy.decide(f,draft).kind)
    }

    @Test fun approvalIsSeparateEphemeralAndConsumedBeforeClick() {
        val s=StopLossPrefillSession
        s.finish("TEST_RESET")
        s.arm(draft,1000L)
        assertFalse(s.canAuthorize(draft,1100L))
        s.move(StopLossPrefillPolicy.Stage.VERIFY_QUANTITY)
        assertTrue(s.readyForOwner(1200L))
        assertFalse(s.canAuthorize(draft.copy(quantity=4),1300L))
        assertTrue(s.canAuthorize(draft,1300L))
        assertTrue(s.authorizeSubmission(draft,1400L))
        assertFalse(s.authorizeSubmission(draft,1500L))
        assertTrue(s.takeSubmissionAttempt(1600L))
        assertFalse(s.takeSubmissionAttempt(1601L))
        s.finish("ORDER_SENDUNG_UNBESTAETIGT")
        assertFalse(s.canAuthorize(draft,1700L))
        assertFalse(s.takeSubmissionAttempt(1700L))
        assertTrue(s.status.contains("prüfen"))
    }

    @Test fun expiryPreventsApprovalOrSubmission() {
        val s=StopLossPrefillSession
        s.finish("TEST_RESET")
        s.arm(draft,1000L)
        s.move(StopLossPrefillPolicy.Stage.VERIFY_QUANTITY)
        assertTrue(s.readyForOwner(1100L))
        assertFalse(s.canAuthorize(draft,121_001L))
        s.finish("TEST_RESET")
        s.arm(draft,1000L)
        s.move(StopLossPrefillPolicy.Stage.VERIFY_QUANTITY)
        assertTrue(s.readyForOwner(1100L))
        assertTrue(s.authorizeSubmission(draft,1110L))
        assertFalse(s.takeSubmissionAttempt(121_000L))
    }
}
