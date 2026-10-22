package ch.bob.degirocompanion

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PhoneTaskPlanTest {
    @Test fun understandsConnectedGermanSentencesWithoutGuessing() {
        val plan = PhoneTaskPlanParser.parse(
            "Bob, öffne zuerst Bob und danach wähle meine Produktbilder aus"
        )
        assertEquals(listOf(PhoneTask.OPEN_BOB, PhoneTask.PICK_IMAGES), plan?.steps)
        assertEquals(listOf(PhoneTask.OPEN_BOB, PhoneTask.OPEN_SETTINGS),
            PhoneTaskPlanParser.parse("Bitte öffne Bob und dann öffne die Einstellungen!")?.steps)
        assertEquals(listOf(PhoneTask.PICK_IMAGES, PhoneTask.OPEN_SETTINGS),
            PhoneTaskPlanParser.parse("Bilder auswählen, dann Einstellungen öffnen.")?.steps)
        assertEquals(PhoneTask.OPEN_BOB, PhoneTaskPlanParser.parse("Bob öffnen")?.steps?.single())
    }

    @Test fun refusesWholePlanIfAnyClauseIsUnsupportedOrDangerous() {
        listOf(
            "Öffne Bob und kaufe Gold", "Öffne Bob und danach logge dich in DEGIRO ein",
            "Öffne Bob und platziere eine Order", "Öffne Bob und zeige mein Depot",
            "Öffne Bob und danach ändere das Passwort",
            "Öffne Bob und danach Produktbilder auswählen und danach kaufe Gold",
            "Öffne Bob und öffne Bob", "Öffne Bob; Einstellungen öffnen",
            "Öffne Bob\\nEinstellungen öffnen", "Öffne Bob und danach",
            "Öffne Bob und danach Einstellungen öffnen und danach Produktbilder auswählen und Bob öffnen",
            "Öffne Bob und danach Android-Einstellungen öffnen und danach Produktbilder auswählen und dann Bob öffnen",
            "Öffne Bob und danach Produktbilder auswählen? Warum?",
            "Öffne Bob " + "x".repeat(250)
        ).forEach { assertNull("Must fail closed: $it", PhoneTaskPlanParser.parse(it)) }
    }

    @Test fun readOnlyBobPagesCanBeCombinedButBrokerAutomationCannot() {
        assertEquals(listOf(PhoneTask.OPEN_PRODUCTS, PhoneTask.OPEN_SIMULATION),
            PhoneTaskPlanParser.parse("Zeige meine Goldprodukte und danach die Simulationen")?.steps)
        assertEquals(listOf(PhoneTask.OPEN_MARKET, PhoneTask.OPEN_RESEARCH),
            PhoneTaskPlanParser.parse("Analysiere den Goldmarkt und danach zeige die Videos")?.steps)
        for (phrase in listOf(
            "Analysiere den Goldmarkt und kaufe den besten Hebel",
            "Zeige meine Goldprodukte und eröffne eine Position",
            "Zeige die Simulationen und logge dich bei DEGIRO ein",
            "Zeige meine Goldprodukte und drücke Kaufen",
            "Öffne das Orderformular", "Öffne die Trading-App"
        )) assertNull("unsafe: $phrase", PhoneTaskPlanParser.parse(phrase))
    }

    @Test fun aMultiStepPlanCannotBypassSingleStepProtocol() {
        val multiple = "Bob öffnen und danach Einstellungen öffnen"
        assertNull(PhoneTaskProtocol.parseSpeech(multiple))
        assertNull(PhoneTaskProtocol.parseDisplayed(multiple))
        assertEquals(2, PhoneTaskPlanParser.parse(multiple)?.steps?.size)
    }

    @Test fun stopOnlyMatchesExplicitStopPhrases() {
        assertTrue(PhoneTaskPlanParser.isStop("Bob stopp!"))
        assertTrue(PhoneTaskPlanParser.isStop("Auftrag abbrechen"))
        assertFalse(PhoneTaskPlanParser.isStop("Bob stoppen und kaufen"))
        assertNull(PhoneTaskPlanParser.parse("Bob stopp!"))
    }
    @Test fun acceptsCommonSentencePunctuationWithoutPartialExecution() {
        assertEquals(listOf(PhoneTask.OPEN_PRODUCTS, PhoneTask.OPEN_SIMULATION),
            PhoneTaskPlanParser.parse("Zeige meine Goldprodukte. Danach die Simulationen.")?.steps)
        assertEquals(listOf(PhoneTask.OPEN_BOB, PhoneTask.OPEN_PRODUCTS),
            PhoneTaskPlanParser.parse("Bob, öffne Bob, zeige meine Goldprodukte")?.steps)
        assertEquals(listOf(PhoneTask.OPEN_BOB),
            PhoneTaskPlanParser.parse("Bitte zuerst öffne Bob!")?.steps)
        assertNull(PhoneTaskPlanParser.parse(
            "Zeige meine Goldprodukte. Danach kaufe ein Knock-out-Produkt."))
        assertNull(PhoneTaskPlanParser.parse(
            "Öffne Bob, logge dich bei DEGIRO ein"))
        assertNull(PhoneTaskPlanParser.parse(
            "Zeige die Simulationen; sende meine Zugangsdaten"))
    }

    @Test fun keyboardDictationValidatesWholeTextBeforeAnyAction() {
        val dictated = "Zeige meine Goldprodukte und danach die Simulationen"
        val plan = PhoneTaskPlanParser.parse(dictated)
        assertEquals(listOf(PhoneTask.OPEN_PRODUCTS, PhoneTask.OPEN_SIMULATION), plan?.steps)
        assertNull(PhoneTaskProtocol.parseDisplayed(dictated))
        assertEquals(PhoneTask.OPEN_PRODUCTS,
            PhoneTaskProtocol.parseDisplayed("Zeige meine Goldprodukte"))
        assertNull(PhoneTaskPlanParser.parse("Zeige meine Goldprodukte und kaufe Gold"))
        assertNull(PhoneTaskPlanParser.parse("Zeige die Simulationen und öffne die DEGIRO App"))
        assertNull(PhoneTaskPlanParser.parse("Zeige meine Goldprodukte; ändere alle Stopps"))
    }
}
