package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class MorningLocalOcrTest {
    private val first="DE000SQ02JQ6"
    private val second="DE000FG8NHQ3"
    private val firstRow="SG Gold Turbo Unlimited Mini Call BAR 2166 BP 2125.38 Bv 10 | $first Societe Generale OTC EUR K V"
    private val secondRow="SG Gold Knock-Out Warrant Put BAR 4400 BP 4400 Bv 10 19/03/2027 | $second Societe Generale OTC CHF K V"

    @Test fun onlyProductRowsAreReturnedAndAccountTextStaysLocal() {
        val frame=listOf("Märkte CHF 504,81", "Top Ergebnisse",
            firstRow, secondRow, "Portfolio Kontostand CHF 500").joinToString(" ")
        val rows=MorningLocalOcr.productRows(frame,listOf(first,second))!!
        assertEquals(2,rows.size)
        assertEquals(true,rows[0].startsWith("SG Gold Turbo"))
        assertTrue(rows[0].endsWith("OTC EUR"))
        assertTrue(rows[1].endsWith("OTC CHF"))
        assertFalse(rows.joinToString().contains("504,81"))
        assertFalse(rows.joinToString().contains("Portfolio"))
        assertFalse(rows.joinToString().contains(" K V"))
    }

    @Test fun rejectMissingAmbiguousWrongOrAccountContaminatedRows() {
        val page=listOf(firstRow,secondRow).joinToString(" ")
        assertNull(MorningLocalOcr.productRows(page,listOf(second,first)))
        assertNull(MorningLocalOcr.productRows(page,listOf(first)))
        assertNull(MorningLocalOcr.productRows(page,listOf(first,first)))
        assertNull(MorningLocalOcr.productRows(page,listOf(first,"DE000SQ02JQ5")))
        assertNull(MorningLocalOcr.productRows(firstRow.replace("Societe Generale OTC",""),listOf(first)))
        assertNull(MorningLocalOcr.productRows(firstRow.replace("Societe Generale OTC","Kontostand Societe Generale OTC"),listOf(first)))
        assertNull(MorningLocalOcr.productRows(firstRow.replace(first,second),listOf(first)))
    }

    @Test fun clippedEdgeNeighbourDoesNotDiscardCompleteExpectedRows() {
        val clipped="BNP GOLD Unlimited Long SL 3800.25 STR 3800.25 R 10"
        val complete=listOf(firstRow,secondRow).joinToString(" ")
        val baseline=MorningLocalOcr.productRows(complete,listOf(first,second))
        assertNotNull(baseline)
        assertEquals(baseline,MorningLocalOcr.productRows(complete+" "+clipped,listOf(first,second)))
        assertEquals(baseline,MorningLocalOcr.productRows(clipped+" "+complete,listOf(first,second)))
        assertEquals(baseline,MorningLocalOcr.productRows(clipped+" "+complete+" "+clipped,listOf(first,second)))
        val clippedWithId=clipped+" | DE000FD0S0G4"
        assertEquals(baseline,MorningLocalOcr.productRows(complete+" "+clippedWithId,listOf(first,second)))
        assertFalse(MorningLocalOcr.productRows(complete+" "+clippedWithId,listOf(first,second))!!
            .joinToString().contains("DE000FD0S0G4"))
    }

    @Test fun edgeHandlingNeverSkipsExpectedCompleteExtraOrAmbiguousProducts() {
        val clipped="BNP GOLD Unlimited Long SL 3800.25 STR 3800.25 R 10"
        val complete=listOf(firstRow,secondRow).joinToString(" ")
        val expected=listOf(first,second)
        assertNull(MorningLocalOcr.productRows(firstRow+" "+clipped+" "+secondRow,expected))
        assertNull(MorningLocalOcr.productRows(complete+" "+clipped+" | DE000FD0S0G4 BNP OTC EUR",expected))
        assertNull(MorningLocalOcr.productRows(complete+" "+clipped+" | DE000FD0S0G4 "+first,expected))
        assertNull(MorningLocalOcr.productRows(complete+" "+clipped+" | "+first,expected))
        assertNull(MorningLocalOcr.productRows(firstRow+" "+clipped,expected))
        assertEquals(MorningLocalOcr.productRows(complete,expected),
            MorningLocalOcr.productRows(complete+" "+clipped+" Portfolio Kontostand",expected))
    }
}
