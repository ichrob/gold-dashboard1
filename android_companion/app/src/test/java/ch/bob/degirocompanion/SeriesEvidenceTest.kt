package ch.bob.degirocompanion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class SeriesEvidenceTest {
    private val isin = "DE000PJ9NB98"

    @Test fun recognizesBothImagesEvenWhenZerosLookLikeLetters() {
        val result = SeriesEvidence.analyze(listOf(
            "Symbol | ISIN\nDE000PJ9NB98\nBörse BNP OTC\nZuletzt € 11,31",
            "DEOOOPJ9NB98 • BNP OTC\nBNP GOLD Unlimited Long\n€11,31"
        ))
        assertNotNull(result)
        assertEquals(isin, result!!.isin)
        assertEquals(2, result.imageCount)
        assertEquals(2, result.anchorCount)
        assertFalse(result.provisional)
    }

    @Test fun associatesNeighboringCropWithoutVisibleIsinButKeepsProvisional() {
        val result = SeriesEvidence.analyze(listOf(
            "Symbol ISIN\nDE000PJ9NB98\nBörse BNP OTC",
            "BNP GOLD Unlimited Long\n€ 11,31\nBNP OTC"
        ))
        assertNotNull(result)
        assertEquals(isin, result!!.isin)
        assertEquals(1, result.anchorCount)
        assertEquals(2, result.imageCount)
        assertTrue(result.provisional)
    }

    @Test fun rejectsConflictingValidIsins() {
        assertNull(SeriesEvidence.analyze(listOf(
            "DE000PJ9NB98", "DE000FG14AV8"
        )))
    }

    @Test fun rejectsConflictingIsinEvenWhenOtherTokenHasBadChecksum() {
        assertNull(SeriesEvidence.analyze(listOf(
            "DE000PJ9NB98", "DE000PJ9NB99"
        )))
    }

    @Test fun rejectsNoAnchorAndInvalidBatches() {
        assertNull(SeriesEvidence.analyze(listOf("BNP OTC", "€11,31")))
        assertNull(SeriesEvidence.analyze(emptyList()))
        assertNull(SeriesEvidence.analyze(List(5) { "DE000PJ9NB98" }))
    }

    @Test fun preservesStrictChecksumAndRepairsOnlyVisuallyConfusableOCR() {
        assertTrue(SeriesEvidence.validIsin(isin))
        assertFalse(SeriesEvidence.validIsin("DE000PJ9NB99"))
        assertEquals(setOf(isin), SeriesEvidence.validCandidates("DEOOOPJ9NB98"))
        assertEquals(setOf(isin), SeriesEvidence.validCandidates("DE000PJ9NB9B"))
        assertTrue(SeriesEvidence.validCandidates("DE000PJ9NB99").isEmpty())
    }
}
