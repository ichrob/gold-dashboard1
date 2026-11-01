package ch.bob.degirocompanion

/** After an acknowledged BACK, do not process the next ISIN until a genuine
 * read-only DEGIRO Markets search is independently recognized. No order action
 * is ever authorized by this transition. */
internal class ProductReturnTransition {
    enum class State { IDLE, WAITING, READY, FAILED }
    private var target: String? = null
    private var window: Int? = null
    private var started = 0L

    fun begin(previousTarget: String, previousWindow: Int, now: Long) {
        target=previousTarget;window=previousWindow;started=now
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
            clear(); return State.FAILED
        }
        // Real order forms, sensitive inputs, and credentials are never
        // mistaken for a transient WebView or a search return.
        val dangerous=Regex("(?iu)order bestätigen|confirm order|limitpreis|orderart|ordertyp|stückzahl|anzahl kaufen|passwort|password|anmelden|login|verification code")
        if (nodes.any { n -> n.password || n.sensitive ||
                listOf(n.text,n.description,n.hint).any { dangerous.containsMatchIn(it) } }) {
            clear(); return State.FAILED
        }
        if (searchReady(nodes,previous)) {
            clear(); return State.READY
        }
        // An unrecognized input, a different visible product or an unexpected
        // window switch is never interpreted as the next product's search.
        if (currentWindow != window || nodes.any { it.editable }) {
            clear(); return State.FAILED
        }
        val visible=Regex("\\b[A-Z]{2}[A-Z0-9]{9}[0-9]\\b")
            .findAll(nodes.joinToString("\n") { it.text.uppercase() }).map { it.value }.toSet()
        if (visible.isNotEmpty() && visible!=setOf(previous)) {
            clear(); return State.FAILED
        }
        // Await a verified search; do not silently fall through to the next
        // product when the old detail or a partially rebuilt overview persists.
        return State.WAITING
    }

    fun clear() { target=null;window=null;started=0L }
}
