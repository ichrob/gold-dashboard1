package ch.bob.degirocompanion

/** Pure navigation policy: a list read can only search and open an exact ISIN. */
internal object MorningReadPolicy {
    data class Node(val text: String, val id: String = "", val clickable: Boolean = false,
                    val editable: Boolean = false, val sensitive: Boolean = false,
                    val row: String = text, val containsInput: Boolean = false,
                    val description: String = "", val hint: String = "")
    enum class Kind { WAIT, SEARCH, QUERY, RESULT, READ, BACK, BLOCK }
    data class Action(val kind: Kind, val index: Int = -1, val code: String = "")
    private val ids = Regex("\\b[A-Z]{2}[A-Z0-9]{9}[0-9]\\b")
    private val unsafe = Regex("(?iu)passwort|password|anmelden|einloggen|login|bestätigungscode|verification code|order platzieren|order bestätigen|place order|confirm order|orderart|ordertyp|limitpreis|stückzahl|anzahl kaufen")
    private fun searchLabel(value: String) = Regex("(?iu)^(suche|suchen|search|produkt suchen|produkte suchen|search products|search instruments|instrument suchen|instrumente suchen|suchen nach)(?:[.…: ]*)$").matches(value.trim())
    private fun search(n: Node) = searchLabel(n.text) || searchLabel(n.description) || searchLabel(n.hint) ||
        Regex("(?iu)(^|[/_:])(search|search_input|search_src_text|search_field|search_button|search_view)([/:_]|$)").containsMatchIn(n.id)
    fun isSearchInput(id: String, description: String, hint: String): Boolean =
        search(Node("", id=id, description=description, hint=hint))
    fun decide(nodes: List<Node>, target: String): Action {
        if (!SeriesEvidence.validIsin(target) || nodes.size > 500) return Action(Kind.BLOCK, code="INVALID_VIEW")
        if (nodes.any { it.sensitive || listOf(it.text,it.description,it.hint).any(unsafe::containsMatchIn) || (it.editable && !search(it)) })
            return Action(Kind.BLOCK, code="PROTECTED_VIEW")
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
