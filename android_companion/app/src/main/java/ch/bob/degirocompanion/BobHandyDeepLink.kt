package ch.bob.degirocompanion

/**
 * User-tapped, allowlisted, one-shot local display proposal.
 *
 * The HTTPS form is an OS-verified Android App Link ONLY after the public
 * web domain has associated the exact stable signing certificate. An app link
 * is still never authorization to navigate without a second local approval.
 */
internal object BobHandyDeepLink {
    private const val LEGACY_PREFIX = "bobhandy://handoff/"
    private const val VERIFIED_HTTPS_PREFIX = "https://bob-private-scanner.onrender.com/handy/"
    private val allowedName = Regex("OPEN_[A-Z_]{3,30}")

    fun linkFor(task: PhoneTask): String? {
        val candidate = LEGACY_PREFIX + task.name
        return candidate.takeIf { parse(it) == task }
    }

    fun httpsLinkFor(task: PhoneTask): String? {
        val candidate = VERIFIED_HTTPS_PREFIX + task.name
        return candidate.takeIf { parse(it) == task }
    }

    fun parse(raw: String?): PhoneTask? {
        if (raw == null || raw.length !in 27..110) return null
        // ChatGPT appends this fixed attribution suffix when tapping HTTPS.
        // It cannot select a task, authorize it or carry arbitrary parameters.
        val clean = if (raw.startsWith(VERIFIED_HTTPS_PREFIX) &&
            raw.endsWith("?utm_source=chatgpt.com"))
            raw.removeSuffix("?utm_source=chatgpt.com") else raw
        val prefix = when {
            clean.startsWith(LEGACY_PREFIX) -> LEGACY_PREFIX
            clean.startsWith(VERIFIED_HTTPS_PREFIX) -> VERIFIED_HTTPS_PREFIX
            else -> return null
        }
        // Only the exact ChatGPT marker on verified HTTPS is permitted.
        // Extra query fields, fragments, encoded paths and broker commands fail.
        val name = clean.substring(prefix.length)
        if (!allowedName.matches(name)) return null
        return ChatShareHandoff.parse("BOB-HANDY/1|" + name)
    }
}
