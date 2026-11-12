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
    @Test fun samsungAggregateWebViewCanSupplyTwoDistinctExactProductRows() {
        val other="DE000SQ02JQ6"
        val title1="SG Gold Turbo Unlimited Mini Call BAR 3942 BP 3901.07 Bv 10 | $isin"
        val title2="SG Gold Turbo Unlimited Mini Call BAR 2144 BP 2122.67 Bv 10 | $other"
        val row1="$title1\nSociete Generale OTC EUR K V"
        val row2="$title2\nSociete Generale OTC EUR K V"
        val nodes=listOf(
            MorningReadPolicy.Node("Hebelprodukte"),
            MorningReadPolicy.Node("Order platzieren",clickable=true),
            MorningReadPolicy.Node("",row="$row1\n$row2"),
            MorningReadPolicy.Node(title1,parent=2),
            MorningReadPolicy.Node(title2,parent=2),
            MorningReadPolicy.Node("CHF 504.74 account"))
        val found=MorningListText.capture(nodes,listOf(isin,other))!!
        assertEquals(2,found.size)
        assertTrue(found[0].contains(isin))
        assertTrue(found[1].contains(other))
        assertTrue(found.all { it.endsWith("OTC EUR") })
        assertTrue(found.none { it.contains("account") || it.contains("K V") })
        assertNull(MorningListText.capture(nodes,listOf(other,isin)))
        assertNull(MorningListText.capture(nodes+
            MorningReadPolicy.Node("Order bestätigen"),listOf(isin,other)))
    }
    @Test fun splitTitleIsinAndVenueAreReadFromTheirProductContainer() {
        val nodes=page().dropLast(1)+MorningReadPolicy.Node("",row=text)+
            MorningReadPolicy.Node("SG Gold Turbo Unlimited Mini Call BAR 3942 BP 3901.07 Bv 10",parent=2)+
            MorningReadPolicy.Node(isin,parent=2)+MorningReadPolicy.Node("Societe Generale OTC",parent=2)+MorningReadPolicy.Node("EUR",parent=2)
        assertEquals(1,MorningListText.capture(nodes,listOf(isin))!!.size)
    }
    @Test fun detachedCurrencyColumnCanUseExactPositionedAppTextWithoutOcr() {
        val other="DE000SQ02JQ6"
        val title1="SG Gold Turbo Unlimited Mini Call BAR 3942 BP 3901.07 Bv 10 | $isin"
        val title2="SG Gold Turbo Unlimited Mini Call BAR 2166 BP 2126.05 Bv 10 | $other"
        val values=listOf(title1,"Societe Generale OTC",title2,"Societe Generale OTC","EUR","CHF")
        val nodes=page().dropLast(1)+values.map { MorningReadPolicy.Node(it) }
        val xy=listOf(10 to 100,10 to 150,10 to 250,10 to 300,500 to 152,500 to 302)
        val parts=values.indices.map { i ->
            val (x,y)=xy[i]
            MorningListText.Positioned(i+2,MorningOcrLayout.Line(values[i],x,y,x+100,y+20))
        }
        // Tree traversal emits the currency column last, which the old
        // container-string extraction cannot assign to individual products.
        assertNull(MorningListText.capture(nodes,listOf(isin,other)))
        val rows=MorningListText.capturePositioned(nodes,parts,listOf(isin,other))!!
        assertTrue(rows[0].contains("BP 3901.07"));assertTrue(rows[0].endsWith("OTC EUR"))
        assertTrue(rows[1].contains("BP 2126.05"));assertTrue(rows[1].endsWith("OTC CHF"))
        assertEquals(rows,MorningListText.capturePositioned(nodes,parts.reversed(),listOf(isin,other)))
        assertNull(MorningListText.capturePositioned(nodes,parts,listOf(other,isin)))
        assertNull(MorningListText.capturePositioned(nodes,parts.dropLast(1),listOf(isin,other)))
        assertNull(MorningListText.capturePositioned(nodes,parts+parts.last(),listOf(isin,other)))
        val invented=parts.toMutableList();invented[0]=parts[0].copy(line=parts[0].line.copy(text=title1.replace("3901.07","4000")))
        assertNull(MorningListText.capturePositioned(nodes,invented,listOf(isin,other)))
        val overlap=parts.toMutableList();overlap[5]=parts[5].copy(line=parts[5].line.copy(top=152,bottom=172))
        assertNull(MorningListText.capturePositioned(nodes,overlap,listOf(isin,other)))
        for(bad in listOf(nodes[2].copy(editable=true),nodes[2].copy(sensitive=true),nodes[2].copy(enabled=false))) {
            val changed=nodes.toMutableList();changed[2]=bad
            assertNull(MorningListText.capturePositioned(changed,parts,listOf(isin,other)))
        }
        assertNull(MorningListText.capturePositioned(nodes+MorningReadPolicy.Node("Order bestätigen"),parts,listOf(isin,other)))
    }

}
