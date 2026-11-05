package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class MorningLocalOcrTest {
    @Test fun rejectedOriginalStillAllowsTwoRealScaledReads() {
        val row=MorningLocalOcr.Rows(listOf(first),listOf(firstRow))
        val called=mutableListOf<Int>()
        var result:List<MorningLocalOcr.Rows>?=null
        MorningLocalOcr.collectPasses({ index,complete ->
            called.add(index);complete(if(index==0)null else row)
        }) { result=it }
        assertEquals(listOf(0,1,2),called)
        assertEquals(listOf(row,row),result)
    }

    @Test fun oneSuccessfulReadCannotBeDuplicatedIntoAgreement() {
        val row=MorningLocalOcr.Rows(listOf(first),listOf(firstRow))
        var calls=0;var completions=0
        var result:List<MorningLocalOcr.Rows>?=listOf(row)
        MorningLocalOcr.collectPasses({ index,complete ->
            calls++;complete(if(index==1)row else null)
            // A repeated task callback must never count as another optical pass.
            complete(row)
        }) { completions++;result=it }
        assertEquals(3,calls);assertEquals(1,completions);assertNull(result)
    }

    @Test fun mismatchedValidIdentitiesCannotBeCherryPicked() {
        val a=MorningLocalOcr.Rows(listOf(first),listOf(firstRow))
        val b=MorningLocalOcr.Rows(listOf(second),listOf(secondRow))
        var calls=0;var result:List<MorningLocalOcr.Rows>?=listOf(a)
        MorningLocalOcr.collectPasses({ index,complete ->
            calls++;complete(if(index==1)b else a)
        }) { result=it }
        assertEquals(2,calls);assertNull(result)
    }

    @Test fun successfulOriginalPairStopsWithoutExtraWork() {
        val row=MorningLocalOcr.Rows(listOf(first),listOf(firstRow))
        var calls=0
        MorningLocalOcr.collectPasses({ _,complete -> calls++;complete(row) }) {
            assertEquals(2,it!!.size)
        }
        assertEquals(2,calls)
        for(width in listOf(200,709,1080,1440,1600,2000)) {
            val widths=MorningLocalOcr.passWidths(width)
            assertEquals(3,widths.size);assertEquals(widths,widths.distinct())
            assertTrue(widths.drop(1).all { it<=1600 })
        }
    }

    @Test fun failedParserReportsOnlyFixedReasonWithoutScreenText() {
        ProductReadDiagnostics.reset(0)
        assertNull(MorningLocalOcr.completeViewportRows(
            firstRow.substringBefore("Societe"),listOf(first),diagnose=true))
        val report=ProductReadDiagnostics.report(1)
        assertTrue(report.contains("LIST_OCR_FOOTER_MISSING: 1"))
        assertFalse(report.contains(first));assertFalse(report.contains("2125"))
        ProductReadDiagnostics.clear()
        assertFalse(ProductReadDiagnostics.report(2).contains("LIST_OCR_FOOTER_MISSING"))
    }

    @Test fun expectedClippedEdgeDoesNotDiscardOtherCompleteRows() {
        val raw=firstRow+" "+secondRow.substringBefore("Societe")
        assertNull(MorningLocalOcr.productRows(raw,listOf(first,second)))
        val result=MorningLocalOcr.completeViewportRows(raw,listOf(first,second))!!
        assertEquals(listOf(first),result.ids)
        assertEquals(MorningLocalOcr.productRows(firstRow,listOf(first)),result.values)
        assertFalse(result.values.joinToString().contains(second))
        val reverse=MorningLocalOcr.completeViewportRows(
            firstRow.substringBefore("Societe")+" "+secondRow,listOf(first,second))!!
        assertEquals(listOf(second),reverse.ids)
    }

    @Test fun completeExtraRowsAndInteriorGapsRemainRejected() {
        assertNull(MorningLocalOcr.completeViewportRows(firstRow+" "+secondRow,listOf(first)))
        assertNull(MorningLocalOcr.completeViewportRows(firstRow+" "+secondRow,listOf(second,first)))
        assertNull(MorningLocalOcr.completeViewportRows(firstRow.substringBefore("Societe"),listOf(first)))
        assertNull(MorningLocalOcr.completeViewportRows(firstRow+" "+secondRow,listOf(first,first)))
        val middle="DE000FB0CVV9"
        val clipped="SG Gold Turbo BEST Open-End Put BAR 4000 BP 4000 Bv 10 | $middle"
        assertNull(MorningLocalOcr.completeViewportRows(firstRow+" "+clipped+" "+secondRow,
            listOf(first,middle,second)))
    }
    @Test fun overlappingRecoveryWindowSelectsOnlyTheOpticallyIdentifiedCard() {
        val page=firstRow+" "+secondRow
        // Full-viewport validation remains strict about complete extra products.
        assertNull(MorningLocalOcr.productRows(page,listOf(first)))
        assertEquals(MorningLocalOcr.productRows(firstRow,listOf(first)),
            MorningLocalOcr.regionRows(page,first))
        assertEquals(MorningLocalOcr.productRows(secondRow,listOf(second)),
            MorningLocalOcr.regionRows(page,second))
        val third="DE000FB0CVV9"
        val thirdRow=firstRow.replace(first,third)
        assertEquals(MorningLocalOcr.productRows(secondRow,listOf(second)),
            MorningLocalOcr.regionRows(firstRow+" "+secondRow+" "+thirdRow,second))
        assertEquals(MorningLocalOcr.productRows(firstRow,listOf(first)),
            MorningLocalOcr.regionRows(page.replace("SG Gold","SGGold"),first))
    }

    @Test fun recoveryCannotInventIdentityBorrowFooterOrAcceptDuplicate() {
        assertNull(MorningLocalOcr.regionRows(secondRow,first))
        assertNull(MorningLocalOcr.regionRows(firstRow+" "+firstRow,first))
        assertNull(MorningLocalOcr.regionRows(firstRow.substringBefore("Societe")+" "+secondRow,first))
        assertNull(MorningLocalOcr.regionRows(firstRow.replace(first,"$first $second"),first))
        assertNull(MorningLocalOcr.regionRows(firstRow.replace("Societe","Kontostand Societe"),first))
        assertNull(MorningLocalOcr.regionRows(firstRow.substringAfter("Unlimited"),first))
        assertNull(MorningLocalOcr.regionRows(firstRow+" "+secondRow.replace("SG Gold","unreadable"),second))
        assertNull(MorningLocalOcr.regionRows(firstRow,"DE000SQ02JQ5"))
        assertNull(MorningLocalOcr.regionRows(firstRow.replace(first,"")+" "+
            secondRow.replace("SG Gold","unreadable"),second))
    }

    @Test fun recoveryExportsNeitherNeighbourValuesNorAccountFrame() {
        val selected=MorningLocalOcr.regionRows("Portfolio Kontostand 123456 "+firstRow+" "+secondRow+
            " Portfolio Kontostand 987654",first)!!
        assertEquals(MorningLocalOcr.productRows(firstRow,listOf(first)),selected)
        assertFalse(selected.joinToString().contains(second))
        assertFalse(selected.joinToString().contains("Kontostand"))
        assertFalse(selected.joinToString().contains("123456"))
        assertFalse(selected.joinToString().contains("987654"))
    }

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
