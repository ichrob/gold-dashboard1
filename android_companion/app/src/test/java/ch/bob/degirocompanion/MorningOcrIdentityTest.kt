package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class MorningOcrIdentityTest {
    private val id="DE000SQ02JQ6"
    private val raw="DEOOOSQO2JQ6"
    private val row="SG Gold Turbo Unlimited Mini Call BAR 2166 BP 2126.05 Bv 10 | $raw Societe Generale OTC EUR"
    @Test fun germanGlyphRepairRequiresChecksumAndNeverChangesRawEvidence() {
        assertEquals(id,MorningOcrIdentity.canonical(raw))
        assertEquals(id,MorningOcrIdentity.canonical(raw.lowercase()))
        assertEquals(id,MorningOcrIdentity.canonical(id))
        assertNull(MorningOcrIdentity.canonical("DEOOOSQO2JQ5"))
        assertNull(MorningOcrIdentity.canonical("DEOOOPU8APE4")) // no context-specific J/U aliases
        assertNull(MorningOcrIdentity.canonical("DE000SQ02JQ"))
        val read=MorningLocalOcr.completeViewportRows(row,listOf(id))!!
        assertEquals(listOf(id),read.ids)
        assertEquals(listOf(row),read.values)
        assertEquals(listOf(row),MorningLocalOcr.regionRows(row,id))
        // Exact app text is not OCR and must never use glyph correction.
        assertNull(MorningLocalOcr.productRows(row,listOf(id)))
    }
    @Test fun wrongAndDuplicateOpticalIdentitiesCannotBeMatchedToAnAnchor() {
        val other="DE000FG8NHQ3"
        assertEquals(other,MorningOcrIdentity.canonical(other))
        assertNull(MorningLocalOcr.regionRows(row.replace(raw,other),id))
        assertNull(MorningLocalOcr.regionRows(row+" "+row,id))
        assertNull(MorningLocalOcr.regionRows(row.replace(raw,"$raw $id"),id))
        assertNull(MorningLocalOcr.regionRows(row.replace(raw,"DEOOOSQO2JQ5"),id))
        assertNull(MorningLocalOcr.regionRows(row.substringBefore("Societe"),id))
    }
    @Test fun recoveredGlyphsCanSeedGeometryWithoutSupplyingProductValues() {
        val lines=listOf(MorningOcrLayout.Line("SG Gold Turbo Call",10,50,300,70),
            MorningOcrLayout.Line(raw,10,100,300,120),
            MorningOcrLayout.Line("Societe Generale OTC EUR",10,150,400,170))
        assertEquals(listOf(id),MorningOcrLayout.productBands(lines,listOf(id),300)!!.map { it.id })
        assertNull(MorningOcrLayout.productBands(lines.map { it.copy(text=it.text.replace(raw,"DEOOOSQO2JQ5")) },listOf(id),300))
    }
}
