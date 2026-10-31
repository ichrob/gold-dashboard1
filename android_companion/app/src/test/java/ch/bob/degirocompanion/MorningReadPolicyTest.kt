package ch.bob.degirocompanion
import org.junit.Assert.*
import org.junit.Test
class MorningReadPolicyTest {
    @Test fun exactProductPromptWithoutAndroidHintFlagStillIdentifiesSearch() {
        val prompt="Mit Namen, ISIN oder Symbol suchen"
        val hint=MorningReadPolicy.inputHint("",prompt,false)
        val input=MorningReadPolicy.Node(prompt,editable=true,hint=hint)
        val launcher=MorningReadPolicy.Node("",description="Order platzieren",clickable=true)
        assertEquals(MorningReadPolicy.Kind.QUERY,MorningReadPolicy.discoverGold(listOf(input,launcher)).kind)
        for(text in listOf("Suche","Gold","DE000FD0S0G4","Order suchen",prompt+" Order bestätigen"))
            assertEquals("",MorningReadPolicy.inputHint("",text,false))
        assertEquals("Limitpreis",MorningReadPolicy.inputHint("Limitpreis",prompt,false))
        assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.discoverGold(listOf(input,launcher,node("Stückzahl"))).kind)
    }
    @Test fun launcherExceptionUsesSemanticInputIdentityNotOneLongPlaceholder() {
        val launcher=MorningReadPolicy.Node("",description="Order platzieren",clickable=true)
        for(input in listOf(
                MorningReadPolicy.Node("",editable=true,id="nl.degiro.trader:id/search_src_text"),
                MorningReadPolicy.Node("",editable=true,hint="Suche"),
                MorningReadPolicy.Node("",editable=true,description="Search products"))) {
            assertEquals(MorningReadPolicy.Kind.QUERY,MorningReadPolicy.discoverGold(listOf(launcher,input)).kind)
            for(extra in listOf(node("Order bestätigen"),node("Limitpreis"),node("Stückzahl"),node("Passwort"),
                    node("").copy(editable=true),node("").copy(sensitive=true)))
                assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.discoverGold(listOf(launcher,input,extra)).kind)
        }
        for(input in listOf(MorningReadPolicy.Node("Suche",editable=true),
                MorningReadPolicy.Node("",editable=true,id="nl.degiro.trader:id/amount")))
            assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.discoverGold(listOf(launcher,input)).kind)
    }
    @Test fun submitOnlyRecognizedSearchWithMatchingQueryAndNoResult() {
        val input=MorningReadPolicy.Node("Gold",editable=true,hint="Mit Namen, ISIN oder Symbol suchen",imeEnter=true)
        assertEquals(MorningReadPolicy.Kind.SUBMIT,MorningReadPolicy.discoverGold(listOf(input)).kind)
        assertEquals(MorningReadPolicy.Kind.QUERY,MorningReadPolicy.discoverGold(listOf(input.copy(text=""))).kind)
        assertEquals(MorningReadPolicy.Kind.WAIT,MorningReadPolicy.discoverGold(listOf(input.copy(imeEnter=false))).kind)
        assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.discoverGold(listOf(input.copy(hint=""))).kind)
        assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.discoverGold(listOf(input, node("Limitpreis"))).kind)
        val result=node("Gold Turbo DE000FD0S0G4",true)
        assertEquals(MorningReadPolicy.Kind.COLLECT,MorningReadPolicy.discoverGold(listOf(input,result)).kind)
        assertEquals(MorningReadPolicy.Kind.RESULT,MorningReadPolicy.decide(listOf(input.copy(text=isin),result),isin).kind)
    }
    @Test fun submitIsAttemptedOnceUntilQueryOrWindowChanges() {
        val progress=SearchClickProgress()
        val input=MorningReadPolicy.Node("Gold",editable=true,hint="Suche",imeEnter=true)
        val nodes=listOf(input)
        val proposed=MorningReadPolicy.discoverGold(nodes)
        assertEquals(MorningReadPolicy.Kind.SUBMIT,progress.select(nodes,proposed,1,100).kind)
        progress.record(0,100)
        assertEquals(MorningReadPolicy.Kind.WAIT,progress.select(nodes,proposed,1,2000).kind)
        assertEquals(MorningReadPolicy.Kind.SUBMIT,progress.select(nodes,proposed,2,3000).kind)
        progress.clear()
        assertEquals(MorningReadPolicy.Kind.SUBMIT,progress.select(nodes,proposed,1,4000).kind)
    }
    private val isin="DE000FD0S0G4"
    private fun node(text:String,click:Boolean=false)=MorningReadPolicy.Node(text,clickable=click)
    @Test fun splitSearchTextAndActionOnlyContainersCanOpenSearch() {
        val label="Mit Namen,\nISIN oder\u00a0Symbol suchen"
        val wrapper=node("").copy(row=label,clickAction=true)
        assertEquals(MorningReadPolicy.Kind.SEARCH,MorningReadPolicy.decide(listOf(wrapper),isin).kind)
        assertEquals(MorningReadPolicy.Kind.SEARCH,MorningReadPolicy.decide(listOf(node(label).copy(clickAction=true)),isin).kind)
        assertEquals("SEARCH_NOT_ACTIONABLE",MorningReadPolicy.decide(listOf(node(label)),isin).code)
        assertEquals("SEARCH_NOT_ACTIONABLE",MorningReadPolicy.decide(listOf(wrapper.copy(enabled=false)),isin).code)
        assertEquals("SEARCH_TREE_EMPTY",MorningReadPolicy.decide(listOf(node("")),isin).code)
        assertEquals("SEARCH_MISSING",MorningReadPolicy.decide(listOf(node("Märkte")),isin).code)
        for(extra in listOf("\nPortfolio","\nKaufen","\nIndizes"))
            assertEquals(MorningReadPolicy.Kind.WAIT,MorningReadPolicy.decide(listOf(wrapper.copy(row=label+extra)),isin).kind)
        assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.decide(listOf(wrapper,node("Limitpreis")),isin).kind)
    }
    @Test fun nestedSearchWrappersAreOneTargetButSiblingSearchesRemainAmbiguous() {
        val label="Mit Namen, ISIN oder Symbol suchen"
        val outer=node("").copy(row=label,clickAction=true)
        val inner=node(label,true).copy(parent=0)
        assertEquals(1,MorningReadPolicy.decide(listOf(outer,inner),isin).index)
        assertEquals("SEARCH_AMBIGUOUS",MorningReadPolicy.decide(listOf(outer,inner.copy(parent=-1)),isin).code)
        assertEquals(0,MorningReadPolicy.decide(listOf(outer,inner.copy(enabled=false)),isin).index)
        val input=node("").copy(editable=true,hint=label,parent=0)
        assertEquals(MorningReadPolicy.Kind.QUERY,MorningReadPolicy.decide(listOf(outer.copy(containsInput=true),input),isin).kind)
        // A wholly blank wrapper does not make an unrelated clickable parent a search.
        assertEquals(MorningReadPolicy.Kind.WAIT,MorningReadPolicy.decide(listOf(node("",true),node(label).copy(parent=0)),isin).kind)
        val market=listOf(node("Märkte"),node("Suche",true),node(label,true))
        assertEquals(2,MorningReadPolicy.decide(market,isin).index)
        assertEquals(2,MorningReadPolicy.discoverGold(market).index)
        assertEquals("SEARCH_AMBIGUOUS",MorningReadPolicy.decide(market+node(label,true),isin).code)
    }
    @Test fun onlySearchFieldCanReceiveIsin() {
        val input=MorningReadPolicy.Node("",id="nl.degiro.trader:id/search_src_text",editable=true)
        assertEquals(MorningReadPolicy.Kind.QUERY,MorningReadPolicy.decide(listOf(input),isin).kind)
        assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.decide(listOf(input.copy(id="amount")),isin).kind)
        assertEquals(MorningReadPolicy.Kind.SEARCH,MorningReadPolicy.decide(listOf(node("Suche",true)),isin).kind)
        assertEquals(MorningReadPolicy.Kind.WAIT,MorningReadPolicy.decide(listOf(node("Suche",true),node("Search",true)),isin).kind)
    }
    @Test fun resultNeedsExactSingleIsinWithoutSearchInputAncestorOrOrderAction() {
        val input=MorningReadPolicy.Node(isin,id="search",editable=true)
        val exact=node("SG Gold $isin",true)
        assertEquals(1,MorningReadPolicy.decide(listOf(input,exact),isin).index)
        for(bad in listOf(node("DE000FG77MY4",true),node("$isin DE000FG77MY4",true),node("Kauf $isin",true),exact.copy(containsInput=true)))
            assertEquals(MorningReadPolicy.Kind.WAIT,MorningReadPolicy.decide(listOf(input,bad),isin).kind)
    }
    @Test fun searchLabelOnChildCanIdentifyOnlyItsOwnClickableIcon() {
        val icon=MorningReadPolicy.Node("",clickable=true,row="Suchen")
        assertEquals(MorningReadPolicy.Kind.SEARCH,MorningReadPolicy.decide(listOf(icon,node("Suchen")),isin).kind)
        assertEquals(MorningReadPolicy.Kind.WAIT,MorningReadPolicy.decide(listOf(icon.copy(row="Suchen\nKauf")),isin).kind)
        assertEquals(MorningReadPolicy.Kind.WAIT,MorningReadPolicy.decide(listOf(icon.copy(containsInput=true)),isin).kind)
        assertEquals(MorningReadPolicy.Kind.SEARCH,MorningReadPolicy.decide(listOf(node("Search instruments",true)),isin).kind)
    }
    @Test fun semanticDescriptionsAndHintsSurviveEmptyOrEnteredText() {
        val icon=node("",true).copy(description="Suchen")
        assertEquals(MorningReadPolicy.Kind.SEARCH,MorningReadPolicy.decide(listOf(icon),isin).kind)
        val input=node("").copy(editable=true,hint="Search instruments")
        assertTrue(MorningReadPolicy.isSearchInput("","","Search instruments"))
        assertFalse(MorningReadPolicy.isSearchInput("amount","","Search orders"))
        assertEquals(MorningReadPolicy.Kind.QUERY,MorningReadPolicy.decide(listOf(input),isin).kind)
        assertEquals(MorningReadPolicy.Kind.RESULT,MorningReadPolicy.decide(listOf(input.copy(text=isin),node(isin,true)),isin).kind)
        for(bad in listOf(icon.copy(description="Order bestätigen"),icon.copy(hint="Passwort"),input.copy(hint="Search orders")))
            assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.decide(listOf(bad),isin).kind)
    }
    @Test fun protectedLoginAndOrderViewsAlwaysStop() {
        for(n in listOf(node("Passwort"),node("Orderart"),node("Anmelden"),node("Gold").copy(sensitive=true)))
            assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.decide(listOf(node(isin),node("Übersicht"),n),isin).kind)
    }
    @Test fun markedSearchPlaceholderCanIdentifyInputWithoutViewId() {
        for(label in listOf("Suche", "Search instruments", "Name, ISIN oder Symbol", "Mit Namen, ISIN oder Symbol suchen")) {
            val hint=MorningReadPolicy.inputHint("",label,true)
            val input=node("").copy(editable=true,hint=hint)
            assertEquals(MorningReadPolicy.Kind.QUERY,MorningReadPolicy.decide(listOf(input),isin).kind)
            assertEquals(if(label=="Mit Namen, ISIN oder Symbol suchen") label else "",MorningReadPolicy.inputHint("",label,false))
        }
        for(label in listOf("Passwort", "Limitpreis", "Search orders", "ISIN", isin)) {
            assertEquals("",MorningReadPolicy.inputHint("",label,true))
            assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.decide(listOf(node("").copy(editable=true)),isin).kind)
        }
    }
    @Test fun marketSearchLabelSupportsButtonHintAndDescriptionWithoutBypassingProtection() {
        val label="Mit Namen, ISIN oder Symbol suchen"
        for(button in listOf(node(label,true),node("",true).copy(description=label),node("",true).copy(row=label))) {
            assertEquals(MorningReadPolicy.Kind.SEARCH,MorningReadPolicy.decide(listOf(node("Märkte"),button),isin).kind)
            assertEquals("PROTECTED_ORDER_TYPE",MorningReadPolicy.decide(listOf(button,node("Orderart")),isin).code)
        }
        val input=node("").copy(editable=true,hint=label)
        assertTrue(MorningReadPolicy.isSearchInput("","",label))
        assertEquals(MorningReadPolicy.Kind.QUERY,MorningReadPolicy.decide(listOf(input),isin).kind)
        assertEquals(MorningReadPolicy.Kind.RESULT,MorningReadPolicy.decide(listOf(input.copy(text=isin),node(isin,true)),isin).kind)
        assertEquals(MorningReadPolicy.Kind.WAIT,MorningReadPolicy.decide(listOf(node("Andere "+label,true)),isin).kind)
        assertEquals("PROTECTED_ORDER_PRICE",MorningReadPolicy.decide(listOf(input,node("Limitpreis")),isin).code)
        assertEquals("PROTECTED_LOGIN",MorningReadPolicy.decide(listOf(input,node("Anmelden")),isin).code)
    }
    @Test fun protectionCausesAreDistinctWithoutExportingScreenText() {
        val cases=listOf(
            node("").copy(password=true,sensitive=true,editable=true) to "PROTECTED_PASSWORD",
            node("").copy(sensitive=true,editable=true) to "PROTECTED_SENSITIVE_INPUT",
            node("").copy(sensitive=true) to "PROTECTED_SENSITIVE_CONTENT",
            node("Anmelden") to "PROTECTED_LOGIN",
            node("Orderart") to "PROTECTED_ORDER_TYPE",
            node("").copy(editable=true) to "UNRECOGNIZED_INPUT")
        for((blocked,code) in cases) {
            val action=MorningReadPolicy.decide(listOf(node("Suchen",true),blocked),isin)
            assertEquals(MorningReadPolicy.Kind.BLOCK,action.kind)
            assertEquals(code,action.code)
        }
        assertEquals("PROTECTED_PASSWORD",MorningReadPolicy.decide(listOf(node("Suchen").copy(editable=true,password=true)),isin).code)
    }
    @Test fun everyExistingOrderMarkerStillBlocksAndExportsOnlyFixedCause() {
        val cases=listOf("Order platzieren" to "CONFIRM", "Order bestätigen" to "CONFIRM",
            "Place order" to "CONFIRM", "Confirm order" to "CONFIRM",
            "Orderart" to "TYPE", "Ordertyp" to "TYPE", "Limitpreis" to "PRICE",
            "Stückzahl" to "QUANTITY", "Anzahl kaufen" to "QUANTITY")
        for ((label,cause) in cases) for (n in listOf(node(label),node("").copy(description=label),node("").copy(hint=label))) {
            val action=MorningReadPolicy.decide(listOf(node("Suchen",true),n),isin)
            assertEquals(MorningReadPolicy.Kind.BLOCK,action.kind)
            assertEquals("PROTECTED_ORDER_"+cause,action.code)
            assertEquals(-1,action.index)
        }
    }
    @Test fun isolatedMarketLauncherAllowsOnlyExplicitProductSearch() {
        val search=node("Mit Namen, ISIN oder Symbol suchen",true)
        val launcher=node("",true).copy(description="Order platzieren")
        val home=listOf(node("Märkte"),node("Indizes"),search,launcher)
        val action=MorningReadPolicy.decide(home,isin)
        assertEquals(MorningReadPolicy.Kind.SEARCH,action.kind)
        assertEquals(2,action.index)
        // A generic toolbar search icon does not compete with the exact product label.
        assertEquals(2,MorningReadPolicy.decide(home+node("Suche",true),isin).index)
        for (bad in listOf(
            home+node("Order bestätigen",true), home+node("Confirm order",true),
            home+node("Orderart"),home+node("Limitpreis"),home+node("Stückzahl"),
            home+node("").copy(editable=true),home+node("").copy(password=true),
            home+node("").copy(sensitive=true),home+node("Anmelden"),
            home+search,home+launcher,
            home.filterNot { it.text=="Indizes" },home.filterNot { it.text=="Märkte" },
            home.take(3)+launcher.copy(clickable=false),
            home.take(3)+launcher.copy(row="Order platzieren\nKauf"),
            home.take(3)+launcher.copy(description="Order bestätigen"),
            home.take(2)+search.copy(row="Mit Namen, ISIN oder Symbol suchen\nOrder platzieren")+launcher,
            home.take(2)+search.copy(clickable=false)+launcher,
            home.take(2)+search.copy(editable=true)+launcher,
            home.take(2)+node("Suche",true)+launcher,
            home+node(isin).copy(editable=true,hint="Betrag"))) {
            assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.decide(bad,isin).kind)
        }
        // An order launcher on product/results views remains blocked.
        assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.decide(listOf(node(isin),node("Übersicht"),launcher),isin).kind)
    }
    @Test fun explicitProductInputWorksBesideIsolatedGlobalLauncher() {
        val input=node("").copy(editable=true,hint="Mit Namen, ISIN oder Symbol suchen")
        val launcher=node("",true).copy(description="Order platzieren")
        val page=listOf(launcher,input,node("Nach Produkttyp durchsuchen"))
        val query=MorningReadPolicy.discoverGold(page)
        assertEquals(MorningReadPolicy.Kind.QUERY,query.kind)
        assertEquals(1,query.index)
        val row=node("Gold Turbo $isin",true)
        val results=listOf(launcher,input.copy(text="Gold"),row)
        assertEquals(listOf(isin),MorningReadPolicy.discoverGold(results).isins)
        assertEquals(2,MorningReadPolicy.decide(listOf(launcher,input.copy(text=isin),row),isin).index)
        assertEquals("GOLD_IDENTITIES_MISSING",MorningReadPolicy.discoverGold(results.take(2)).code)
        for(extra in listOf(node("Order bestätigen",true),node("Orderart"),node("Limitpreis"),
                node("Stückzahl"),node("Anmelden"),node("").copy(password=true),
                node("").copy(sensitive=true),node("").copy(editable=true)))
            assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.discoverGold(page+extra).kind)
        for(bad in listOf(
                listOf(launcher,input.copy(hint="Betrag")),
                listOf(launcher.copy(description="Order bestätigen"),input),
                listOf(launcher.copy(row="Order platzieren\nKaufen"),input),
                listOf(launcher.copy(clickable=false),input),
                listOf(launcher,input.copy(parent=0)),
                listOf(launcher.copy(parent=1),input),
                listOf(launcher,input.copy(enabled=false)),page+launcher))
            assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.discoverGold(bad).kind)
    }
    @Test fun detailNeedsIdentityAndNeverClicksBuy() {
        assertEquals(MorningReadPolicy.Kind.READ,MorningReadPolicy.decide(listOf(node(isin),node("Übersicht"),node("KAUF",true)),isin).kind)
        assertEquals(MorningReadPolicy.Kind.BACK,MorningReadPolicy.decide(listOf(node("DE000FG77MY4"),node("Übersicht")),isin).kind)
        assertEquals(MorningReadPolicy.Kind.WAIT,MorningReadPolicy.decide(listOf(node("KAUF",true)),isin).kind)
    }
    @Test fun repeatedLauncherRowLabelsAreNotAnOrderForm() {
        val input=node("").copy(editable=true,hint="Mit Namen, ISIN oder Symbol suchen")
        val launcher=node("Order platzieren",true).copy(description="Order platzieren",
            row="Order platzieren\nOrder platzieren")
        assertEquals(MorningReadPolicy.Kind.QUERY,MorningReadPolicy.discoverGold(listOf(launcher,input)).kind)
        assertEquals(MorningReadPolicy.LauncherIssue.NONE,MorningReadPolicy.launcherSearchIssue(listOf(launcher,input)))
        val mixed=launcher.copy(row="Order platzieren\nOrder bestätigen")
        assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.discoverGold(listOf(mixed,input)).kind)
        assertEquals(MorningReadPolicy.LauncherIssue.LAUNCHER_ROW,MorningReadPolicy.launcherSearchIssue(listOf(mixed,input)))
        assertEquals(MorningReadPolicy.LauncherIssue.INPUT_COUNT,MorningReadPolicy.launcherSearchIssue(listOf(launcher)))
        assertEquals(MorningReadPolicy.LauncherIssue.INPUT_LABEL,MorningReadPolicy.launcherSearchIssue(listOf(launcher,input.copy(hint="Betrag"))))
        assertEquals(MorningReadPolicy.LauncherIssue.MARKER_COUNT,MorningReadPolicy.launcherSearchIssue(listOf(launcher,launcher,input)))
    }
    @Test fun knownSymbolHandsDetailToReaderButNeverOverridesVisibleIdentityOrProtection() {
        val header=node("12345678 • Societe Generale OTC | R")
        val page=listOf(header,node("Übersicht"),node("KAUF",true))
        val lookup: (String)->String? = { if(it=="12345678") isin else null }
        assertEquals(MorningReadPolicy.Kind.READ,MorningReadPolicy.decide(page,isin,lookup).kind)
        assertEquals(MorningReadPolicy.Kind.BACK,MorningReadPolicy.decide(page,isin).kind)
        for (stored in listOf(null,ProductSymbolMemory.CONFLICT,"DE000FG77MY4","DE000FD0S0G5"))
            assertEquals(MorningReadPolicy.Kind.BACK,MorningReadPolicy.decide(page,isin) { stored }.kind)
        for (extra in listOf(node("DE000FG77MY4"),node("87654321 • Societe Generale OTC | R")))
            assertEquals(MorningReadPolicy.Kind.BACK,MorningReadPolicy.decide(page+extra,isin,lookup).kind)
        for (extra in listOf(node("Anmelden"),node("Order bestätigen"),node("Limitpreis"),node("").copy(sensitive=true)))
            assertEquals(MorningReadPolicy.Kind.BLOCK,MorningReadPolicy.decide(page+extra,isin,lookup).kind)
        assertEquals(MorningReadPolicy.Kind.WAIT,MorningReadPolicy.decide(listOf(header),isin,lookup).kind)
        assertEquals(MorningReadPolicy.Kind.BACK,MorningReadPolicy.decide(listOf(header.copy(text="",row=header.text),node("Übersicht")),isin,lookup).kind)
        // Search results must still show the exact ISIN before a click is allowed.
        val input=node(isin).copy(editable=true,hint="Suche")
        assertEquals("RESULT_MISSING",MorningReadPolicy.decide(page+input,isin,lookup).code)
    }
    @Test fun listNavigationAndReaderRequireVisibleIsinBeforePublishing() {
        val texts=listOf("12345678 • Societe Generale OTC | R","Übersicht")
        val lookup: (String)->String? = { isin }
        assertEquals(MorningReadPolicy.Kind.READ,MorningReadPolicy.decide(texts.map { node(it) },isin,lookup).kind)
        fun lines(values:List<String>)=values.mapIndexed { index,text -> QuoteLayout.Line(text,0,index*50,250,index*50+30) }
        val header=lines(texts)
        val reader=ProductPageReader()
        val hint=ProductSymbolMemory.resolve(header,lookup)
        assertEquals(ProductPageReader.Move.FORWARD,reader.inspect(1,header,"",false,true,true,identityHint=hint).move)
        val quotes=lines(listOf("Geld EUR 10,20","Brief EUR 10,30"))
        assertEquals(ProductPageReader.Move.BACKWARD,reader.inspect(1,quotes,"",false,true,true).move)
        val refused=reader.inspect(1,header,"",false,false,false,identityHint=hint)
        assertEquals(ProductPageReader.Move.ABORT,refused.move)
        assertEquals("",refused.result.draft)
        reader.inspect(1,header,"",false,true,true,identityHint=hint)
        val verified=reader.inspect(1,lines(listOf("Geld EUR 10,20","Brief EUR 10,30",isin)),"",false,true,true)
        assertEquals(ProductPageReader.Move.FINISHED,verified.move)
        assertTrue(verified.result.draft.contains("ISIN: $isin"))
    }

    private fun samsungSearchResult():List<MorningReadPolicy.Node> {
        val target="DE000SQ02JQ6"
        val title="SG Gold Turbo Unlimited Mini Call BAR 2144 BP 2122.67 Bv 10"
        val card="$title | $target\nSociete Generale OTC EUR\nK\nV"
        return listOf(
            MorningReadPolicy.Node(target,editable=true,hint="Mit Namen, ISIN oder Symbol suchen"),
            MorningReadPolicy.Node(""),
            MorningReadPolicy.Node("Hebelprodukte",parent=1),
            MorningReadPolicy.Node("",row=card,parent=1),
            MorningReadPolicy.Node(title,row=title,parent=3),
            MorningReadPolicy.Node(target,parent=3),
            MorningReadPolicy.Node("Societe Generale OTC EUR",parent=3),
            MorningReadPolicy.Node("K",clickable=true,parent=3),
            MorningReadPolicy.Node("V",clickable=true,parent=3))
    }
    @Test fun samsungResultTitleIsSafeTargetNotKOrV() {
        val target="DE000SQ02JQ6"
        val view=samsungSearchResult()
        assertEquals("RESULT_MISSING",MorningReadPolicy.decide(view,target).code)
        assertEquals(4,MorningReadPolicy.resultTapIndex(view,target))
    }
    @Test fun samsungRejectsWrongSearchInput() {
        val view=samsungSearchResult().toMutableList().also { it[0]=it[0].copy(text="DE000FD0S0G4") }
        assertNull(MorningReadPolicy.resultTapIndex(view,"DE000SQ02JQ6"))
    }
    @Test fun samsungRejectsNoLeverageCategory() {
        val view=samsungSearchResult().toMutableList().also { it[2]=it[2].copy(text="Alle") }
        assertNull(MorningReadPolicy.resultTapIndex(view,"DE000SQ02JQ6"))
    }
    @Test fun samsungRejectsCardLacksIsin() {
        val view=samsungSearchResult().toMutableList().also { it[3]=it[3].copy(row="SG Gold Turbo Unlimited Mini Call BAR 2144 BP 2122.67 Bv 10\nK\nV") }
        assertNull(MorningReadPolicy.resultTapIndex(view,"DE000SQ02JQ6"))
    }
    @Test fun samsungRejectsTitleContainsBuy() {
        val view=samsungSearchResult().toMutableList().also { it[4]=it[4].copy(text=it[4].text+" Kaufen") }
        assertNull(MorningReadPolicy.resultTapIndex(view,"DE000SQ02JQ6"))
    }
    @Test fun samsungRejectsTitleRowContainsTradeControl() {
        val view=samsungSearchResult().toMutableList().also { it[4]=it[4].copy(row=it[4].row+"\nK") }
        assertNull(MorningReadPolicy.resultTapIndex(view,"DE000SQ02JQ6"))
    }
    @Test fun samsungRejectsMismatchedVisibleIsin() {
        val view=samsungSearchResult().toMutableList().also { it[5]=it[5].copy(text="DE000FD0S0G4") }
        assertNull(MorningReadPolicy.resultTapIndex(view,"DE000SQ02JQ6"))
    }
    @Test fun samsungRejectsPasswordInput() {
        val view=samsungSearchResult().toMutableList().also { it[0]=it[0].copy(password=true) }
        assertNull(MorningReadPolicy.resultTapIndex(view,"DE000SQ02JQ6"))
    }
    @Test fun samsungRejectsUnrecognizedInput() {
        val view=samsungSearchResult().toMutableList().also { it[0]=it[0].copy(hint="Limitpreis") }
        assertNull(MorningReadPolicy.resultTapIndex(view,"DE000SQ02JQ6"))
    }
    @Test fun samsungRejectsOrderConfirmation() {
        assertNull(MorningReadPolicy.resultTapIndex(
            samsungSearchResult()+MorningReadPolicy.Node("Order bestätigen"),"DE000SQ02JQ6"))
    }
    @Test fun samsungRejectsDuplicatedProductTitle() {
        val view=samsungSearchResult()
        assertNull(MorningReadPolicy.resultTapIndex(
            view+view[4].copy(parent=3),"DE000SQ02JQ6"))
    }
    @Test fun isolatedTitleWithInlineIsinCanBeTappedButNotTradingControls() {
        val target="DE000SQ02JQ6"
        val title="SG Gold Turbo Unlimited Mini Call BAR 2144 BP 2122.67 Bv 10 | $target"
        val view=listOf(
            MorningReadPolicy.Node(target,editable=true,hint="Suche"),
            MorningReadPolicy.Node("Hebelprodukte"),
            MorningReadPolicy.Node(title,clickable=true,row=title),
            MorningReadPolicy.Node("K",clickable=true),
            MorningReadPolicy.Node("V",clickable=true))
        assertEquals(2,MorningReadPolicy.resultTapIndex(view,target))
        assertNull(MorningReadPolicy.resultTapIndex(view+MorningReadPolicy.Node("Passwort"),target))
        assertNull(MorningReadPolicy.resultTapIndex(view+MorningReadPolicy.Node("Limitpreis"),target))
    }
}
