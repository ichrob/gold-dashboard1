package ch.bob.degirocompanion

/** Strictly a decision to SEND existing, already cropped list evidence for
 * independent server verification, never a claim that ten products were read.
 * No extra screen capture, scrolling on an order form, or broker action.
 */
internal object MorningListEndPolicy {
    private val footer = Regex(
        "(?iu)(?:flatexDEGIRO\\s+Bank\\s+Dutch\\s+Branch|Datenquellen\\s+und\\s+-anbieter)"
    )

    fun hasVerifiedFooter(nodes: List<MorningReadPolicy.Node>): Boolean =
        nodes.any { n -> !n.editable && !n.password && !n.sensitive &&
            footer.containsMatchIn(n.text) }

    fun maySubmitAtEnd(nodes: List<MorningReadPolicy.Node>,
                       capturedImages: Int, seen: Set<String>,
                       current: List<String>, action: MorningReadPolicy.Action): Boolean =
        capturedImages in 2..4 && seen.size in 5..9 &&
        seen.all(SeriesEvidence::validIsin) &&
        current.isNotEmpty() && current.size <= 10 &&
        current.distinct() == current &&
        current.all { SeriesEvidence.validIsin(it) && it in seen } &&
        action.kind == MorningReadPolicy.Kind.COLLECT && action.isins == current &&
        hasVerifiedFooter(nodes) &&
        !nodes.any { it.password || it.sensitive || it.editable }

    /** App text is capture coverage only when it passes the same complete-row
     * contract (heading, single identity, issuer/venue/currency footer) as the
     * local OCR parser. Matching identities alone must not suppress an edge image. */
    fun completeAppRowCoverage(first: List<String>, second: List<String>,
                               visible: List<String>): Set<String> {
        if (visible.isEmpty() || visible.size>10 || visible.distinct()!=visible ||
            visible.any { !SeriesEvidence.validIsin(it) } || first!=second ||
            first.size!=visible.size) return emptySet()
        val rows=MorningLocalOcr.productRows(first.joinToString("\n"),visible)
            ?: return emptySet()
        return visible.toSet().takeIf { rows.size==visible.size } ?: emptySet()
    }

    /** Ten visible ISIN labels do not prove ten complete product rows.
     * Permit at most one additional cropped, read-only edge capture when
     * independent on-device row text has not confirmed all ten labels.
     * This never marks a server import successful or loosens its parser. */
    fun needsEdgeCapture(capturedImages: Int, seen: Set<String>,
                         covered: Set<String>): Boolean =
        capturedImages in 1..3 && seen.size==10 &&
        seen.all(SeriesEvidence::validIsin) &&
        covered.all { it in seen } && covered.size<10

