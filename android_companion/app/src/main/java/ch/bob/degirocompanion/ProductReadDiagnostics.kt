package ch.bob.degirocompanion

/** Local counters only: no package names, screen text, ISINs or account values. */
internal object ProductReadDiagnostics {
    enum class Outcome { LIST_IMAGE_CAPTURED, LIST_SCROLL_SENT, LIST_HEADER_SCROLLED_AWAY, LIST_TAB_SELECTION_UNREPORTED, CATEGORY_CLICK_SENT, CATEGORY_SCROLL_SENT, SEARCH_INPUT_TAP_SENT, SEARCH_INPUT_TAP_REJECTED, SEARCH_INPUT_SPATIAL, SEARCH_INPUT_CLUSTER, SEARCH_FOCUS_ACCEPTED, SEARCH_FOCUS_REJECTED, SEARCH_TAP_SENT, SEARCH_TAP_COMPLETED, SEARCH_TAP_CANCELLED, SEARCH_TAP_REJECTED, NO_ROOT, NO_FOCUSED_WINDOW, WINDOW_ROOT_MISSING, OTHER_APP,
        DIRECT_ROOT, WINDOW_ROOT, PROTECTED_VIEW, NO_FIELDS, DRAFT, CHANGED, ERROR, LOCKED, SCREEN_HELD, SCREEN_HOLD_FAILED, WINDOW_RECHECK, USER_INTERRUPTED, APP_LEFT, WINDOW_INTERRUPTED, REQUEST_EXPIRED, REQUEST_ATTEMPT_LIMIT, REQUEST_CLOCK_CHANGED, PAGE_SCROLL, PAGE_ABORT, PAGE_COMPLETE, SCROLL_NO_ACTION, SCROLL_AMBIGUOUS, SCROLL_AVAILABLE, SCROLL_REJECTED, SCROLL_PRODUCT_SCOPED, SCROLL_MARKERS_MISSING, SCROLL_MARKERS_CONFLICT }
    var connected = false
    var canRead = false
    var windowAccess = false
    private val counts = mutableMapOf<Outcome, Int>()
    private val pageCauses = mutableMapOf<ProductPageReader.Cause, Int>()
    private val reasons = mutableMapOf<ProductScreenEvidence.Reason, Int>()
    private val launcherIssues = mutableMapOf<MorningReadPolicy.LauncherIssue, Int>()
    enum class SearchInputEvidence { NO_EDITABLE, MULTIPLE_EDITABLE, DISABLED,
        TRACKED_QUERY_IDENTITY, TRACKED_QUERY_NODE_CHANGED, TRACKED_QUERY_MISSING,
        NO_METADATA, OTHER_METADATA }
    private val searchInputEvidence = mutableMapOf<SearchInputEvidence, Int>()
    enum class SearchSource { INPUT_TEXT, INPUT_HINT, INPUT_DESCRIPTION, INPUT_ID, PAGE_LABEL }
    enum class SearchFeature { PRESENT, EXACT_PROMPT, PROMPT_WORDS, SEARCH_WORD, ISIN_WORD, SYMBOL_WORD }
    private val searchShape = mutableMapOf<Pair<SearchSource, SearchFeature>, Int>()
    /** Convert field metadata to fixed flags immediately; never retain its value. */
    fun searchShape(source:SearchSource, value:String) {
        val normalized=value.take(2000).lowercase().replace(Regex("[\\s\\p{Zs}]+")," ").trim()
        if(normalized.isEmpty()) return
        fun flag(feature:SearchFeature) {
            val key=source to feature
            searchShape[key]=((searchShape[key] ?: 0)+1).coerceAtMost(999)
        }
        flag(SearchFeature.PRESENT)
        if(normalized=="mit namen, isin oder symbol suchen") flag(SearchFeature.EXACT_PROMPT)
        val isin=Regex("\\bisin\\b").containsMatchIn(normalized)
        val symbol=Regex("\\bsymbol\\b").containsMatchIn(normalized)
        val search=Regex("suche|search").containsMatchIn(normalized)
        if(isin) flag(SearchFeature.ISIN_WORD)
        if(symbol) flag(SearchFeature.SYMBOL_WORD)
        if(search) flag(SearchFeature.SEARCH_WORD)
        if(isin && symbol && search) flag(SearchFeature.PROMPT_WORDS)
    }
    private fun classifySearchInput(nodes: List<MorningReadPolicy.Node>): SearchInputEvidence {
        val inputs=nodes.filter { it.editable }
        if(inputs.isEmpty()) return SearchInputEvidence.NO_EDITABLE
        if(inputs.size!=1) return SearchInputEvidence.MULTIPLE_EDITABLE
        val input=inputs.single()
        if(!input.enabled) return SearchInputEvidence.DISABLED
        if(input.writtenNodeIdentity) return SearchInputEvidence.TRACKED_QUERY_IDENTITY
        if(input.writtenQueryPresent) return SearchInputEvidence.TRACKED_QUERY_NODE_CHANGED
        if(input.writtenQueryExpected) return SearchInputEvidence.TRACKED_QUERY_MISSING
        if(input.id.isBlank() && input.description.isBlank() && input.hint.isBlank())
            return SearchInputEvidence.NO_METADATA
        return SearchInputEvidence.OTHER_METADATA
    }
    fun launcher(issue: MorningReadPolicy.LauncherIssue, nodes: List<MorningReadPolicy.Node> = emptyList()) {
        if(issue != MorningReadPolicy.LauncherIssue.NONE)
            launcherIssues[issue] = ((launcherIssues[issue] ?: 0) + 1).coerceAtMost(999)
        if(issue == MorningReadPolicy.LauncherIssue.INPUT_LABEL) {
            val evidence=classifySearchInput(nodes)
            searchInputEvidence[evidence] = ((searchInputEvidence[evidence] ?: 0) + 1).coerceAtMost(999)
        }
    }
    private var startedAt: Long? = null
    fun reset(now: Long) { counts.clear(); launcherIssues.clear(); searchInputEvidence.clear(); searchShape.clear(); reasons.clear(); pageCauses.clear(); startedAt = now }
    fun clear() { counts.clear(); launcherIssues.clear(); searchInputEvidence.clear(); searchShape.clear(); reasons.clear(); pageCauses.clear(); startedAt = null }
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
            appendLine("BOB-LESEDIAGNOSE/7")
            appendLine("Dienst verbunden: $connected · Textzugriff: $canRead · Fensterzugriff: $windowAccess")
            if (counts.isEmpty()) append("Noch keine Diagnosemessung.")
            else for (outcome in Outcome.values()) counts[outcome]?.let { appendLine("${outcome.name}: $it") }
            for (issue in MorningReadPolicy.LauncherIssue.values()) launcherIssues[issue]?.let { appendLine("SEARCH_GUARD_${issue.name}: $it") }
            for (evidence in SearchInputEvidence.values()) searchInputEvidence[evidence]?.let { appendLine("SEARCH_INPUT_${evidence.name}: $it") }
            for (source in SearchSource.values()) for(feature in SearchFeature.values())
                searchShape[source to feature]?.let { appendLine("SEARCH_SHAPE_${source.name}_${feature.name}: $it") }
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
