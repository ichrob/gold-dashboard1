package ch.bob.degirocompanion

/** Fixed Gold discovery query or exact-ISIN reading; never order navigation. */
internal object MorningReadPolicy {
    data class Node(val text: String, val id: String = "", val clickable: Boolean = false,
                    val editable: Boolean = false, val sensitive: Boolean = false,
                    val row: String = text, val containsInput: Boolean = false,
                    val description: String = "", val hint: String = "",
                    val password: Boolean = false, val clickAction: Boolean = false,
                    val enabled: Boolean = true, val parent: Int = -1, val imeEnter: Boolean = false,
                    val writtenQueryExpected: Boolean = false, val writtenQueryPresent: Boolean = false,
                    val writtenNodeIdentity: Boolean = false, val focused: Boolean = true, val focusAction: Boolean = false,
                    val selected: Boolean = false, val scrollRight: Boolean = false, val captureComplete: Boolean = true)
    enum class Kind { WAIT, SEARCH, FOCUS, QUERY, SUBMIT, CATEGORY, CATEGORY_SCROLL, RESULT, READ, BACK, BLOCK, COLLECT }
    data class Action(val kind: Kind, val index: Int = -1, val code: String = "", val isins: List<String> = emptyList())
    private val ids = Regex("\\b[A-Z]{2}[A-Z0-9]{9}[0-9]\\b")
    private val login = Regex("(?iu)passwort|password|anmelden|einloggen|login|bestätigungscode|verification code")
    private val orderMarkers = listOf(
        "PROTECTED_ORDER_CONFIRM" to Regex("(?iu)order platzieren|order bestätigen|place order|confirm order"),
        "PROTECTED_ORDER_TYPE" to Regex("(?iu)orderart|ordertyp"),
        "PROTECTED_ORDER_PRICE" to Regex("(?iu)limitpreis"),
        "PROTECTED_ORDER_QUANTITY" to Regex("(?iu)stückzahl|anzahl kaufen"))
    private fun normalized(value: String) = value.replace(Regex("[\\s\\p{Zs}]+"), " ").trim()
    private fun searchLabel(value: String) = Regex("(?iu)^(suche|suchen|search|produkt suchen|produkte suchen|search products|search instruments|instrument suchen|instrumente suchen|suchen nach|name, isin oder symbol|name, isin or symbol|mit namen, isin oder symbol suchen)(?:[.…: ]*)$").matches(normalized(value))
    private fun canClick(n: Node) = n.enabled && (n.clickable || n.clickAction)
    private fun rowSearch(n: Node) = searchLabel(n.row.lines().map { it.trim() }.filter(String::isNotBlank).distinct().joinToString(" "))
    // Nested clickable wrappers for the same search are one target. Distinct
    // sibling targets remain ambiguous; never choose by coordinates or list order.
    private fun innermost(nodes: List<Node>, candidates: List<Int>): List<Int> = candidates.filter { ancestor ->
        candidates.none { child ->
            var cursor=nodes[child].parent
            var steps=0
            var found=false
            while(cursor in nodes.indices && steps++ < nodes.size) {
                if(cursor==ancestor) { found=true;break }
                cursor=nodes[cursor].parent
            }
            child!=ancestor && found
        }
    }
    private fun search(n: Node) = searchLabel(n.text) || searchLabel(n.description) || searchLabel(n.hint) ||
        searchResource(n.id)
    // Android resource names and WebView IDs use different separators and casing.
    // Inspect the resource name, never a package name or arbitrary substring.
    private fun searchResource(id:String):Boolean {
        val name=id.substringAfterLast('/').substringAfterLast(':')
        val words=name.replace(Regex("([a-z0-9])([A-Z])"),"$1_$2")
            .lowercase().split(Regex("[^a-z0-9]+"))
        return "search" in words || words.any {
            Regex("^(product|instrument)?search(input|field|text|query|view|box|bar)$").matches(it)
        }
    }
    // Retry enclosing wrappers, then one independently labelled Markets search.
    // Aggregate pages, order launchers and coordinates are never fallbacks.
    fun searchClickChain(nodes: List<Node>, action: Action): List<Int> {
        if (action.kind != Kind.SEARCH || action.index !in nodes.indices) return emptyList()
        val result = mutableListOf(action.index)
        val seen = mutableSetOf(action.index)
        var parent = nodes[action.index].parent
        while (parent in nodes.indices && seen.add(parent) && result.size < 3) {
            val n = nodes[parent]
            if (n.sensitive || n.password || n.editable || n.containsInput || !rowSearch(n)) break
            if (listOf(n.text,n.description,n.hint).filter(String::isNotBlank).any { !searchLabel(it) }) break
            if (canClick(n)) result += parent
            parent = n.parent
        }
        marketToolbarSearch(nodes, action)?.let { if(it !in result) result += it }
        return result
    }
    private fun marketToolbarSearch(nodes: List<Node>, action: Action): Int? {
        if(nodes.any { it.editable || it.containsInput || it.password || it.sensitive }) return null
        if(!nodes.any { it.text.trim()=="Märkte" } || !nodes.any { it.text.trim()=="Indizes" }) return null
        val selected=nodes[action.index]
        val label="Mit Namen, ISIN oder Symbol suchen"
        if(listOf(selected.text,selected.description,selected.hint,selected.row).none { normalized(it).equals(label,true) }) return null
        val cause=protection(nodes)
        if(cause!=null && (cause!="PROTECTED_ORDER_CONFIRM" || marketSearchBesideLauncher(nodes)!=action.index)) return null
        val generic=Regex("(?iu)^(suche|suchen|search)$")
        val candidates=nodes.indices.filter { i ->
            val n=nodes[i]
            val values=listOf(n.text,n.description,n.hint).filter(String::isNotBlank)
            i!=action.index && canClick(n) && values.isNotEmpty() && values.all { generic.matches(normalized(it)) } &&
                n.row.lines().filter(String::isNotBlank).all { generic.matches(normalized(it)) }
        }
        return innermost(nodes,candidates).singleOrNull()
    }
    fun isSearchInput(id: String, description: String, hint: String): Boolean =
        search(Node("", id=id, description=description, hint=hint))
    // Android may expose a placeholder as text, without hintText or a view ID.
    // A full product-search prompt is explicit even if a WebView omits the hint flag.
    // Short labels still require the Android placeholder flag.
    fun inputHint(hint: String, text: String, showingHint: Boolean): String =
        hint.ifBlank { if ((showingHint && searchLabel(text)) ||
            normalized(text).equals("Mit Namen, ISIN oder Symbol suchen",ignoreCase=true)) text else "" }
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
    /** Only an isolated global launcher beside an identified read-only product.
     * This grants READ only; it never returns a click/search/submit target. */
    /** The DEGIRO Markets landing page can expose a separate global "Order
     * platzieren" accessibility button next to its RECENT products. The
     * presence of that button does not turn the read-only recent-list page into
     * an order form. Only its isolated, uniquely labelled search BAR may be
     * clicked. The order launcher and K/V buttons are never action targets. */
    private fun recentMarketSearchBesideLauncher(nodes: List<Node>): Int? {
        if(nodes.size>500 || nodes.any { it.editable || it.containsInput || it.password || it.sensitive }) return null
        val values: (Node)->List<String> = { listOf(it.text,it.description,it.hint) }
        if(nodes.any { n -> values(n).any(login::containsMatchIn) ||
            orderMarkers.drop(1).any { (_,marker) -> values(n).any(marker::containsMatchIn) } }) return null
        fun has(label:String)=nodes.any { normalized(it.text).equals(label,true) }
        // Samsung DEGIRO virtualizes the recent-list header as the screen
        // scrolls. ZULETZT / Alle löschen can disappear from accessibility
        // even while the exact Markets search bar remains visible.
        // Require Markets AND at least one independently labelled Markets
        // landing section, alongside the unique isolated search and launcher
        // checks below. Missing recent items never authorizes an order click.
        if(!has("Märkte") || !(has("Nach Produkttyp durchsuchen") ||
            (has("Zuletzt") && has("Alle löschen")))) return null
        // A genuine product detail or order form is never a Markets landing.
        if(nodes.any { n -> normalized(n.text).lowercase() in setOf(
                "kursdaten","produktdetails","order bestätigen","orderdetails",
                "orderübersicht","orderzusammenfassung","orderart","limitpreis","stückzahl") }) return null
        val marked=nodes.indices.filter { i ->
            values(nodes[i]).any(orderMarkers.first().second::containsMatchIn)
        }
        val launcherIndex=marked.singleOrNull() ?: return null
        val launcher=nodes[launcherIndex]
        val exactOrder=Regex("(?iu)^order platzieren$")
        if(!canClick(launcher) || values(launcher).filter(String::isNotBlank).any {
                !exactOrder.matches(normalized(it)) } ||
            launcher.row.lines().filter(String::isNotBlank).any { !exactOrder.matches(normalized(it)) })
            return null
        fun descends(child:Int,parent:Int):Boolean {
            var cursor=nodes[child].parent;var count=0
            while(cursor in nodes.indices && count++<nodes.size) {
                if(cursor==parent)return true
                cursor=nodes[cursor].parent
            }
            return false
        }
        if(nodes.indices.any { it!=launcherIndex && descends(it,launcherIndex) }) return null
        // A button nested under a product row is not a global launcher.
        // Never let it authorize touching the Markets search bar.
        var cursor=launcher.parent
        var depth=0
        while(cursor in nodes.indices && depth++<nodes.size) {
            val ancestor=nodes[cursor]
            if(ids.containsMatchIn(ancestor.text.uppercase()) ||
                (Regex("(?iu)\\b(gold|xau)\\b").containsMatchIn(ancestor.text) &&
                 Regex("(?iu)\\b(turbo|mini[ -]?future|knock[ -]?out)\\b").containsMatchIn(ancestor.text)))
                return null
            cursor=ancestor.parent
        }
        val prompt="Mit Namen, ISIN oder Symbol suchen"
        val search=innermost(nodes,nodes.indices.filter { i ->
            val n=nodes[i]
            i!=launcherIndex && canClick(n) && !n.editable && !n.containsInput &&
                !n.password && !n.sensitive && !descends(i,launcherIndex) &&
                !descends(launcherIndex,i) &&
                values(n).filter(String::isNotBlank).let { it.isNotEmpty() &&
                    it.all { value -> normalized(value).equals(prompt,true) } } &&
                n.row.lines().filter(String::isNotBlank).all { normalized(it).equals(prompt,true) }
        }).singleOrNull()
        return search
    }

