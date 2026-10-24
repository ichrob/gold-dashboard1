package ch.bob.degirocompanion

/**
 * Clickable same-phone handoff URI (NO authentication and NO remote authority).
 *
 * A link may be opened by any Android app. Therefore the link only offers a
 * harmless, allowlisted Bob view, and ALWAYS requires fresh local approval.
 * Do not extend this format to URL parameters, files, credentials or trades.
 */
internal object BobHandyDeepLink {
    private const val PREFIX = "bobhandy://handoff/"
    private val allowedName = Regex("OPEN_[A-Z_]{3,30}")

    fun linkFor(task: PhoneTask): String? {
        val candidate = PREFIX + task.name
        return candidate.takeIf { parse(it) == task }
    }

    fun parse(raw: String?): PhoneTask? {
        if (raw == null || raw.length !in 27..90 || !raw.startsWith(PREFIX)) return null
        // Strict canonical representation: no query, fragment, userinfo, encoded
        // aliases, whitespace, authority changes or multiple commands.
        val name = raw.substring(PREFIX.length)
        if (!allowedName.matches(name)) return null
        return ChatShareHandoff.parse("BOB-HANDY/1|" + name)
    }
}
