package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test
class MorningReadPolicyTest {
    private val isin="DE000FD0S0G4"
    private fun node(text:String,click:Boolean=false)=MorningReadPolicy.Node(text,clickable=click)
    @Test fun onlySearchFieldCanReceiveIsin() {
        val input=MorningReadPolicy.Node("",id="nl.degiro.trader:id/search_src_text",editable=true)
        assertEquals(MorningReadPolicy.Kind.QUERY,MorningReadPolicy.decide(listOf(input),isin).kind)
        assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.decide(listOf(input.copy(id="amount")),isin).kind)
        assertEquals(MorningReadPolicy.Kind.SEARCH,MorningReadPolicy.decide(listOf(node("Suche",true)),isin).kind)
        assertEquals(MorningReadPolicy.Kind.WAIT,MorningReadPolicy.decide(listOf(node("Suche",true),node("Search",true)),isin).kind)
    }
    @Test fun resultNeedsExactSingleIsinWithoutSearchInputAncestorOrOrderAction() {
        val input=MorningReadPolicy.Node(isin,id="search",editable=true)
        val exact=node("SG Gold $isin",true)
        assertEquals(1,MorningReadPolicy.decide(listOf(input,exact),isin).index)
        for(bad in listOf(node("DE000FG77MY4",true),node("$isin DE000FG77MY4",true),node("Kauf $isin",true),exact.copy(containsInput=true)))
            assertEquals(MorningReadPolicy.Kind.WAIT,MorningReadPolicy.decide(listOf(input,bad),isin).kind)
    }
    @Test fun searchLabelOnChildCanIdentifyOnlyItsOwnClickableIcon() {
        val icon=MorningReadPolicy.Node("",clickable=true,row="Suchen")
        assertEquals(MorningReadPolicy.Kind.SEARCH,MorningReadPolicy.decide(listOf(icon,node("Suchen")),isin).kind)
        assertEquals(MorningReadPolicy.Kind.WAIT,MorningReadPolicy.decide(listOf(icon.copy(row="Suchen\nKauf")),isin).kind)
        assertEquals(MorningReadPolicy.Kind.WAIT,MorningReadPolicy.decide(listOf(icon.copy(containsInput=true)),isin).kind)
        assertEquals(MorningReadPolicy.Kind.SEARCH,MorningReadPolicy.decide(listOf(node("Search instruments",true)),isin).kind)
    }
    @Test fun semanticDescriptionsAndHintsSurviveEmptyOrEnteredText() {
        val icon=node("",true).copy(description="Suchen")
        assertEquals(MorningReadPolicy.Kind.SEARCH,MorningReadPolicy.decide(listOf(icon),isin).kind)
        val input=node("").copy(editable=true,hint="Search instruments")
        assertTrue(MorningReadPolicy.isSearchInput("","","Search instruments"))
        assertFalse(MorningReadPolicy.isSearchInput("amount","","Search orders"))
        assertEquals(MorningReadPolicy.Kind.QUERY,MorningReadPolicy.decide(listOf(input),isin).kind)
        assertEquals(MorningReadPolicy.Kind.RESULT,MorningReadPolicy.decide(listOf(input.copy(text=isin),node(isin,true)),isin).kind)
        for(bad in listOf(icon.copy(description="Order bestätigen"),icon.copy(hint="Passwort"),input.copy(hint="Search orders")))
            assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.decide(listOf(bad),isin).kind)
    }
    @Test fun protectedLoginAndOrderViewsAlwaysStop() {
        for(n in listOf(node("Passwort"),node("Orderart"),node("Anmelden"),node("Gold").copy(sensitive=true)))
            assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.decide(listOf(node(isin),node("Übersicht"),n),isin).kind)
    }
    @Test fun detailNeedsIdentityAndNeverClicksBuy() {
        assertEquals(MorningReadPolicy.Kind.READ,MorningReadPolicy.decide(listOf(node(isin),node("Übersicht"),node("KAUF",true)),isin).kind)
        assertEquals(MorningReadPolicy.Kind.BACK,MorningReadPolicy.decide(listOf(node("DE000FG77MY4"),node("Übersicht")),isin).kind)
        assertEquals(MorningReadPolicy.Kind.WAIT,MorningReadPolicy.decide(listOf(node("KAUF",true)),isin).kind)
    }
}
