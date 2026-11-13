package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class ProductScreenEvidenceTest {
    private val at = "2026-10-27T14:00:00Z"
    private fun lines(vararg text: String) = text.mapIndexed { i, value -> QuoteLayout.Line(value, 0, i * 50, 500, i * 50 + 30) }
    private val product get() = lines("ISIN DE000FD0S0G4", "EUR", "Geld 10,20", "Brief 10,30", "27/10/2026 14:59")
    private fun read(items: List<QuoteLayout.Line> = product, pkg: String = ProductScreenEvidence.PACKAGE, sensitive: Boolean = false) = ProductScreenEvidence.read(pkg, items, at, sensitive)
    @Test fun exactDegiroTwoColumnQuoteKeepsDisplayClockAndAccountSeparate() {
        // Redacted geometric reconstruction of the 06 Nov SG quote view.
        // No screenshot bytes, customer balance or broker credentials stored.
        fun cell(text:String,x:Int,y:Int,w:Int=145)=QuoteLayout.Line(text,x,y,x+w,y+30)
        val product=listOf(
            cell("CHF 999,99",125,85), // Synthetic account balance, not product currency
            cell("Kursdaten",40,293),
            cell("Zuletzt",40,386,95), cell("€ 51,00",244,386,125),
            cell("06/11/2026",460,386,141), cell("09:46",610,386,67),
            cell("Geld",40,446,65), cell("€ 51,00",244,446,125),
            cell("Brief",380,446,69), cell("€ 51,01",588,446,120),
            cell("Geld Vol.",40,500), cell("25K",283,500),
            cell("Brief Vol.",380,500), cell("25K",626,500),
            cell("Schluss",380,560), cell("€ 53,30",588,560),
            cell("+/-",40,720), cell("€ -2,30 (-4,32%)",137,720,185),
            cell("Symbol | ISIN",40,1070,200), cell("DE000SX7PE82",485,1070,200),
            cell("Börse",40,1135,100), cell("Societe Generale OTC",418,1135,255),
            cell("KAUF",146,1350), cell("VERKAUF",450,1350))
        val result=read(product)
        assertEquals(ProductScreenEvidence.Reason.NONE,result.reason)
        assertTrue(result.draft.contains("ISIN: DE000SX7PE82"))
        assertTrue(result.draft.contains("Währung (Anzeige ungeprüft): EUR"))
        assertTrue(result.draft.contains("Geld (Anzeige ungeprüft): 51,00"))
        assertTrue(result.draft.contains("Brief (Anzeige ungeprüft): 51,01"))
        assertTrue(result.draft.contains("Anzeigezeit (Anzeige ungeprüft): 06/11/2026 09:46"))
        assertTrue(result.draft.contains("Handelsplatz (Anzeige ungeprüft): SOCIETE GENERALE OTC"))
        assertFalse(result.draft.contains("Hebel (Anzeige ungeprüft):"))
        assertFalse(result.draft.contains("999,99"))
        assertFalse(result.draft.contains("53,30"))
        assertFalse(result.draft.contains("-4,32"))
        assertTrue(result.draft.contains("Keine Freigabe, keine Order") ||
            result.draft.contains("keine Freigabe, keine Order"))
        // The phone clock alone cannot replace a missing DEGIRO quote time.
        val withoutDisplayedTime=product.filterNot { it.text=="09:46" }+cell("09:46",27,25)
        assertFalse(read(withoutDisplayedTime).draft.contains("Anzeigezeit (Anzeige ungeprüft):"))
        // A second visible identity is never merged with the first one's quotes.
        assertEquals(ProductScreenEvidence.Reason.ISIN_AMBIGUOUS,
            read(product+cell("DE000FG0SGZ2",480,1020)).reason)
    }

    @Test fun groupedTableRowsKeepEuroQuotesSeparateFromChfAccount() {
        val result = read(lines("CHF 505,05", "DE000FG77MY4 • Societe Generale OTC",
            "Zuletzt € 11,15 28/10/2026 07:55", "Geld € 11,14 Brief € 11,16"))
        assertEquals(ProductScreenEvidence.Reason.NONE, result.reason)
        assertTrue(result.draft.contains("Währung (Anzeige ungeprüft): EUR"))
        assertTrue(result.draft.contains("Geld (Anzeige ungeprüft): 11,14"))
        assertTrue(result.draft.contains("Brief (Anzeige ungeprüft): 11,16"))
        assertTrue(result.draft.contains("Anzeigezeit (Anzeige ungeprüft): 28/10/2026 07:55"))
        assertFalse(result.draft.contains("505,05"))
    }

    @Test fun explicitDashesAreSourceAbsenceNotLastPriceQuotes() {
        for (unit in listOf("CHF", "€")) {
            val input = lines("DE000FD0S0G4", "Kursdaten", "Zuletzt $unit 4,98",
                "Geld $unit —", "Brief $unit —")
            val result = read(input)
            assertTrue(result.draft.contains("Kursstatus (Anzeige ungeprüft): Geld/Brief nicht angezeigt"))
            assertTrue(result.draft.contains("Zuletzt (Anzeige ungeprüft): 4,98"))
            assertFalse(result.draft.contains("Geld (Anzeige ungeprüft):"))
            assertFalse(result.draft.contains("Brief (Anzeige ungeprüft):"))
            assertFalse(result.draft.contains("Anzeigezeit (Anzeige ungeprüft):"))
            assertFalse(read(input.filterNot { it.text.startsWith("Brief") }).draft.contains("Kursstatus"))
            assertFalse(read(input + lines("Geld $unit 4,97")).draft.contains("Kursstatus"))
            assertEquals("", read(input + lines("Passwort")).draft)
        }
    }
    @Test fun separateDashCellsUseTheirLabelGeometry() {
        val result = read(lines("DE000FD0S0G4", "Kursdaten", "Zuletzt CHF 4,98") + listOf(
            QuoteLayout.Line("Geld", 20, 200, 90, 230),
            QuoteLayout.Line("CHF —", 200, 200, 300, 230),
            QuoteLayout.Line("Brief", 350, 200, 430, 230),
            QuoteLayout.Line("CHF —", 550, 200, 650, 230)))
        assertTrue(result.draft.contains("Kursstatus (Anzeige ungeprüft): Geld/Brief nicht angezeigt"))
    }

    @Test fun rejectionReasonsSeparateIdentityCurrencyAndQuotes() {
        assertEquals(ProductScreenEvidence.Reason.ISIN_MISSING, read(lines("Geld EUR 10,20")).reason)
        assertEquals(ProductScreenEvidence.Reason.ISIN_AMBIGUOUS, read(product + lines("DE000FE2JJ20")).reason)
        assertEquals(ProductScreenEvidence.Reason.ISIN_INVALID, read(lines("DE000FD0S0G5")).reason)
        assertEquals(ProductScreenEvidence.Reason.CURRENCY_AMBIGUOUS, read(product + lines("CHF")).reason)
        assertEquals(ProductScreenEvidence.Reason.QUOTES_MISSING, read(lines("DE000FD0S0G4", "EUR")).reason)
        assertEquals(ProductScreenEvidence.Reason.PROTECTED, read(sensitive = true).reason)
        assertEquals(ProductScreenEvidence.Reason.LOGIN_OR_ORDER, read(product + lines("Ordertyp")).reason)
        assertEquals(ProductScreenEvidence.Reason.QUOTES_INVALID, read(lines("DE000FD0S0G4", "Geld EUR 12,00", "Brief EUR 11,00")).reason)
        assertEquals(ProductScreenEvidence.Reason.NONE, read().reason)
    }
    @Test fun readsOnlyLabelledProductFieldsWithoutApprovingTrading() {
        val result = read()
        assertTrue(result.draft.contains("Geld (Anzeige ungeprüft): 10,20"))
        assertTrue(result.draft.contains("Erfasst: $at"))
        assertTrue(result.draft.contains("Keine Aussage zur Handelbarkeit"))
        assertFalse(result.draft.contains("tradeApproved"))
    }
    @Test fun rejectsOtherAppsCredentialsOrderPagesAndMultipleIdentities() {
        assertEquals("", read(pkg = "browser").draft)
        assertEquals("", read(sensitive = true).draft)
        for (text in listOf("Passwort", "Order bestätigen", "Ordertyp", "ISIN DE000FE2JJ20"))
            assertEquals(text, "", read(product + lines(text)).draft)
        assertEquals("", read(lines("ISIN DE000FD0S0G5", "EUR", "Geld 10,20")).draft)
    }
    @Test fun noCurrencyGuessingOrAccountTextExport() {
        assertEquals("", read(product + lines("CHF")).draft)
        val result = read(product + lines("Kontostand 12345", "Name Max Mustermann", "Kaufen", "Kurse verzögert"))
        assertFalse(result.draft.contains("12345"))
        assertFalse(result.draft.contains("Mustermann"))
        assertTrue(result.draft.contains("Kurse verzögert"))
        assertEquals("", read(lines("ISIN DE000FD0S0G4", "EUR", "Geld 10,40", "Brief 10,30")).draft)
    }
    @Test fun separateCurrencySymbolOnQuoteRowIgnoresAccountHeader() {
        val input = listOf(QuoteLayout.Line("CHF 999,00", 0, 0, 500, 30),
            QuoteLayout.Line("DE000FD0S0G4", 0, 100, 500, 130),
            QuoteLayout.Line("Geld", 0, 200, 100, 230),
            QuoteLayout.Line("€", 120, 200, 140, 230),
            QuoteLayout.Line("10,20", 150, 200, 240, 230))
        assertTrue(read(input).draft.contains("Währung (Anzeige ungeprüft): EUR"))
    }
    @Test fun accountCurrencyIsNotProductCurrency() {
        val result = read(lines("CHF 987,65", "ISIN DE000FD0S0G4", "Geld € 10,20", "Brief € 10,30"))
        assertTrue(result.draft.contains("Währung (Anzeige ungeprüft): EUR"))
        assertFalse(result.draft.contains("987"))
        assertEquals("", read(lines("ISIN DE000FD0S0G4", "Geld EUR 10,20", "Brief CHF 10,30")).draft)
        assertEquals("", read(lines("CHF 987,65", "ISIN DE000FD0S0G4", "Geld 10,20", "Brief 10,30", "EUR")).draft)
    }
    @Test fun separateScreensCannotSilentlyReuseIdentity() {
        assertEquals("", read(lines("EUR", "Geld 10,20", "Brief 10,30")).draft)
        assertEquals("", read(lines("ISIN DE000FD0S0G4", "EUR", "10,20")).draft)
    }
    @Test fun metadataOnlyReadNeedsExplicitOptInRealIsinAndProductCurrency() {
        val detail=lines("DE000FD0S0G4 EUR",
            "SG Gold Turbo Unlimited Mini Call BAR 3942 BP 3901.07 Bv 10 LV 27.07",
            "CHF 900 Account balance")
        assertEquals(ProductScreenEvidence.Reason.QUOTES_MISSING,read(detail).reason)
        val safe=ProductScreenEvidence.read(ProductScreenEvidence.PACKAGE,detail,at,false,allowTermsOnly=true)
        assertEquals(ProductScreenEvidence.Reason.NONE,safe.reason)
        assertTrue(safe.draft.contains("KO-Schwelle (Anzeige ungeprüft): 3942"))
        assertTrue(safe.draft.contains("Basispreis (Anzeige ungeprüft): 3901,07"))
        assertFalse(safe.draft.contains("Geld ("))
        assertFalse(safe.draft.contains("900"))
        val unpriced = ProductScreenEvidence.read(ProductScreenEvidence.PACKAGE,
            lines("DE000FD0S0G4","SG Gold Turbo Unlimited Mini Call BAR 3942 BP 3901.07 Bv 10 LV 27.07",
                "CHF 900 Account balance"),at,false,allowTermsOnly=true)
        assertEquals(ProductScreenEvidence.Reason.NONE, unpriced.reason)
        assertTrue(unpriced.draft.contains("Hebel (Anzeige ungeprüft): 27,07"))
        assertTrue(unpriced.draft.contains("Produktwährung nicht nachgewiesen"))
        assertFalse(unpriced.draft.contains("Währung (Anzeige ungeprüft): "))
        assertFalse(unpriced.draft.contains("CHF 900"))
        assertFalse(unpriced.draft.contains("Geld ("))
        // A genuine contradictory product currency is never a terms-only success.
        assertEquals(ProductScreenEvidence.Reason.CURRENCY_AMBIGUOUS,
            ProductScreenEvidence.read(ProductScreenEvidence.PACKAGE,
                lines("DE000FD0S0G4","Produktwährung: EUR","Währung: CHF",
                    "SG Gold Turbo Unlimited Mini Call BAR 3942 BP 3901.07 Bv 10 LV 27.07"),
                at,false,allowTermsOnly=true).reason)
        assertEquals(ProductScreenEvidence.Reason.LOGIN_OR_ORDER,
            ProductScreenEvidence.read(ProductScreenEvidence.PACKAGE,detail+lines("Order bestätigen"),
                at,false,allowTermsOnly=true).reason)
        assertEquals(ProductScreenEvidence.Reason.ISIN_AMBIGUOUS,
            ProductScreenEvidence.read(ProductScreenEvidence.PACKAGE,detail+lines("DE000FG77MY4"),
                at,false,allowTermsOnly=true).reason)
    }
    @Test fun boundedMemoryAndFailureClearPreviousDraft() {
        ProductReadSession.put(read(), 1000)
        assertTrue(ProductReadSession.get(2000).draft.isNotEmpty())
        assertEquals("", ProductReadSession.get(301001).draft)
        ProductReadSession.put(read(), 400000)
        ProductReadSession.put(read(pkg = "other"), 400001)
        assertEquals("", ProductReadSession.get(400002).draft)
        ProductReadSession.clear()
    }
}
