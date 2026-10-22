package ch.bob.degirocompanion

import java.util.Locale

/**
 * Ephemeral, on-device conversation context for harmless actions only.
 * Memory means the last successfully LAUNCHED action, not a permission token.
 * There are no names, passwords, trades, network calls or persistent storage.
 */
internal class PhoneConversation(private val contextTtlMs: Long = 120_000L) {
    private var lastTask: PhoneTask? = null
    private var lastTime: Long = 0L

    fun recordLaunched(task: PhoneTask, nowMs: Long) {
        // Only a launched, allowlisted Bob *page* may become conversational
        // memory. A device setting or image picker must never be replayed by
        // saying 'nochmal', even if manually opened once.
        if (VoiceAutoNavigation.allowed(PhoneTaskPlan(listOf(task))) != task) {
            clear()
            return
        }
        lastTask = task
        lastTime = nowMs
    }

    fun interpret(spoken: String, nowMs: Long): PhoneTaskPlan? {
        if (spoken.length > 240) return null
        val value = spoken.lowercase(Locale.GERMAN)
            .trim().replace(Regex("[.!?]+$"), "").replace(Regex("\\s+"), " ")
        if (value in setOf("warum", "wieso", "warum das", "erkläre das",
                "kannst du das erklären", "was bedeutet das", "warum diese auswahl",
                "und warum", "wieso das", "warum denn")) {
            val previous = lastTask
            // A "why?" question is only meaningful after a product explanation.
            // It never upgrades an ordinary page visit into a trade recommendation.
            return if (previous in setOf(PhoneTask.OPEN_LONG_REVIEW, PhoneTask.OPEN_LEVERAGE_REVIEW)
                && nowMs >= lastTime && nowMs - lastTime < contextTtlMs)
                PhoneTaskPlan(listOf(previous!!)) else null
        }
        if (value in setOf("noch mal", "nochmal", "noch einmal", "wiederhole das",
                "wiederhole den letzten schritt", "mach das nochmal", "das nochmal",
                "bitte nochmal")) {
            val previous = lastTask
            return if (previous != null && nowMs >= lastTime &&
                nowMs - lastTime < contextTtlMs) PhoneTaskPlan(listOf(previous)) else null
        }
        return PhoneTaskPlanParser.parse(spoken)
    }

    fun clear() {
        lastTask = null
        lastTime = 0L
    }
}
