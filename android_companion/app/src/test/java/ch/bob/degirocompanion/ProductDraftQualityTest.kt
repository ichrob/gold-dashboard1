package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class ProductDraftQualityTest {
    @Test fun acceptsNewOrEqualEvidence() {
        assertTrue(ProductDraftQuality.noRegression(listOf("Hebel", "KO-Schwelle", "Bv"), listOf("Bv")))
        assertTrue(ProductDraftQuality.noRegression(listOf("Bv"), listOf("Bv")))
        assertTrue(ProductDraftQuality.noRegression(emptyList(), emptyList()))
    }

    @Test fun rejectsLostEvidenceEvenIfMissingCountsMatch() {
        assertFalse(ProductDraftQuality.noRegression(listOf("Hebel", "Bv"), listOf("KO-Schwelle", "Bv")))
        assertFalse(ProductDraftQuality.noRegression(listOf("Hebel"), listOf("Hebel", "Anzeigezeit")))
        assertFalse(ProductDraftQuality.noRegression(emptyList(), listOf("Brief")))
    }
    @Test fun richerScreenReplacesOnlyWithoutLosingAnEarlierField() {
        val old = "ISIN: DE000FD0S0G4\nWährung (Anzeige ungeprüft): EUR\nZuletzt (Anzeige ungeprüft): 10,20\nAnzeigezeit (Anzeige ungeprüft): 31/10/2026 10:00"
        val less = "ISIN: DE000FD0S0G4\nWährung (Anzeige ungeprüft): EUR\nZuletzt (Anzeige ungeprüft): 10,20"
        val other = "ISIN: DE000FD0S0G4\nWährung (Anzeige ungeprüft): EUR\nGeld (Anzeige ungeprüft): 10,10"
        val more = old + "\nHandelsplatz (Anzeige ungeprüft): SG OTC"
        assertFalse(ProductDraftQuality.preferScreen(old, less))
        assertFalse(ProductDraftQuality.preferScreen(old, other))
        assertTrue(ProductDraftQuality.preferScreen(old, more))
        assertFalse(ProductDraftQuality.preferScreen(more, old))
    }

    @Test fun aMatchingBidAskPairTakesPriorityOverSingleLastQuote() {
        val last = "ISIN: DE000FD0S0G4\nZuletzt (Anzeige ungeprüft): 10,20"
        val pair = "ISIN: DE000FD0S0G4\nGeld (Anzeige ungeprüft): 10,10\nBrief (Anzeige ungeprüft): 10,30"
        assertTrue(ProductDraftQuality.preferScreen(last, pair))
        assertFalse(ProductDraftQuality.preferScreen(pair, last))
        assertFalse(ProductDraftQuality.preferScreen(pair, ""))
        assertTrue(ProductDraftQuality.preferScreen("", pair))
    }

}
