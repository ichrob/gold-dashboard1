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
    OPEN_SETTINGS("Android-Einstellungen nur öffnen")
}

internal object PhoneTaskProtocol {
    const val OPEN_BOB = "BOB-AUFTRAG: BOB_OEFFNEN"
    const val PICK_IMAGES = "BOB-AUFTRAG: PRODUKTBILDER_WAEHLEN"
    const val OPEN_SETTINGS = "BOB-AUFTRAG: ANDROID_EINSTELLUNGEN_OEFFNEN"

    fun displayLabel(task: PhoneTask): String = when (task) {
        PhoneTask.OPEN_BOB -> "Bob öffnen"
        PhoneTask.PICK_IMAGES -> "Produktbilder auswählen"
        PhoneTask.OPEN_SETTINGS -> "Android-Einstellungen öffnen"
    }

    fun parseDisplayed(input: String): PhoneTask? =
        PhoneTask.entries.firstOrNull { input == displayLabel(it) } ?: parse(input)

    /** Full-phrase allowlist. Never guess an action from a partial transcript. */
    fun parseSpeech(input: String): PhoneTask? {
        if (input.length > 100 || input.any { it == '\n' || it == '\r' || it == ';' }) return null
        val normalized = input.lowercase(Locale.GERMAN)
            .trim().replace(Regex("[.!?]+$"), "")
            .replace(Regex("\\s+"), " ")
        return when (normalized) {
            "bob öffnen", "öffne bob", "starte bob", "bitte bob öffnen" -> PhoneTask.OPEN_BOB
            "produktbilder auswählen", "produktbilder wählen", "bilder für bob auswählen" -> PhoneTask.PICK_IMAGES
            "android-einstellungen öffnen", "einstellungen öffnen", "öffne die einstellungen" -> PhoneTask.OPEN_SETTINGS
            else -> null
        }
    }

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
