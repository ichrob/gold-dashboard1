package ch.bob.degirocompanion

/** Acknowledged BACK can leave the old accessibility tree visible briefly.
 * Never read/export it under the next target, or bypass a protected view. */
internal class ProductReturnTransition {
    private var target: String? = null
    private var window: Int? = null
    private var started = 0L
    fun begin(previousTarget: String, previousWindow: Int, now: Long) {
        target=previousTarget;window=previousWindow;started=now
    }
    fun waiting(nodes: List<MorningReadPolicy.Node>, currentWindow: Int, now: Long): Boolean {
        val previous=target ?: return false
        if (now < started || now-started >= 5000 || currentWindow != window) {
            clear(); return false
        }
        // Never conceal an order confirmation, sensitive input or a different
        // product during a transition. Only the isolated "Order platzieren"
        // launcher is a neutral label; no action is performed while waiting.
        val dangerous=Regex("(?iu)order bestätigen|confirm order|limitpreis|orderart|ordertyp|stückzahl|anzahl kaufen|passwort|password|anmelden|login|verification code")
        if(nodes.any { n -> n.password || n.sensitive || n.editable ||
                listOf(n.text,n.description,n.hint).any { dangerous.containsMatchIn(it) } }) {
            clear(); return false
        }
        val visible=Regex("\\b[A-Z]{2}[A-Z0-9]{9}[0-9]\\b")
            .findAll(nodes.joinToString("\n") { it.text.uppercase() }).map { it.value }.toSet()
        if(visible.isNotEmpty() && visible!=setOf(previous)) {
            clear();return false
        }
        if (MorningReadPolicy.returnAfterRead(nodes,previous,currentWindow,window,"READ")) return true
        // A WebView can briefly expose a partially rebuilt old overview after
        // the guarded BACK succeeded. Wait passively for 1.4s, rather than
        // processing its standalone launcher under the *next* product target.
        val oldOverview=nodes.any { it.text.trim().equals("Übersicht",true) ||
            it.text.trim().equals("Overview",true) }
        if (now-started<1400 && oldOverview) return true
        clear();return false
    }
    fun clear() { target=null;window=null;started=0L }
}
