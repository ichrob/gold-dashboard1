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
        val spaced=AccountSettingsEvidence.read(app,
            listOf("Währungseinstellungen","Auto FX","Aktiviert"))
        assertEquals("ACCOUNT_SETTINGS_PARTIAL",spaced.code)
        assertEquals("ON",spaced.autoFx)
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


    @Test fun actualGermanAccountChoicePageIsNotBrokerOrderConfirmation() {
        val fullPage=listOf("Ihre Handelseinstellungen",
            "Basic-Benutzerkonto",
            "Active-Benutzerkonto","Benutzerkonto auswählen",
            "Trader-Benutzerkonto","Benutzerkonto auswählen")
        assertTrue(AccountSettingsEvidence.recognizesSettings(fullPage))
        assertFalse(AccountSettingsEvidence.hasProtectedLabel("Benutzerkonto auswählen"))
        val selected=AccountSettingsEvidence.read(app,fullPage)
        assertEquals("ACCOUNT_SETTINGS_PARTIAL",selected.code)
        assertEquals("BASIC",selected.feeProfile)
        assertNull(selected.autoFx)
        assertFalse(selected.toString().contains("Benutzerkonto"))
        // In a short Samsung viewport, Basic and Active are visible but
        // Active's select button could be below the fold: never guess.
        val cropped=listOf("Ihre Handelseinstellungen",
            "Basic-Benutzerkonto","Active-Benutzerkonto")
        assertTrue(AccountSettingsEvidence.recognizesSettings(cropped))
        assertEquals("SETTINGS_UNCONFIRMED",
            AccountSettingsEvidence.read(app,cropped).code)
        val lower=listOf("Active-Benutzerkonto","Benutzerkonto auswählen",
            "Trader-Benutzerkonto","Benutzerkonto auswählen")
        assertTrue(AccountSettingsEvidence.recognizesSettings(lower))
        assertEquals("SETTINGS_UNCONFIRMED",
            AccountSettingsEvidence.read(app,lower).code)
    }

    @Test fun multipleAccountOptionsAreNotMisreadAsCurrentPlan() {
        val headings=listOf("Ihre Handelseinstellungen",
            "Basic-Benutzerkonto","Active-Benutzerkonto","Trader-Benutzerkonto")
        assertEquals("SETTINGS_UNCONFIRMED",
            AccountSettingsEvidence.read(app,headings).code)
        val buttons=listOf("Ihre Handelseinstellungen",
            "Basic-Benutzerkonto","Benutzerkonto auswählen",
            "Active-Benutzerkonto","Benutzerkonto auswählen",
            "Trader-Benutzerkonto","Benutzerkonto auswählen")
        assertEquals("SETTINGS_UNCONFIRMED",
            AccountSettingsEvidence.read(app,buttons).code)
        val lastCardPossiblyCropped=listOf("Ihre Handelseinstellungen",
            "Basic-Benutzerkonto","Benutzerkonto auswählen",
            "Active-Benutzerkonto","Benutzerkonto auswählen",
            "Trader-Benutzerkonto")
        assertEquals("SETTINGS_UNCONFIRMED",
            AccountSettingsEvidence.read(app,lastCardPossiblyCropped).code)
        val semanticallySelected=AccountSettingsEvidence.read(app,headings,
            selectedProfiles=listOf("ACTIVE"))
        assertEquals("ACCOUNT_SETTINGS_PARTIAL",semanticallySelected.code)
        assertEquals("ACTIVE",semanticallySelected.feeProfile)
        val conflict=AccountSettingsEvidence.read(app,headings,
            selectedProfiles=listOf("ACTIVE","BASIC"))
        assertEquals("SETTINGS_CONFLICT",conflict.code)
        assertEquals("SETTINGS_NOT_VISIBLE",
            AccountSettingsEvidence.read(app,listOf("Produkt", "Basic",
                "Handel mit Optionen","Benutzerkonto auswählen")).code)
        assertEquals("PROTECTED_VIEW",
            AccountSettingsEvidence.read(app,headings+"Order bestätigen").code)
    }

    @Test fun basicOwnerConfirmationIsScopedToExactVisibleProfilePage() {
        val page=listOf("Ihre Handelseinstellungen","Basic-Benutzerkonto",
            "Active-Benutzerkonto","Benutzerkonto auswählen")
        val e=AccountSettingsEvidence.ownerConfirmedProfile(app,page,"BASIC")
        assertEquals("ACCOUNT_SETTINGS_PARTIAL",e.code)
        assertEquals("BASIC",e.feeProfile)
        assertNull(e.autoFx)
        assertEquals("degiro-app-owner-confirmed",e.source)
        for (labels in listOf(
            listOf("Produkt","Basic-Benutzerkonto"),
            listOf("Ihre Handelseinstellungen","Active-Benutzerkonto"),
            listOf("Benutzerkonto auswählen","Basic-Benutzerkonto"))) {
            assertEquals("SETTINGS_UNCONFIRMED",
                AccountSettingsEvidence.ownerConfirmedProfile(app,labels,"BASIC").code)
        }
        assertEquals("SETTINGS_UNCONFIRMED",
            AccountSettingsEvidence.ownerConfirmedProfile(app,page,"UNKNOWN").code)
        assertEquals("OTHER_APP",
            AccountSettingsEvidence.ownerConfirmedProfile("com.other",page,"BASIC").code)
        assertEquals("PROTECTED_VIEW",
            AccountSettingsEvidence.ownerConfirmedProfile(app,
                page+listOf("PIN eingeben"),"BASIC").code)
        assertEquals("PROTECTED_VIEW",
            AccountSettingsEvidence.ownerConfirmedProfile(app,page,"BASIC",true).code)
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

    @Test fun currencyRowsInOwnerScreenshotConfirmOnlyAutoFxAndNotAccountFees() {
        // Real DEGIRO UI variant: the title may be scrolled away, "Auto FX"
        // is shown on all three rows and the manual button shows an i18n key.
        val rows=listOf(
            "EUR", "Auto FX", "trader.currencySettings.manualActionDisabled",
            "GBP", "Auto FX", "trader.currencySettings.manualActionDisabled",
            "USD", "Auto FX", "trader.currencySettings.manualActionDisabled")
        assertTrue(AccountSettingsEvidence.recognizesSettings(rows))
        val found=AccountSettingsEvidence.read(app,rows)
        assertEquals("ACCOUNT_SETTINGS_PARTIAL",found.code)
        assertEquals("ON",found.autoFx)
        assertNull(found.feeProfile)
        assertFalse(found.toString().contains("EUR"))
        // One badge or a generic FX menu must never confirm an account status.
        assertFalse(AccountSettingsEvidence.recognizesSettings(
            listOf("EUR","Auto FX","trader.currencySettings.manualActionDisabled")))
        assertEquals("SETTINGS_NOT_VISIBLE",AccountSettingsEvidence.read(app,
            listOf("EUR","Auto FX","trader.currencySettings.manualActionDisabled")).code)
        assertEquals("SETTINGS_CONFLICT",AccountSettingsEvidence.read(app,
            rows + listOf("AutoFX: OFF")).code)
    }

    @Test fun longHelpAndAccountBalanceNeverEnterLocalSettingsEvidence() {
        val help=("Wenn Sie Manual FX aktivieren, können Sie Währungsumrechnungen " +
            "manuell durchführen. Weitere Hinweise zur Auswahl der Währungen. ").repeat(5)
        assertTrue(help.length>250)
        assertFalse(AccountSettingsEvidence.isRelevantLabel(help))
        assertFalse(AccountSettingsEvidence.isRelevantLabel("CHF 504,30"))
        assertFalse(AccountSettingsEvidence.isRelevantLabel("Konto: privat 987654"))
        assertTrue(AccountSettingsEvidence.isRelevantLabel(
            "trader.currencySettings.manualActionDisabled"))
        val picture=listOf(help,"CHF 504,30","EUR","Auto FX",
            "trader.currencySettings.manualActionDisabled","GBP","Auto FX",
            "trader.currencySettings.manualActionDisabled","USD","Auto FX",
            "trader.currencySettings.manualActionDisabled")
        val allowed=picture.filter(AccountSettingsEvidence::isRelevantLabel)
        val result=AccountSettingsEvidence.read(app,allowed)
        assertEquals("ACCOUNT_SETTINGS_PARTIAL",result.code)
        assertEquals("ON",result.autoFx)
        assertNull(result.feeProfile)
        assertFalse(allowed.any { it.contains("504") || it.contains("Wenn Sie") })
        // A password/OTP/order warning embedded in a long paragraph must
        // still stop the scan, not get silently filtered out.
        assertTrue(AccountSettingsEvidence.hasProtectedLabel(help+" PIN eingeben"))
        assertTrue(AccountSettingsEvidence.hasProtectedLabel("Order bestätigen"))
        assertFalse(AccountSettingsEvidence.hasProtectedLabel("Passwort ändern"))
    }

    @Test fun settingsOwnerTapIsRequiredAndCannotReadProtectedViews() {
        assertTrue(AccountSettingsEvidence.ownerReadAllowed(true,true,"SETTINGS_READY"))
        for (code in listOf("PROTECTED_VIEW","PROTECTED_LOGIN","SCREEN_LOCKED",
            "SETTINGS_UNCONFIRMED","OTHER_APP","PRODUCT_SEARCH")) {
            assertFalse(code,AccountSettingsEvidence.ownerReadAllowed(true,true,code))
        }
        assertFalse(AccountSettingsEvidence.ownerReadAllowed(false,true,"SETTINGS_READY"))
        assertFalse(AccountSettingsEvidence.ownerReadAllowed(true,false,"SETTINGS_READY"))
        assertEquals("PROTECTED_VIEW",AccountSettingsEvidence.read(app,
            listOf("EUR","GBP","USD","Auto FX","Auto FX","Auto FX",
                "trader.currencySettings.manualActionDisabled","PIN eingeben")).code)
    }
}
