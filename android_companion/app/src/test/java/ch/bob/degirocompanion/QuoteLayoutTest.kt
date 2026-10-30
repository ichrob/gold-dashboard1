package ch.bob.degirocompanion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class QuoteLayoutTest {
    private fun row(label: String, labelX: Int, value: String, valueX: Int, y: Int): List<QuoteLayout.Line> =
        listOf(
            QuoteLayout.Line(label, labelX, y, labelX + label.length * 8, y + 22),
            QuoteLayout.Line(value, valueX, y, valueX + value.length * 9, y + 22)
        )

    @Test fun joinedQuoteRowsAndFullIssuerVenueAreReadWithoutGuessing() {
        val input = listOf(
            QuoteLayout.Line("DE000FG77MY4 • Societe Generale OTC", 0, 100, 650, 130),
            QuoteLayout.Line("Zuletzt € 11,15 28/10/2026 07:55", 0, 200, 650, 230),
            QuoteLayout.Line("Geld € 11,14 Brief € 11,16", 0, 250, 650, 280),
            QuoteLayout.Line("Geld Vol. 25K Brief Vol. 25K", 0, 300, 650, 330))
        val actual = QuoteLayout.extract(input)
        assertEquals("11,14", actual["Geld"])
        assertEquals("11,16", actual["Brief"])
        assertEquals("11,15", actual["Zuletzt"])
        assertEquals("28/10/2026 07:55", actual["Anzeigezeit"])
        assertEquals("SOCIETE GENERALE OTC", actual["Handelsplatz"])
        assertNull(QuoteLayout.extract(input + QuoteLayout.Line("Geld € 12,00",0,400,400,430))["Geld"])
        assertNull(QuoteLayout.extract(listOf(QuoteLayout.Line("Kaufen Geld € 12,00",0,0,400,30)))["Geld"])
    }

    @Test fun compactTitleParametersRemainSeparateFromAccountAndChart() {
        val header = listOf(
            QuoteLayout.Line("CHF 505,05", 0, 70, 650, 120),
            QuoteLayout.Line("DE000FG77MY4 • Societe Generale OTC", 24, 210, 650, 245),
            QuoteLayout.Line("SG Gold Turbo BEST Open-End Put BAR", 85, 270, 680, 305),
            QuoteLayout.Line("4181.33 BP 4181.33 Bv 10 LV 32.33", 85, 325, 650, 360),
            QuoteLayout.Line("€11,37", 24, 380, 200, 425),
            QuoteLayout.Line("17.44", 560, 620, 630, 660))
        val result = QuoteLayout.extract(header)
        assertEquals("4181,33", result["KO-Schwelle"])
        assertEquals("4181,33", result["Basispreis"])
        assertEquals("10", result["Bv"])
        assertEquals("32,33", result["Hebel"])
        assertNull(result["Geld"])
        assertNull(result["Zuletzt"])
        assertTrue(QuoteLayout.productParameters(header.filterNot { it.text.contains("Gold Turbo") }).isEmpty())
        assertTrue(QuoteLayout.productParameters(header.map { it.copy(text = it.text.replace("LV 32.33", "LV 0.00")) }).isEmpty())
        assertTrue(QuoteLayout.productParameters(header + QuoteLayout.Line("BAR 4181.33 BP 4181.33 Bv 10 LV 31.00", 85, 365, 680, 390)).isEmpty())
    }

    @Test fun compactMiniCallAcceptsWholeBarrierWithoutLosingOtherParameters() {
        fun parse(sequence: String) = QuoteLayout.productParameters(listOf(
            QuoteLayout.Line("SG Gold Turbo Unlimited Mini Call BAR", 85, 270, 680, 305),
            QuoteLayout.Line(sequence, 85, 325, 650, 360)))
        assertEquals(mapOf("KO-Schwelle" to "3942", "Basispreis" to "3901,07", "Bv" to "10", "Hebel" to "27,07"),
            parse("3942 BP 3901.07 Bv 10 LV 27.07"))
        assertEquals("3901", parse("3942 BP 3901 Bv 10 LV 27")["Basispreis"])
        assertEquals("27", parse("3942 BP 3901 Bv 10 LV 27")["Hebel"])
        for (bad in listOf("-3942 BP 3901.07 Bv 10 LV 27.07", "0 BP 3901.07 Bv 10 LV 27.07",
            "3942 BP 3901.07 LV 27.07", "3942 BP 3901.07 Bv 10 LV 27.12345", "3942 BP 3901.07 Bv 10 LV 27e3")) assertTrue(parse(bad).isEmpty())
    }

    @Test fun datedKnockOutTitleAndWrappedLeverageAreReadLiterally() {
        val header = listOf(
            QuoteLayout.Line("SG Gold Knock-Out Warrant Put BAR",85,270,680,310),
            QuoteLayout.Line("4300 BP 4300 Bv 10 18/03/2027 LV",85,325,680,365),
            QuoteLayout.Line("8.30",85,380,200,420))
        val fields = QuoteLayout.productParameters(header)
        assertEquals("4300",fields["KO-Schwelle"])
        assertEquals("4300",fields["Basispreis"])
        assertEquals("10",fields["Bv"])
        assertEquals("8,30",fields["Hebel"])
        assertTrue(QuoteLayout.productParameters(header.map { it.copy(text=it.text.replace("8.30","-8.30")) }).isEmpty())
    }
    @Test fun bnpTermsDoNotInventLeverageOrConvertRatioNotation() {
        val fields=QuoteLayout.productParameters(listOf(
            QuoteLayout.Line("BNP GOLD Mini Long SL 3700.1234 STR 3600.1234 R",0,0,680,30),
            QuoteLayout.Line("10",0,50,100,80)))
        assertEquals("3700,1234",fields["KO-Schwelle"])
        assertEquals("3600,1234",fields["Basispreis"])
        assertNull(fields["Hebel"])
        assertNull(fields["Bv"])
        val withLeverage=QuoteLayout.productParameters(listOf(
            QuoteLayout.Line("BNP GOLD Mini Long SL 3700 STR 3600 R 10 LV 12.34",0,0,680,30)))
        assertEquals("12,34",withLeverage["Hebel"])
        assertNull(withLeverage["Bv"])
    }

    @Test fun readsLabelsAndValuesInSeparateVisualColumns() {
        // Synthetic ML Kit line geometry based on the DEGIRO screenshot layout.
        val lines = mutableListOf<QuoteLayout.Line>()
        lines += QuoteLayout.Line("DE000PJ9NB98 • BNP OTC", 20, 190, 250, 216)
        lines += QuoteLayout.Line("€7,02", 24, 405, 115, 440) // unlabeled header: must NOT be bid
        lines += row("Zuletzt", 40, "€ 7,04", 276, 555)
        lines += QuoteLayout.Line("22/10/2026 10:35", 465, 555, 668, 577)
        lines += row("Geld", 40, "€ 7,04", 276, 610)
        lines += row("Brief", 380, "€ 7,05", 625, 610)
        lines += row("Geld Vol.", 40, "8K", 280, 666)
        lines += row("Brief Vol.", 380, "8K", 625, 666)
        lines += row("Eröffnung", 40, "€ 7,19", 280, 718)
        lines += row("Hoch", 40, "€ 8,34", 280, 762)
        lines += row("Tief", 40, "€ 6,53", 280, 806)
        val actual = QuoteLayout.extract(lines)
        assertEquals("7,04", actual["Zuletzt"])
        assertEquals("7,04", actual["Geld"])
        assertEquals("7,05", actual["Brief"])
        assertEquals("BNP OTC", actual["Handelsplatz"])
        assertEquals("22/10/2026 10:35", actual["Anzeigezeit"])
        assertFalse(actual.containsKey("Hebel"))
        assertFalse(actual.containsKey("KO-Schwelle"))
    }

    @Test fun exactOneLineQuoteAndExplicitVenueAlsoWork() {
        val lines = listOf(
            QuoteLayout.Line("Geld: € 11,31", 30, 90, 215, 110),
            QuoteLayout.Line("Brief: EUR 11,32", 30, 121, 220, 141),
            QuoteLayout.Line("Börse BNP OTC", 28, 152, 200, 172)
        )
        val fields = QuoteLayout.extract(lines)
        assertEquals("11,31", fields["Geld"])
        assertEquals("11,32", fields["Brief"])
        assertEquals("BNP OTC", fields["Handelsplatz"])
        assertNull(fields["Anzeigezeit"])
    }

    @Test fun refusesUnlabeledValuesAndPhoneClockAsQuote() {
        val fields = QuoteLayout.extract(listOf(
            QuoteLayout.Line("10:35", 30, 12, 90, 36),
            QuoteLayout.Line("€7,02", 80, 320, 165, 350),
            QuoteLayout.Line("Geld Vol.", 40, 545, 132, 568),
            QuoteLayout.Line("8K", 278, 545, 320, 568)
        ))
        assertTrue(fields.isEmpty())
    }

    @Test fun conflictingSameLabelNeverSelectsOneValue() {
        val fields = QuoteLayout.extract(
            row("Geld", 40, "€ 7,04", 280, 610) +
            row("Geld", 40, "€ 7,12", 280, 810)
        )
        assertNull(fields["Geld"])
    }

    @Test fun readsVenueWhenIsinAndBnpOtcAppearAsSeparateOcrLines() {
        val lines = listOf(
            QuoteLayout.Line("DE000PJ9NB98", 24, 189, 195, 216),
            QuoteLayout.Line("•", 200, 189, 212, 216),
            QuoteLayout.Line("BNP OTC", 220, 190, 315, 216),
            QuoteLayout.Line("R", 342, 190, 361, 216),
            QuoteLayout.Line("BNP GOLD Unlimited Long", 85, 250, 540, 285)
        )
        assertEquals("BNP OTC", QuoteLayout.extract(lines)["Handelsplatz"])
    }

    @Test fun readsVenueWhenBnpAndOtcAreIndependentOcrWords() {
        val lines = listOf(
            QuoteLayout.Line("DE000PJ9NB98", 24, 190, 190, 217),
            QuoteLayout.Line("BNP", 220, 192, 262, 215),
            QuoteLayout.Line("OTC", 269, 192, 309, 215),
            QuoteLayout.Line("R", 360, 192, 380, 215)
        )
        assertEquals("BNP OTC", QuoteLayout.extract(lines)["Handelsplatz"])
    }

    @Test fun detectsVenueNextToSeparateBoerseLabel() {
        val lines = listOf(
            QuoteLayout.Line("Börse", 40, 640, 116, 666),
            QuoteLayout.Line("BNP", 425, 640, 475, 666),
            QuoteLayout.Line("OTC", 481, 640, 531, 666)
        )
        assertEquals("BNP OTC", QuoteLayout.extract(lines)["Handelsplatz"])
    }

    @Test fun doesNotInferIssuerOtcFromOtherRowsOrNoIsin() {
        val lines = listOf(
            QuoteLayout.Line("DE000PJ9NB98", 24, 190, 193, 216),
            QuoteLayout.Line("BNP OTC", 218, 292, 312, 318)
        )
        assertNull(QuoteLayout.extract(lines)["Handelsplatz"])
        assertNull(QuoteLayout.extract(listOf(
            QuoteLayout.Line("BNP OTC", 220, 190, 315, 216),
            QuoteLayout.Line("BNP GOLD Unlimited Long", 30, 290, 500, 315)
        ))["Handelsplatz"])
    }

    @Test fun venueDoesNotComeFromProductNameAlone() {
        val fields = QuoteLayout.extract(listOf(
            QuoteLayout.Line("BNP GOLD Unlimited Long", 24, 100, 550, 130),
            QuoteLayout.Line("€ 7,02", 24, 143, 130, 170)
        ))
        assertNull(fields["Handelsplatz"])
    }
}