    /** Exact informational footer groups; never sufficient to start a read. */
    fun detailFooter(texts: List<String>): Boolean {
        val labels=texts.map { normalized(it).lowercase() }.toSet()
        return labels.containsAll(setOf("notizen", "notiz hinzufügen")) ||
            labels.containsAll(setOf("kontaktdaten", "website", "e-mail", "telefon"))
    }
    enum class DetailIssue { INPUT_OR_TARGET, MARKER_COUNT, LAUNCHER_LABEL, LAUNCHER_CHILD,
        PROTECTED_CONTENT, ORDER_FIELD, SECTION_MISSING, IDENTITY_CONTEXT }
    fun detailLauncherIndex(nodes: List<Node>, target: String, anchored: Boolean = false, symbolProbe: Boolean = false, rejected: (DetailIssue) -> Unit = {}): Int? {
        fun reject(issue: DetailIssue): Int? { rejected(issue); return null }
        if(nodes.size>500 || !SeriesEvidence.validIsin(target) ||
            nodes.any { it.editable || it.containsInput || it.password || it.sensitive }) return reject(DetailIssue.INPUT_OR_TARGET)
        val values: (Node) -> List<String> = { listOf(it.text,it.description,it.hint) }
        val marked=nodes.indices.filter { i -> values(nodes[i]).any(orderMarkers.first().second::containsMatchIn) }
        val index=marked.singleOrNull() ?: return reject(DetailIssue.MARKER_COUNT)
        val launcher=nodes[index]
        val exact=Regex("(?iu)^(order platzieren|place order)$")
        if(!canClick(launcher) || values(launcher).filter(String::isNotBlank).any { !exact.matches(normalized(it)) } ||
            launcher.row.lines().filter(String::isNotBlank).any { !exact.matches(normalized(it)) }) return reject(DetailIssue.LAUNCHER_LABEL)
        // No descendant may hide other controls or product content in the launcher.
        for(i in nodes.indices) {
            var cursor=nodes[i].parent;var steps=0
            while(cursor in nodes.indices && steps++<nodes.size) {
                if(cursor==index) return reject(DetailIssue.LAUNCHER_CHILD)
                cursor=nodes[cursor].parent
            }
        }
        val cleaned=nodes.mapIndexed { i,n -> if(i==index) Node("") else n }
        if(protection(cleaned)!=null) return reject(DetailIssue.PROTECTED_CONTENT)
        if(cleaned.any { n -> values(n).any { Regex("(?iu)order type|limit price|quantity").containsMatchIn(it) } }) return reject(DetailIssue.ORDER_FIELD)
        val seen=cleaned.flatMap { n -> values(n).flatMap { ids.findAll(it.uppercase()).map { m -> m.value }.toList() } }.toSet()
        val section=cleaned.any { n -> values(n).any { Regex("(?iu)^(übersicht|overview|kursdaten|produktdetails)$").matches(normalized(it)) } }
        if(!section) return reject(DetailIssue.SECTION_MISSING)
        val productTitle=cleaned.any { n ->
            Regex("(?iu)\\b(gold|xau)\\b").containsMatchIn(n.row) &&
                Regex("(?iu)\\b(turbo|knock[ -]?out|mini[ -]?(future|long|short))\\b").containsMatchIn(n.row) &&
                ids.findAll(n.row.uppercase()).map { it.value }.toSet().let { it.isEmpty() || it==setOf(target) }
        }
        // A missing header is allowed only during an already anchored same-window
        // transaction, with quote labels or an exact informational footer group.
        val quoteSection=cleaned.any { normalized(it.text).equals("Kursdaten",true) }
        fun label(name:String)=cleaned.any { Regex("(?iu)^$name(?:\\s|[:：]|$)").containsMatchIn(normalized(it.text)) }
        val quotes=quoteSection && label("Geld") && label("Brief")
        val footer=detailFooter(cleaned.map { it.text })
        return index.takeIf { (seen==setOf(target) && (productTitle || quotes)) ||
            (symbolProbe && seen.isEmpty() && productTitle && ProductSymbolMemory.detailSymbol(cleaned.map { it.text })!=null) ||
            (anchored && (seen.isEmpty() || seen==setOf(target)) && (quotes || footer)) } ?: reject(DetailIssue.IDENTITY_CONTEXT)
    }
    /** One BACK from a previously observed product window, never from an order form. */
    fun returnAfterRead(nodes: List<Node>, target: String, window: Int, readWindow: Int?, code: String): Boolean {
        if (readWindow != window || code !in setOf("READ", "NO_QUOTES", "RETURN_FAILED", "SEEK_LIMIT", "SCROLL_LIMIT")) return false
        if (detailLauncherIndex(nodes, target, anchored=true, symbolProbe=true) != null) return true
        if (protection(nodes) != null || nodes.size > 500 || !SeriesEvidence.validIsin(target)) return false
        val action = detailDecision(nodes, target, true)
        return action.kind == Kind.READ
    }
    fun detailReadLines(nodes: List<Node>, lines: List<QuoteLayout.Line>, target: String,
                        anchored: Boolean = false, symbolProbe: Boolean = false): List<QuoteLayout.Line> {
        if(detailLauncherIndex(nodes,target,anchored,symbolProbe)==null) return lines
        // A second traversal must not smuggle a compound order label past the
        // strict parser. Remove only the exact isolated launcher label.
        val exact=Regex("(?iu)^(order platzieren|place order)$")
        return lines.filterNot { exact.matches(normalized(it.text)) }
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
        if (!canClick(launcher) || values(launcher).filter(String::isNotBlank).any { !launchLabel.matches(it.trim()) } ||
            launcher.row.lines().filter(String::isNotBlank).any { !launchLabel.matches(it.trim()) }) return null
        val productLabel="Mit Namen, ISIN oder Symbol suchen"
        val searches=nodes.indices.filter { index ->
            val n=nodes[index]
            canClick(n) && (values(n).any { exact(normalized(it),productLabel) } || exact(normalized(n.row),productLabel)) &&
                values(n).filter(String::isNotBlank).all { exact(normalized(it),productLabel) } && rowSearch(n)
        }
        return innermost(nodes, searches).singleOrNull()
    }
    fun decide(nodes: List<Node>, target: String, lookupSymbol: (String) -> String? = { null }): Action {
        if (!SeriesEvidence.validIsin(target)) return Action(Kind.BLOCK, code="INVALID_VIEW")
        return navigate(nodes,target,false,lookupSymbol)
    }
    /** A gesture may target only a unique product-name label, never the row's K/V controls. */
    fun resultTapIndex(nodes: List<Node>, target: String): Int? {
        // A DEGIRO search results page can retain a separate "Order platzieren"
        // launcher. It is NOT a permission to touch that button. Validate the
        // isolated exact launcher and search input, then ignore only that one
        // launcher while selecting a separately validated product-name label.
        // A real order form, compound launcher, extra input or confirmation
        // remains protected; no other order marker may be stripped.
        val initial=decide(nodes,target)
        val launcherIds=nodes.indices.filter { i ->
            listOf(nodes[i].text,nodes[i].description,nodes[i].hint).any {
                normalized(it).equals("Order platzieren",true) ||
                    normalized(it).equals("Place order",true)
            }
        }
        // navigate() can already return WAIT after verifying the separate
        // launcher (for example RESULT_MISSING on a K/V result card). This
        // guard must cover that WAIT state, not only BLOCK.
        val validated=if(launcherIds.isNotEmpty()) {
            if(initial.kind==Kind.BLOCK && initial.code!="PROTECTED_ORDER_CONFIRM") return null
            // A genuine global launcher is outside the individual product card.
            // Refuse a launcher nested inside an identified result even if its
            // isolated button label is otherwise valid.
            val launcherIndex=launcherIds.singleOrNull() ?: return null
            var parent=nodes[launcherIndex].parent
            var steps=0
            while(parent in nodes.indices && steps++<nodes.size) {
                val n=nodes[parent]
                if(n.parent !in nodes.indices) break // page root is not a card
                val idMatches=ids.findAll(n.row.uppercase()).map { it.value }.toSet()
                if(target in idMatches) return null
                parent=n.parent
            }
            productSearchWithoutLauncher(nodes) ?: return null
        } else nodes
        val action=if(validated===nodes) initial else decide(validated,target)
        if(action.kind !in setOf(Kind.RESULT,Kind.WAIT,Kind.SUBMIT)) return null
        val input=validated.filter { it.editable }.singleOrNull() ?: return null
        if(input.text!=target || !isSearchInput(input.id,input.description,input.hint)) return null
        val controls=Regex("(?iu)\\b(k|v|kauf|kaufen|verkauf|verkaufen|buy|sell|order)\\b")
        fun productName(value:String)=Regex("(?iu)\\b(gold|xau)\\b").containsMatchIn(value) &&
            Regex("(?iu)\\b(turbo|knock[ -]?out|mini[ -]?(future|long|short))\\b").containsMatchIn(value)
        fun safe(n:Node)=n.enabled && !n.editable && !n.containsInput && !n.password && !n.sensitive
        val groups=validated.indices.filter { i ->
            val n=validated[i]
            safe(n) && n.row.length<=800 &&
                ids.findAll(n.row.uppercase()).map { it.value }.toSet()==setOf(target) &&
                productName(n.row) && !controls.containsMatchIn(n.row)
        }
        val group=innermost(validated,groups).singleOrNull()
        fun ancestorOf(ancestor:Int, child:Int):Boolean {
            var at=child;var steps=0
            while(at in validated.indices && steps++<validated.size) {
                if(at==ancestor)return true
                at=validated[at].parent
            }
            return false
        }
        // Prefer the original isolated product group when it has no trading
        // controls. Never tap its wrapper: only its exact product-name label.
        if(group!=null) {
            innermost(validated,validated.indices.filter { i ->
                val n=validated[i]
                ancestorOf(group,i) && safe(n) && !n.containsInput &&
                    productName(n.text) && !controls.containsMatchIn(n.row)
            }).singleOrNull()?.let { return it }
        }
        // Samsung DEGIRO also renders a single product title/ISIN and separate
        // K/V trading buttons inside the SAME WebView card. In that case the
        // original group filter correctly refuses the aggregate row; however a
        // unique isolated name label is still a safe read-only gesture target.
        //
        // Demand one verified result, one exact input, the leverage category,
        // no order/login form, and a nearby enclosing product identity. Neither
        // the K/V validated nor their enclosing row may ever be a tap target.
        if(validated.any { it.password || it.sensitive } || protection(validated)!=null ||
            validated.none { normalized(it.text).equals("Hebelprodukte",ignoreCase=true) }) return null
        val visible=validated.filterNot { it.editable }.flatMap { n ->
            ids.findAll(n.text.uppercase()).map { it.value }.toList()
        }.toSet()
        if(visible!=setOf(target))return null
        val isolated=innermost(validated,validated.indices.filter { i ->
            val name=validated[i]
            if(!safe(name) || name.containsInput || !productName(name.text) ||
                controls.containsMatchIn(name.text) ||
                controls.containsMatchIn(name.description) ||
                controls.containsMatchIn(name.hint) ||
                controls.containsMatchIn(name.row))return@filter false
            // Never use a name node that encloses any trading button.
            if(validated.indices.any { j -> j!=i && ancestorOf(i,j) &&
                listOf(validated[j].text,validated[j].description).any(controls::containsMatchIn) })return@filter false
            var parent=i;var steps=0;var linked=false
            while(parent in validated.indices && steps++<6) {
                val container=validated[parent]
                // The root may contain unrelated navigation and trade actions.
                if((parent==i || container.parent in validated.indices) &&
                    container.row.length in 1..800 &&
                    ids.findAll(container.row.uppercase()).map { it.value }.toSet()==setOf(target) &&
                    productName(container.row)) {
                    // If K/V is visible in the card, it must be isolated in
                    // child controls, never baked into this title label.
                    if(!controls.containsMatchIn(container.row) || validated.indices.any { j ->
                        ancestorOf(parent,j) && !ancestorOf(i,j) &&
                        normalized(validated[j].text).lowercase() in setOf("k","v","kauf","verkauf","buy","sell")
                    })linked=true
                }
                if(linked)break
                parent=container.parent
            }
            linked
        })
        isolated.singleOrNull()?.let { return it }
        // On certain Samsung WebView builds the exact product-name text
        // includes its ISIN, while the node's recorded *row* also contains
        // separate sibling K/V controls. Do not tap the row or either control.
        // Select only that single isolated title, and only when the K/V
        // controls are independent clickable siblings within the same card.
        // The later gesture layer additionally rejects any coordinates
        // overlapping a trading control.
        val inlineTitle=innermost(validated,validated.indices.filter { i ->
            val title=validated[i]
            if(!safe(title) || title.containsInput || !productName(title.text) ||
                controls.containsMatchIn(title.text) ||
                controls.containsMatchIn(title.description) ||
                controls.containsMatchIn(title.hint) ||
                title.row.length !in 1..800 ||
                ids.findAll(title.text.uppercase()).map { it.value }.toSet()!=setOf(target) ||
                ids.findAll(title.row.uppercase()).map { it.value }.toSet()!=setOf(target))
                return@filter false
            // The aggregate row may contain ONLY separately-rendered K/V
            // labels, never an order form or a compound buy/sell title.
            val parts=title.row.lines().map(::normalized).filter(String::isNotBlank)
            val controlParts=parts.filter(controls::containsMatchIn)
            if(controlParts.toSet()!=setOf("K","V") || controlParts.size!=2) return@filter false
            if(validated.indices.any { j -> j!=i && ancestorOf(i,j) &&
                listOf(validated[j].text,validated[j].description).any(controls::containsMatchIn) })
                return@filter false
            val parent=title.parent
            if(parent !in validated.indices || parent==i) return@filter false
            val card=validated[parent]
            if(!safe(card) || card.row.length !in 1..800 ||
                ids.findAll(card.row.uppercase()).map { it.value }.toSet()!=setOf(target) ||
                !productName(card.row)) return@filter false
            val siblings=validated.indices.filter { j ->
                j!=i && validated[j].parent==parent &&
                    normalized(validated[j].text).uppercase() in setOf("K","V") &&
                    safe(validated[j]) && canClick(validated[j])
            }.map { normalized(validated[it].text).uppercase() }
            siblings.toSet()==setOf("K","V") && siblings.size==2
        })
        return inlineTitle.singleOrNull()
    }

