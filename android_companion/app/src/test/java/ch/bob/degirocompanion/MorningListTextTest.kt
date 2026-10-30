package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test
class MorningListTextTest {
    private val isin="DE000FD0S0G4"
    private val text="SG Gold Turbo Unlimited Mini Call BAR 3942 BP 3901.07 Bv 10 | $isin\nSociete Generale OTC EUR K V"
    private fun page(value:String=text)=listOf(MorningReadPolicy.Node("Hebelprodukte"),
        MorningReadPolicy.Node("Order platzieren",clickable=true),MorningReadPolicy.Node(value))
    @Test fun capturesOnlyProductRowWithoutAccountOrButtons() {
        val nodes=page()+MorningReadPolicy.Node("CHF 500 Account balance")
        val rows=MorningListText.capture(nodes,listOf(isin))!!
        assertEquals(1,rows.size)
        assertTrue(rows.single().endsWith("OTC EUR"))
        assertFalse(rows.single().contains("Account"))
        assertFalse(rows.single().contains("K V"))
    }
    @Test fun rejectsIncompleteConflictingAndProtectedRows() {
        assertNull(MorningListText.capture(page(text.substringBefore("Societe")),listOf(isin)))
        assertNull(MorningListText.capture(page()+MorningReadPolicy.Node(text.replace("3942","4000")),listOf(isin)))
        assertNull(MorningListText.capture(page(),listOf(isin,isin)))
        for(extra in listOf(MorningReadPolicy.Node("Order bestätigen"),MorningReadPolicy.Node("",password=true),MorningReadPolicy.Node("",sensitive=true)))
            assertNull(MorningListText.capture(page()+extra,listOf(isin)))
        assertNull(MorningListText.capture(page().drop(1),listOf(isin)))
    }
    @Test fun splitTitleIsinAndVenueAreReadFromTheirProductContainer() {
        val nodes=page().dropLast(1)+MorningReadPolicy.Node("",row=text)+
            MorningReadPolicy.Node("SG Gold Turbo Unlimited Mini Call BAR 3942 BP 3901.07 Bv 10",parent=2)+
            MorningReadPolicy.Node(isin,parent=2)+MorningReadPolicy.Node("Societe Generale OTC",parent=2)+MorningReadPolicy.Node("EUR",parent=2)
        assertEquals(1,MorningListText.capture(nodes,listOf(isin))!!.size)
    }
}
