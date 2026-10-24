package ch.bob.degirocompanion

/**
 * Same-phone ChatGPT -> Bob handoff via the Android Sharesheet.
 *
 * Nothing here authenticates ChatGPT as sender. All incoming shares are untrusted
 * proposals which MUST be reviewed and individually approved on this phone.
 * No arbitrary URLs, apps, settings, images, broker actions or multi-step plans.
 * No network, accessibility permissions or hidden Android automation.
 */
internal object ChatShareHandoff {
    private val allowed = setOf(
        PhoneTask.OPEN_BOB, PhoneTask.OPEN_PRODUCTS,
        PhoneTask.OPEN_LONG_REVIEW, PhoneTask.OPEN_LEVERAGE_REVIEW,
        PhoneTask.OPEN_TRADE, PhoneTask.OPEN_SIMULATION, PhoneTask.OPEN_LEARNING,
        PhoneTask.OPEN_RESEARCH, PhoneTask.OPEN_MARKET
    )

    const val PRODUCTS = "BOB-HANDY/1|OPEN_PRODUCTS"

    fun parse(raw: String): PhoneTask? {
        // Reject entire shared messages, URLs, control characters, multi-line
        // content, compound plans and credential/broker input. No partial match.
        if (raw.isBlank() || raw.length > 100 ||
            raw.any { it == '\n' || it == '\r' || it == '\u0000' ||
                it == ';' || it == '<' || it == '>' }) return null
        val clean = raw.trim()
        val task = if (clean.startsWith("BOB-HANDY/1|")) {
            val name = clean.removePrefix("BOB-HANDY/1|")
            allowed.firstOrNull { it.name == name }
        } else if (clean.startsWith("https://") || clean.startsWith("bobhandy://")) {
            // Some ChatGPT/Android clients hand off an app link as a text
            // share rather than an ACTION_VIEW Intent. Accept ONLY the
            // exact canonical harmless links already permitted by the
            // same OS-link parser; never a partial URL or extra query.
            // BobHandyDeepLink delegates back only with BOB-HANDY/1|,
            // so this branch cannot recurse on link input.
            BobHandyDeepLink.parse(clean)
        } else {
            // Legacy German command shared from ChatGPT; exact local parser only.
            PhoneTaskProtocol.parseDisplayed(clean)
        }
        return task?.takeIf { it in allowed }
    }
}