    fun discoverGold(nodes: List<Node>): Action = navigate(nodes,"Gold",true,{ null })
    /** A real search control takes precedence over another backward scroll. */
    fun detailSearchRestore(nodes: List<Node>, importedListRun: Boolean): Action? {
        if(!importedListRun || nodes.any { it.editable } || importedListSearch(nodes)!=null) return null
        return captureGoldList(nodes,true).takeIf { it.kind==Kind.COLLECT }
    }
    private fun importedListSearch(nodes: List<Node>): Action? {
        if(nodes.any { it.editable } || captureGoldList(nodes,true).kind!=Kind.COLLECT) return null
        val context=nodes + Node("Gold",id="search-input",editable=true)
        val validated=productSearchWithoutLauncher(context) ?: return null
        // The synthetic input validates list context only; remove it before choosing a target.
        val action=navigate(validated.dropLast(1),"",false,{ null })
        if(action.kind!=Kind.SEARCH || action.index !in nodes.indices) return null
        val n=nodes[action.index]
        // Never let a search-labelled aggregate wrapper include a product or order control.
        if(n.row.lines().filter(String::isNotBlank).any {
            !searchLabel(it) && !normalized(it).equals("Gold",true)
        }) return null
        return action
    }
    fun detailDecision(nodes: List<Node>, target: String, importedListRun: Boolean,
                       keyboardReady: Boolean = true, resultOpened: Boolean = true, lookupSymbol: (String) -> String? = { null }): Action {
        if(!SeriesEvidence.validIsin(target)) return Action(Kind.BLOCK,code="INVALID_VIEW")
        if(importedListRun) importedListSearch(nodes)?.let { return it }
        val action=navigate(nodes,target,false,lookupSymbol,symbolProbe=importedListRun)
        // Each batch attempt must open its own exact search result. A numeric
        // header left by the preceding attempt cannot identify the new target.
        if (!resultOpened && action.kind == Kind.READ) return Action(Kind.BACK)
        // A WebView can retain focus after hiding the keyboard. Open it before editing.
        return if(action.kind==Kind.QUERY && !keyboardReady) action.copy(kind=Kind.FOCUS) else action
    }
    /** Move back toward the existing search only after ten exact list identities
     * were captured. This permits SCROLL_BACKWARD, not a product tap, input, or
     * acceptance of still-pending server OCR. Reject every ambiguous surface. */
    fun listReturnScrollTarget(nodes: List<Node>, backwardIndices: Set<Int>, capturedIsins: Set<String>): Int? {
        if (capturedIsins.size != 10 || capturedIsins.any { !SeriesEvidence.validIsin(it) } ||
            nodes.any { it.editable || it.password || it.sensitive }) return null
        val action=captureGoldList(nodes,true)
        if (action.kind!=Kind.COLLECT || action.isins.isEmpty() ||
            !capturedIsins.containsAll(action.isins)) return null
        val candidates=backwardIndices.filter { i ->
            i in nodes.indices && nodes[i].enabled && !nodes[i].containsInput &&
                !nodes[i].password && !nodes[i].sensitive &&
                action.isins.any { nodes[i].row.contains(it) }
        }
        return innermost(nodes,candidates).singleOrNull()
    }

