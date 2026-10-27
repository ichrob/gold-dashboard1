package ch.bob.degirocompanion

/** Local counters only: no package names, screen text, ISINs or account values. */
internal object ProductReadDiagnostics {
    enum class Outcome { NO_ROOT, NO_FOCUSED_WINDOW, WINDOW_ROOT_MISSING, OTHER_APP,
        DIRECT_ROOT, WINDOW_ROOT, PROTECTED_VIEW, NO_FIELDS, DRAFT, CHANGED, ERROR, LOCKED, PAGE_SCROLL, PAGE_ABORT, PAGE_COMPLETE, SCROLL_NO_ACTION, SCROLL_AMBIGUOUS, SCROLL_AVAILABLE, SCROLL_REJECTED }
    var connected = false
    var canRead = false
    var windowAccess = false
    private val counts = mutableMapOf<Outcome, Int>()
    private val pageCauses = mutableMapOf<ProductPageReader.Cause, Int>()
    private val reasons = mutableMapOf<ProductScreenEvidence.Reason, Int>()
    private var startedAt: Long? = null
    fun reset(now: Long) { counts.clear(); reasons.clear(); pageCauses.clear(); startedAt = now }
    fun clear() { counts.clear(); reasons.clear(); pageCauses.clear(); startedAt = null }
    fun record(outcome: Outcome) { counts[outcome] = ((counts[outcome] ?: 0) + 1).coerceAtMost(999) }
    fun page(cause: ProductPageReader.Cause) {
        if (cause != ProductPageReader.Cause.NONE) pageCauses[cause] = ((pageCauses[cause] ?: 0) + 1).coerceAtMost(999)
    }
    fun rejected(reason: ProductScreenEvidence.Reason) {
        if (reason != ProductScreenEvidence.Reason.NONE) reasons[reason] = ((reasons[reason] ?: 0) + 1).coerceAtMost(999)
    }
    fun report(now: Long): String {
        val start = startedAt
        if (start != null && (now < start || now - start > 300000)) clear()
        return buildString {
            appendLine("BOB-LESEDIAGNOSE/4")
            appendLine("Dienst verbunden: $connected · Textzugriff: $canRead · Fensterzugriff: $windowAccess")
            if (counts.isEmpty()) append("Noch keine Diagnosemessung.")
            else for (outcome in Outcome.values()) counts[outcome]?.let { appendLine("${outcome.name}: $it") }
            for (cause in ProductPageReader.Cause.values()) pageCauses[cause]?.let { appendLine("PAGE_${cause.name}: $it") }
            for (reason in ProductScreenEvidence.Reason.values()) reasons[reason]?.let { appendLine("FIELD_${reason.name}: $it") }
        }.trim()
    }
}

internal object ProductWindowPolicy {
    data class Window(val active: Boolean, val focused: Boolean, val application: Boolean)
    fun select(windows: List<Window>): Int? = windows.indices.filter {
        windows[it].active && windows[it].focused && windows[it].application
    }.singleOrNull()
}

/** Only a unique advertised action can be used; unrelated non-action containers do not veto it. */
internal object ProductScrollPolicy {
    data class Capability(val forward: Boolean, val backward: Boolean)
    fun select(nodes: List<Capability>, forward: Boolean): Int? = nodes.indices.filter {
        if (forward) nodes[it].forward else nodes[it].backward
    }.singleOrNull()
}
