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
        lastTask = task
        lastTime = nowMs
    }

    fun interpret(spoken: String, nowMs: Long): PhoneTaskPlan? {
        if (spoken.length > 240) return null
        val value = spoken.lowercase(Locale.GERMAN)
            .trim().replace(Regex("[.!]+$"), "").replace(Regex("\\s+"), " ")
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
