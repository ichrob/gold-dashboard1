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
    @Test fun productQuestionsAreReadOnlyAndRequireExactUtterance() {
        for (phrase in listOf(
            "Zeige mir die drei besten LONG-Produkte und erkläre die Unterschiede",
            "Zeige mir die drei besten Long Produkte",
            "Vergleiche die drei besten Long-Produkte",
            "Erkläre mir die LONG-Produkte"
        )) {
            assertEquals("read-only question: $phrase", PhoneTask.OPEN_LONG_REVIEW,
                PhoneTaskPlanParser.parse(phrase)?.steps?.singleOrNull())
        }
        assertEquals(PhoneTask.OPEN_PRODUCTS,
            PhoneTaskPlanParser.parse("Gold Hebelprodukte")?.steps?.singleOrNull())
        for (phrase in listOf(
            "Zeige mir die drei besten LONG-Produkte und kaufe sie",
            "LONG-Produkte vergleichen und danach handle automatisch",
            "Verkaufe mein Gold-Hebelprodukt",
            "Zeige mir die drei besten LONG-Produkte und ändere den Stopp"
        )) assertNull("unsafe mix: $phrase", PhoneTaskPlanParser.parse(phrase))
    }
    @Test fun recognizesOnlySpecificHighestLeverageReadOnlyQuestions() {
        for (phrase in listOf("Welches hat den besten Hebel",
            "Welches Produkt hat den höchsten Hebel",
            "Erkläre den höchsten Hebel",
            "Welches von den Produkten hat den größten Hebel")) {
            assertEquals(listOf(PhoneTask.OPEN_LEVERAGE_REVIEW),
                PhoneTaskPlanParser.parse(phrase)?.steps)
        }
        assertNull(PhoneTaskPlanParser.parse(
            "Welches hat den besten Hebel und kaufe davon 100"))
        assertNull(PhoneTaskPlanParser.parse(
            "Zeige mir das Hebelrisiko und ändere den Stopp"))
    }
    @Test fun samsungTranscribesBobAddressWithoutComma() {
        // User's real Samsung result: "Bob zeige meine goldprodukte" was
        // rejected, so Bob never opened despite working voice recognition.
        for (spoken in listOf(
            "Bob zeige meine goldprodukte",
            "Bob zeige mir die goldprodukte",
            "Bob, zeige mir die Goldprodukte.",
            "Hallo Bob zeige mir die Goldprodukte",
            "Hey Bob zeige mir die Gold-Produkte",
            "Bob zeige mir die Gold Hebelprodukte",
            "Bob, zeige meine Goldprodukte",
            "Bob zeige meine Goldprodukte.",
            "Bob zeige meine Goldprodukte!",
            "Hallo Bob zeige meine Goldprodukte",
            "Hey Bob zeige meine Goldprodukte",
            "Bob Gold Hebelprodukte",
            "Bob zeige mir die Gold Hebelprodukte"
        )) {
            val task=PhoneTaskPlanParser.parse(spoken)?.steps?.singleOrNull()
            assertEquals("spoken: $spoken", PhoneTask.OPEN_PRODUCTS, task)
            assertEquals("same safe navigation: $spoken", PhoneTask.OPEN_PRODUCTS,
                task?.let { VoiceAutoNavigation.allowed(PhoneTaskPlan(listOf(it))) })
        }
        // Important regression: Bob öffnen is a complete legacy command,
        // not an address followed by the unrecognized word "öffnen".
        assertEquals(PhoneTask.OPEN_BOB, PhoneTaskPlanParser.parse("Bob öffnen")?.steps?.singleOrNull())
        assertEquals(PhoneTask.OPEN_BOB, PhoneTaskPlanParser.parse("Bob starten")?.steps?.singleOrNull())
        assertEquals(PhoneTask.OPEN_LONG_REVIEW,
            PhoneTaskPlanParser.parse("Bob zeige mir die drei besten Long-Produkte und erkläre die Unterschiede")?.steps?.singleOrNull())
    }

    @Test fun addressedMixedOrTradingInstructionsRemainFullyRejected() {
        for (spoken in listOf(
            "Bob zeige mir die Goldprodukte und kaufe davon 100 Stück",
            "Bob zeige mir die Goldprodukte und logge dich in DEGIRO ein",
            "Bob zeige mir die Goldprodukte und öffne die Ordermaske",
            "Bob zeige Goldprodukte und kaufe Gold",
            "Bob zeige meine Goldprodukte und danach platziere eine Order",
            "Bob zeige meine Goldprodukte und logge dich in DEGIRO ein",
            "Bob kaufe mir das beste Goldprodukt",
            "Bob ändere meinen Stopp",
            "Bob öffne ein Orderformular",
            "Bob zeige meine Goldprodukte? kaufe Gold",
            "Bob"
        )) {
            assertNull("must reject full unsafe utterance: $spoken",
                PhoneTaskPlanParser.parse(spoken))
        }
        val compound=PhoneTaskPlanParser.parse("Bob zeige Goldprodukte und danach Simulationen")
        assertEquals(listOf(PhoneTask.OPEN_PRODUCTS, PhoneTask.OPEN_SIMULATION), compound?.steps)
        assertNull("compound commands must not auto-run",
            compound?.let { VoiceAutoNavigation.allowed(it) })
    }
}
