package ch.bob.degirocompanion

/** One volatile owner task, continued only after the existing local login verifies Markets. No PIN is stored here. */
internal object WorkflowLoginHandoff {
    private var started = -1L
    private var action: (() -> Unit)? = null
    var generation = 0; private set
    fun pending(now: Long) = action != null && now >= started && now - started < 65_000L
    fun arm(now: Long, next: () -> Unit) {
        check(action == null) { "Anmeldung läuft bereits." }
        generation++; started = now; action = next
    }
    fun complete(code: String, now: Long): (() -> Unit)? {
        val next = action.takeIf { pending(now) && code == "LOCAL_PIN_HOME_VISIBLE" }
        clear()
        return next
    }
    fun clear() { generation++; started = -1L; action = null }
}
