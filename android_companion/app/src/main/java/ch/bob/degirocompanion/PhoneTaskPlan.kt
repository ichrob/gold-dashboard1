package ch.bob.degirocompanion

import java.util.Locale

/**
 * Fully validated, bounded local voice plan. This is deliberately NOT a general
 * instruction interpreter: every clause must match a harmless action exactly.
 * Unsupported clauses reject the WHOLE sentence, never a partial execution.
 */
internal data class PhoneTaskPlan(val steps: List<PhoneTask>) {
    init { require(steps.size in 1..3 && steps.distinct().size == steps.size) }
    fun summary(): String = steps.mapIndexed { i, action ->
        "${i + 1}. ${PhoneTaskProtocol.displayLabel(action)}"
    }.joinToString(" → ")
}

internal object PhoneTaskPlanParser {
    private val separators = Regex(
        "(?:\\s*,\\s*und\\s+dann\\s+|\\s+und\\s+danach\\s+|\\s+und\\s+dann\\s+|" +
        "\\s+und\\s+|\\s+danach\\s+|\\s+anschließend\\s+|,\\s*dann\\s+)"
    )

    fun isStop(input: String): Boolean {
        val clean = normalize(input) ?: return false
        return clean in setOf("stopp", "stop", "bob stopp", "bob stop",
            "stoppe den auftrag", "auftrag abbrechen", "abbrechen")
    }

    fun parse(input: String): PhoneTaskPlan? {
        val clean = normalize(input) ?: return null
        if (isStop(clean)) return null
        val parts = separators.split(clean)
        if (parts.isEmpty() || parts.size > 3 || parts.any { it.isBlank() }) return null
        val steps = parts.map { parseClause(it) ?: return null }
        if (steps.distinct().size != steps.size) return null
        return PhoneTaskPlan(steps)
    }

    private fun normalize(raw: String): String? {
        if (raw.isBlank() || raw.length > 240 ||
            raw.any { it == '\n' || it == '\r' || it == ';' || it == ':' ||
                it == '|' || it == '\u0000' || it == '?' }) return null
        return raw.lowercase(Locale.GERMAN).trim()
            .replace(Regex("[.!]+$"), "")
            .replace(Regex("\\s+"), " ")
            .replace(Regex("^(?:hallo bob|hey bob|bob),\\s*"), "")
            .trim()
    }

    private fun parseClause(raw: String): PhoneTask? {
        val text = raw.replace(Regex("^(?:bitte |kannst du bitte |würdest du bitte |zuerst |als erstes )"), "")
            .replace(Regex("^dann "), "")
            .replace(Regex(" bitte$"), "")
            .trim()
        return when (text) {
            "bob öffnen", "öffne bob", "starte bob", "öffne zuerst bob",
            "bob starten", "öffne die bob app", "bob app öffnen" -> PhoneTask.OPEN_BOB

            "produktbilder auswählen", "produktbilder wählen", "bilder für bob auswählen",
            "wähle produktbilder aus", "wähle meine produktbilder aus",
            "öffne die bildauswahl", "bilder auswählen", "bilder wählen" -> PhoneTask.PICK_IMAGES

            "android-einstellungen öffnen", "einstellungen öffnen",
            "öffne die einstellungen", "öffne die android-einstellungen",
            "android einstellungen öffnen", "öffne die android einstellungen" ->
                PhoneTask.OPEN_SETTINGS

            else -> null
        }
    }
}
