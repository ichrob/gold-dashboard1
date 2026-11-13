package ch.bob.degirocompanion

/** After an acknowledged BACK, do not process the next ISIN until a genuine
 * read-only DEGIRO Markets search is independently recognized. No order action
 * is ever authorized by this transition. */
internal class ProductReturnTransition {
    enum class State { IDLE, WAITING, READY, FAILED }
    enum class Failure { NONE, TIMEOUT, PROTECTED, WINDOW, INPUT, IDENTITY }
    var failure = Failure.NONE
        private set
    private fun fail(reason: Failure): State { clear(); failure=reason; return State.FAILED }
    private var target: String? = null
    private var window: Int? = null
    private var started = 0L
    private var backRetried = false

    fun begin(previousTarget: String, previousWindow: Int, now: Long) {
        target=previousTarget;window=previousWindow;started=now;backRetried=false;failure=Failure.NONE
    }

    /** The broker may already be back at its independently verified search.
     * In that case no additional BACK should leave Markets or abort the batch. */
    fun confirmSearch(nodes: List<MorningReadPolicy.Node>, previous: String,
                      currentWindow: Int, now: Long): Boolean {
        begin(previous, currentWindow, now)
        val ready = poll(nodes, currentWindow, now) == State.READY
        clear()
        return ready
    }

    private fun searchReady(nodes: List<MorningReadPolicy.Node>, previous: String): Boolean {
        fun has(label: String) = nodes.any { it.text.trim().equals(label, true) }
        // A detail's overview/search icon is not the Markets search page.
        if (nodes.size > 500 || !has("Märkte") ||
            !(has("Nach Produkttyp durchsuchen") || has("Top Ergebnisse") ||
                (has("Zuletzt") && has("Alle löschen"))) ||
            listOf("Kursdaten", "Produktdetails", "Orderdetails", "Orderübersicht",
                "Orderzusammenfassung").any(::has)) return false
        val inputs=nodes.filter { it.editable }
        if (inputs.size > 1 || inputs.any {
                !MorningReadPolicy.isSearchInput(it.id,it.description,it.hint)
            }) return false
        // Reuse the *existing* search and protected-form decision tree. A
        // genuine order form, ambiguous launcher or unrelated input stays BLOCK.
        val decision=MorningReadPolicy.detailDecision(nodes,previous,true)
        return if(inputs.size == 1)
            decision.kind in setOf(MorningReadPolicy.Kind.FOCUS, MorningReadPolicy.Kind.QUERY,
                MorningReadPolicy.Kind.SUBMIT, MorningReadPolicy.Kind.RESULT, MorningReadPolicy.Kind.WAIT) &&
                decision.code !in setOf("SEARCH_AMBIGUOUS", "SEARCH_NOT_ACTIONABLE")
        else decision.kind == MorningReadPolicy.Kind.SEARCH
    }

    fun poll(nodes: List<MorningReadPolicy.Node>, currentWindow: Int, now: Long): State {
        val previous=target ?: return State.IDLE
        if (now < started || now-started >= 5000) {
            return fail(Failure.TIMEOUT)
        }
        // Real order forms, sensitive inputs, and credentials are never
        // mistaken for a transient WebView or a search return.
        val dangerous=Regex("(?iu)order bestätigen|confirm order|limitpreis|orderart|ordertyp|stückzahl|anzahl kaufen|passwort|password|anmelden|login|verification code")
        if (nodes.any { n -> n.password || n.sensitive ||
                listOf(n.text,n.description,n.hint).any { dangerous.containsMatchIn(it) } }) {
            return fail(Failure.PROTECTED)
        }
        if (searchReady(nodes,previous)) {
            clear(); return State.READY
        }
        // An unrecognized input, a different visible product or an unexpected
        // window switch is never interpreted as the next product's search.
        if (currentWindow != window) return fail(Failure.WINDOW)
        val inputs=nodes.filter { it.editable }
        if (inputs.isNotEmpty()) {
            // A rebuilding Markets WebView may expose its known search field
            // before its header. WAIT performs no action and retains the original
            // deadline; it never authorizes another ISIN or an extra BACK.
            val partialSearch=inputs.size==1 && inputs.single().enabled &&
                MorningReadPolicy.isSearchInput(inputs.single().id,
                    inputs.single().description,inputs.single().hint) &&
                nodes.none { it.password || it.sensitive ||
                    it.text.trim().lowercase() in setOf("kursdaten","produktdetails",
                        "orderdetails","orderübersicht","orderzusammenfassung") } &&
                MorningReadPolicy.detailDecision(nodes,previous,true).kind != MorningReadPolicy.Kind.BLOCK
            if(partialSearch) return State.WAITING
            return fail(Failure.INPUT)
        }
        val visible=Regex("\\b[A-Z]{2}[A-Z0-9]{9}[0-9]\\b")
            .findAll(nodes.joinToString("\n") { it.text.uppercase() }).map { it.value }.toSet()
        if (visible.isNotEmpty() && visible!=setOf(previous)) {
            return fail(Failure.IDENTITY)
        }
        // Await a verified search; do not silently fall through to the next
        // product when the old detail or a partially rebuilt overview persists.
        return State.WAITING
    }

    /** One optional extra system BACK after a confirmed initial BACK when
     * the exact SAME previous product is still visible. This never authorizes
     * searching, tapping or continuing to the next product.
     * Unknown screens, order forms, or identity changes remain fail-closed. */
    fun safeBackRetry(nodes: List<MorningReadPolicy.Node>, currentWindow: Int, now: Long): Boolean {
        val previous=target ?: return false
        if (backRetried || now-started !in 1200..3000 || window != currentWindow) return false
        val visible=Regex("\\b[A-Z]{2}[A-Z0-9]{9}[0-9]\\b")
            .findAll(nodes.joinToString("\n") { it.text.uppercase() }).map { it.value }.toSet()
        if (visible != setOf(previous) ||
            !MorningReadPolicy.returnAfterRead(nodes,previous,currentWindow,window,"READ")) return false
        // Mark the retry before any gesture; never send two for the same back.
        backRetried=true
        started=now
        return true
    }

    fun clear() { target=null;window=null;started=0L;backRetried=false }
}
