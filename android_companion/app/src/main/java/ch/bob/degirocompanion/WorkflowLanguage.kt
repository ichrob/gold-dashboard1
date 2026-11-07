package ch.bob.degirocompanion

/** Normalize only the owner's instruction grammar. Preserve field values and never parse OCR as commands. */
internal object WorkflowLanguage {
    fun goal(text: String): String = text.trim().lines().joinToString("\n", transform=::line)
    fun line(text: String): String {
        val question = Regex("(?iu)^(?:kannst du|könntest du|würdest du)\\s+").containsMatchIn(text.trim())
        var value = text.trim()
            .replace(Regex("(?iu)^(?:kannst du|könntest du|würdest du)\\s+"), "")
            .replace(Regex("(?iu)^bitte\\s+"), "")
        if (question) {
            value = value.removeSuffix("?").trim()
            Regex("(?iu)^auf (.+?) (?:drücken|klicken|tippen)$").matchEntire(value)?.let { return "Tippe auf ${it.groupValues[1]}" }
            Regex("(?iu)^(.+?) (?:in|ins) (.+?) (?:eintragen|eingeben|einfügen)$").matchEntire(value)?.let {
                return "Schreibe ${it.groupValues[1]} in ${it.groupValues[2]}"
            }
            Regex("(?iu)^(?:die )?(favoriten|favorites|watchlist) (?:öffnen|anzeigen)$").matchEntire(value)?.let {
                return "Tippe auf ${it.groupValues[1]}"
            }
        }
        val write = Regex("(?iu)^(?:trage|trag|gib|gebe|füge) (.+?) (?:in|ins) (.+?) ein$").matchEntire(value)
        if (write != null) return "Schreibe ${write.groupValues[1]} in ${write.groupValues[2]}"
        val set = Regex("(?iu)^setze (?:das |die |den )?(.+?) auf (.+)$").matchEntire(value)
        if (set != null) return "Schreibe ${set.groupValues[2]} in ${set.groupValues[1]}"
        value = value.replace(Regex("(?iu)^(?:drücke|drück|druecke|drueck|klick|tipp|betätige)\\s+(?:auf\\s+)?"), "Tippe auf ")
        val tab = Regex("(?iu)^(?:öffne|zeige|zeig|wähle|gehe zu|geh zu|wechsle zu|wechsel zu) (?:mir )?(?:die |den |das )?(?:reiter |registerkarte )?(favoriten|favorites|watchlist)$").matchEntire(value)
        if (tab != null) return "Tippe auf ${tab.groupValues[1]}"
        value = value.replace(Regex("(?iu)^(?:such|finde|find)\\s+(?:nach\\s+)?"), "Suche ")
        val products = Regex("(?iu)^(?:zeige|zeig) mir (?:die )?(gold|silber)([- ]hebelprodukte)?$").matchEntire(value)
        if (products != null) return "Suche ${products.groupValues[1]}${products.groupValues[2]}"
        return value.replace(Regex("(?iu)^(?:tippe|klicke) auf "), "Tippe auf ")
            .replace(Regex("(?iu)^(?:schreib|schreibe) "), "Schreibe ")
    }
}
