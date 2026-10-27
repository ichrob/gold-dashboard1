package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class ProductScreenEvidenceTest {
    private val at = "2026-10-27T14:00:00Z"
    private fun lines(vararg text: String) = text.mapIndexed { i, value -> QuoteLayout.Line(value, 0, i * 50, 500, i * 50 + 30) }
    private val product get() = lines("ISIN DE000FD0S0G4", "EUR", "Geld 10,20", "Brief 10,30", "27/10/2026 14:59")
    private fun read(items: List<QuoteLayout.Line> = product, pkg: String = ProductScreenEvidence.PACKAGE, sensitive: Boolean = false) = ProductScreenEvidence.read(pkg, items, at, sensitive)
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
