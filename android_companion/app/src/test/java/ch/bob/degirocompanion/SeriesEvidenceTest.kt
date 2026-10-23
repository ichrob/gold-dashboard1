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

    @Test fun secondImageWithSplitIsinIsRecognized() {
        val series = SeriesEvidence.analyze(listOf(
            "ISIN DE000PJ9NB98\nBörse BNP OTC",
            "Kursdaten\nSymbol | ISIN\nDE 000 PJ9 NB9 8\nBörse BNP OTC\nGeld 12,34 Brief 12,35"
        ))
        assertNotNull(series)
        assertEquals(isin, series!!.isin)
        assertEquals(2, series.anchorCount)
        assertFalse(series.provisional)
    }

    @Test fun secondImageWithTwoBoundedGlyphErrorsStaysProvisional() {
        val series = SeriesEvidence.analyze(listOf(
            "BNP OTC\nISIN DE000PJ9NB98",
            "BNP OTC\nSymbol | ISIN\nDEOOOPJONB9S\nGeld 12,34"
        ))
        assertNotNull(series)
        assertEquals(isin, series!!.isin)
        assertEquals(1, series.anchorCount)
        assertTrue(series.provisional)
    }

    @Test fun conflictingWknAndVenueStillBlockGrouping() {
        assertNull(SeriesEvidence.analyze(listOf(
            "BNP OTC\nISIN DE000PJ9NB98",
            "BNP OTC\nWKN FG14AV\nGeld 12,34"
        )))
        assertNull(SeriesEvidence.analyze(listOf(
            "BNP OTC\nISIN DE000PJ9NB98",
            "Societe Generale OTC\nGeld 12,34"
        )))
        assertNull(SeriesEvidence.analyze(listOf(
            "BNP OTC\nISIN DE000PJ9NB98",
            "BNP OTC\nISIN DEOOOPJONB99"
        )))
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
