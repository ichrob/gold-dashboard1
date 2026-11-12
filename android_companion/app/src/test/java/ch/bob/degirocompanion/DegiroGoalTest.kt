package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class DegiroGoalTest {
    private val isin = "DE000PM96QY2"
    @Test fun bareIsinAndExplicitProductGoalsUseTheSameLocalTarget() {
        for (text in listOf(isin, "  de000pm96qy2  ", "ISIN: $isin", "Öffne das Produkt $isin", "Suche $isin bei DEGIRO"))
            assertEquals(text, isin, DegiroGoal.productIsin(text))
        assertTrue(DegiroGoal.needsProductIsin("Öffne das Produkt"))
        assertTrue(DegiroGoal.acceptsQuery(isin))
        for (text in listOf("DE000PM96QY3", "1234567890123", "$isin DE000FD0S0G4", "kaufe $isin", "öffne $isin und kaufe", "öffne $isin nicht"))
            assertNull(text, DegiroGoal.productIsin(text))
    }
    @Test fun loginMustCompleteBeforeOneShotIsinContinuation() {
        LoginToReadHandoff.clear()
        LoginToReadHandoff.arm(1000, isin)
        assertEquals(isin, LoginToReadHandoff.searchQuery)
        assertFalse(LoginToReadHandoff.consume("LOCAL_PIN_ENTRY_SENT",2000))
        LoginToReadHandoff.arm(3000, isin)
        val query = LoginToReadHandoff.searchQuery!!
        assertTrue(LoginToReadHandoff.consume("LOCAL_PIN_HOME_VISIBLE",4000))
        assertFalse(LoginToReadHandoff.consume("LOCAL_PIN_HOME_VISIBLE",4001))
        GoldSearchRun.startSearch(query)
        assertTrue(GoldSearchRun.openingProduct)
        assertEquals(isin, GoldSearchRun.query)
        GoldSearchRun.clear()
        assertFalse(GoldSearchRun.openingProduct)
        LoginToReadHandoff.arm(5000, isin)
        LoginToReadHandoff.clear()
        assertFalse(LoginToReadHandoff.consume("LOCAL_PIN_HOME_VISIBLE",6000))
    }
    @Test fun exactOwnerProductNavigatesSearchAndOpensOnlyIsolatedMatchingTitle() {
        val search = MorningReadPolicy.Node("Suche",clickable=true)
        assertEquals(MorningReadPolicy.Kind.SEARCH, MorningReadPolicy.ownerProductDecision(listOf(search),isin).kind)
        val input = MorningReadPolicy.Node("",id="search_input",editable=true)
        assertEquals(MorningReadPolicy.Kind.QUERY, MorningReadPolicy.ownerProductDecision(listOf(input),isin).kind)
        assertEquals(MorningReadPolicy.Kind.FOCUS, MorningReadPolicy.ownerProductDecision(listOf(input),isin,false).kind)
        val title = MorningReadPolicy.Node("Beispiel Silber Turbo $isin",clickable=true)
        val nodes = listOf(input.copy(text=isin), title)
        assertEquals(1, MorningReadPolicy.resultTapIndex(nodes,isin,explicitOwnerTarget=true))
        assertNull(MorningReadPolicy.resultTapIndex(nodes,isin)) // Gold importer unchanged.
        assertNull(MorningReadPolicy.resultTapIndex(nodes+title,isin,true))
        assertNull(MorningReadPolicy.resultTapIndex(nodes, "DE000FD0S0G4",true))
        for (word in listOf("Passwort", "Limitpreis", "Order bestätigen"))
            assertNull(MorningReadPolicy.resultTapIndex(nodes+MorningReadPolicy.Node(word),isin,true))
        val detail = listOf(title, MorningReadPolicy.Node("Übersicht"), MorningReadPolicy.Node("Order platzieren",clickable=true))
        assertEquals(MorningReadPolicy.Kind.READ, MorningReadPolicy.ownerProductDecision(detail,isin).kind)
        assertNotEquals(MorningReadPolicy.Kind.READ, MorningReadPolicy.ownerProductDecision(detail,"DE000FD0S0G4").kind)
        assertEquals(MorningReadPolicy.Kind.BLOCK, MorningReadPolicy.ownerProductDecision(detail+MorningReadPolicy.Node("Limitpreis"),isin).kind)
    }
}