    /** Continue only an already captured Top Results list. The search header may
     * scroll out of the accessibility tree. A synthetic context node is used only
     * for policy validation; no action can target it or any product row. */
    fun captureGoldList(nodes: List<Node>, continuing: Boolean): Action {
        // DEGIRO's WebView may draw the selected tab without exposing Android's
        // selected/checked flag. A captured Top Results page is stronger evidence.
        val tabs=innermost(nodes,nodes.indices.filter { nodes[it].enabled && normalized(nodes[it].text).equals("Hebelprodukte",true) })
        val topResults=nodes.any { normalized(it.text).equals("Top Ergebnisse",true) }
        if(tabs.size!=1 || !(nodes[tabs.single()].selected || continuing || topResults)) return discoverGold(nodes)
        val context=if(continuing && nodes.none { it.editable })
            nodes + Node("Gold",id="search-input",editable=true) else nodes
        val action=navigate(context,"Gold",true,{ null },captureAll=true)
        if(context !== nodes && action.kind !in setOf(Kind.COLLECT,Kind.BLOCK))
            return Action(Kind.WAIT,code="GOLD_IDENTITIES_MISSING")
        return action
    }
    /** Search pages retain the global order launcher. Recognize only its exact,
     * isolated label beside one explicitly labelled product input. Keep indexes
     * unchanged and re-run every protection against the remaining nodes. */
    enum class LauncherIssue { NONE, INPUT_COUNT, INPUT_DISABLED, INPUT_LABEL, MARKER_COUNT,
        LAUNCHER_UNSAFE, LAUNCHER_LABEL, LAUNCHER_ROW, RELATED_TARGETS }
    fun launcherSearchIssue(nodes: List<Node>): LauncherIssue {
        var issue=LauncherIssue.NONE
        productSearchWithoutLauncher(nodes) { issue=it }
        return issue
    }
    private fun productSearchWithoutLauncher(nodes: List<Node>, rejected: (LauncherIssue) -> Unit = {}): List<Node>? {
        fun reject(issue: LauncherIssue): List<Node>? { rejected(issue); return null }
        val inputs=nodes.filter { it.editable }
        if (inputs.size != 1) return reject(LauncherIssue.INPUT_COUNT)
        if (!inputs.single().enabled) return reject(LauncherIssue.INPUT_DISABLED)
        val input=inputs.single()
        // Use the same semantic input identity as navigationTree and the normal
        // query path: Android may expose a search resource ID or short hint.
        // User-entered text alone never establishes a search input here.
        if (!isSearchInput(input.id,input.description,input.hint)) return reject(LauncherIssue.INPUT_LABEL)
        val marked=nodes.indices.filter { i ->
            listOf(nodes[i].text,nodes[i].description,nodes[i].hint).any(orderMarkers.first().second::containsMatchIn)
        }
        val index=marked.singleOrNull() ?: return reject(LauncherIssue.MARKER_COUNT)
        val launcher=nodes[index]
        val exact=Regex("(?iu)^(order platzieren|place order)$")
        if (!canClick(launcher) || launcher.editable || launcher.containsInput || launcher.password || launcher.sensitive) return reject(LauncherIssue.LAUNCHER_UNSAFE)
        if (listOf(launcher.text,launcher.description,launcher.hint).filter(String::isNotBlank)
                .any { !exact.matches(normalized(it)) }) return reject(LauncherIssue.LAUNCHER_LABEL)
        if (launcher.row.lines().filter(String::isNotBlank).any { !exact.matches(normalized(it)) })
            return reject(LauncherIssue.LAUNCHER_ROW)
        // The search must not be nested in the launcher (or vice versa).
        fun below(child: Int, ancestor: Int): Boolean {
            var cursor=nodes[child].parent
            var steps=0
            while(cursor in nodes.indices && steps++ < nodes.size) {
                if(cursor==ancestor) return true
                cursor=nodes[cursor].parent
            }
            return false
        }
        val inputIndex=nodes.indexOf(input)
        if(below(inputIndex,index) || below(index,inputIndex)) return reject(LauncherIssue.RELATED_TARGETS)
        return nodes.mapIndexed { i,n -> if(i==index) Node("") else n }
    }
    private fun navigate(nodes: List<Node>, target: String, discovery: Boolean, lookupSymbol: (String) -> String?, captureAll: Boolean = false, symbolProbe: Boolean = false): Action {
        if (nodes.size > 500) return Action(Kind.BLOCK, code="INVALID_VIEW")
        protection(nodes)?.let { cause ->
            if (cause == "PROTECTED_ORDER_CONFIRM") {
                if(!discovery) {
                    if(detailLauncherIndex(nodes,target,symbolProbe=symbolProbe)!=null) return Action(Kind.READ)
                    // After finishing one item, leave only a separately validated
                    // product page before searching for the next requested ISIN.
                    val current=nodes.flatMap { n -> ids.findAll(n.text.uppercase()).map { it.value }.toList() }
                        .toSet().singleOrNull()
                    // Recent-search lists contain other product ISINs but
                    // are not the opened detail of that product. A synthetic
                    // detail label in the same tree must not trigger BACK.
                    val recentList=nodes.any { normalized(it.text).equals("ZULETZT",true) } ||
                        nodes.any { normalized(it.text).equals("Nach Produkttyp durchsuchen",true) }
                    if(!recentList && current!=null && current!=target &&
                        detailLauncherIndex(nodes,current)!=null)
                        return Action(Kind.BACK)
                }
                marketSearchBesideLauncher(nodes)?.let { return Action(Kind.SEARCH,it) }
                recentMarketSearchBesideLauncher(nodes)?.let { return Action(Kind.SEARCH,it) }
                productSearchWithoutLauncher(nodes)?.let { searchNodes ->
                    val action=navigate(searchNodes,target,discovery,lookupSymbol,captureAll,symbolProbe)
                    if(action.kind in setOf(Kind.FOCUS,Kind.QUERY,Kind.SUBMIT,Kind.CATEGORY,Kind.CATEGORY_SCROLL,Kind.RESULT,Kind.COLLECT,Kind.WAIT)) return action
                }
            }
            return Action(Kind.BLOCK, code=cause)
        }
        val inputs = nodes.indices.filter { nodes[it].editable && search(nodes[it]) }
        if (inputs.size > 1) return Action(Kind.WAIT, code="SEARCH_AMBIGUOUS")
        if (inputs.size == 1) {
            val i = inputs.single()
            if (!nodes[i].enabled) return Action(Kind.WAIT,code="SEARCH_NOT_ACTIONABLE")
            if (nodes[i].text != target) return Action(if(nodes[i].focused) Kind.QUERY else Kind.FOCUS, i)
            if (discovery) {
                // Only visible, explicit identities in Gold leverage-product rows.
                // This is a bounded candidate sample, never a complete catalog or
                // proof of the underlying, quote freshness, or trade approval.
                val candidates=nodes.filter { it.enabled && !it.editable && !it.containsInput && (!captureAll || it.captureComplete) }.mapNotNull { n ->
                    val row=n.row
                    val found=ids.findAll(row.uppercase()).map { it.value }.toSet().singleOrNull()
                    found?.takeIf { SeriesEvidence.validIsin(it) &&
                        Regex("(?iu)\\b(gold|xau)\\b").containsMatchIn(row) &&
                        Regex(if(captureAll) "(?iu)\\b(turbo|knock[ -]?out|mini[ -]?(future|long|short)|faktor|factor)\\b" else "(?iu)\\b(turbo|knock[ -]?out|mini[ -]?(future|long|short))\\b").containsMatchIn(row) &&
                        !Regex(if(captureAll) "(?iu)\\b(kauf|kaufen|verkauf|verkaufen|buy|sell|order)\\b" else "(?iu)\\b(faktor|factor|kauf|kaufen|verkauf|verkaufen|buy|sell|order)\\b").containsMatchIn(row) }
                }.distinct().take(12)
                if(candidates.isNotEmpty()) return Action(Kind.COLLECT,isins=candidates)
                goldCategory(nodes)?.let { return it }
                return Action(if(nodes[i].imeEnter) Kind.SUBMIT else Kind.WAIT,index=i,code="GOLD_IDENTITIES_MISSING")
            }
            val candidates = nodes.indices.filter { j ->
                val n = nodes[j]
                canClick(n) && !n.editable && !n.containsInput && ids.findAll(n.row.uppercase()).map { it.value }.toSet() == setOf(target) &&
                    !Regex("(?iu)\\b(kauf|verkauf|buy|sell|order)\\b").containsMatchIn(n.row)
            }
            val smallest = candidates.minByOrNull { nodes[it].row.length }
            return if (smallest == null) Action(if(nodes[i].imeEnter) Kind.SUBMIT else Kind.WAIT,index=i, code="RESULT_MISSING") else Action(Kind.RESULT, smallest)
        }
        val visibleIds = nodes.filterNot { it.editable }.flatMap { ids.findAll(it.text.uppercase()).map { m -> m.value }.toList() }.toSet()
        val detail = nodes.any { Regex("(?iu)^(übersicht|overview|kursdaten|produktdetails)$").matches(it.text.trim()) }
        if (symbolProbe && visibleIds.isEmpty() && ProductSymbolMemory.detailSymbol(nodes.map { it.text })!=null) return Action(Kind.READ)
        if (visibleIds == setOf(target) && detail) return Action(Kind.READ)
        // A known symbol may open the bounded page reader, but cannot publish
        // quotes. That reader still requires a real visible ISIN before export.
        // Use individual non-input labels, never aggregate rows or search results.
        if (detail && visibleIds.isEmpty() && ProductSymbolMemory.resolveTexts(
                nodes.filterNot { it.editable || it.containsInput }.map { it.text }, lookupSymbol) == target)
            return Action(Kind.READ)
        // Some accessibility trees put the search label on a child of the clickable icon.
        // Accept only a single exact search label; never an aggregate page/list row.
        val buttons = innermost(nodes, nodes.indices.filter {
            val n=nodes[it]
            canClick(n) && !n.containsInput && (search(n) || (n.text.isBlank() && rowSearch(n)))
        })
        // Markets exposes both a toolbar magnifier and the explicitly labelled
        // product-search bar. Prefer that unique bar over generic search icons.
        val explicit=buttons.filter { index ->
            val n=nodes[index]
            listOf(n.text,n.description,n.hint,n.row).any {
                normalized(it).equals("Mit Namen, ISIN oder Symbol suchen",ignoreCase=true)
            }
        }
        if(explicit.size==1) return Action(Kind.SEARCH,explicit.single())
        if (buttons.size == 1) return Action(Kind.SEARCH, buttons.single())
        if (buttons.size > 1) return Action(Kind.WAIT, code="SEARCH_AMBIGUOUS")
        return if (detail) Action(Kind.BACK) else Action(Kind.WAIT, code=when {
            nodes.any { search(it) || rowSearch(it) } -> "SEARCH_NOT_ACTIONABLE"
            nodes.all { it.text.isBlank() && it.description.isBlank() && it.hint.isBlank() } -> "SEARCH_TREE_EMPTY"
            else -> "SEARCH_MISSING"
        })
    }

