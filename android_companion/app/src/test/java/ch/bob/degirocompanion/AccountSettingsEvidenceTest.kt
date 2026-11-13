package ch.bob.degirocompanion

import org.junit.Assert.*
import org.junit.Test

class AccountSettingsEvidenceTest {
    private val app = "nl.degiro.trader"

    @Test fun exactGermanAndEnglishSettingsWithoutRawAccountData() {
        val x = AccountSettingsEvidence.read(app, listOf(
            "Währungseinstellungen", "AutoFX", "Aktiviert", "Kontotyp: Trader"))
        assertEquals("ACCOUNT_SETTINGS_COMPLETE", x.code)
        assertEquals("TRADER", x.feeProfile)
        assertEquals("ON", x.autoFx)
        assertFalse(x.toString().contains("Kontotyp:"))
        val y = AccountSettingsEvidence.read(app, listOf("Currency settings", "AutoFX: OFF",
            "Trading profile", "Basic"))
        assertEquals("ACCOUNT_SETTINGS_COMPLETE", y.code)
        assertEquals("BASIC", y.feeProfile)
        assertEquals("OFF", y.autoFx)
    }

    @Test fun separatePagesStayPartialAndCannotImplyNoConversion() {
        val x = AccountSettingsEvidence.read(app, listOf("Währungseinstellungen", "AutoFX", "Aus"))
        assertEquals("ACCOUNT_SETTINGS_PARTIAL", x.code)
        assertNull(x.feeProfile)
        assertEquals("OFF", x.autoFx)
        val y = AccountSettingsEvidence.read(app, listOf("Handelsprofil", "Active"))
        assertEquals("ACCOUNT_SETTINGS_PARTIAL", y.code)
        assertEquals("ACTIVE", y.feeProfile)
        assertNull(y.autoFx)
    }

    @Test fun ambiguousOrNavigationOnlyLabelsNeverConfirm() {
        assertEquals("SETTINGS_UNCONFIRMED", AccountSettingsEvidence.read(app,
            listOf("Währungseinstellungen", "AutoFX", "Weiter")).code)
        assertEquals("SETTINGS_NOT_VISIBLE", AccountSettingsEvidence.read(app,
            listOf("Portfolio", "Basic", "AutoFX")).code)
        assertEquals("SETTINGS_CONFLICT", AccountSettingsEvidence.read(app,
            listOf("Währungseinstellungen", "AutoFX: on", "AutoFX: off")).code)
        assertEquals("SETTINGS_CONFLICT", AccountSettingsEvidence.read(app,
            listOf("Kontotyp: Basic", "Handelsprofil: Trader")).code)
        assertEquals("SETTINGS_UNCONFIRMED", AccountSettingsEvidence.read(app,
            listOf("Währungseinstellungen", "AutoFX", "Konto Guthaben CHF")).code)
        // A static password-change navigation item is not a password input.
        val nav=AccountSettingsEvidence.read(app,
            listOf("Währungseinstellungen", "AutoFX: on", "Passwort ändern"))
        assertEquals("ACCOUNT_SETTINGS_PARTIAL",nav.code)
        assertEquals("ON",nav.autoFx)
    }

    @Test fun safetyBoundaryStopsCredentialAndOrderScreens() {
        assertEquals("OTHER_APP", AccountSettingsEvidence.read("com.other.app",
            listOf("Währungseinstellungen", "AutoFX: on")).code)
        for (text in listOf("Passwort", "PIN eingeben", "Order bestätigen",
            "Limitpreis", "Place order", "Bestätigungscode")) {
            assertEquals(text, "PROTECTED_VIEW", AccountSettingsEvidence.read(app,
                listOf("Währungseinstellungen", "AutoFX: on", text)).code)
        }
        assertEquals("PROTECTED_VIEW", AccountSettingsEvidence.read(app,
            listOf("Währungseinstellungen", "AutoFX: on"), sensitive = true).code)
        assertEquals("PROTECTED_VIEW", AccountSettingsEvidence.read(app,
            List(501) { "währungseinstellungen" }).code)
    }
}
