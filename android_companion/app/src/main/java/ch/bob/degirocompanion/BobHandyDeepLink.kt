package ch.bob.degirocompanion

/**
 * User-tapped, allowlisted, one-shot local display proposal.
 *
 * The HTTPS form is an OS-verified Android App Link ONLY after the public
 * web domain has associated the exact stable signing certificate. An explicit
 * HTTPS view tap may open only Bob's own fixed, read-only page; no orders,
 * credentials, custom actions or remote permissions are ever granted.
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

    /**
     * A deliberate Android HTTPS App Link tap may directly display one fixed
     * Bob-owned website section, without clipboard or a second tap.
     * This is not authentication: OS verification is handled by Android and
     * the parser below still rejects all non-allowlisted paths.
     * Legacy bobhandy:// links and shared text continue to require approval.
     */
    fun directHttpsDisplay(raw: String?): PhoneTask? =
        if (raw?.startsWith(VERIFIED_HTTPS_PREFIX) == true) parse(raw) else null

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
