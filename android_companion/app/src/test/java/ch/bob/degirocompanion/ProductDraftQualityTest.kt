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
}
