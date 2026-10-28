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
