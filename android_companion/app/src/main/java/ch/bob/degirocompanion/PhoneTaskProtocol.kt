package ch.bob.degirocompanion

import java.util.Locale

/**
 * Local, one-shot actions accepted from a user-shared ChatGPT/Bob text.
 *
 * This parser is intentionally NOT a language model or a general script runner.
 * An untrusted share intent can only suggest one exact, harmless action. The
 * activity must present the action and require another explicit tap.
 */
internal enum class PhoneTask(val description: String) {
    OPEN_BOB("Bob im Browser öffnen"),
    PICK_IMAGES("Android-Bildauswahl für bestehende Bob-OCR öffnen"),
    OPEN_SETTINGS("Android-Einstellungen nur öffnen"),
    OPEN_PRODUCTS("Bob Gold-Hebelprodukte anzeigen"),
    OPEN_LONG_REVIEW("Bobs vorhandene LONG-Produktauswahl und Begründungen ansehen"),
    OPEN_LEVERAGE_REVIEW("Bobs vorhandene Hebel-Risikohinweise ansehen"),
    OPEN_TRADE("Bob Mein Trade anzeigen"),
    OPEN_SIMULATION("Bob Simulation anzeigen"),
    OPEN_LEARNING("Bob Lernen und Ergebnisse anzeigen"),
    OPEN_RESEARCH("Bob Gold-Recherche anzeigen"),
    OPEN_MARKET("Bob Goldmarkt-Übersicht anzeigen")
}

internal object PhoneTaskProtocol {
    const val OPEN_BOB = "BOB-AUFTRAG: BOB_OEFFNEN"
    const val PICK_IMAGES = "BOB-AUFTRAG: PRODUKTBILDER_WAEHLEN"
    const val OPEN_SETTINGS = "BOB-AUFTRAG: ANDROID_EINSTELLUNGEN_OEFFNEN"

    fun displayLabel(task: PhoneTask): String = when (task) {
        PhoneTask.OPEN_BOB -> "Bob öffnen"
        PhoneTask.PICK_IMAGES -> "Produktbilder auswählen"
        PhoneTask.OPEN_SETTINGS -> "Android-Einstellungen öffnen"
        PhoneTask.OPEN_PRODUCTS -> "Goldprodukte anzeigen"
        PhoneTask.OPEN_LONG_REVIEW -> "LONG-Produkte vergleichen"
        PhoneTask.OPEN_LEVERAGE_REVIEW -> "Höchsten Hebel erklären"
        PhoneTask.OPEN_TRADE -> "Mein Trade anzeigen"
        PhoneTask.OPEN_SIMULATION -> "Simulationen anzeigen"
        PhoneTask.OPEN_LEARNING -> "Lernen anzeigen"
        PhoneTask.OPEN_RESEARCH -> "Recherche anzeigen"
        PhoneTask.OPEN_MARKET -> "Goldmarkt anzeigen"
    }

    fun parseDisplayed(input: String): PhoneTask? =
        PhoneTask.entries.firstOrNull { input == displayLabel(it) }
            ?: parse(input)
            ?: PhoneTaskPlanParser.parse(input)?.steps?.singleOrNull()

    /** Single-command callers retain the old safe semantics. Compound plans
     * must use PhoneTaskPlanParser and review EACH step on the device. */
    fun parseSpeech(input: String): PhoneTask? =
        PhoneTaskPlanParser.parse(input)?.steps?.singleOrNull()

    fun parse(input: String): PhoneTask? {
        if (input.length > 90) return null
        return when (input.trim()) {
            OPEN_BOB -> PhoneTask.OPEN_BOB
            PICK_IMAGES -> PhoneTask.PICK_IMAGES
            OPEN_SETTINGS -> PhoneTask.OPEN_SETTINGS
            else -> null
        }
    }
}
