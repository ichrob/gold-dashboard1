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
        "(?:\\.\\s*(?:und\\s+)?(?:dann|danach|anschließend)\\s+|" +
        "\\s*,\\s*und\\s+dann\\s+|\\s+und\\s+danach\\s+|\\s+und\\s+dann\\s+|" +
        "\\s+und\\s+|\\s+danach\\s+|\\s+anschließend\\s+|,\\s*dann\\s+|,\\s+)"
    )

    fun isStop(input: String): Boolean {
        val clean = normalize(input) ?: return false
        return clean in setOf("stopp", "stop", "bob stopp", "bob stop",
            "stoppe den auftrag", "auftrag abbrechen", "abbrechen")
    }

    fun parse(input: String): PhoneTaskPlan? {
        val clean = normalize(input) ?: return null
        if (isStop(clean)) return null
        // A few exact, read-only product QUESTIONS contain the German word
        // "und" but are one intent, not a series of unrestricted commands.
        if (parseClause(clean) == PhoneTask.OPEN_LONG_REVIEW)
            return PhoneTaskPlan(listOf(PhoneTask.OPEN_LONG_REVIEW))
        val parts = separators.split(clean)
        if (parts.isEmpty() || parts.size > 3 || parts.any { it.isBlank() }) return null
        val steps = parts.map { parseClause(it) ?: return null }
        if (steps.distinct().size != steps.size) return null
        return PhoneTaskPlan(steps)
    }

    private fun normalize(raw: String): String? {
        if (raw.isBlank() || raw.length > 240 ||
            raw.any { it == '\n' || it == '\r' || it == ';' || it == ':' ||
                it == '|' || it == '\u0000' }) return null
        val clean = raw.lowercase(Locale.GERMAN).trim()
            .replace(Regex("[.!?]+$"), "")
            .replace(Regex("\\s+"), " ")
            .replace(Regex("^(?:hallo bob|hey bob|bob),\\s*"), "")
            .trim()
        // Google/Samsung can omit spoken punctuation: "Bob zeige ..."
        // is the SAME explicit, locally allowlisted navigation as "Bob, zeige ...".
        // Preserve "Bob öffnen"/"Bob starten" (existing exact commands).
        // The remaining complete sentence MUST still match our strict whitelist;
        // no prefix-only, fuzzy, broker or partial execution is allowed.
        val addressed = if (listOf("bob öffnen", "bob starten", "bob app öffnen")
                .any { clean == it || clean.startsWith("$it und ") ||
                    clean.startsWith("$it, ") || clean.startsWith("$it. ") }) {
            clean
        } else {
            clean.replace(Regex("^(?:hallo bob|hey bob|bob)\\s+"), "")
        }
        // Natural speech questions may end in '?' but an internal question
        // mark still rejects a mixed/ambiguous sentence in its entirety.
        return addressed.takeUnless { '?' in it }
    }

    private fun parseClause(raw: String): PhoneTask? {
        val text = raw.replace(Regex("^(?:(?:bitte|kannst du bitte|würdest du bitte|zuerst|" +
            "als erstes|und jetzt|und danach|und dann|jetzt|zeige mir bitte|" +
            "zeig mir bitte|dann)\\s+)+"), "")
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
            // Exact Samsung dictation: "Bob zeige mir die Goldprodukte" was
            // transcribed correctly but rejected by the local whitelist.
            "zeige mir die goldprodukte", "zeig mir die goldprodukte",
            // Samsung real-device dictation omitted "die":
            // "Bob zeige mir goldprodukte". Keep exact safe page aliases;
            // do not turn product actions into fuzzy or partial commands.
            "zeige mir goldprodukte", "zeig mir goldprodukte",
            "zeige mir gold-produkte", "zeig mir gold-produkte",
            "zeige mir goldhebelprodukte", "zeig mir goldhebelprodukte",
            "zeige mir gold hebelprodukte", "zeige mir gold hebel produkte",
            "zeige mir die gold-produkte", "zeige mir die gold hebelprodukte",
            "zeige die gold-hebelprodukte",
            "öffne die goldprodukte", "öffne goldprodukte", "zeige mir die goldhebelprodukte",
            "meine goldprodukte", "die goldprodukte", "gold hebelprodukte",
            "gold hebel produkte", "gold-hebelprodukte", "goldhebelprodukte",
            "gold hebelprodukte anzeigen", "zeige mir die gold hebelprodukte",
            "öffne die gold hebelprodukte" -> PhoneTask.OPEN_PRODUCTS

            "long-produkte vergleichen", "long produkte vergleichen",
            "zeige mir die drei besten long-produkte",
            "zeige mir die drei besten long produkte",
            "zeige mir die drei besten long-produkte und erkläre die unterschiede",
            "zeige mir die drei besten long produkte und erkläre die unterschiede",
            "vergleiche die drei besten long-produkte",
            "vergleiche die drei besten long produkte",
            "erkläre mir die long-produkte", "erkläre mir die long produkte",
            "zeige mir den long-vergleich" -> PhoneTask.OPEN_LONG_REVIEW

            "höchsten hebel erklären", "welches produkt hat den höchsten hebel",
            "welches hat den höchsten hebel", "welches hat den besten hebel",
            "welches goldprodukt hat den höchsten hebel",
            "welches von den produkten hat den größten hebel",
            "was ist mit dem hebelrisiko", "zeige das hebelrisiko",
            "erkläre den höchsten hebel" -> PhoneTask.OPEN_LEVERAGE_REVIEW

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
