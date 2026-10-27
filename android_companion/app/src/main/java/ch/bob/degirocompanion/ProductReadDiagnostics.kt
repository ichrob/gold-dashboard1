package ch.bob.degirocompanion

/** Local counters only: no package names, screen text, ISINs or account values. */
internal object ProductReadDiagnostics {
    enum class Outcome { NO_ROOT, NO_FOCUSED_WINDOW, WINDOW_ROOT_MISSING, OTHER_APP,
        DIRECT_ROOT, WINDOW_ROOT, PROTECTED_VIEW, NO_FIELDS, DRAFT, CHANGED, ERROR, LOCKED }
    var connected = false
    var canRead = false
    var windowAccess = false
    private val counts = mutableMapOf<Outcome, Int>()
    private var startedAt: Long? = null
    fun reset(now: Long) { counts.clear(); startedAt = now }
    fun clear() { counts.clear(); startedAt = null }
    fun record(outcome: Outcome) { counts[outcome] = ((counts[outcome] ?: 0) + 1).coerceAtMost(999) }
    fun report(now: Long): String {
        val start = startedAt
        if (start != null && (now < start || now - start > 300000)) clear()
        return buildString {
            appendLine("BOB-LESEDIAGNOSE/1")
            appendLine("Dienst verbunden: $connected · Textzugriff: $canRead · Fensterzugriff: $windowAccess")
            if (counts.isEmpty()) append("Noch keine Diagnosemessung.")
            else for (outcome in Outcome.values()) counts[outcome]?.let { appendLine("${outcome.name}: $it") }
        }.trim()
    }
}

internal object ProductWindowPolicy {
    data class Window(val active: Boolean, val focused: Boolean, val application: Boolean)
    fun select(windows: List<Window>): Int? = windows.indices.filter {
        windows[it].active && windows[it].focused && windows[it].application
    }.singleOrNull()
}
