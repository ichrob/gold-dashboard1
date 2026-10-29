package ch.bob.degirocompanion

/** Local counters only: no package names, screen text, ISINs or account values. */
internal object ProductReadDiagnostics {
    enum class Outcome { NO_ROOT, NO_FOCUSED_WINDOW, WINDOW_ROOT_MISSING, OTHER_APP,
        DIRECT_ROOT, WINDOW_ROOT, PROTECTED_VIEW, NO_FIELDS, DRAFT, CHANGED, ERROR, LOCKED, SCREEN_HELD, SCREEN_HOLD_FAILED, WINDOW_RECHECK, USER_INTERRUPTED, APP_LEFT, WINDOW_INTERRUPTED, REQUEST_EXPIRED, REQUEST_ATTEMPT_LIMIT, REQUEST_CLOCK_CHANGED, PAGE_SCROLL, PAGE_ABORT, PAGE_COMPLETE, SCROLL_NO_ACTION, SCROLL_AMBIGUOUS, SCROLL_AVAILABLE, SCROLL_REJECTED, SCROLL_PRODUCT_SCOPED, SCROLL_MARKERS_MISSING, SCROLL_MARKERS_CONFLICT }
    var connected = false
    var canRead = false
    var windowAccess = false
    private val counts = mutableMapOf<Outcome, Int>()
    private val pageCauses = mutableMapOf<ProductPageReader.Cause, Int>()
    private val reasons = mutableMapOf<ProductScreenEvidence.Reason, Int>()
    private val launcherIssues = mutableMapOf<MorningReadPolicy.LauncherIssue, Int>()
    fun launcher(issue: MorningReadPolicy.LauncherIssue) {
        if(issue != MorningReadPolicy.LauncherIssue.NONE)
            launcherIssues[issue] = ((launcherIssues[issue] ?: 0) + 1).coerceAtMost(999)
    }
    private var startedAt: Long? = null
    fun reset(now: Long) { counts.clear(); launcherIssues.clear(); reasons.clear(); pageCauses.clear(); startedAt = now }
    fun clear() { counts.clear(); launcherIssues.clear(); reasons.clear(); pageCauses.clear(); startedAt = null }
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
            appendLine("BOB-LESEDIAGNOSE/6")
            appendLine("Dienst verbunden: $connected · Textzugriff: $canRead · Fensterzugriff: $windowAccess")
            if (counts.isEmpty()) append("Noch keine Diagnosemessung.")
            else for (outcome in Outcome.values()) counts[outcome]?.let { appendLine("${outcome.name}: $it") }
            for (issue in MorningReadPolicy.LauncherIssue.values()) launcherIssues[issue]?.let { appendLine("SEARCH_GUARD_${issue.name}: $it") }
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

/** Select the deepest common product container, never a chart merely offering an action. */
internal object ProductScrollPolicy {
    data class Capability(val forward: Boolean, val backward: Boolean,
                          val ancestors: List<Int> = emptyList(), val evidence: Int = 0)
    fun evidence(text: String): Int {
        val identity = Regex("\\b[A-Z]{2}[A-Z0-9]{9}[0-9]\\b").findAll(text.uppercase())
            .any { SeriesEvidence.validIsin(it.value) }
        // Accessibility can expose a label and its price as one node. Recognize
        // only complete labelled quote rows, never bare chart/account amounts.
        val heading = Regex("(?i)^(kursdaten|produktdetails|geld|brief|zuletzt)\\s*[:：]?$")
        val quotedRow = Regex("(?i)^(?:(?:Geld|Brief|Zuletzt)\\s*[:：]?\\s*(?:EUR|CHF|€)?\\s*[0-9]{1,5}[,.][0-9]{2,4}(?:\\s*(?:EUR|CHF|€))?\\s*)+(?:[0-9]{2}/[0-9]{2}/20[0-9]{2}\\s+[0-9]{2}:[0-9]{2})?$")
        val quotes = text.lineSequence().map { it.trim() }.any { heading.matches(it) || quotedRow.matches(it) }
        return (if (identity) 1 else 0) or (if (quotes) 2 else 0)
    }
    fun surface(nodes: List<Capability>): Int? {
        if (nodes.size == 1) return 0
        val required = nodes.fold(0) { bits, node -> bits or node.evidence }
        if (required == 0) return null
        val candidates = nodes.indices.filter { nodes[it].evidence and required == required }
        // A nested wrapper is less specific than its product-bearing descendant.
        return candidates.filter { i -> candidates.none { j -> i != j && i in nodes[j].ancestors } }.singleOrNull()
    }
    fun select(nodes: List<Capability>, forward: Boolean): Int? = surface(nodes)?.takeIf {
        if (forward) nodes[it].forward else nodes[it].backward
    }
}
