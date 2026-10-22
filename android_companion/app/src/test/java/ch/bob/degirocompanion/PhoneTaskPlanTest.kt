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
}
