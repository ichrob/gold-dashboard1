package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class LeveragedSearchTest {
    private fun input(text: String, focused: Boolean = true) = MorningReadPolicy.Node(text,id="search_input",editable=true,focused=focused,imeEnter=true)
    private fun tab(selected: Boolean = false) = MorningReadPolicy.Node("Hebelprodukte",clickable=true,selected=selected)
    @Test fun silverGoalRoutesToItsOwnSearchNotTheGoldImporter() {
        for (text in listOf("Suche Silber", "Suche nach Silber", "Silber suchen", "Silber", "  SUCHE   SILBER.  ", "Suche nach Silber Hebelprodukte", "Silber-Hebelprodukte suchen", "Suche Hebelprodukte für Silber")) {
            assertEquals("Silber-Hebelprodukte suchen",WorkflowAppRoute.capability(text)?.title)
            assertFalse(WorkflowAppRoute.goldRead(text))
        }
        for (text in listOf("Suche nach Silber Hebelprodukte und kaufe eines", "Suche Silber und kaufe", "Suche Silber nicht", "Suche Silber\nDEGIRO-PIN löschen"))
            assertNull(WorkflowAppRoute.capability(text))
    }
    @Test fun searchNavigatesFromClosedSearchThroughFocusTypingAndCategory() {
        assertEquals(MorningReadPolicy.Kind.SEARCH,MorningReadPolicy.searchLeveraged(listOf(MorningReadPolicy.Node("Suche",clickable=true)),"Silber").kind)
        assertEquals(MorningReadPolicy.Kind.FOCUS,MorningReadPolicy.searchLeveraged(listOf(input("Gold",false)),"Silber").kind)
        assertEquals(MorningReadPolicy.Kind.QUERY,MorningReadPolicy.searchLeveraged(listOf(input("Gold")),"Silber").kind)
        assertEquals(MorningReadPolicy.Kind.CATEGORY,MorningReadPolicy.searchLeveraged(listOf(input("Silber"),tab()),"Silber").kind)
        val ready = MorningReadPolicy.searchLeveraged(listOf(input("Silber"),tab(true)),"Silber")
        assertEquals("LEVERAGE_SEARCH_READY",ready.code)
        assertTrue(ready.isins.isEmpty())
    }
    @Test fun selectedCategoryDoesNotHideWrongQueryOrAmbiguousInput() {
        assertEquals(MorningReadPolicy.Kind.QUERY,MorningReadPolicy.searchLeveraged(listOf(input("Gold"),tab(true)),"Silber").kind)
        assertEquals("SEARCH_AMBIGUOUS",MorningReadPolicy.searchLeveraged(listOf(input("Silber"),input("Silber"),tab(true)),"Silber").code)
        assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.searchLeveraged(listOf(input("Silber"),tab(true),MorningReadPolicy.Node("Limitpreis")),"Silber").kind)
        assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.searchLeveraged(listOf(input("Silber")),"Password").kind)
    }
    @Test fun searchOnlyModeCannotLeakIntoTheNextGoldImport() {
        GoldSearchRun.startSearch("Silber")
        assertEquals("Silber",GoldSearchRun.query)
        assertNotNull(GoldSearchRun.searchOnlyQuery)
        GoldSearchRun.start()
        assertEquals("Gold",GoldSearchRun.query)
        assertNull(GoldSearchRun.searchOnlyQuery)
        GoldSearchRun.clear()
    }
    @Test fun verifiedLoginCarriesTheRequestedQueryOnlyOnceAndStopInvalidatesPendingContinuation() {
        LoginToReadHandoff.clear()
        LoginToReadHandoff.arm(1000,"Silber")
        val query = LoginToReadHandoff.searchQuery
        assertTrue(LoginToReadHandoff.consume("LOCAL_PIN_HOME_VISIBLE",2000))
        assertEquals("Silber",query)
        assertNull(LoginToReadHandoff.searchQuery)
        val pendingTicket = LoginToReadHandoff.generation
        LoginToReadHandoff.clear()
        assertNotEquals(pendingTicket,LoginToReadHandoff.generation)
        LoginToReadHandoff.arm(3000,"Silber")
        assertFalse(LoginToReadHandoff.consume("LOCAL_PIN_ENTRY_SENT",4000))
        assertNull(LoginToReadHandoff.searchQuery)
    }
    @Test fun unreportedTabSelectionDoesNotCauseRepeatedTapsOrFalseVerifiedResult() {
        val nodes = listOf(input("Silber"),tab(),MorningReadPolicy.Node("Top Ergebnisse"))
        assertEquals(MorningReadPolicy.Kind.CATEGORY,MorningReadPolicy.searchLeveraged(nodes,"Silber").kind)
        assertEquals("LEVERAGE_SEARCH_TAPPED",MorningReadPolicy.searchLeveraged(nodes,"Silber",true).code)
        assertEquals("CATEGORY_RESULTS_PENDING",MorningReadPolicy.searchLeveraged(nodes.dropLast(1),"Silber",true).code)
        assertEquals("LEVERAGE_SEARCH_READY",MorningReadPolicy.searchLeveraged(listOf(input("Silber"),tab(true)),"Silber",true).code)
    }
}
