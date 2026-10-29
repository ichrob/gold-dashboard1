package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test

class GoldSearchRunTest {
    private val isin="DE000FD0S0G4"
    private fun input(text:String)=MorningReadPolicy.Node(text,editable=true,hint="Mit Namen, ISIN oder Symbol suchen")
    private fun row(text:String)=MorningReadPolicy.Node(text,clickable=true)
    @Test fun searchGoldThenCollectExplicitCandidatesThenSearchEachIsin() {
        assertEquals(MorningReadPolicy.Kind.SEARCH,MorningReadPolicy.discoverGold(listOf(row("Suchen"))).kind)
        assertEquals(MorningReadPolicy.Kind.QUERY,MorningReadPolicy.discoverGold(listOf(input(""))).kind)
        val nodes=listOf(input("Gold"),row("SG Turbo Gold $isin"),row("SG Turbo Gold $isin"),row("Faktor Gold DE000FG77MY4"))
        val action=MorningReadPolicy.discoverGold(nodes)
        assertEquals(MorningReadPolicy.Kind.COLLECT,action.kind)
        assertEquals(listOf(isin),action.isins)
        assertEquals(MorningReadPolicy.Kind.QUERY,MorningReadPolicy.decide(nodes,action.isins.single()).kind)
        assertEquals(MorningReadPolicy.Kind.RESULT,MorningReadPolicy.decide(nodes.mapIndexed { i,n -> if(i==0) input(isin) else n },isin).kind)
    }
    @Test fun discoveryNeverGuessesAnIdentityOrReadsProtectedScreens() {
        for(text in listOf("Turbo Gold 12345678","Faktor Gold $isin","Turbo Silver $isin","Gold ETF $isin",
            "Kaufen Turbo Gold $isin","Turbo Gold $isin DE000FG77MY4","Turbo Gold DE000FD0S0G5")) {
            val action=MorningReadPolicy.discoverGold(listOf(input("Gold"),row(text)))
            assertEquals("GOLD_IDENTITIES_MISSING",action.code)
            assertTrue(action.isins.isEmpty())
        }
        val candidate=row("Knock-out Gold $isin")
        assertEquals(listOf(isin),MorningReadPolicy.discoverGold(listOf(input("Gold"),candidate.copy(clickable=false))).isins)
        assertEquals("GOLD_IDENTITIES_MISSING",MorningReadPolicy.discoverGold(listOf(input("Gold"),candidate.copy(containsInput=true))).code)
        for(protected in listOf(row("Order bestätigen"),row("Anmelden"),row("").copy(password=true),row("").copy(sensitive=true)))
            assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.discoverGold(listOf(input("Gold"),candidate,protected)).kind)
    }
    @Test fun candidateCountIsBoundedAndSourceRowsAreNotReturned() {
        val candidates=(0..15).map { index ->
            val prefix="DE000"+index.toString().padStart(6,'0')
            val valid=(0..9).map { prefix+it }.first { SeriesEvidence.validIsin(it) }
            row("Mini Future Gold $valid")
        }
        val result=MorningReadPolicy.discoverGold(listOf(input("Gold"))+candidates)
        assertEquals(12,result.isins.size)
        assertTrue(result.isins.all { SeriesEvidence.validIsin(it) })
        assertEquals(-1,result.index)
    }
    @Test fun localSearchStateStopsAndExportsOnlyClosedCodes() {
        GoldSearchRun.start();assertTrue(GoldSearchRun.running)
        GoldSearchRun.event("GOLD_IDENTITIES_MISSING","2026-10-29T10:00:00Z")
        GoldSearchRun.stop("SCREEN_LOCKED","2026-10-29T10:00:01Z")
        assertFalse(GoldSearchRun.running);assertEquals("SCREEN_LOCKED",GoldSearchRun.lastCode)
        GoldSearchRun.stop("STOPPED","2026-10-29T10:00:02Z")
        assertEquals("SCREEN_LOCKED",GoldSearchRun.lastCode)
        GoldSearchRun.start();GoldSearchRun.event("private screen text","")
        assertEquals("OTHER",GoldSearchRun.lastCode)
        GoldSearchRun.clear();assertFalse(GoldSearchRun.running);assertNull(GoldSearchRun.lastCode)
    }
}
