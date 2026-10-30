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
        repeat(4) { assertEquals("",reader.inspect(1,lines(top),at,false,true,true,allowSymbolProbe=true).result.draft) }
        assertEquals(ProductPageReader.Cause.SEEK_LIMIT,reader.inspect(1,lines(top),at,false,true,true,allowSymbolProbe=true).cause)
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