    /** On a verified read-only footer, one final cropped photo may clarify
     * rows missing from the virtualized WebView text. Android may locally see
     * only 5..8 identities even when independent server OCR extracts nine.
     * At most four original photos; the server must still validate all ten
     * distinct complete product rows before approving the list. */
    private val footerProtection = Regex(
        "(?iu)order platzieren|order bestätigen|place order|confirm order|" +
            "orderart|ordertyp|limitpreis|stückzahl|anzahl kaufen|passwort|password|login|anmelden"
    )
    /** The global Markets Order launcher is sometimes still exposed beside
     * the read-only Gold footer. Ignore it only for deciding whether to
     * capture one additional CROPPED picture; NEVER return a click target.
     * A true order form, nested launcher or second marker remains rejected. */
    /** Android may expose one standalone Markets launcher twice: once as
     * a passive text-only ancestor and once as the actual clickable leaf.
     * This remains a permission to take ONE cropped list PHOTO, not to click
     * any launcher or to accept an incomplete list. Genuine multiple order
     * controls, forms or product-card nesting still fail closed. */
    private fun safeFooterProtection(nodes: List<MorningReadPolicy.Node>): Boolean {
        val marked=nodes.indices.filter { i ->
            val n=nodes[i]
            listOf(n.text,n.description,n.hint,n.row)
                .any(footerProtection::containsMatchIn)
        }
        if(marked.isEmpty()) return true
        val exact=Regex("(?iu)^(order platzieren|place order)$")
        // Every marked node must be a strict, exact copy of the global label.
        // An extra order field or aggregate text rejects the entire screen.
        if(marked.any { i ->
            val n=nodes[i]
            !n.enabled || n.editable || n.containsInput || n.password ||
            n.sensitive || listOf(n.text,n.description,n.hint,n.row)
                .filter(String::isNotBlank).let { labels ->
                    labels.isEmpty() || labels.any { !exact.matches(it.trim()) }
                }
        }) return false
        val clickable=marked.filter { i -> nodes[i].clickable || nodes[i].clickAction }
        val leaf=clickable.singleOrNull() ?: return false
        fun below(child:Int,parent:Int):Boolean {
            var at=nodes[child].parent
            var steps=0
            while(at in nodes.indices && steps++<nodes.size) {
                if(at==parent) return true
                at=nodes[at].parent
            }
            return false
        }
        // A leaf launcher cannot own any nested UI, and passive wrappers
        // must form the *single* parent chain of that leaf, not siblings or
        // separate buttons. A wrapper containing a card is never isolated.
        if(nodes.indices.any { it!=leaf && below(it,leaf) }) return false
        if(marked.any { it!=leaf && !below(leaf,it) }) return false
        if(marked.any { wrapper -> wrapper!=leaf &&
            nodes.indices.any { i -> i!=leaf && !below(leaf,i) && below(i,wrapper) }
        }) return false
        val ids=Regex("\\b[A-Z]{2}[A-Z0-9]{9}[0-9]\\b")
        var at=nodes[leaf].parent
        var steps=0
        while(at in nodes.indices && steps++<nodes.size) {
            val parent=nodes[at]
            if(ids.containsMatchIn(parent.text.uppercase()) ||
               ids.containsMatchIn(parent.row.uppercase())) return false
            at=parent.parent
        }
        return true
    }

    fun needsFooterRecapture(nodes: List<MorningReadPolicy.Node>,
                             capturedImages: Int, seen: Set<String>,
                             current: List<String>, action: MorningReadPolicy.Action): Boolean =
        capturedImages == 3 && seen.size in 5..9 &&
        seen.all(SeriesEvidence::validIsin) &&
        // Samsung's local accessibility tree can see fewer rows than
        // server-side OCR (for example, 6 local vs 9 server-confirmed).
        // The footer photo is bounded to this known, safe read-only context.
        current.isNotEmpty() && current.size<=10 &&
        current.distinct()==current &&
        current.all { SeriesEvidence.validIsin(it) && it in seen } &&
        action.kind == MorningReadPolicy.Kind.COLLECT && action.isins == current &&
        hasVerifiedFooter(nodes) &&
        // The original Gold search EditText may remain in the virtualized
        // footer tree after the keyboard was dismissed. For a FOURTH cropped
        // photo only, tolerate this single proven Gold input (and ancestors).
        // Order forms, account content and any other input remain forbidden.
        fourthPhotoSurfaceGate(nodes) == FourthPhotoGate.ALLOWED &&
        safeFooterProtection(nodes)

    /** A fourth CROPPED Gold-list photograph is evidence collection only.
     * The server still independently requires all ten complete product rows.
     * Report the exact anonymous reason a known ten-label case could not
     * obtain its fourth original photo instead of a generic guard failure. */
    enum class FourthPhotoGate {
        ALLOWED, CAPTURE_LIMIT, NO_MISSING_ROW_EVIDENCE, INVALID_VISIBLE_IDS,
        ACTION_NOT_COLLECT, FOOTER_UNVERIFIED, ORDER_OR_PRIVATE_SURFACE,
        UNKNOWN_INPUT
    }

    private val actualOrderForm = Regex(
        "(?iu)order bestätigen|confirm order|orderart|ordertyp|limitpreis|" +
            "stückzahl|anzahl kaufen|orderdetails|orderübersicht|" +
            "orderzusammenfassung|passwort|password|login|anmelden|" +
            "kontostand|portfolio|depotwert"
    )