    private fun goldCategory(nodes:List<Node>):Action? {
        val labels=setOf("alle","aktien","etfs","anleihen","investmentfonds","hebelprodukte","zertifikate","optionen","futures")
        fun parts(n:Node)=listOf(n.text,n.description,n.hint,n.row).flatMap { it.lines() }
            .map { normalized(it).lowercase() }.filter(String::isNotBlank).distinct()
        fun safe(n:Node)=n.enabled && !n.editable && !n.containsInput && !n.password && !n.sensitive
        val tabs=innermost(nodes,nodes.indices.filter { safe(nodes[it]) && canClick(nodes[it]) && parts(nodes[it])==listOf("hebelprodukte") })
        if(tabs.size>1) return Action(Kind.WAIT,code="CATEGORY_AMBIGUOUS")
        tabs.singleOrNull()?.let { return if(nodes[it].selected) Action(Kind.WAIT,code="CATEGORY_RESULTS_PENDING") else Action(Kind.CATEGORY,it) }
        val strips=innermost(nodes,nodes.indices.filter {
            val n=nodes[it];val names=parts(n)
            safe(n) && n.scrollRight && names.size>=2 && names.all { name -> name in labels }
        })
        return when(strips.size) {
            1 -> Action(Kind.CATEGORY_SCROLL,strips.single())
            0 -> null
            else -> Action(Kind.WAIT,code="CATEGORY_STRIP_AMBIGUOUS")
        }
    }
}

