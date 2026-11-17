package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

/** The original ten-row DEGIRO list may contain a non-KO leverage certificate.
 * Record its original ISIN, but never recommend it as a KO product.
 */
class ConstantLeverageListTest {
    private val isin = "DE000PK778A1"
    private val title = "BNP GOLD (COMEX) DEC. 26 Constant Leverage short R 1 | $isin"
    private val input = MorningReadPolicy.Node("Gold",editable=true,hint="Suche")
    private val tab = MorningReadPolicy.Node("Hebelprodukte",selected=true)
    private val row = MorningReadPolicy.Node(title)

    @Test fun factorStyleIsIncludedInSourceListButNotDiscoveryRanking() {
        val visible=listOf(input,tab,MorningReadPolicy.Node("Top Ergebnisse"),row)
        assertEquals(listOf(isin),MorningReadPolicy.captureGoldList(visible,false).isins)
        val scrolled=listOf(tab,row)
        assertEquals(listOf(isin),MorningReadPolicy.captureGoldList(scrolled,true).isins)
        // The research shortlist excludes constant-leverage/factor products.
        assertTrue(MorningReadPolicy.discoverGold(visible).isins.isEmpty())
    }

    @Test fun completeSourceRowAndProtectedOrderViewAreRequired() {
        val incomplete=row.copy(captureComplete=false)
        assertTrue(MorningReadPolicy.captureGoldList(listOf(tab,incomplete),true).isins.isEmpty())
        for(extra in listOf(MorningReadPolicy.Node("Order bestätigen"),
                MorningReadPolicy.Node("Limitpreis"),
                MorningReadPolicy.Node("",password=true),
                MorningReadPolicy.Node("",editable=true,id="quantity"))) {
            assertEquals(MorningReadPolicy.Kind.BLOCK,
                MorningReadPolicy.captureGoldList(listOf(tab,row,extra),true).kind)
        }
    }

    @Test fun marketWithoutGoldOrWithoutExactIsinIsNotACandidate() {
        assertTrue(MorningReadPolicy.captureGoldList(listOf(tab,
            row.copy(text=title.replace("GOLD","SILVER"),row=title.replace("GOLD","SILVER"))),true).isins.isEmpty())
        assertTrue(MorningReadPolicy.captureGoldList(listOf(tab,
            row.copy(text=title.replace(isin,"DE000PK778A2"),row=title.replace(isin,"DE000PK778A2"))),true).isins.isEmpty())
    }
}
