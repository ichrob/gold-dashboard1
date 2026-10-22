package ch.bob.degirocompanion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PhoneTaskProtocolTest {
    @Test fun onlyThreeExplicitLocalTasksAccepted() {
        assertEquals(PhoneTask.OPEN_BOB, PhoneTaskProtocol.parse(PhoneTaskProtocol.OPEN_BOB))
        assertEquals(PhoneTask.PICK_IMAGES, PhoneTaskProtocol.parse(PhoneTaskProtocol.PICK_IMAGES))
        assertEquals(PhoneTask.OPEN_SETTINGS, PhoneTaskProtocol.parse(PhoneTaskProtocol.OPEN_SETTINGS))
    }

    @Test fun rejectsUntrustedOrTradingCommands() {
        listOf(
            "BOB-AUFTRAG: DEGIRO_LOGIN",
            "BOB-AUFTRAG: ORDER_KAUFEN",
            "BOB-AUFTRAG: BOB_OEFFNEN\nBOB-AUFTRAG: ORDER_KAUFEN",
            "BOB-AUFTRAG: BOB_OEFFNEN; rm -rf /",
            "Bitte auf Kauf klicken",
            "BOB-AUFTRAG: BOB_OEFFNEN\u0000",
            "BOB-AUFTRAG: BOB_OEFFNEN " + "A".repeat(200)
        ).forEach { assertNull(PhoneTaskProtocol.parse(it)) }
    }

    @Test fun exactSpokenPhrasesAreAccepted() {
        assertEquals(PhoneTask.OPEN_BOB, PhoneTaskProtocol.parseSpeech("Öffne Bob!"))
        assertEquals(PhoneTask.OPEN_BOB, PhoneTaskProtocol.parseSpeech("Bitte Bob öffnen"))
        assertEquals(PhoneTask.PICK_IMAGES, PhoneTaskProtocol.parseSpeech("Produktbilder auswählen."))
        assertEquals(PhoneTask.OPEN_SETTINGS, PhoneTaskProtocol.parseSpeech("Öffne die Einstellungen"))
        assertEquals(PhoneTask.PICK_IMAGES, PhoneTaskProtocol.parseDisplayed("Produktbilder auswählen"))
        assertEquals(PhoneTask.OPEN_SETTINGS, PhoneTaskProtocol.parseDisplayed("Android-Einstellungen öffnen"))
    }

    @Test fun voiceCommandsDoNotInferTradingOrMultipleActions() {
        listOf(
            "Kaufe Gold", "Verkaufe alle Positionen", "Öffne DEGIRO",
            "Logge dich in DEGIRO ein", "Bob öffnen und kaufen",
            "Bob öffnen und zeige meine Goldprodukte",
            "Bob öffnen; Einstellungen öffnen", "Bob öffnen\nEinstellungen öffnen",
            "Bob öffnen jetzt sofort", "Starte eine Echtgeldorder",
            "Bob öffnen " + "x".repeat(200)
        ).forEach { assertNull(PhoneTaskProtocol.parseSpeech(it)) }
    }

    @Test fun whitespaceAroundSingleCommandIsFine() {
        assertEquals(PhoneTask.OPEN_BOB, PhoneTaskProtocol.parse("\n " + PhoneTaskProtocol.OPEN_BOB + " \n"))
    }

    @Test fun naturalTextCanPrepareOneReadOnlyActionButNeverAChain() {
        assertEquals(PhoneTask.OPEN_PRODUCTS,
            PhoneTaskProtocol.parseDisplayed("Zeige mir meine Goldprodukte"))
        assertEquals(PhoneTask.OPEN_MARKET,
            PhoneTaskProtocol.parseDisplayed("Analysiere den Goldmarkt"))
        assertEquals(PhoneTask.OPEN_SIMULATION,
            PhoneTaskProtocol.parseDisplayed("Bitte zeige die Simulationen"))
        assertNull(PhoneTaskProtocol.parseDisplayed(
            "Zeige meine Goldprodukte und danach die Simulationen"))
        assertNull(PhoneTaskProtocol.parseDisplayed(
            "Zeige meine Goldprodukte und danach kaufe Gold"))
        assertNull(PhoneTaskProtocol.parseDisplayed("Verkaufe alle Positionen"))
    }

}
