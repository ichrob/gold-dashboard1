package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class NumericProductDetailTest {
    private val isin="DE000FD0S0G4"
    private val at="2026-10-30T08:00:00Z"
    private val top=listOf("12345678 • Societe Generale OTC | R", "Übersicht",
        "SG Gold Turbo Unlimited Mini Call BAR 3942 BP 3901.07 Bv 10 LV 27.07")
    private fun lines(texts:List<String>)=texts.mapIndexed { i,t -> QuoteLayout.Line(t,0,i*50,500,i*50+30) }
    private fun nodes(texts:List<String>)=texts.map { MorningReadPolicy.Node(it) }+
        MorningReadPolicy.Node("Order platzieren",clickable=true)
    @Test fun onlyImportedReadCanDiscoverNumericHeaderWithIsolatedLauncher() {
        val n=nodes(top)
        assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.decide(n,isin).kind)
        assertEquals(MorningReadPolicy.Kind.READ,MorningReadPolicy.detailDecision(n,isin,true).kind)
        assertEquals(-1,MorningReadPolicy.detailDecision(n,isin,true).index)
        for(extra in listOf(MorningReadPolicy.Node("Order bestätigen"),MorningReadPolicy.Node("Limitpreis"),
            MorningReadPolicy.Node("",editable=true),MorningReadPolicy.Node("",sensitive=true),
            MorningReadPolicy.Node("87654321 • Societe Generale OTC | R"))) {
            assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.detailDecision(n+extra,isin,true).kind)
        }
        assertNull(MorningReadPolicy.detailLauncherIndex(nodes(top.dropLast(1)),isin,symbolProbe=true))
    }
    @Test fun splitNumericHeaderOnlyPermitsBoundedDiscoveryWithKnownVenue() {
        val split=listOf("12345678", "Societe Generale OTC", "R")+top.drop(1)
        assertEquals("12345678",ProductSymbolMemory.detailSymbol(split))
        assertNull(ProductSymbolMemory.resolveTexts(split) { isin })
        val n=nodes(split)
        assertEquals(MorningReadPolicy.Kind.READ,MorningReadPolicy.detailDecision(n,isin,true).kind)
        assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.decide(n,isin).kind)
        val reader=ProductPageReader()
        val clean=MorningReadPolicy.detailReadLines(n,lines(n.map { it.text }),isin,symbolProbe=true)
        val first=reader.inspect(1,clean,at,false,true,true,allowSymbolProbe=true)
        assertEquals(ProductPageReader.Move.FORWARD,first.move)
        assertEquals("",first.result.draft)
        assertFalse(reader.anchored)
        assertNull(ProductSymbolMemory.detailSymbol(split.filter { it!="Societe Generale OTC" }))
        assertNull(ProductSymbolMemory.detailSymbol(split+"87654321"))
        assertNull(ProductSymbolMemory.detailSymbol(split.filter { it!="Übersicht" }))
        assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.detailDecision(n+MorningReadPolicy.Node("Order bestätigen"),isin,true).kind)
        assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.detailDecision(n+MorningReadPolicy.Node("",editable=true),isin,true).kind)
        assertEquals(ProductPageReader.Cause.IDENTITY_CHANGED,reader.inspect(1,
            lines(split.map { it.replace("12345678","87654321") }),at,false,true,true,allowSymbolProbe=true).cause)
        for(header in listOf("12345678 • Societe Generale OTC", "12345678 · Societe Generale OTC | R"))
            assertEquals("12345678",ProductSymbolMemory.detailSymbol(listOf(header)+top.drop(1)))
    }
    @Test fun detailGuardReportsOnlyFixedCauseWithoutScreenContents() {
        val rejected=mutableListOf<MorningReadPolicy.DetailIssue>()
        assertNull(MorningReadPolicy.detailLauncherIndex(nodes(listOf("Übersicht")),isin,
            symbolProbe=true,rejected={ rejected += it }))
        assertEquals(listOf(MorningReadPolicy.DetailIssue.IDENTITY_CONTEXT),rejected)
        rejected.clear()
        assertNull(MorningReadPolicy.detailLauncherIndex(nodes(top)+MorningReadPolicy.Node("",editable=true),isin,
            symbolProbe=true,rejected={ rejected += it }))
        assertEquals(listOf(MorningReadPolicy.DetailIssue.INPUT_OR_TARGET),rejected)
        rejected.clear()
        assertNotNull(MorningReadPolicy.detailLauncherIndex(nodes(top),isin,
            symbolProbe=true,rejected={ rejected += it }))
        assertTrue(rejected.isEmpty())
    }
    @Test fun discoveryExportsNothingUntilVisibleIdentityAndReturnCheck() {
        val reader=ProductPageReader()
        val n=nodes(top)
        val readable=MorningReadPolicy.detailReadLines(n,lines(n.map { it.text }),isin,symbolProbe=true)
        val first=reader.inspect(1,readable,at,false,true,true,allowSymbolProbe=true)
        assertEquals(ProductPageReader.Move.FORWARD,first.move)
        assertEquals("",first.result.draft)
        assertFalse(reader.anchored)
        assertTrue(reader.sameWindow(1))
        val q=lines(listOf("Kursdaten","Geld EUR 10,20","Brief EUR 10,30"))
        val unidentified=reader.inspect(1,q,at,false,true,true,allowSymbolProbe=true)
        assertEquals(ProductPageReader.Move.FORWARD,unidentified.move)
        assertEquals("",unidentified.result.draft)
        // Identity is read from the page, never inferred from the search target.
        reader.inspect(1,lines(listOf("Symbol | ISIN 12345678 | $isin")),at,false,true,true,allowSymbolProbe=true)
        assertTrue(reader.anchored)
        assertEquals(ProductPageReader.Move.FORWARD,reader.inspect(1,q,at,false,true,true,allowSymbolProbe=true).move)
        val done=reader.inspect(1,lines(listOf("Symbol | ISIN 12345678 | $isin")),at,false,false,false,allowSymbolProbe=true)
        assertEquals(ProductPageReader.Move.FINISHED,done.move)
        assertTrue(done.result.draft.contains("ISIN: $isin"))
        assertTrue(done.result.draft.contains("Hebel (Anzeige ungeprüft): 27,07"))
    }
    @Test fun boundedDiscoveryRejectsChangedWindowSymbolAndProtectedPage() {
        for(change in listOf(0,1,2)) {
            val reader=ProductPageReader()
            reader.inspect(1,lines(top),at,false,true,true,allowSymbolProbe=true)
            val next=when(change) {
                0 -> reader.inspect(2,lines(top),at,false,true,true,allowSymbolProbe=true)
                1 -> reader.inspect(1,lines(top.map { it.replace("12345678","87654321") }),at,false,true,true,allowSymbolProbe=true)
                else -> reader.inspect(1,lines(listOf("Order bestätigen")),at,false,true,true,allowSymbolProbe=true)
            }
            assertEquals("",next.result.draft)
            assertTrue(next.move==ProductPageReader.Move.ABORT || next.cause==ProductPageReader.Cause.WAIT_PROTECTED)
        }
        val reader=ProductPageReader()
        repeat(6) {
            val step=reader.inspect(1,lines(top),at,false,true,true,allowSymbolProbe=true)
            assertEquals(ProductPageReader.Move.FORWARD,step.move)
            assertEquals("",step.result.draft)
        }
        assertEquals(ProductPageReader.Cause.SEEK_LIMIT,
            reader.inspect(1,lines(top),at,false,true,true,allowSymbolProbe=true).cause)
    }
    @Test fun confirmedNumericHeaderMayFindRealIsinOnFifthPageWithoutBorrowingIdentity() {
        val reader=ProductPageReader()
        repeat(5) {
            val result=reader.inspect(1,lines(top),at,false,true,true,allowSymbolProbe=true)
            assertEquals(ProductPageReader.Move.FORWARD,result.move)
            assertEquals("",result.result.draft)
        }
        val real=reader.inspect(1,lines(listOf("Symbol | ISIN 12345678 | $isin")),
            at,false,true,true,allowSymbolProbe=true)
        assertTrue(reader.anchored)
        assertEquals("",real.result.draft)
        val changed=reader.inspect(1,lines(listOf("DE000FE2JJ20")),at,false,true,true,
            allowSymbolProbe=true)
        assertEquals(ProductPageReader.Cause.IDENTITY_CHANGED,changed.cause)
        assertEquals("",changed.result.draft)
    }
    @Test fun exactSymbolIsinFooterKeepsOneSidedHistoricalQuoteWithoutReverseScroll() {
        // Reproduces the two user-provided views of DE000FE6B3G9:
        // BAR/BP/Bv in the numeric header and Geld/Zuletzt plus real
        // Symbol|ISIN in the lower Kursdaten section; Brief is unavailable.
        val reader=ProductPageReader()
        val header=lines(listOf("156825577 • Societe Generale OTC | R",
            "Übersicht", "SG Gold Mini-Future Call BAR 3852 BP",
            "3813.35 Bv 10", "CHF 5,20"))
        val first=reader.inspect(11,header,at,false,true,true,
            requireParameters=true,allowSymbolProbe=true,seekLeverage=true)
        assertEquals(ProductPageReader.Move.FORWARD,first.move)
        assertEquals("",first.result.draft)
        assertFalse(reader.anchored)
        val footer=lines(listOf("Kursdaten","Zuletzt CHF 5,20","Geld CHF 5,20",
            "Brief CHF —","Symbol | ISIN 156825577 | DE000FE6B3G9"))
        val done=reader.inspect(11,footer,at,false,false,false,scrollAmbiguous=true,
            requireParameters=true,allowSymbolProbe=true,seekLeverage=true)
        assertEquals(ProductPageReader.Move.FINISHED,done.move)
        val draft=done.result.draft
        assertTrue(draft.contains("ISIN: DE000FE6B3G9"))
        assertTrue(draft.contains("Geld (Anzeige ungeprüft): 5,20"))
        assertTrue(draft.contains("Zuletzt (Anzeige ungeprüft): 5,20"))
        assertTrue(draft.contains("KO-Schwelle (Anzeige ungeprüft): 3852"))
        assertTrue(draft.contains("Basispreis (Anzeige ungeprüft): 3813,35"))
        assertTrue(draft.contains("Bv (Anzeige ungeprüft): 10"))
        assertFalse(draft.contains("Brief (Anzeige ungeprüft):"))
        assertFalse(draft.contains("Hebel (Anzeige ungeprüft):"))
        assertTrue(draft.contains("keine Order"))
        assertFalse(reader.anchored)
    }

    @Test fun brokerSymbolShortcutFailsClosedForOtherIsinOrUnsafeView() {
        val original=lines(listOf("156825577 • Societe Generale OTC | R",
            "Übersicht", "SG Gold Mini-Future Call BAR 3852 BP 3813.35 Bv 10"))
        val footer=lines(listOf("Kursdaten","Zuletzt CHF 5,20","Geld CHF 5,20",
            "Symbol | ISIN 156825577 | DE000FE6B3G9"))
        fun armed():ProductPageReader {
            val r=ProductPageReader()
            assertEquals(ProductPageReader.Move.FORWARD,
                r.inspect(11,original,at,false,true,true,requireParameters=true,
                    allowSymbolProbe=true).move)
            return r
        }
        val other=armed().inspect(11,footer.map {
            it.copy(text=it.text.replace("DE000FE6B3G9","DE000FD0S0G4"))
        },at,false,true,true,requireParameters=true,allowSymbolProbe=true,
            identityHint="DE000FE6B3G9")
        assertNotEquals(ProductPageReader.Move.FINISHED,other.move)
        assertEquals("",other.result.draft)
        val mismatchedSymbol=armed().inspect(11,footer.map {
            it.copy(text=it.text.replace("156825577 |","87654321 |"))
        },at,false,true,true,requireParameters=true,allowSymbolProbe=true)
        assertNotEquals(ProductPageReader.Move.FINISHED,mismatchedSymbol.move)
        assertEquals("",mismatchedSymbol.result.draft)
        val unsafe=armed().inspect(11,footer+lines(listOf("Order bestätigen")),
            at,false,true,true,requireParameters=true,allowSymbolProbe=true)
        assertEquals(ProductPageReader.Move.ABORT,unsafe.move)
        assertEquals("",unsafe.result.draft)
        val noTerms=ProductPageReader()
        noTerms.inspect(11,lines(listOf("156825577 • Societe Generale OTC | R",
            "Übersicht", "SG Gold Mini-Future Call")),at,false,true,true,
            requireParameters=true,allowSymbolProbe=true)
        val notDone=noTerms.inspect(11,footer,at,false,true,true,
            requireParameters=true,allowSymbolProbe=true)
        assertNotEquals(ProductPageReader.Move.FINISHED,notDone.move)
        assertEquals("",notDone.result.draft)
    }

    @Test fun plannedKursdatenSavesSplitFooterQuoteWithoutScroll() {
        val quote=lines(listOf("Kursdaten","Zuletzt CHF 5,20","Geld CHF 5,20",
            "Brief CHF —","Symbol | ISIN","156825577 | DE000FE6B3G9"))
        val result=ProductPageReader().inspect(37,quote,at,false,false,false,
            scrollAmbiguous=true,requireParameters=true,allowSymbolProbe=true,
            expectedIsin="DE000FE6B3G9",seekLeverage=true)
        assertEquals(ProductPageReader.Move.FINISHED,result.move)
        assertTrue(result.result.draft.contains("Geld (Anzeige ungeprüft): 5,20"))
        assertTrue(result.result.draft.contains("ISIN: DE000FE6B3G9"))
        assertFalse(result.result.draft.contains("Brief (Anzeige ungeprüft):"))
        assertFalse(result.result.draft.contains("Hebel (Anzeige ungeprüft):"))
    }
    @Test fun plannedKursdatenRejectsAccountOnlyCurrencyOrWrongIdentity() {
        val base=listOf("Kursdaten","Geld CHF 5,20","Symbol | ISIN",
            "156825577 | DE000FE6B3G9")
        val variants=listOf(
            base to "DE000FD0S0G4",
            (base+"DE000FD0S0G4") to "DE000FE6B3G9",
            base.map { it.replace("Kursdaten","Übersicht") } to "DE000FE6B3G9",
            (base.map { it.replace("Geld CHF 5,20","Geld 5,20") }+
                listOf("CHF 504,74")) to "DE000FE6B3G9")
        for((content,expected) in variants) {
            val result=ProductPageReader().inspect(37,lines(content),at,false,false,false,
                scrollAmbiguous=true,requireParameters=true,allowSymbolProbe=true,
                expectedIsin=expected)
            assertNotEquals(ProductPageReader.Move.FINISHED,result.move)
            assertEquals("",result.result.draft)
        }
    }

    @Test fun exactPlannedFooterCompletesWithoutPriorHeaderProbeOrReturnScroll() {
        // Real DEGIRO 10404 failure: the quote and literal identity were
        // visible but the transaction did not retain a header-probe symbol.
        // Never invent a Brief or infer a leverage from price/graph labels.
        val footer=lines(listOf("Kursdaten",
            "Zuletzt CHF 5,20","Geld CHF 5,20","Brief CHF —",
            "31/10/2026 11:28",
            "Symbol | ISIN 156825577 | DE000FE6B3G9"))
        val result=ProductPageReader().inspect(17,footer,at,false,false,false,
            scrollAmbiguous=true,requireParameters=true,allowSymbolProbe=true,
            expectedIsin="DE000FE6B3G9",seekLeverage=true)
        assertEquals(ProductPageReader.Move.FINISHED,result.move)
        assertTrue(result.result.draft.contains("ISIN: DE000FE6B3G9"))
        assertTrue(result.result.draft.contains("Geld (Anzeige ungeprüft): 5,20"))
        assertTrue(result.result.draft.contains("Zuletzt (Anzeige ungeprüft): 5,20"))
        assertFalse(result.result.draft.contains("Brief (Anzeige ungeprüft):"))
        assertFalse(result.result.draft.contains("Hebel (Anzeige ungeprüft):"))
        assertFalse(result.result.draft.contains("KO-Schwelle (Anzeige ungeprüft):"))
        assertTrue(result.result.draft.contains("keine Order"))
    }

    @Test fun footerShortcutRequiresExactRequestedIsinAndRejectsProtectedOrAmbiguous() {
        val footer=lines(listOf("Kursdaten","Zuletzt CHF 5,20",
            "Geld CHF 5,20","Symbol | ISIN 156825577 | DE000FE6B3G9"))
        fun inspect(data:List<QuoteLayout.Line>, expected:String="DE000FE6B3G9",
            sensitive:Boolean=false) = ProductPageReader().inspect(17,data,at,sensitive,
            false,false,scrollAmbiguous=true,requireParameters=true,
            allowSymbolProbe=true,expectedIsin=expected)
        for (rejected in listOf(
            inspect(footer,expected="DE000FD0S0G4"),
            inspect(footer,sensitive=true),
            inspect(footer+lines(listOf("Order bestätigen"))),
            inspect(footer+lines(listOf("DE000FD0S0G4"))),
            inspect(footer.map { it.copy(text=it.text.replace("156825577 |","87654321 |")) }
                +lines(listOf("156825577 • Societe Generale OTC | R"))),
            inspect(footer.map { it.copy(text=it.text
                .replace("Geld CHF 5,20","Geld Vol. 25K")
                .replace("Zuletzt CHF 5,20","Schluss CHF 17,29")) }) )) {
            assertNotEquals(ProductPageReader.Move.FINISHED,rejected.move)
            assertEquals("",rejected.result.draft)
        }
        assertNotEquals(ProductPageReader.Move.FINISHED,
            ProductPageReader().inspect(17,footer,at,false,false,false,
                scrollAmbiguous=true,requireParameters=false,allowSymbolProbe=true,
                expectedIsin="DE000FE6B3G9").move)
    }

    @Test fun numericHeaderIsRevisitedAndRealIsinRecheckedBeforeExport() {
        val reader=ProductPageReader()
        fun read(text:List<String>)=reader.inspect(1,lines(text),at,false,true,true,
            requireParameters=true,allowSymbolProbe=true)
        read(top)
        read(listOf("Symbol | ISIN",isin))
        val quotes=listOf("Kursdaten","Geld EUR 10,20","Brief EUR 10,30")
        assertEquals(ProductPageReader.Move.BACKWARD,read(quotes).move)
        val revisited=read(top)
        assertEquals(ProductPageReader.Move.FORWARD,revisited.move)
        assertEquals("",revisited.result.draft)
        val done=read(listOf("Symbol | ISIN",isin))
        assertEquals(ProductPageReader.Move.FINISHED,done.move)
        assertTrue(done.result.draft.contains("Hebel (Anzeige ungeprüft): 27,07"))
        assertTrue(done.result.draft.contains("Brief (Anzeige ungeprüft): 10,30"))
        // Revisited headers never create a durable symbol/ISIN pairing.
        assertNull(ProductSymbolMemory.observe(lines(top),false))
    }
    @Test fun headerRevisitRejectsDifferentSymbolAndFinalIdentity() {
        for (changedHeader in listOf(true,false)) {
            val r=ProductPageReader()
            fun read(text:List<String>)=r.inspect(1,lines(text),at,false,true,true,
                requireParameters=true,allowSymbolProbe=true)
            read(top);read(listOf(isin));read(listOf("Geld EUR 10,20","Brief EUR 10,30"))
            val result=if(changedHeader) read(top.map { it.replace("12345678","87654321") })
                else { read(top);read(listOf("DE000FE2JJ20")) }
            assertEquals(ProductPageReader.Cause.IDENTITY_CHANGED,result.cause)
            assertEquals("",result.result.draft)
        }
    }
    @Test fun unpairedHeaderParametersAreNeverCarried() {
        val reader=ProductPageReader()
        reader.inspect(1,lines(top),at,false,true,true,allowSymbolProbe=true)
        reader.inspect(1,lines(listOf(isin)),at,false,true,true,allowSymbolProbe=true)
        reader.inspect(1,lines(listOf("Kursdaten","Geld EUR 10,20","Brief EUR 10,30")),at,false,true,true,allowSymbolProbe=true)
        val result=reader.inspect(1,lines(listOf(isin)),at,false,false,false,allowSymbolProbe=true)
        assertEquals(ProductPageReader.Move.FINISHED,result.move)
        assertFalse(result.result.draft.contains("Hebel ("))
    }
}
