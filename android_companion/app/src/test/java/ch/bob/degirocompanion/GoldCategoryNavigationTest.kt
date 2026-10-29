package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test
class GoldCategoryNavigationTest {
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
}
