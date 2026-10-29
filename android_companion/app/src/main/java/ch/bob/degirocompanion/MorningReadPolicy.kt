package ch.bob.degirocompanion

/** Pure navigation policy: a list read can only search and open an exact ISIN. */
internal object MorningReadPolicy {
    data class Node(val text: String, val id: String = "", val clickable: Boolean = false,
                    val editable: Boolean = false, val sensitive: Boolean = false,
                    val row: String = text, val containsInput: Boolean = false,
                    val description: String = "", val hint: String = "",
                    val password: Boolean = false)
    enum class Kind { WAIT, SEARCH, QUERY, RESULT, READ, BACK, BLOCK }
    data class Action(val kind: Kind, val index: Int = -1, val code: String = "")
    private val ids = Regex("\\b[A-Z]{2}[A-Z0-9]{9}[0-9]\\b")
    private val login = Regex("(?iu)passwort|password|anmelden|einloggen|login|bestätigungscode|verification code")
    private val orderMarkers = listOf(
        "PROTECTED_ORDER_CONFIRM" to Regex("(?iu)order platzieren|order bestätigen|place order|confirm order"),
        "PROTECTED_ORDER_TYPE" to Regex("(?iu)orderart|ordertyp"),
        "PROTECTED_ORDER_PRICE" to Regex("(?iu)limitpreis"),
        "PROTECTED_ORDER_QUANTITY" to Regex("(?iu)stückzahl|anzahl kaufen"))
    private fun searchLabel(value: String) = Regex("(?iu)^(suche|suchen|search|produkt suchen|produkte suchen|search products|search instruments|instrument suchen|instrumente suchen|suchen nach|name, isin oder symbol|name, isin or symbol|mit namen, isin oder symbol suchen)(?:[.…: ]*)$").matches(value.trim())
    private fun search(n: Node) = searchLabel(n.text) || searchLabel(n.description) || searchLabel(n.hint) ||
        Regex("(?iu)(^|[/_:])(search|search_input|search_src_text|search_field|search_button|search_view)([/:_]|$)").containsMatchIn(n.id)
    fun isSearchInput(id: String, description: String, hint: String): Boolean =
        search(Node("", id=id, description=description, hint=hint))
    // Android may expose a placeholder as text, without hintText or a view ID.
    // Only an exact, explicitly marked search placeholder may identify an input.
    fun inputHint(hint: String, text: String, showingHint: Boolean): String =
        hint.ifBlank { if (showingHint && searchLabel(text)) text else "" }
    private fun protection(nodes: List<Node>): String? {
        if (nodes.any { it.password }) return "PROTECTED_PASSWORD"
        if (nodes.any { it.sensitive && it.editable }) return "PROTECTED_SENSITIVE_INPUT"
        if (nodes.any { it.sensitive }) return "PROTECTED_SENSITIVE_CONTENT"
        if (nodes.any { n -> listOf(n.text,n.description,n.hint).any(login::containsMatchIn) }) return "PROTECTED_LOGIN"
        // Export only a fixed cause code, never the matching screen text.
        for ((code, marker) in orderMarkers)
            if (nodes.any { n -> listOf(n.text,n.description,n.hint).any(marker::containsMatchIn) }) return code
        if (nodes.any { it.editable && !search(it) }) return "UNRECOGNIZED_INPUT"
        return null
    }
    /** A market navigation launcher is not an open order form. This exception
     * permits only opening an isolated, explicit product search on Markets;
     * never entering text, opening results, reading, or activating the launcher. */
    private fun marketSearchBesideLauncher(nodes: List<Node>): Int? {
        if (nodes.any { it.editable || it.containsInput || it.sensitive || it.password }) return null
        fun values(n: Node) = listOf(n.text,n.description,n.hint)
        fun exact(value: String, label: String) = value.trim().equals(label,ignoreCase=true)
        if (!nodes.any { exact(it.text,"Märkte") } || !nodes.any { exact(it.text,"Indizes") }) return null
        if (orderMarkers.drop(1).any { (_,marker) -> nodes.any { n -> values(n).any(marker::containsMatchIn) } }) return null
        val launchLabel=Regex("(?iu)^(order platzieren|place order)$")
        val marked=nodes.filter { n -> values(n).any(orderMarkers.first().second::containsMatchIn) }
        if (marked.size != 1) return null
        val launcher=marked.single()
        if (!launcher.clickable || values(launcher).filter(String::isNotBlank).any { !launchLabel.matches(it.trim()) } ||
            launcher.row.lines().filter(String::isNotBlank).any { !launchLabel.matches(it.trim()) }) return null
        val productLabel="Mit Namen, ISIN oder Symbol suchen"
        val searches=nodes.indices.filter { index ->
            val n=nodes[index]
            n.clickable && values(n).any { exact(it,productLabel) } &&
                values(n).filter(String::isNotBlank).all { exact(it,productLabel) } &&
                n.row.lines().filter(String::isNotBlank).all { exact(it,productLabel) }
        }
        return searches.singleOrNull()
    }
    fun decide(nodes: List<Node>, target: String, lookupSymbol: (String) -> String? = { null }): Action {
        if (!SeriesEvidence.validIsin(target) || nodes.size > 500) return Action(Kind.BLOCK, code="INVALID_VIEW")
        protection(nodes)?.let { cause ->
            if (cause == "PROTECTED_ORDER_CONFIRM") {
                marketSearchBesideLauncher(nodes)?.let { return Action(Kind.SEARCH,it) }
            }
            return Action(Kind.BLOCK, code=cause)
        }
        val inputs = nodes.indices.filter { nodes[it].editable && search(nodes[it]) }
        if (inputs.size > 1) return Action(Kind.WAIT, code="SEARCH_AMBIGUOUS")
        if (inputs.size == 1) {
            val i = inputs.single()
            if (nodes[i].text != target) return Action(Kind.QUERY, i)
            val candidates = nodes.indices.filter { j ->
                val n = nodes[j]
                n.clickable && !n.editable && !n.containsInput && ids.findAll(n.row.uppercase()).map { it.value }.toSet() == setOf(target) &&
                    !Regex("(?iu)\\b(kauf|verkauf|buy|sell|order)\\b").containsMatchIn(n.row)
            }
            val smallest = candidates.minByOrNull { nodes[it].row.length }
            return if (smallest == null) Action(Kind.WAIT, code="RESULT_MISSING") else Action(Kind.RESULT, smallest)
        }
        val visibleIds = nodes.filterNot { it.editable }.flatMap { ids.findAll(it.text.uppercase()).map { m -> m.value }.toList() }.toSet()
        val detail = nodes.any { Regex("(?iu)^(übersicht|overview|kursdaten|produktdetails)$").matches(it.text.trim()) }
        if (visibleIds == setOf(target) && detail) return Action(Kind.READ)
        // A known symbol may open the bounded page reader, but cannot publish
        // quotes. That reader still requires a real visible ISIN before export.
        // Use individual non-input labels, never aggregate rows or search results.
        if (detail && visibleIds.isEmpty() && ProductSymbolMemory.resolveTexts(
                nodes.filterNot { it.editable || it.containsInput }.map { it.text }, lookupSymbol) == target)
            return Action(Kind.READ)
        // Some accessibility trees put the search label on a child of the clickable icon.
        // Accept only a single exact search label; never an aggregate page/list row.
        val buttons = nodes.indices.filter {
            val n=nodes[it]
            n.clickable && !n.containsInput && (search(n) || (n.text.isBlank() && n.row.lines().filter(String::isNotBlank).size==1 && search(n.copy(text=n.row.trim(),id=""))))
        }
        if (buttons.size == 1) return Action(Kind.SEARCH, buttons.single())
        if (buttons.size > 1) return Action(Kind.WAIT, code="SEARCH_AMBIGUOUS")
        return if (detail) Action(Kind.BACK) else Action(Kind.WAIT, code="SEARCH_MISSING")
    }
}
