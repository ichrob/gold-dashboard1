package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class MorningListEndPolicyTest {
    private val ids = listOf(
        "DE000FB0A490", "DE000FE6B3E4", "DE000FG77FN1", "DE000PK778A1",
        "DE000PJ8N975", "DE000FD0S0G4")
    private fun page(extra: MorningReadPolicy.Node? = null) =
        listOf(MorningReadPolicy.Node("Hebelprodukte", selected=true),
            MorningReadPolicy.Node("SG Gold Mini-Future Call | ${ids[0]}"),
            MorningReadPolicy.Node("BNP GOLD (COMEX) DEC. 26 Constant Leverage short R 1 | ${ids[3]}"),
            MorningReadPolicy.Node("© 2026 — flatexDEGIRO Bank Dutch Branch. Erfahren Sie mehr über unsere Datenquellen und -anbieter")
        ) + listOfNotNull(extra)
    private fun action() = MorningReadPolicy.Action(MorningReadPolicy.Kind.COLLECT,
        isins = listOf(ids[0], ids[3]))

    @Test fun bottomCanSendCapturedImagesForStrictServerVerificationOnly() {
        assertTrue(MorningListEndPolicy.maySubmitAtEnd(page(),3,ids.toSet(),
            action().isins,action()))
        assertFalse(MorningListEndPolicy.maySubmitAtEnd(page(),1,ids.toSet(),
            action().isins,action()))
        assertFalse(MorningListEndPolicy.maySubmitAtEnd(page(),3,ids.take(4).toSet(),
            action().isins,action()))
        assertFalse(MorningListEndPolicy.maySubmitAtEnd(page(),3,ids.toSet(),
            listOf("DE000PD00000"),action()))
        assertFalse(MorningListEndPolicy.maySubmitAtEnd(page(),3,ids.toSet(),
            action().isins,MorningReadPolicy.Action(MorningReadPolicy.Kind.BLOCK,code="PROTECTED_ORDER_CONFIRM")))
    }

    @Test fun missingFooterOrOrderFormCannotAuthorizeIncompleteUpload() {
        val withoutFooter=page().dropLast(1)
        assertFalse(MorningListEndPolicy.maySubmitAtEnd(withoutFooter,3,ids.toSet(),action().isins,action()))
        for (extra in listOf(MorningReadPolicy.Node("Order bestätigen"),
            MorningReadPolicy.Node("Limitpreis"),MorningReadPolicy.Node("",password=true),
            MorningReadPolicy.Node("",editable=true,id="quantity"))) {
            val nodes=page(extra)
            assertFalse(MorningListEndPolicy.maySubmitAtEnd(nodes,3,ids.toSet(),action().isins,
                MorningReadPolicy.captureGoldList(nodes,true)))
        }
    }

    @Test fun verifiedNineRowFooterPrefersFourthPhotoOverThreeImageSubmission() {
        val seen=ids.take(6).toSet()+setOf(
            "DE000SQ02JQ6","DE000FG8K0P8","DE000FG77MY4")
        assertEquals(9,seen.size)
        val visible=listOf(ids[0],ids[3])
        val action=MorningReadPolicy.Action(MorningReadPolicy.Kind.COLLECT,isins=visible)
        val footer=page()
        // Both rules are true. The existing service must prioritize one safe
        // final screenshot BEFORE submitting its three incomplete images.
        assertTrue(MorningListEndPolicy.needsFooterRecapture(
            footer,3,seen,visible,action))
        assertTrue(MorningListEndPolicy.maySubmitAtEnd(
            footer,3,seen,visible,action))
        assertFalse(MorningListEndPolicy.needsFooterRecapture(
            footer,4,seen,visible,action))
        assertFalse(MorningListEndPolicy.needsFooterRecapture(
            footer+MorningReadPolicy.Node("Orderart"),3,seen,visible,action))
        assertFalse(MorningListEndPolicy.needsFooterRecapture(
            footer+MorningReadPolicy.Node("",sensitive=true),3,seen,visible,action))
    }

    @Test fun partialLocalWebViewStillAllowsOneSafeFooterPhoto() {
        // The server may identify nine complete rows even if Samsung exposes
        // only five to eight checksum-valid labels in its virtualized view.
        val visible=listOf(ids[0],ids[3])
        val collect=MorningReadPolicy.Action(MorningReadPolicy.Kind.COLLECT,isins=visible)
        for (count in 5..8) {
            val seen=(ids + listOf("DE000SQ02JQ6","DE000FG8K0P8","DE000FG77MY4"))
                .take(count).toSet()
            assertTrue("local count $count",MorningListEndPolicy.needsFooterRecapture(
                page(),3,seen,visible,collect))
        }
        assertFalse(MorningListEndPolicy.needsFooterRecapture(
            page(),3,ids.take(4).toSet(),visible,collect))
        assertFalse(MorningListEndPolicy.needsFooterRecapture(
            page(),4,ids.toSet(),visible,collect))
        assertFalse(MorningListEndPolicy.needsFooterRecapture(
            page(MorningReadPolicy.Node("Order platzieren")),
            3,ids.toSet(),visible,collect))
        assertFalse(MorningListEndPolicy.needsFooterRecapture(
            page(MorningReadPolicy.Node("Passwort",password=true)),
            3,ids.toSet(),visible,collect))
        assertFalse(MorningListEndPolicy.needsFooterRecapture(
            page(),3,ids.toSet(),visible,
            MorningReadPolicy.Action(MorningReadPolicy.Kind.SEARCH,isins=visible)))
    }

    @Test fun fourImagesMayBeSubmittedButNeverCountAsLocalCompletion() {
        assertTrue(MorningListEndPolicy.maySubmitAtCaptureLimit(4,ids.toSet()))
        assertFalse(MorningListEndPolicy.maySubmitAtCaptureLimit(3,ids.toSet()))
        assertFalse(MorningListEndPolicy.maySubmitAtCaptureLimit(4,ids.take(4).toSet()))
        assertFalse(MorningListEndPolicy.maySubmitAtCaptureLimit(4,
            ids.toSet()+"DE000INVALID"))
        assertFalse(MorningListEndPolicy.maySubmitAtCaptureLimit(4,
            (ids + listOf("DE000SQ02JQ6","DE000FG8K0P8","DE000FG77MY4","DE000FC1CHB7")).toSet()))
    }
}
