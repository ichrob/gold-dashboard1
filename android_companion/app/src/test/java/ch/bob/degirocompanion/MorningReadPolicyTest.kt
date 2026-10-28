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
    @Test fun markedSearchPlaceholderCanIdentifyInputWithoutViewId() {
        for(label in listOf("Suche", "Search instruments", "Name, ISIN oder Symbol", "Mit Namen, ISIN oder Symbol suchen")) {
            val hint=MorningReadPolicy.inputHint("",label,true)
            val input=node("").copy(editable=true,hint=hint)
            assertEquals(MorningReadPolicy.Kind.QUERY,MorningReadPolicy.decide(listOf(input),isin).kind)
            assertEquals("",MorningReadPolicy.inputHint("",label,false))
        }
        for(label in listOf("Passwort", "Limitpreis", "Search orders", "ISIN", isin)) {
            assertEquals("",MorningReadPolicy.inputHint("",label,true))
            assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.decide(listOf(node("").copy(editable=true)),isin).kind)
        }
    }
    @Test fun marketSearchLabelSupportsButtonHintAndDescriptionWithoutBypassingProtection() {
        val label="Mit Namen, ISIN oder Symbol suchen"
        for(button in listOf(node(label,true),node("",true).copy(description=label),node("",true).copy(row=label))) {
            assertEquals(MorningReadPolicy.Kind.SEARCH,MorningReadPolicy.decide(listOf(node("Märkte"),button),isin).kind)
            assertEquals("PROTECTED_ORDER_TYPE",MorningReadPolicy.decide(listOf(button,node("Orderart")),isin).code)
        }
        val input=node("").copy(editable=true,hint=label)
        assertTrue(MorningReadPolicy.isSearchInput("","",label))
        assertEquals(MorningReadPolicy.Kind.QUERY,MorningReadPolicy.decide(listOf(input),isin).kind)
        assertEquals(MorningReadPolicy.Kind.RESULT,MorningReadPolicy.decide(listOf(input.copy(text=isin),node(isin,true)),isin).kind)
        assertEquals(MorningReadPolicy.Kind.WAIT,MorningReadPolicy.decide(listOf(node("Andere "+label,true)),isin).kind)
        assertEquals("PROTECTED_ORDER_PRICE",MorningReadPolicy.decide(listOf(input,node("Limitpreis")),isin).code)
        assertEquals("PROTECTED_LOGIN",MorningReadPolicy.decide(listOf(input,node("Anmelden")),isin).code)
    }
    @Test fun protectionCausesAreDistinctWithoutExportingScreenText() {
        val cases=listOf(
            node("").copy(password=true,sensitive=true,editable=true) to "PROTECTED_PASSWORD",
            node("").copy(sensitive=true,editable=true) to "PROTECTED_SENSITIVE_INPUT",
            node("").copy(sensitive=true) to "PROTECTED_SENSITIVE_CONTENT",
            node("Anmelden") to "PROTECTED_LOGIN",
            node("Orderart") to "PROTECTED_ORDER_TYPE",
            node("").copy(editable=true) to "UNRECOGNIZED_INPUT")
        for((blocked,code) in cases) {
            val action=MorningReadPolicy.decide(listOf(node("Suchen",true),blocked),isin)
            assertEquals(MorningReadPolicy.Kind.BLOCK,action.kind)
            assertEquals(code,action.code)
        }
        assertEquals("PROTECTED_PASSWORD",MorningReadPolicy.decide(listOf(node("Suchen").copy(editable=true,password=true)),isin).code)
    }
    @Test fun everyExistingOrderMarkerStillBlocksAndExportsOnlyFixedCause() {
        val cases=listOf("Order platzieren" to "CONFIRM", "Order bestätigen" to "CONFIRM",
            "Place order" to "CONFIRM", "Confirm order" to "CONFIRM",
            "Orderart" to "TYPE", "Ordertyp" to "TYPE", "Limitpreis" to "PRICE",
            "Stückzahl" to "QUANTITY", "Anzahl kaufen" to "QUANTITY")
        for ((label,cause) in cases) for (n in listOf(node(label),node("").copy(description=label),node("").copy(hint=label))) {
            val action=MorningReadPolicy.decide(listOf(node("Suchen",true),n),isin)
            assertEquals(MorningReadPolicy.Kind.BLOCK,action.kind)
            assertEquals("PROTECTED_ORDER_"+cause,action.code)
            assertEquals(-1,action.index)
        }
    }
    @Test fun isolatedMarketLauncherAllowsOnlyExplicitProductSearch() {
        val search=node("Mit Namen, ISIN oder Symbol suchen",true)
        val launcher=node("",true).copy(description="Order platzieren")
        val home=listOf(node("Märkte"),node("Indizes"),search,launcher)
        val action=MorningReadPolicy.decide(home,isin)
        assertEquals(MorningReadPolicy.Kind.SEARCH,action.kind)
        assertEquals(2,action.index)
        // A generic toolbar search icon does not compete with the exact product label.
        assertEquals(2,MorningReadPolicy.decide(home+node("Suche",true),isin).index)
        for (bad in listOf(
            home+node("Order bestätigen",true), home+node("Confirm order",true),
            home+node("Orderart"),home+node("Limitpreis"),home+node("Stückzahl"),
            home+node("").copy(editable=true),home+node("").copy(password=true),
            home+node("").copy(sensitive=true),home+node("Anmelden"),
            home+search,home+launcher,
            home.filterNot { it.text=="Indizes" },home.filterNot { it.text=="Märkte" },
            home.take(3)+launcher.copy(clickable=false),
            home.take(3)+launcher.copy(row="Order platzieren\nKauf"),
            home.take(3)+launcher.copy(description="Order bestätigen"),
            home.take(2)+search.copy(row="Mit Namen, ISIN oder Symbol suchen\nOrder platzieren")+launcher,
            home.take(2)+search.copy(clickable=false)+launcher,
            home.take(2)+search.copy(editable=true)+launcher,
            home.take(2)+node("Suche",true)+launcher,
            home+node(isin).copy(editable=true,hint="Suche"))) {
            assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.decide(bad,isin).kind)
        }
        // An order launcher on product/results views remains blocked.
        assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.decide(listOf(node(isin),node("Übersicht"),launcher),isin).kind)
    }
    @Test fun detailNeedsIdentityAndNeverClicksBuy() {
        assertEquals(MorningReadPolicy.Kind.READ,MorningReadPolicy.decide(listOf(node(isin),node("Übersicht"),node("KAUF",true)),isin).kind)
        assertEquals(MorningReadPolicy.Kind.BACK,MorningReadPolicy.decide(listOf(node("DE000FG77MY4"),node("Übersicht")),isin).kind)
        assertEquals(MorningReadPolicy.Kind.WAIT,MorningReadPolicy.decide(listOf(node("KAUF",true)),isin).kind)
    }
}
