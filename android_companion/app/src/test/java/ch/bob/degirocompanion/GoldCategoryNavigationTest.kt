package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test
class GoldCategoryNavigationTest {
    @Test fun importedDetailsRestoreScrolledSearchWithoutWeakeningOrderGuards() {
        val rows=listOf(MorningReadPolicy.Node("Hebelprodukte"),
            MorningReadPolicy.Node("Order platzieren",clickable=true),
            MorningReadPolicy.Node("Gold Turbo DE000FD0S0G4"))
        assertNull(MorningReadPolicy.detailSearchRestore(rows,false))
        val restore=MorningReadPolicy.detailSearchRestore(rows,true)!!
        assertEquals(MorningReadPolicy.Kind.COLLECT,restore.kind)
        assertEquals(-1,restore.index) // Never target a synthetic input or order launcher.
        assertEquals(listOf("DE000FD0S0G4"),restore.isins)
        for(extra in listOf(MorningReadPolicy.Node("Order bestätigen"),MorningReadPolicy.Node("Limitpreis"),
            MorningReadPolicy.Node("",password=true),MorningReadPolicy.Node("",sensitive=true),
            MorningReadPolicy.Node("Gold",editable=true,id="search-input"),
            MorningReadPolicy.Node("",editable=true,id="quantity")))
            assertNull(MorningReadPolicy.detailSearchRestore(rows+extra,true))
        assertNull(MorningReadPolicy.detailSearchRestore(rows.drop(1),true))
    }
    @Test fun restoredTopUsesRealSearchAndNeverScrollsAgain() {
        val rows=listOf(MorningReadPolicy.Node("Hebelprodukte"),
            MorningReadPolicy.Node("Order platzieren",clickable=true),
            MorningReadPolicy.Node("Gold Turbo DE000FD0S0G4"),
            MorningReadPolicy.Node("Top Ergebnisse"),
            MorningReadPolicy.Node("Suchen",clickable=true))
        assertNull(MorningReadPolicy.detailSearchRestore(rows,true))
        val action=MorningReadPolicy.detailDecision(rows,"DE000FD0S0G4",true)
        assertEquals(MorningReadPolicy.Kind.SEARCH,action.kind)
        assertEquals(4,action.index)
        for(extra in listOf(MorningReadPolicy.Node("Order bestätigen"),MorningReadPolicy.Node("Limitpreis"),
            MorningReadPolicy.Node("",password=true),MorningReadPolicy.Node("",editable=true,id="quantity")))
            assertEquals(MorningReadPolicy.Kind.BLOCK, MorningReadPolicy.detailDecision(rows+extra,"DE000FD0S0G4",true).kind)
        assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.detailDecision(rows,"invalid",true).kind)
    }
    @Test fun detailFocusUsesIsinInsteadOfCompletedGoldQuery() {
        val nodes=listOf(MorningReadPolicy.Node("Gold",id="search-input",editable=true,focused=false),
            MorningReadPolicy.Node("Order platzieren",clickable=true),
            MorningReadPolicy.Node("Gold Turbo DE000FD0S0G4"))
        assertEquals(MorningReadPolicy.Kind.COLLECT,MorningReadPolicy.discoverGold(nodes).kind)
        assertEquals(MorningReadPolicy.Kind.FOCUS,MorningReadPolicy.detailDecision(nodes,"DE000FD0S0G4",true).kind)
    }
    @Test fun realSearchEndsRestoreEvenWhenTopLabelIsMissingFromTree() {
        val rows=listOf(MorningReadPolicy.Node("Hebelprodukte"),
            MorningReadPolicy.Node("Order platzieren",clickable=true),
            MorningReadPolicy.Node("Gold Turbo DE000FD0S0G4"),
            MorningReadPolicy.Node("Suchen",clickable=true))
        assertNull(MorningReadPolicy.detailSearchRestore(rows,true))
        val action=MorningReadPolicy.detailDecision(rows,"DE000FD0S0G4",true,false)
        assertEquals(MorningReadPolicy.Kind.SEARCH,action.kind)
        assertEquals(3,action.index)
        val aggregate=rows.dropLast(1)+rows.last().copy(row="Suchen\nOrder platzieren")
        assertNotEquals(MorningReadPolicy.Kind.SEARCH,MorningReadPolicy.detailDecision(aggregate,"DE000FD0S0G4",true,false).kind)
        for(extra in listOf(MorningReadPolicy.Node("Order bestätigen"),MorningReadPolicy.Node("Limitpreis"),
            MorningReadPolicy.Node("",password=true),MorningReadPolicy.Node("",sensitive=true)))
            assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.detailDecision(rows+extra,"DE000FD0S0G4",true,false).kind)
    }
    @Test fun focusedGoldStillOpensKeyboardBeforeReplacement() {
        val nodes=listOf(MorningReadPolicy.Node("Gold",id="search-input",editable=true,focused=true,imeEnter=true),
            MorningReadPolicy.Node("Order platzieren",clickable=true))
        val target="DE000FD0S0G4"
        assertEquals(MorningReadPolicy.Kind.FOCUS,MorningReadPolicy.detailDecision(nodes,target,true,false).kind)
        assertEquals(MorningReadPolicy.Kind.QUERY,MorningReadPolicy.detailDecision(nodes,target,true,true).kind)
        val written=listOf(nodes.first().copy(text=target),nodes.last())
        assertEquals(MorningReadPolicy.Kind.SUBMIT,MorningReadPolicy.detailDecision(written,target,true,true).kind)
    }
    private val input=MorningReadPolicy.Node("Gold",id="search-input",editable=true,focused=false)
    private val tab=MorningReadPolicy.Node("Hebelprodukte",clickable=true)
    @Test fun selectsVisibleCategoryWithoutRefocusingQuery() {
        val launcher=MorningReadPolicy.Node("Order platzieren",clickable=true)
        val action=MorningReadPolicy.discoverGold(listOf(input,tab,launcher))
        assertEquals(MorningReadPolicy.Kind.CATEGORY,action.kind)
        assertEquals(1,action.index)
        assertEquals(MorningReadPolicy.Kind.WAIT,MorningReadPolicy.discoverGold(listOf(input,tab.copy(selected=true))).kind)
    }
    @Test fun scrollsOnlyIsolatedHorizontalCategoryStrip() {
        val strip=MorningReadPolicy.Node("",row="Aktien\nETFs\nAnleihen",scrollRight=true)
        assertEquals(MorningReadPolicy.Kind.CATEGORY_SCROLL,MorningReadPolicy.discoverGold(listOf(input,strip)).kind)
        for(n in listOf(strip.copy(row="Aktien\nCHF 500"),strip.copy(containsInput=true),strip.copy(scrollRight=false)))
            assertNotEquals(MorningReadPolicy.Kind.CATEGORY_SCROLL,MorningReadPolicy.discoverGold(listOf(input,n)).kind)
        assertEquals(MorningReadPolicy.Kind.CATEGORY,MorningReadPolicy.discoverGold(listOf(input,strip,tab)).kind)
    }
    @Test fun waitsOnAmbiguityAndPreservesOrderGuards() {
        assertEquals(MorningReadPolicy.Kind.WAIT,MorningReadPolicy.discoverGold(listOf(input,tab,tab)).kind)
        assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.discoverGold(listOf(input,tab,MorningReadPolicy.Node("Limitpreis"))).kind)
        assertNotEquals(MorningReadPolicy.Kind.CATEGORY,MorningReadPolicy.discoverGold(listOf(input,tab.copy(row="Hebelprodukte\nKaufen"))).kind)
    }
    @Test fun collectsLeverageResultsAfterCategoryNavigation() {
        val row=MorningReadPolicy.Node("Gold Turbo DE000FD0S0G4",clickable=true)
        assertEquals(MorningReadPolicy.Kind.COLLECT,MorningReadPolicy.discoverGold(listOf(input,tab.copy(selected=true),row)).kind)
        val stock=MorningReadPolicy.Node("Gold stock US38141G1040",clickable=true)
        assertEquals(MorningReadPolicy.Kind.CATEGORY,MorningReadPolicy.discoverGold(listOf(input,tab,stock)).kind)
    }
    @Test fun staysInTopResultsAndNeverOpensAllResults() {
        val all=MorningReadPolicy.Node("Alle Ergebnisse in Hebelprodukte",clickable=true)
        val row=MorningReadPolicy.Node("Gold Turbo DE000FD0S0G4",clickable=true)
        val action=MorningReadPolicy.discoverGold(listOf(input,tab.copy(selected=true),all,row))
        assertEquals(MorningReadPolicy.Kind.COLLECT,action.kind)
        assertEquals(listOf("DE000FD0S0G4"),action.isins)
        assertEquals(MorningReadPolicy.Kind.COLLECT,MorningReadPolicy.discoverGold(listOf(input,tab.copy(selected=true),all,row.copy(clickable=false))).kind)
        assertNotEquals(MorningReadPolicy.Kind.CATEGORY, MorningReadPolicy.discoverGold(listOf(input,all.copy(row="Alle Ergebnisse in Hebelprodukte\nKaufen"))).kind)
        assertEquals(MorningReadPolicy.Kind.BLOCK, MorningReadPolicy.discoverGold(listOf(input,all,MorningReadPolicy.Node("Order bestätigen"))).kind)
    }
    @Test fun capturedListContinuesWithoutSearchHeaderButNeverAnOrderForm() {
        val rows=listOf(tab.copy(selected=true),MorningReadPolicy.Node("Order platzieren",clickable=true),
            MorningReadPolicy.Node("SG Gold Future Faktor Long HB 15 | DE000FG8K0P8"),
            MorningReadPolicy.Node("Gold Turbo DE000FD0S0G4"))
        assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.captureGoldList(rows,false).kind)
        val result=MorningReadPolicy.captureGoldList(rows,true)
        assertEquals(MorningReadPolicy.Kind.COLLECT,result.kind)
        assertEquals(listOf("DE000FG8K0P8","DE000FD0S0G4"),result.isins)
        assertEquals(listOf("DE000FG8K0P8"),MorningReadPolicy.captureGoldList(rows.dropLast(1)+rows.last().copy(captureComplete=false),true).isins)
        for(extra in listOf(MorningReadPolicy.Node("Order bestätigen"),MorningReadPolicy.Node("Limitpreis"),
            MorningReadPolicy.Node("",password=true),MorningReadPolicy.Node("",editable=true,id="quantity")))
            assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.captureGoldList(rows+extra,true).kind)
        assertNotEquals(MorningReadPolicy.Kind.COLLECT,MorningReadPolicy.captureGoldList(rows.drop(1),true).kind)
        // Ordinary product discovery still excludes factors.
        assertEquals(listOf("DE000FD0S0G4"),MorningReadPolicy.discoverGold(listOf(input)+rows).isins)
    }
    @Test fun webViewTabWithoutSelectedFlagCanContinueOnlyCapturedTopResults() {
        val row=MorningReadPolicy.Node("Gold Turbo DE000FD0S0G4")
        val launcher=MorningReadPolicy.Node("Order platzieren",clickable=true)
        val scrolled=listOf(tab,row,launcher)
        assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.captureGoldList(scrolled,false).kind)
        assertEquals(MorningReadPolicy.Kind.COLLECT,MorningReadPolicy.captureGoldList(scrolled,true).kind)
        assertNotEquals(MorningReadPolicy.Kind.COLLECT,MorningReadPolicy.captureGoldList(scrolled+tab,true).kind)
        assertNotEquals(MorningReadPolicy.Kind.COLLECT,MorningReadPolicy.captureGoldList(scrolled.drop(1),true).kind)
        for(extra in listOf(MorningReadPolicy.Node("Order bestätigen"),MorningReadPolicy.Node("Limitpreis"),
            MorningReadPolicy.Node("",password=true),MorningReadPolicy.Node("",editable=true,id="quantity")))
            assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.captureGoldList(scrolled+extra,true).kind)
        val first=listOf(input,tab,MorningReadPolicy.Node("Top Ergebnisse"),launcher,
            MorningReadPolicy.Node("Gold Future Faktor Long DE000FG8K0P8"),row)
        assertEquals(listOf("DE000FG8K0P8","DE000FD0S0G4"),MorningReadPolicy.captureGoldList(first,false).isins)
    }
}
