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
        val text = raw.replace(Regex("^(?:bitte |kannst du bitte |würdest du bitte |zuerst |als erstes |und jetzt |und danach |und dann |jetzt |zeige mir bitte |zeig mir bitte )"), "")
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

            "goldprodukte anzeigen", "gold-hebelprodukte anzeigen", "goldhebelprodukte anzeigen",
            "zeige goldprodukte", "zeige meine goldprodukte", "zeige mir meine goldprodukte",
            "zeig mir die goldprodukte", "zeige die gold-hebelprodukte",
            "öffne die goldprodukte", "öffne goldprodukte", "zeige mir die goldhebelprodukte",
            "meine goldprodukte", "die goldprodukte" -> PhoneTask.OPEN_PRODUCTS

            "mein trade anzeigen", "zeige meinen trade", "zeig meinen trade",
            "zeige mir meinen trade", "öffne mein trade", "mein trade", "meinen trade",
            "zeige den aktiven trade", "aktiven trade anzeigen" -> PhoneTask.OPEN_TRADE

            "simulationen anzeigen", "simulation anzeigen", "zeige die simulationen",
            "zeig mir die simulationen", "zeige mir meine simulationen",
            "öffne die simulationen", "die simulationen", "simulationen",
            "zeige die tests", "zeige mir die tests" -> PhoneTask.OPEN_SIMULATION

            "lernen anzeigen", "zeige meine lernergebnisse", "lernergebnisse anzeigen",
            "zeige mir die lernergebnisse", "zeige die lernfunktion",
            "öffne lernen", "die lernergebnisse", "zeige mir die auswertungen" ->
                PhoneTask.OPEN_LEARNING

            "recherche anzeigen", "zeige mir die recherche", "öffne die recherche",
            "zeige die goldrecherche", "zeige die videos", "öffne recherche",
            "die recherche" -> PhoneTask.OPEN_RESEARCH

            "goldmarkt anzeigen", "goldmarkt analysieren", "analysiere den goldmarkt",
            "zeige die goldmarktanalyse", "zeige mir die goldmarktanalyse",
            "zeige die marktübersicht", "marktübersicht anzeigen",
            "zeige mir den goldmarkt", "goldanalyse anzeigen",
            "öffne die marktübersicht" -> PhoneTask.OPEN_MARKET

            else -> null
        }
    }
}
