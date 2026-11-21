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

    @Test fun oneIndependentGlobalOrderLauncherDoesNotSuppressFourthReadOnlyPhoto() {
        val visible=listOf(ids[0],ids[3])
        val collect=MorningReadPolicy.Action(MorningReadPolicy.Kind.COLLECT,isins=visible)
        val seen=ids.toSet()
        val standalone=MorningReadPolicy.Node("Order platzieren",clickable=true)
        assertTrue(MorningListEndPolicy.needsFooterRecapture(
            page(standalone),3,seen,visible,collect))
        // The decision only permits a cropped PHOTO, not a product or order action.
        assertFalse(MorningListEndPolicy.needsFooterRecapture(
            page(standalone),4,seen,visible,collect))
        assertFalse(MorningListEndPolicy.needsFooterRecapture(
            page(standalone),3,seen,visible,
            MorningReadPolicy.Action(MorningReadPolicy.Kind.SEARCH,isins=visible)))
        assertFalse(MorningListEndPolicy.needsFooterRecapture(
            page(MorningReadPolicy.Node("Order platzieren")),
            3,seen,visible,collect))
        assertFalse(MorningListEndPolicy.needsFooterRecapture(
            page(MorningReadPolicy.Node("Order bestätigen",clickable=true)),
            3,seen,visible,collect))
        assertFalse(MorningListEndPolicy.needsFooterRecapture(
            page(MorningReadPolicy.Node("Order platzieren | Limitpreis",clickable=true)),
            3,seen,visible,collect))
        assertFalse(MorningListEndPolicy.needsFooterRecapture(
            page(MorningReadPolicy.Node("Order platzieren",clickable=true,parent=1)),
            3,seen,visible,collect))
        assertFalse(MorningListEndPolicy.needsFooterRecapture(
            page(standalone)+MorningReadPolicy.Node("Order platzieren",clickable=true),
            3,seen,visible,collect))
        assertFalse(MorningListEndPolicy.needsFooterRecapture(
            page(standalone)+MorningReadPolicy.Node("Stückzahl"),
            3,seen,visible,collect))
        assertFalse(MorningListEndPolicy.needsFooterRecapture(
            page(standalone)+MorningReadPolicy.Node("Passwort",password=true),
            3,seen,visible,collect))
    }

    @Test fun passiveDuplicateGlobalOrderTextDoesNotPreventFourthPhoto() {
        val seen=ids.toSet()
        val visible=action().isins
        // Samsung may expose an "Order platzieren" text wrapper and its
        // distinct clickable leaf. Both refer to ONE isolated launcher,
        // never to an order form or an actionable list item.
        val passive=MorningReadPolicy.Node("Order platzieren")
        val clickable=MorningReadPolicy.Node("Order platzieren",
            clickable=true,parent=4)
        val nodes=page(passive)+clickable
        assertTrue(MorningListEndPolicy.needsFooterRecapture(
            nodes,3,seen,visible,action()))
        assertFalse(MorningListEndPolicy.needsFooterRecapture(
            nodes,4,seen,visible,action()))
        // Two real buttons are never one; no screenshot bypass.
        assertFalse(MorningListEndPolicy.needsFooterRecapture(
            nodes+MorningReadPolicy.Node("Order platzieren",clickable=true),
            3,seen,visible,action()))
        // The nonclickable wrapper must be an actual ancestor, not a
        // duplicate text somewhere else in the tree.
        assertFalse(MorningListEndPolicy.needsFooterRecapture(
            page(passive)+clickable.copy(parent=-1),
            3,seen,visible,action()))
        // If a wrapper has any sibling UI it cannot be considered a pure
        // global leaf duplicate.
        assertFalse(MorningListEndPolicy.needsFooterRecapture(
            nodes+MorningReadPolicy.Node("K",clickable=true,parent=4),
            3,seen,visible,action()))
        assertFalse(MorningListEndPolicy.needsFooterRecapture(
            nodes+MorningReadPolicy.Node("Orderart"),
            3,seen,visible,action()))
        assertFalse(MorningListEndPolicy.needsFooterRecapture(
            nodes+MorningReadPolicy.Node("Limitpreis",editable=true),
            3,seen,visible,action()))
        assertFalse(MorningListEndPolicy.needsFooterRecapture(
            nodes+MorningReadPolicy.Node("Order bestätigen"),
            3,seen,visible,action()))
        assertFalse(MorningListEndPolicy.needsFooterRecapture(
            nodes+MorningReadPolicy.Node("Passwort",password=true),
            3,seen,visible,action()))
        assertFalse(MorningListEndPolicy.needsFooterRecapture(
            page(passive.copy(row="Order platzieren | Gold Turbo ${ids[0]}"))+
                clickable,
            3,seen,visible,action()))
    }

    @Test fun tenSeenButIncompleteRowCoverageNeedsFourthSafeFooterPhoto() {
        val ten=(ids+listOf("DE000SQ02JQ6","DE000FG8K0P8",
            "DE000FG77MY4","DE000FG8NHQ3")).toSet()
        assertEquals(10,ten.size)
        assertTrue(ten.all(SeriesEvidence::validIsin))
        val incomplete=ten-"DE000FG8NHQ3"
        val visible=action().isins
        val collected=action()
        assertTrue(MorningListEndPolicy.needsEdgeCapture(3,ten,incomplete))
        assertTrue(MorningListEndPolicy.needsUncoveredFooterCapture(
            page(),3,ten,incomplete,visible,collected))
        assertFalse(MorningListEndPolicy.needsUncoveredFooterCapture(
            page(),2,ten,incomplete,visible,collected))
        assertFalse(MorningListEndPolicy.needsUncoveredFooterCapture(
            page(),4,ten,incomplete,visible,collected))
        assertFalse(MorningListEndPolicy.needsUncoveredFooterCapture(
            page(),3,ten,ten,visible,collected))
        assertFalse(MorningListEndPolicy.needsUncoveredFooterCapture(
            page().dropLast(1),3,ten,incomplete,visible,collected))
        for(unsafe in listOf(
            MorningReadPolicy.Node("Order bestätigen"),
            MorningReadPolicy.Node("Limitpreis"),
            MorningReadPolicy.Node("Stückzahl"),
            MorningReadPolicy.Node("",password=true),
            MorningReadPolicy.Node("",editable=true,hint="Anzahl"),
            MorningReadPolicy.Node("",sensitive=true),
            MorningReadPolicy.Node("",containsInput=true))) {
            assertFalse("Unsafe footer $unsafe",MorningListEndPolicy.needsUncoveredFooterCapture(
                page(unsafe),3,ten,incomplete,visible,collected))
        }
        assertFalse(MorningListEndPolicy.needsUncoveredFooterCapture(
            page(),3,ten,incomplete,listOf("DE000INVALID"),collected))
        assertFalse(MorningListEndPolicy.needsUncoveredFooterCapture(
            page(),3,ten,incomplete,visible,
            MorningReadPolicy.Action(MorningReadPolicy.Kind.SEARCH,isins=visible)))
    }

    @Test fun fourthGoldPhotoIgnoresOrderLauncherTextButNeverOrderForms() {
        val ten=(ids+listOf("DE000SQ02JQ6","DE000FG8K0P8",
            "DE000FG77MY4","DE000FG8NHQ3")).toSet()
        val incomplete=ten-"DE000FG8NHQ3"
        val visible=action().isins
        val base=page()
        // The *photo* may read the Gold footer even when Android repeats
        // a harmless global Order launcher in different wrappers.
        val launcher=MorningReadPolicy.Node("Order platzieren",clickable=true)
        val duplicated=base+launcher+launcher.copy(clickable=false)
        assertTrue(MorningListEndPolicy.needsUncoveredFooterCapture(
            duplicated,3,ten,incomplete,visible,action()))
        // No action ever targets the launcher; even a copy under a product
        // card is harmless for this one already-authorized cropped photo.
        assertTrue(MorningListEndPolicy.needsUncoveredFooterCapture(
            base+launcher.copy(parent=1),3,ten,incomplete,visible,action()))
        // A true order form, login, multiple edit fields or sensitive content
        // can never be photographed by this read-only fallback.
        for(extra in listOf(
            MorningReadPolicy.Node("Order bestätigen"),
            MorningReadPolicy.Node("Orderart"),
            MorningReadPolicy.Node("Limitpreis"),
            MorningReadPolicy.Node("Stückzahl"),
            MorningReadPolicy.Node("Konto",sensitive=true),
            MorningReadPolicy.Node("Mein Depotwert"),
            MorningReadPolicy.Node("Passwort"),
            MorningReadPolicy.Node("",containsInput=true),
            MorningReadPolicy.Node("",editable=true))) {
            assertFalse("Unsafe footer: $extra",
                MorningListEndPolicy.needsUncoveredFooterCapture(
                    duplicated+extra,3,ten,incomplete,visible,action()))
        }
        assertFalse(MorningListEndPolicy.needsUncoveredFooterCapture(
            duplicated,3,ten,ten,visible,action()))
    }

    @Test fun existingGoldSearchEditTextAncestryMayNotSuppressReadOnlyFourthPhoto() {
        val ten=(ids+listOf("DE000SQ02JQ6","DE000FG8K0P8",
            "DE000FG77MY4","DE000FG8NHQ3")).toSet()
        val incomplete=ten-"DE000FG8NHQ3"
        val footer=page()+MorningReadPolicy.Node("Order platzieren",clickable=true)
        val parentIndex=footer.size
        val webView=MorningReadPolicy.Node("Gold preview",containsInput=true)
        val actualSearch=MorningReadPolicy.Node("Gold",id="search-input",
            editable=true,hint="Mit Namen, ISIN oder Symbol suchen",parent=parentIndex)
        val safe=footer+webView+actualSearch
        assertEquals(MorningListEndPolicy.FourthPhotoGate.ALLOWED,
            MorningListEndPolicy.uncoveredFooterGate(
                safe,3,ten,incomplete,action().isins,action()))
        assertTrue(MorningListEndPolicy.needsUncoveredFooterCapture(
            safe,3,ten,incomplete,action().isins,action()))
        // A virtual WebView input with no independently identified real Gold
        // EditText is NOT a reason to bypass the old protection.
        assertEquals(MorningListEndPolicy.FourthPhotoGate.UNKNOWN_INPUT,
            MorningListEndPolicy.uncoveredFooterGate(
                footer+webView,3,ten,incomplete,action().isins,action()))
        assertEquals(MorningListEndPolicy.FourthPhotoGate.UNKNOWN_INPUT,
            MorningListEndPolicy.uncoveredFooterGate(
                safe+MorningReadPolicy.Node("",editable=true,hint="Anzahl"),
                3,ten,incomplete,action().isins,action()))
        assertEquals(MorningListEndPolicy.FourthPhotoGate.UNKNOWN_INPUT,
            MorningListEndPolicy.uncoveredFooterGate(
                footer+webView+actualSearch.copy(text="1234"),
                3,ten,incomplete,action().isins,action()))
        assertEquals(MorningListEndPolicy.FourthPhotoGate.UNKNOWN_INPUT,
            MorningListEndPolicy.uncoveredFooterGate(
                footer+webView+actualSearch.copy(parent=-1),
                3,ten,incomplete,action().isins,action()))
        for(form in listOf("Order bestätigen","Limitpreis","Stückzahl","Passwort")) {
            assertEquals(form,MorningListEndPolicy.FourthPhotoGate.ORDER_OR_PRIVATE_SURFACE,
                MorningListEndPolicy.uncoveredFooterGate(
                    safe+MorningReadPolicy.Node(form),
                    3,ten,incomplete,action().isins,action()))
        }
        assertEquals(MorningListEndPolicy.FourthPhotoGate.ACTION_NOT_COLLECT,
            MorningListEndPolicy.uncoveredFooterGate(
                safe,3,ten,incomplete,action().isins,
                MorningReadPolicy.Action(MorningReadPolicy.Kind.BLOCK,
                    code="PROTECTED_ORDER_CONFIRM")))
        assertFalse(MorningListEndPolicy.needsUncoveredFooterCapture(
            safe,4,ten,incomplete,action().isins,action()))
        assertFalse(MorningListEndPolicy.needsUncoveredFooterCapture(
            safe,3,ten,ten,action().isins,action()))
    }

    @Test fun persistentPortfolioTabIsNotPrivateAccountViewAtGoldFooter() {
        val ten=(ids+listOf("DE000SQ02JQ6","DE000FG8K0P8",
            "DE000FG77MY4","DE000FG8NHQ3")).toSet()
        val incomplete=ten-"DE000FG8NHQ3"
        val base=page()+MorningReadPolicy.Node("Order platzieren",clickable=true)
        // navigationTree() puts the real bottom-tab text into both the leaf
        // and each ancestor's aggregated newline-separated row.
        val normal=base+MorningReadPolicy.Node("Portfolio")+
            MorningReadPolicy.Node("Gold results wrapper",
                row="Märkte\nFavoriten\nPortfolio\nInbox\nTop Ergebnisse")
        val outcome=MorningListEndPolicy.uncoveredFooterGate(
            normal,3,ten,incomplete,action().isins,action())
        assertEquals(MorningListEndPolicy.FourthPhotoGate.ALLOWED,outcome)
        assertTrue(MorningListEndPolicy.needsUncoveredFooterCapture(
            normal,3,ten,incomplete,action().isins,action()))
        // Composite ancestors may repeat the benign navigation label.
        // Their remaining lines must STILL be scanned for real order fields.
        assertEquals(MorningListEndPolicy.FourthPhotoGate.ORDER_OR_PRIVATE_SURFACE,
            MorningListEndPolicy.uncoveredFooterGate(
                normal+MorningReadPolicy.Node("Gold root",
                    row="Portfolio\nOrderart\nGold"),
                3,ten,incomplete,action().isins,action()))
        for(privateView in listOf(
            MorningReadPolicy.Node("Mein Portfolio"),
            MorningReadPolicy.Node("Portfolio 12.345 CHF"),
            MorningReadPolicy.Node("Depotwert"),
            MorningReadPolicy.Node("Kontostand"),
            MorningReadPolicy.Node("Order bestätigen"),
            MorningReadPolicy.Node("Limitpreis"),
            MorningReadPolicy.Node("Passwort"),
            MorningReadPolicy.Node("Portfolio",sensitive=true),
            MorningReadPolicy.Node("",editable=true,hint="Stückzahl"))) {
            assertEquals("Unsafe: $privateView",
                MorningListEndPolicy.FourthPhotoGate.ORDER_OR_PRIVATE_SURFACE,
                MorningListEndPolicy.uncoveredFooterGate(
                    normal+privateView,3,ten,incomplete,action().isins,action()))
        }
        assertFalse(MorningListEndPolicy.needsUncoveredFooterCapture(
            normal,4,ten,incomplete,action().isins,action()))
        assertFalse(MorningListEndPolicy.needsUncoveredFooterCapture(
            normal,3,ten,ten,action().isins,action()))
        assertFalse(MorningListEndPolicy.needsUncoveredFooterCapture(
            normal,3,ten,incomplete,action().isins,
            MorningReadPolicy.Action(MorningReadPolicy.Kind.SEARCH)))
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
