package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class MorningLocalOcrTest {
    private val first="DE000SQ02JQ6"
    private val second="DE000FG8NHQ3"
    private val firstRow="SG Gold Turbo Unlimited Mini Call BAR 2166 BP 2125.38 Bv 10 | $first Societe Generale OTC EUR K V"
    private val secondRow="SG Gold Knock-Out Warrant Put BAR 4400 BP 4400 Bv 10 19/03/2027 | $second Societe Generale OTC CHF K V"

    @Test fun onlyProductRowsAreReturnedAndAccountTextStaysLocal() {
        val frame="Märkte CHF 504,81\\nTop Ergebnisse\\n"+
            firstRow+"\\n"+secondRow+"\\nPortfolio Kontostand CHF 500"
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
        val page=firstRow+"\\n"+secondRow
        assertNull(MorningLocalOcr.productRows(page,listOf(second,first)))
        assertNull(MorningLocalOcr.productRows(page,listOf(first)))
        assertNull(MorningLocalOcr.productRows(page,listOf(first,first)))
        assertNull(MorningLocalOcr.productRows(page,listOf(first,"DE000SQ02JQ5")))
        assertNull(MorningLocalOcr.productRows(firstRow.replace("Societe Generale OTC",""),listOf(first)))
        assertNull(MorningLocalOcr.productRows(firstRow.replace("Societe Generale OTC","Kontostand Societe Generale OTC"),listOf(first)))
        assertNull(MorningLocalOcr.productRows(firstRow.replace(first,second),listOf(first)))
    }
}
