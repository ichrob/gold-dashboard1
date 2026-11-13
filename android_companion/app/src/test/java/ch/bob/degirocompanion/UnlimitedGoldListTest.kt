package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

/** Synthetic rows only; no account or handset observations. */
class UnlimitedGoldListTest {
    private val isin = "DE000FD0S0G4"
    private fun title(direction: String = "Long") =
        "BNP GOLD Unlimited $direction SL 3800.25 STR 3800.25 R 10 | $isin"
    private fun page(row: String) = listOf(
        MorningReadPolicy.Node("Gold", editable=true, hint="Suche"),
        MorningReadPolicy.Node("Hebelprodukte", selected=true),
        MorningReadPolicy.Node(row, row=row)
    )

    @Test fun unlimitedRowsParticipateInListCaptureAndDiscovery() {
        for (direction in listOf("Long", "Short")) {
            val nodes=page(title(direction))
            assertEquals(listOf(isin), MorningReadPolicy.captureGoldList(nodes, true).isins)
            assertEquals(listOf(isin), MorningReadPolicy.discoverGold(nodes).isins)
            // Scrolling hides the search field but must retain the final row.
            assertEquals(listOf(isin), MorningReadPolicy.captureGoldList(nodes.drop(1), true).isins)
        }
    }

    @Test fun unrelatedOrIncompleteUnlimitedLabelsAreNotCandidates() {
        for (row in listOf(
            "BNP GOLD Unlimited Long | $isin",
            title().replace("BNP", "Other"),
            title().replace("GOLD", "Silver"),
            title().replace("Long", "Certificate"),
            title().replace("STR 3800.25", ""),
            title().replace("SL 3800.25", ""),
            title().replace("R 10", ""),
            title()+" Kaufen",
            title().replace(isin, "DE000FD0S0G5")
        )) assertTrue(row, MorningReadPolicy.captureGoldList(page(row), true).isins.isEmpty())
        assertTrue(MorningReadPolicy.discoverGold(page(title()+" Faktor")).isins.isEmpty())
    }

    @Test fun partialRowsAndProtectedViewsRemainBlocked() {
        val partial=page(title()).mapIndexed { i,n ->
            if(i==2) n.copy(captureComplete=false) else n
        }
        assertTrue(MorningReadPolicy.captureGoldList(partial,true).isins.isEmpty())
        for (marker in listOf("Order bestätigen", "Limitpreis", "Stückzahl", "Passwort")) {
            assertEquals(MorningReadPolicy.Kind.BLOCK,
                MorningReadPolicy.captureGoldList(page(title())+MorningReadPolicy.Node(marker),true).kind)
        }
    }

    @Test fun unlimitedResultStillTargetsOnlyProductTitle() {
        val nodes=listOf(
            MorningReadPolicy.Node(isin,editable=true,hint="Suche"),
            MorningReadPolicy.Node("Hebelprodukte"),
            MorningReadPolicy.Node(title(),clickable=true),
            MorningReadPolicy.Node("K",clickable=true),
            MorningReadPolicy.Node("V",clickable=true)
        )
        assertEquals(2, MorningReadPolicy.resultTapIndex(nodes,isin))
        assertNull(MorningReadPolicy.resultTapIndex(nodes+MorningReadPolicy.Node("Order bestätigen"),isin))
        assertNull(MorningReadPolicy.resultTapIndex(nodes,"DE000FG77MY4"))
    }

    @Test fun semanticTransferIncludesUnlimitedRowWithVenue() {
        val row=title()+"\nBNP OTC EUR"
        assertEquals(listOf(row.replace("\n"," ")),MorningListText.capture(page(row),listOf(isin)))
    }
}