    /** DEGIRO has a persistent bottom navigation tab labelled exactly
     * "Portfolio" even on the Gold search/results page. navigationTree()
     * copies that same leaf label into ancestor `row` strings separated
     * by newlines. A substring scan therefore falsely classifies every
     * normal Gold footer as private account content. Exempt ONLY that exact,
     * stand-alone navigation label while scanning node text/description/
     * hint/aggregated rows. "Mein Portfolio", balances and any other
     * account, order, secret or form marker still block the screenshot.
     * This never grants a click, order or access to a portfolio page. */
    private fun containsRealPrivateOrOrderMarker(value:String):Boolean =
        value.lines().any { line ->
            val label=line.trim()
            label.isNotEmpty() &&
                !label.equals("Portfolio",ignoreCase=true) &&
                actualOrderForm.containsMatchIn(label)
        }

    /** Android sometimes keeps the ORIGINAL Gold search EditText in a
     * WebView ancestry beside the read-only verified footer. That field is
     * neither an order field nor a reason to suppress a PHOTO. Only this one
     * labelled, non-secret, Gold-valued input and its containsInput ancestors
     * are tolerated. Nothing here returns an input/click target. */
    private fun fourthPhotoSurfaceGate(nodes: List<MorningReadPolicy.Node>): FourthPhotoGate {
        if(nodes.any { n ->
                n.password || n.sensitive ||
                    listOf(n.text,n.description,n.hint,n.row).any(::containsRealPrivateOrOrderMarker)
            }) return FourthPhotoGate.ORDER_OR_PRIVATE_SURFACE
        val inputs=nodes.indices.filter { nodes[it].editable }
        if(inputs.size>1)return FourthPhotoGate.UNKNOWN_INPUT
        val search=inputs.singleOrNull()
        if(search!=null) {
            val n=nodes[search]
            val metadata=(n.id+" "+n.hint+" "+n.description).lowercase()
            val namedSearch=Regex("(?i)(^|[^a-z])search([^a-z]|$)|mit namen, isin oder symbol suchen")
                .containsMatchIn(metadata)
            if(!n.enabled || !namedSearch || n.text.trim() !in setOf("Gold",""))
                return FourthPhotoGate.UNKNOWN_INPUT
        }
        fun descends(child:Int,parent:Int):Boolean {
            var at=nodes[child].parent
            var hops=0
            while(at in nodes.indices && hops++ < nodes.size) {
                if(at==parent)return true
                at=nodes[at].parent
            }
            return false
        }
        // Any other input surface remains forbidden, including a virtualized
        // unlabelled input with no real Search EditText.
        if(nodes.indices.any { i ->
                nodes[i].containsInput && i!=search &&
                    (search==null || !descends(search,i))
            })return FourthPhotoGate.UNKNOWN_INPUT
        return FourthPhotoGate.ALLOWED
    }

    fun uncoveredFooterGate(nodes: List<MorningReadPolicy.Node>,
                            capturedImages: Int, seen: Set<String>,
                            covered: Set<String>, current: List<String>,
                            action: MorningReadPolicy.Action): FourthPhotoGate {
        if(capturedImages!=3)return FourthPhotoGate.CAPTURE_LIMIT
        if(!needsEdgeCapture(capturedImages,seen,covered))
            return FourthPhotoGate.NO_MISSING_ROW_EVIDENCE
        if(current.isEmpty() || current.size>10 || current.distinct()!=current ||
            current.any { !SeriesEvidence.validIsin(it) || it !in seen })
            return FourthPhotoGate.INVALID_VISIBLE_IDS
        if(action.kind!=MorningReadPolicy.Kind.COLLECT || action.isins!=current)
            return FourthPhotoGate.ACTION_NOT_COLLECT
        if(!hasVerifiedFooter(nodes))return FourthPhotoGate.FOOTER_UNVERIFIED
        return fourthPhotoSurfaceGate(nodes)
    }

    fun needsUncoveredFooterCapture(nodes: List<MorningReadPolicy.Node>,
                                    capturedImages: Int, seen: Set<String>,
                                    covered: Set<String>, current: List<String>,
                                    action: MorningReadPolicy.Action): Boolean =
        uncoveredFooterGate(nodes,capturedImages,seen,covered,current,action)==FourthPhotoGate.ALLOWED

    fun maySubmitAtCaptureLimit(capturedImages: Int, seen: Set<String>): Boolean =
        capturedImages == 4 && seen.size in 5..9 && seen.all(SeriesEvidence::validIsin)
}
