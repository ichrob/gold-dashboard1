package ch.bob.degirocompanion

import android.accessibilityservice.AccessibilityServiceInfo
import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityButtonController
import android.app.KeyguardManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.graphics.Rect
import android.os.PowerManager
import android.os.SystemClock
import android.os.Handler
import android.os.Looper
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo
import android.widget.Toast
import java.time.Instant

/** Explicit one-minute reading request or accessibility button; only bounded scroll actions on validated product pages. */
class ProductReadService : AccessibilityService() {
    private val symbolMemory by lazy { getSharedPreferences("degiro_symbol_identity_v1", MODE_PRIVATE) }
    private var writtenSearchNode: AccessibilityNodeInfo? = null
    private var writtenSearchQuery = ""
    private fun clearWrittenSearch() { writtenSearchNode?.recycle(); writtenSearchNode=null; writtenSearchQuery="" }
    private fun rememberWrittenSearch(node: AccessibilityNodeInfo, query: String) {
        clearWrittenSearch(); writtenSearchNode=AccessibilityNodeInfo.obtain(node); writtenSearchQuery=query
    }
    private var searchTapAttempted = false
    private var batchTransition = false
    private var lastNavigation = 0L
    private var lastNavigationIssue = ""
    private val pageReader = ProductPageReader()
    private val remoteSearchProgress = SearchClickProgress()
    private val automaticSearchProgress = SearchClickProgress()
    private val handler = Handler(Looper.getMainLooper())
    private var screenReceiverRegistered = false
    private val screenOff = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if(intent?.action == Intent.ACTION_USER_PRESENT) {
                handler.postDelayed({ runCatching { MorningReadTransfer.automaticResults(this@ProductReadService) } },1000)
                return
            }
            if(intent?.action==Intent.ACTION_SCREEN_OFF)PhoneRemote.stop(this@ProductReadService,"SCREEN_LOCKED")
            if (intent?.action != Intent.ACTION_SCREEN_OFF || !ProductReadRequest.active(SystemClock.elapsedRealtime())) return
            MorningReadRun.stop(this@ProductReadService,"SCREEN_LOCKED")
            GoldSearchRun.stop("SCREEN_LOCKED",Instant.now().toString())
            ProductReadRequest.cancel()
            ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.LOCKED)
            ProductReadSession.put(ProductScreenEvidence.Result(message = "Bildschirm ausgeschaltet. Leseprüfung beendet; zum Fortsetzen entsperren und erneut starten."), SystemClock.elapsedRealtime())
        }
    }
    private var screenLease: PowerManager.WakeLock? = null
    private val requestDeadline = Runnable { ProductReadRequest.cancel(ProductReadRequest.End.TIMEOUT) }
    private fun releaseScreen() {
        handler.removeCallbacks(requestDeadline)
        screenLease?.let { if (it.isHeld) it.release() }
        screenLease = null
    }
    @Suppress("DEPRECATION")
    private fun keepScreenForRequest() {
        releaseScreen()
        val remaining = ProductReadRequest.remainingMillis(SystemClock.elapsedRealtime())
        if (remaining <= 0) return
        handler.postDelayed(requestDeadline, remaining)
        val power = getSystemService(POWER_SERVICE) as PowerManager
        if (!power.isInteractive || (getSystemService(KEYGUARD_SERVICE) as KeyguardManager).isKeyguardLocked) {
            GoldSearchRun.stop("SCREEN_LOCKED",Instant.now().toString())
            MorningReadRun.stop(this@ProductReadService,"SCREEN_LOCKED")
            ProductReadRequest.cancel()
            ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.LOCKED)
            return
        }
        // The activity window is no longer foreground while DEGIRO is read.
        // No wake-up flag: never turn on or unlock a deliberately locked phone.
        runCatching {
            power.newWakeLock(PowerManager.SCREEN_DIM_WAKE_LOCK, "Bob:ProductRead").also {
                screenLease = it
                it.setReferenceCounted(false)
                it.acquire(remaining)
            }
        }.onSuccess { ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.SCREEN_HELD) }
            .onFailure {
                releaseScreen()
                handler.postDelayed(requestDeadline, remaining)
                ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.SCREEN_HOLD_FAILED)
                Toast.makeText(this, "Bildschirm konnte nicht wachgehalten werden. Während der Prüfung eingeschaltet lassen.", Toast.LENGTH_LONG).show()
            }
    }
    private var readQueued = false
    private val pendingRead = object : Runnable {
        override fun run() {
            readQueued = false
            if (ProductReadRequest.attempt(SystemClock.elapsedRealtime())) readOnce(automatic = true)
            if (ProductReadRequest.active(SystemClock.elapsedRealtime())) queueRead(2000)
        }
    }
    private fun queueRead(delay: Long) {
        if (!readQueued && ProductReadRequest.active(SystemClock.elapsedRealtime())) {
            readQueued = true
            handler.postDelayed(pendingRead, delay)
        }
    }
    private val callback = object : AccessibilityButtonController.AccessibilityButtonCallback() {
        override fun onClicked(controller: AccessibilityButtonController) { readOnce() }
    }
    override fun onServiceConnected() {
        PhoneRemote.reader={command -> remoteRead(command)}
        PhoneRemote.onStop={ code ->
            remoteSearchProgress.clear(); automaticSearchProgress.clear(); clearWrittenSearch()
            GoldSearchRun.stop(code,Instant.now().toString())
            MorningReadRun.stop(this,code)
            ProductReadRequest.cancel()
        }
        ProductReadDiagnostics.connected = true
        ProductReadDiagnostics.canRead = (serviceInfo.capabilities and AccessibilityServiceInfo.CAPABILITY_CAN_RETRIEVE_WINDOW_CONTENT) != 0
        ProductReadDiagnostics.windowAccess = (serviceInfo.flags and AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS) != 0
        accessibilityButtonController.registerAccessibilityButtonCallback(callback)
        if (!screenReceiverRegistered) {
            val filter = IntentFilter(Intent.ACTION_SCREEN_OFF).apply { addAction(Intent.ACTION_USER_PRESENT) }
            if (android.os.Build.VERSION.SDK_INT >= 33) registerReceiver(screenOff, filter, Context.RECEIVER_NOT_EXPORTED)
            else registerReceiver(screenOff, filter)
            screenReceiverRegistered = true
        }
        MorningReadRun.onStopped = {
            handler.post {
                if(!MorningReadRun.running) {
                    ProductReadRequest.cancel()
                    runCatching { MorningReadTransfer.automaticResults(this) }
                }
            }
        }
        ProductReadRequest.onCancelled = {
            val outcome = when (ProductReadRequest.endReason) {
                ProductReadRequest.End.TIMEOUT -> ProductReadDiagnostics.Outcome.REQUEST_EXPIRED
                ProductReadRequest.End.ATTEMPT_LIMIT -> ProductReadDiagnostics.Outcome.REQUEST_ATTEMPT_LIMIT
                ProductReadRequest.End.CLOCK_CHANGED -> ProductReadDiagnostics.Outcome.REQUEST_CLOCK_CHANGED
                else -> null
            }
            if (outcome != null) {
                ProductReadDiagnostics.record(outcome)
                ProductReadSession.put(ProductScreenEvidence.Result(message = "Leseprüfung am Zeit- oder Versuchslimit beendet. Kein fertig geprüfter Entwurf; bitte Diagnose prüfen."), SystemClock.elapsedRealtime())
            }
            if(GoldSearchRun.running) {
                GoldSearchRun.stop(lastNavigationIssue.ifEmpty { if(outcome!=null) "READ_TIMEOUT" else "STOPPED" },Instant.now().toString())
                ProductReadSession.put(ProductScreenEvidence.Result(message="Goldsuche beendet: "+MorningReadUiPolicy.reason(GoldSearchRun.lastCode.orEmpty())),SystemClock.elapsedRealtime())
                PhoneDiagnostics.queue(this)
            }
            pageReader.reset()
            releaseScreen()
            handler.removeCallbacks(pendingRead)
            readQueued = false
            if (MorningReadRun.running && !batchTransition) {
                if (outcome != null && !MorningReadRun.expired()) {
                    val code=lastNavigationIssue.ifEmpty { "READ_TIMEOUT" }
                    handler.post { finishBatchProduct(code) }
                }
                else MorningReadRun.stop(this, "STOPPED")
            }
            PhoneDiagnostics.queue(this)
        }
        ProductReadRequest.onStarted = {
            clearWrittenSearch()
            searchTapAttempted = false
            automaticSearchProgress.clear()
            lastNavigationIssue=""
            pageReader.reset()
            handler.removeCallbacks(pendingRead)
            readQueued = false
            keepScreenForRequest()
            queueRead(600)
        }
        keepScreenForRequest()
        queueRead(600)
        PhoneDiagnostics.queue(this)
    }
    // Only package/type metadata is used. Never read or retain event text.
    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if(PhoneRemote.active() && event?.eventType==AccessibilityEvent.TYPE_TOUCH_INTERACTION_START) {
            val foreground=productRoot(false)
            val touchesProduct=foreground?.packageName?.toString()==ProductScreenEvidence.PACKAGE
            foreground?.recycle()
            if(touchesProduct)PhoneRemote.stop(this,"USER_INTERRUPTED")
        }
        if (!ProductReadRequest.active(SystemClock.elapsedRealtime())) return
        if((MorningReadRun.running || GoldSearchRun.running) && event?.eventType==AccessibilityEvent.TYPE_TOUCH_INTERACTION_START) {
            GoldSearchRun.stop("USER_INTERRUPTED",Instant.now().toString())
            MorningReadRun.stop(this,"USER_INTERRUPTED");ProductReadRequest.cancel();return
        }
        if (event?.packageName?.toString() != ProductScreenEvidence.PACKAGE) return
        val userAction = !(MorningReadRun.running && SystemClock.elapsedRealtime()-lastNavigation in 0..1200) && event.eventType in setOf(AccessibilityEvent.TYPE_VIEW_CLICKED, AccessibilityEvent.TYPE_VIEW_LONG_CLICKED)
        val windowEvent = event.eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED
        if (pageReader.anchored && (userAction || (windowEvent && !pageReader.sameWindow(event.windowId)))) {
            ProductReadDiagnostics.record(if (userAction) ProductReadDiagnostics.Outcome.USER_INTERRUPTED else ProductReadDiagnostics.Outcome.WINDOW_INTERRUPTED)
            ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.PAGE_ABORT)
            ProductReadSession.put(ProductScreenEvidence.Result(message = "Bedienung oder Ansichtswechsel erkannt. Seitenprüfung abgebrochen."), SystemClock.elapsedRealtime())
            ProductReadRequest.cancel()
            return
        }
        // A state event can describe a rebuilt subtree inside the same window.
        // Re-traverse it: inspect() still rejects changed ISINs and protected views.
        if (pageReader.anchored && windowEvent) ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.WINDOW_RECHECK)
        if (event.eventType != AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED &&
            event.eventType != AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED) return
        queueRead(400)
    }
    override fun onInterrupt() { PhoneRemote.stop(this,"SERVICE_INTERRUPTED"); GoldSearchRun.stop("SERVICE_INTERRUPTED",Instant.now().toString()); MorningReadRun.stop(this,"SERVICE_INTERRUPTED"); ProductReadRequest.cancel(); handler.removeCallbacks(pendingRead); readQueued = false; ProductReadSession.clear() }
    override fun onDestroy() { PhoneRemote.stop(this,"SERVICE_STOPPED");PhoneRemote.reader=null;PhoneRemote.onStop=null;
        GoldSearchRun.stop("SERVICE_INTERRUPTED",Instant.now().toString())
        MorningReadRun.onStopped=null
        MorningReadRun.stop(this,"SERVICE_INTERRUPTED")
        ProductReadDiagnostics.connected = false
        ProductReadDiagnostics.canRead = false
        ProductReadDiagnostics.windowAccess = false
        PhoneDiagnostics.queue(this)
        releaseScreen()
        if (screenReceiverRegistered) { unregisterReceiver(screenOff); screenReceiverRegistered = false }
        ProductReadRequest.onStarted = null
        ProductReadRequest.onCancelled = null
        pageReader.reset()
        ProductReadRequest.cancel()
        handler.removeCallbacks(pendingRead)
        accessibilityButtonController.unregisterAccessibilityButtonCallback(callback)
        ProductReadSession.clear()
        super.onDestroy()
    }
    /** Never inspect a background window or traverse another app's content. */
    private fun productRoot(record: Boolean): AccessibilityNodeInfo? {
        fun note(outcome: ProductReadDiagnostics.Outcome) { if (record) ProductReadDiagnostics.record(outcome) }
        val direct = rootInActiveWindow
        if (direct != null) {
            note(if (direct.packageName?.toString() == ProductScreenEvidence.PACKAGE)
                ProductReadDiagnostics.Outcome.DIRECT_ROOT else ProductReadDiagnostics.Outcome.OTHER_APP)
            return direct
        }
        note(ProductReadDiagnostics.Outcome.NO_ROOT)
        val visible = windows
        try {
            val index = ProductWindowPolicy.select(visible.map {
                ProductWindowPolicy.Window(it.isActive, it.isFocused, it.type == AccessibilityWindowInfo.TYPE_APPLICATION)
            })
            if (index == null) { note(ProductReadDiagnostics.Outcome.NO_FOCUSED_WINDOW); return null }
            val root = visible[index].root
            if (root == null) { note(ProductReadDiagnostics.Outcome.WINDOW_ROOT_MISSING); return null }
            if (root.packageName?.toString() != ProductScreenEvidence.PACKAGE) {
                note(ProductReadDiagnostics.Outcome.OTHER_APP)
                return root
            }
            note(ProductReadDiagnostics.Outcome.WINDOW_ROOT)
            return root
        } finally { visible.forEach { it.recycle() } }
    }
    private fun readOnce(automatic: Boolean = false) {
        if (!automatic) { ProductReadRequest.cancel(); ProductReadDiagnostics.reset(SystemClock.elapsedRealtime()) }
        if (!getSharedPreferences("product_reader", MODE_PRIVATE).getBoolean("enabled", false)) { ProductReadRequest.cancel(); return }
        if (!(getSystemService(POWER_SERVICE) as PowerManager).isInteractive || (getSystemService(KEYGUARD_SERVICE) as KeyguardManager).isKeyguardLocked) { ProductReadRequest.cancel(); ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.LOCKED); return }
        val result = runCatching {
            val root = productRoot(record = true)
                ?: return@runCatching ProductScreenEvidence.Result(message = "Android liefert gerade keinen Fensterinhalt. Ursache noch ungeklärt; dies beweist keine DEGIRO-Sperre.")
            val scrollNodes = mutableListOf<AccessibilityNodeInfo>()
            val capabilities = mutableListOf<ProductScrollPolicy.Capability>()
            val symbolContainers = mutableListOf<Pair<String, List<Int>>>()
            try {
                // Returning to Bob must not erase the last DEGIRO rejection or draft.
                if (root.packageName?.toString() != ProductScreenEvidence.PACKAGE) {
                    if (pageReader.anchored) {
                        ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.APP_LEFT)
                        ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.PAGE_ABORT)
                        ProductReadSession.put(ProductScreenEvidence.Result(message = "Produkt-App verlassen. Leseprüfung beendet; kein Entwurf übernommen."), SystemClock.elapsedRealtime())
                        ProductReadRequest.cancel()
                    }
                    return
                }
                if (GoldSearchRun.running) { navigateMorning(root, gold=true);return }
                if (MorningReadRun.running) {
                    if (MorningReadRun.expired()) { MorningReadRun.stop(this,"RUN_TIMEOUT");ProductReadRequest.cancel();return }
                    if (!MorningReadRun.reading && navigateMorning(root)) return
                }
                val lines = mutableListOf<QuoteLayout.Line>()
                var sensitive = false
                var count = 0
                fun collect(node: AccessibilityNodeInfo, depth: Int, ancestors: List<Int>) {
                    check(++count <= 1000 && depth <= 40) { "View too large" }
                    if (!node.isVisibleToUser) return
                    if (node.packageName?.toString() != ProductScreenEvidence.PACKAGE) return
                    if (node.isPassword || node.isEditable) { sensitive = true; return }
                    if (android.os.Build.VERSION.SDK_INT >= 34 && node.isAccessibilityDataSensitive) { sensitive = true; return }
                    var containers = ancestors
                    if (node.actionList.any { it.id == AccessibilityNodeInfo.ACTION_SCROLL_FORWARD || it.id == AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD }) {
                        containers = ancestors + scrollNodes.size
                        scrollNodes += AccessibilityNodeInfo.obtain(node)
                        capabilities += ProductScrollPolicy.Capability(
                            node.actionList.any { it.id == AccessibilityNodeInfo.ACTION_SCROLL_FORWARD },
                            node.actionList.any { it.id == AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD }, ancestors)
                    }
                    val bounds = Rect(); node.getBoundsInScreen(bounds)
                    val value = (node.text ?: node.contentDescription)?.toString()?.trim()
                    if (!value.isNullOrEmpty() && !bounds.isEmpty) {
                        check(value.length <= 2000)
                        lines += QuoteLayout.Line(value, bounds.left, bounds.top, bounds.right, bounds.bottom)
                        ProductSymbolMemory.headerSymbol(value)?.let { symbolContainers += it to containers }
                        val evidence = ProductScrollPolicy.evidence(value)
                        for (index in containers) capabilities[index] = capabilities[index].copy(evidence = capabilities[index].evidence or evidence)
                    }
                    for (i in 0 until node.childCount) {
                        val child = node.getChild(i) ?: continue
                        try { collect(child, depth + 1, containers) } finally { child.recycle() }
                    }
                }
                collect(root, 0, emptyList())
                // Reject navigation during traversal; never combine two screens.
                val current = productRoot(record = false)
                val unchanged = current != null && current.windowId == root.windowId &&
                    current.packageName?.toString() == ProductScreenEvidence.PACKAGE
                current?.recycle()
                if (!unchanged) { ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.CHANGED); ProductScreenEvidence.Result(message = "Ansicht wechselte; bitte erneut lesen.") }
                else (if (automatic) {
                    val pairing = ProductSymbolMemory.observe(lines.distinct(), sensitive)
                    if (pairing != null) {
                        val previous = symbolMemory.getString(pairing.symbol, null)
                        if (previous != null || symbolMemory.all.size < 1000) {
                            val merged = ProductSymbolMemory.merge(previous, pairing.isin)
                            symbolMemory.edit().putString(pairing.symbol, merged).apply()
                        }
                    }
                    val identityHint = if (sensitive) null else ProductSymbolMemory.resolve(lines) {
                        symbolMemory.getString(it, null)
                    }
                    // Mark only the exact header's ancestors, never unrelated chart containers.
                    if (identityHint != null) for ((_, containers) in symbolContainers)
                        for (index in containers) capabilities[index] = capabilities[index].copy(evidence = capabilities[index].evidence or 1)

                    // Resolve the product-bearing subtree before considering direction.
                    val surface = ProductScrollPolicy.surface(capabilities)
                    val forwardIndex = ProductScrollPolicy.select(capabilities, true)
                    val backwardIndex = ProductScrollPolicy.select(capabilities, false)
                    if (!sensitive) {
                        ProductReadDiagnostics.record(when {
                            capabilities.isEmpty() -> ProductReadDiagnostics.Outcome.SCROLL_NO_ACTION
                            surface == null -> ProductReadDiagnostics.Outcome.SCROLL_AMBIGUOUS
                            capabilities.size > 1 -> ProductReadDiagnostics.Outcome.SCROLL_PRODUCT_SCOPED
                            else -> ProductReadDiagnostics.Outcome.SCROLL_AVAILABLE
                        })
                    }
                    if (!sensitive && capabilities.size > 1 && surface == null) {
                        ProductReadDiagnostics.record(if (capabilities.all { it.evidence == 0 })
                            ProductReadDiagnostics.Outcome.SCROLL_MARKERS_MISSING
                        else ProductReadDiagnostics.Outcome.SCROLL_MARKERS_CONFLICT)
                    }
                    // An ambiguous surface is not proof of the page end. Never publish a
                    // partial candidate as a completed round trip on that basis.
                    if (MorningReadRun.running && (sensitive || lines.any { Regex("(?i)passwort|login|orderart|ordertyp|order bestätigen").containsMatchIn(it.text) })) {
                        MorningReadRun.stop(this,"PROTECTED_VIEW");ProductReadRequest.cancel();return
                    }
                    if(MorningReadRun.running) {
                        val ids=Regex("\\b[A-Z]{2}[A-Z0-9]{9}[0-9]\\b").findAll(lines.joinToString("\n"){it.text.uppercase()}).map{it.value}.toSet()
                        if(ids.isNotEmpty() && ids!=setOf(MorningReadRun.target)) { finishBatchProduct("IDENTITY_CHANGED");return }
                    }
                    val step = pageReader.inspect(root.windowId, lines.distinct(), Instant.now().toString(), sensitive,
                        forwardIndex != null, backwardIndex != null,
                        scrollAmbiguous = capabilities.size > 1 && surface == null,
                        requireParameters = MorningReadRun.running, identityHint = identityHint)
                    ProductReadDiagnostics.page(step.cause)
                    when (step.move) {
                        ProductPageReader.Move.FORWARD, ProductPageReader.Move.BACKWARD -> {
                            ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.PAGE_SCROLL)
                            val selectedIndex = if (step.move == ProductPageReader.Move.FORWARD) forwardIndex else backwardIndex
                            val scrollNode = selectedIndex?.let { scrollNodes[it] }
                            val action = if (step.move == ProductPageReader.Move.FORWARD) AccessibilityNodeInfo.ACTION_SCROLL_FORWARD else AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD
                            val fresh = productRoot(record = false)
                            val safe = fresh != null && fresh.windowId == root.windowId && fresh.packageName?.toString() == ProductScreenEvidence.PACKAGE
                            fresh?.recycle()
                            if (!safe || scrollNode == null) { ProductReadRequest.cancel(); ProductScreenEvidence.Result(message = "Scrollansicht nicht eindeutig. Prüfung abgebrochen.") }
                            else {
                                if (!scrollNode.performAction(action)) {
                                    ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.SCROLL_REJECTED)
                                    pageReader.scrollFailed(step.move)
                                } else pageReader.scrollSucceeded(step.move)
                                step.result
                            }
                        }
                        ProductPageReader.Move.ABORT -> {
                            ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.PAGE_ABORT)
                            if (MorningReadRun.running) { finishBatchProduct(step.cause.name); return }
                            ProductReadRequest.cancel(); step.result
                        }
                        ProductPageReader.Move.FINISHED -> { ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.PAGE_COMPLETE); step.result }
                        else -> step.result
                    }
                } else ProductScreenEvidence.read(ProductScreenEvidence.PACKAGE, lines.distinct(), Instant.now().toString(), sensitive)).also {
                    ProductReadDiagnostics.rejected(it.reason)
                    ProductReadDiagnostics.record(when {
                        sensitive -> ProductReadDiagnostics.Outcome.PROTECTED_VIEW
                        it.draft.isNotBlank() -> ProductReadDiagnostics.Outcome.DRAFT
                        else -> ProductReadDiagnostics.Outcome.NO_FIELDS
                    })
                }
            } finally { scrollNodes.forEach { it.recycle() }; root.recycle() }
        }.getOrElse { ProductReadRequest.cancel(); ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.ERROR); ProductScreenEvidence.Result(message = "Ansicht nicht sicher lesbar. Nichts übernommen; Screenshot manuell teilen.") }
        ProductReadSession.put(result, SystemClock.elapsedRealtime())
        if (result.draft.isNotBlank()) {
            if (MorningReadRun.running) { finishBatchProduct("READ",result.draft);return }
            ProductReadRequest.cancel()
            if (automatic && !PhoneRemote.active() && getSharedPreferences("product_reader", MODE_PRIVATE).getBoolean("auto_return", true)) {
                runCatching {
                    startActivity(android.content.Intent(android.content.Intent.ACTION_VIEW,
                        android.net.Uri.parse("https://bob-private-scanner.onrender.com/#bob-ocr=" + android.net.Uri.encode(result.draft)))
                        .addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK))
                }.onFailure { Toast.makeText(this, "Automatische Rückgabe nicht möglich. Entwurf bleibt in Bob Handy.", Toast.LENGTH_LONG).show() }
            }
        }
        if (!automatic || result.draft.isNotBlank()) Toast.makeText(this, result.message, Toast.LENGTH_LONG).show()
    }

    private fun finishBatchProduct(code: String, draft: String = "") {
        if (!MorningReadRun.running) return
        runCatching {
            val more=MorningReadRun.outcome(this,code,draft)
            batchTransition=true
            try { ProductReadRequest.cancel() } finally { batchTransition=false }
            if(more) {
                Toast.makeText(this,MorningReadRun.summary(),Toast.LENGTH_SHORT).show()
                ProductReadRequest.start(SystemClock.elapsedRealtime())
            } else MorningReadTransfer.automaticResults(this)
        }.onFailure {
            MorningReadRun.stop(this,"STORAGE_ERROR");ProductReadRequest.cancel()
            Toast.makeText(this,"Leselauf gestoppt. Gespeicherte Ergebnisse bleiben in Bob Handy.",Toast.LENGTH_LONG).show()
        }
    }

    private fun navigationTree(root:AccessibilityNodeInfo,nodes:MutableList<AccessibilityNodeInfo>,descriptions:MutableList<MorningReadPolicy.Node>) {
            fun walk(n: AccessibilityNodeInfo, depth: Int, parent: Int = -1): String {
                check(depth<=30 && nodes.size<500)
                if(!n.isVisibleToUser || n.packageName?.toString()!=ProductScreenEvidence.PACKAGE) return ""
                val sensitiveNode=n.isPassword || (android.os.Build.VERSION.SDK_INT>=34 && n.isAccessibilityDataSensitive)
                val hint=if(sensitiveNode) "" else MorningReadPolicy.inputHint(
                    n.hintText?.toString().orEmpty(),
                    n.text?.toString().orEmpty(),
                    n.isShowingHintText).ifBlank {
                    // Retain only the exact input Bob just wrote, and only while
                    // it still contains that exact query. All page guards run again.
                    if(n.isEditable && n==writtenSearchNode && n.windowId==writtenSearchNode?.windowId &&
                        n.text?.toString()==writtenSearchQuery && writtenSearchQuery.isNotEmpty())
                        "Mit Namen, ISIN oder Symbol suchen" else ""
                }
                val id=n.viewIdResourceName.orEmpty()
                val description=if(sensitiveNode) "" else n.contentDescription?.toString().orEmpty().take(2000)
                val searchInput=n.isEditable && MorningReadPolicy.isSearchInput(id,description,hint)
                val text=if(sensitiveNode || (n.isEditable && !searchInput)) "" else n.text?.toString().orEmpty().ifBlank { description }.take(2000)
                val index=nodes.size;nodes+=AccessibilityNodeInfo.obtain(n)
                descriptions+=MorningReadPolicy.Node(text,id,n.isClickable,n.isEditable,sensitiveNode,description=description,hint=hint,password=n.isPassword,
                    clickAction=n.actionList.any { it.id==AccessibilityNodeInfo.ACTION_CLICK },enabled=n.isEnabled,parent=parent,focused=n.isFocused,
                    focusAction=n.actionList.any { it.id==AccessibilityNodeInfo.ACTION_FOCUS },
                    imeEnter=android.os.Build.VERSION.SDK_INT>=30 && n.isFocused && n.actionList.any { it.id==AccessibilityNodeInfo.AccessibilityAction.ACTION_IME_ENTER.id })
                val children=mutableListOf<String>()
                if(!sensitiveNode && !n.isEditable) for(i in 0 until n.childCount) {
                    val child=n.getChild(i) ?: continue
                    try { children+=walk(child,depth+1,index) } finally { child.recycle() }
                }
                val row=(listOf(text)+children).filter { it.isNotEmpty() }.joinToString("\n").take(4000)
                descriptions[index]=descriptions[index].copy(row=row, containsInput=n.isEditable || descriptions.subList(index+1,descriptions.size).any { it.editable })
                return row
            }
            walk(root,0)
            for(index in SearchInputCluster.identify(descriptions)) {
                ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.SEARCH_INPUT_CLUSTER)
                val n=nodes[index]
                descriptions[index]=descriptions[index].copy(hint="Mit Namen, ISIN oder Symbol suchen",
                    text=n.text?.toString().orEmpty().take(2000))
            }
    }
    /** Product-only remote observation and ONE guarded semantic action. No raw screen upload. */
    private fun remoteRead(command:org.json.JSONObject?):org.json.JSONObject {
        fun observation(code:String)=PhoneRemote.empty(code)
        if(!PhoneRemote.active())return observation("SESSION_EXPIRED")
        if(!getSharedPreferences("product_reader",MODE_PRIVATE).getBoolean("enabled",false))return observation("SERVICE_MISSING")
        if(!(getSystemService(POWER_SERVICE) as PowerManager).isInteractive || (getSystemService(KEYGUARD_SERVICE) as KeyguardManager).isKeyguardLocked)return observation("SCREEN_LOCKED")
        val root=productRoot(true) ?: return observation("NO_ROOT")
        val nodes=mutableListOf<AccessibilityNodeInfo>()
        val descriptions=mutableListOf<MorningReadPolicy.Node>()
        try {
            if(root.packageName?.toString()!=ProductScreenEvidence.PACKAGE)return observation("OTHER_APP")
            navigationTree(root,nodes,descriptions)
            val actionName=command?.optString("action") ?: "inspect"
            val target=command?.optString("isin").orEmpty()
            val proposed=if(actionName=="search_isin") MorningReadPolicy.decide(descriptions,target) { symbolMemory.getString(it,null) }
                else MorningReadPolicy.discoverGold(descriptions)
            val decision=remoteSearchProgress.select(descriptions,proposed,root.windowId,SystemClock.elapsedRealtime())
            if(decision.kind==MorningReadPolicy.Kind.BLOCK) {
                if(decision.code=="PROTECTED_ORDER_CONFIRM") ProductReadDiagnostics.launcher(MorningReadPolicy.launcherSearchIssue(descriptions))
                return observation(decision.code.ifBlank { "PROTECTED_VIEW" })
            }
            val ids=Regex("\\b[A-Z]{2}[A-Z0-9]{9}[0-9]\\b").findAll(descriptions.filterNot { it.editable }.joinToString("\n") { it.text.uppercase() })
                .map { it.value }.filter { SeriesEvidence.validIsin(it) }.distinct().take(12).toList()
            val result=observation(decision.code.ifBlank { decision.kind.name }).put("nodeCount",nodes.size).put("isins",org.json.JSONArray(ids))
            if(descriptions.none { it.editable || it.sensitive }) {
                val lines=nodes.mapNotNull { node ->
                    val bounds=Rect();node.getBoundsInScreen(bounds)
                    val value=(node.text ?: node.contentDescription)?.toString()?.trim().orEmpty()
                    if(value.isBlank() || bounds.isEmpty)null else QuoteLayout.Line(value.take(2000),bounds.left,bounds.top,bounds.right,bounds.bottom)
                }
                val data=ProductScreenEvidence.read(ProductScreenEvidence.PACKAGE,lines,Instant.now().toString(),false)
                result.put("draft",data.draft.take(8000))
            }
            val collected=ProductReadSession.get(SystemClock.elapsedRealtime()).draft
            if(ids.size==1 && collected.contains(ids.single()))result.put("draft",collected.take(8000))
            if(command==null || actionName=="inspect")return result
            if(ProductReadRequest.active(SystemClock.elapsedRealtime()) || MorningReadRun.running || GoldSearchRun.running)return result.put("code","BUSY")
            val current=productRoot(false)
            val safe=current?.windowId==root.windowId && current?.packageName?.toString()==ProductScreenEvidence.PACKAGE
            current?.recycle()
            if(!safe)return result.put("code","VIEW_CHANGED")
            if(actionName=="read_page") {
                if(ids.size!=1 || descriptions.any { it.editable } || MorningReadPolicy.decide(descriptions,ids.single()).kind!=MorningReadPolicy.Kind.READ)return result.put("code","PRODUCT_IDENTITY_REQUIRED")
                ProductReadSession.clear();ProductReadRequest.start(SystemClock.elapsedRealtime())
                return result.put("code","READ_STARTED")
            }
            if(actionName !in setOf("search_gold","search_isin"))return result.put("code","INVALID_ACTION")
            val success=when(decision.kind) {
                MorningReadPolicy.Kind.SEARCH, MorningReadPolicy.Kind.RESULT -> nodes[decision.index].performAction(AccessibilityNodeInfo.ACTION_CLICK)
                MorningReadPolicy.Kind.QUERY -> nodes[decision.index].performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,android.os.Bundle().apply {
                    putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,if(actionName=="search_gold") "Gold" else target)
                })
                MorningReadPolicy.Kind.FOCUS -> focusSearch(nodes[decision.index])
                MorningReadPolicy.Kind.SUBMIT -> submitSearch(nodes[decision.index])
                MorningReadPolicy.Kind.BACK -> performGlobalAction(GLOBAL_ACTION_BACK)
                else -> return result
            }
            if(success && decision.kind==MorningReadPolicy.Kind.QUERY)
                rememberWrittenSearch(nodes[decision.index],if(actionName=="search_gold") "Gold" else target)
            lastNavigation=SystemClock.elapsedRealtime()
            if(decision.kind in setOf(MorningReadPolicy.Kind.SEARCH,MorningReadPolicy.Kind.SUBMIT))remoteSearchProgress.record(decision.index,lastNavigation)
            return result.put("code",if(success) "ACTION_ACCEPTED" else "ACTION_REJECTED")
        } finally { nodes.forEach { it.recycle() };root.recycle() }
    }

    /** Local-only fallback. No caller-supplied coordinates and no result/order taps. */
    private fun tapRecognizedSearch(expectedWindow: Int): Boolean {
        if(!PhoneRemote.active() || !ProductReadRequest.active(SystemClock.elapsedRealtime())) return false
        if(!(getSystemService(POWER_SERVICE) as PowerManager).isInteractive ||
            (getSystemService(KEYGUARD_SERVICE) as KeyguardManager).isKeyguardLocked) return false
        // Refuse magnification and touch exploration rather than guessing transformed coordinates.
        if(magnificationController.scale != 1f ||
            (getSystemService(ACCESSIBILITY_SERVICE) as android.view.accessibility.AccessibilityManager).isTouchExplorationEnabled) return false
        val root=rootInActiveWindow ?: return false
        val live=mutableListOf<AccessibilityNodeInfo>()
        val descriptions=mutableListOf<MorningReadPolicy.Node>()
        try {
            if(root.windowId!=expectedWindow || root.packageName?.toString()!=ProductScreenEvidence.PACKAGE) return false
            navigationTree(root,live,descriptions)
            val action=MorningReadPolicy.discoverGold(descriptions)
            if(action.kind!=MorningReadPolicy.Kind.SEARCH) return false
            val target=live[action.index]
            if(!target.isVisibleToUser || !target.isEnabled || target.isEditable || target.isPassword) return false
            val bounds=Rect();target.getBoundsInScreen(bounds)
            val screen=Rect();root.getBoundsInScreen(screen)
            val point=SearchTapPolicy.center(
                SearchTapPolicy.Box(bounds.left,bounds.top,bounds.right,bounds.bottom),
                SearchTapPolicy.Box(screen.left,screen.top,screen.right,screen.bottom)) ?: return false
            val currentWindows=windows
            try {
                val app=currentWindows.singleOrNull { it.id==expectedWindow && it.isActive && it.isFocused &&
                    it.type==AccessibilityWindowInfo.TYPE_APPLICATION } ?: return false
                if(android.os.Build.VERSION.SDK_INT>=30 && app.displayId!=android.view.Display.DEFAULT_DISPLAY) return false
                if(currentWindows.any { window ->
                    val rect=Rect();window.getBoundsInScreen(rect)
                    window.id!=app.id && window.layer>=app.layer && rect.contains(point.first,point.second)
                }) return false
            } finally { currentWindows.forEach { it.recycle() } }
            if(!target.refresh()) return false
            val refreshed=Rect();target.getBoundsInScreen(refreshed)
            if(refreshed!=bounds || !PhoneRemote.active() || !ProductReadRequest.active(SystemClock.elapsedRealtime())) return false
            val foreground=rootInActiveWindow
            val same=foreground?.windowId==expectedWindow && foreground?.packageName?.toString()==ProductScreenEvidence.PACKAGE
            foreground?.recycle()
            if(!same) return false
            val path=android.graphics.Path().apply { moveTo(point.first.toFloat(),point.second.toFloat()) }
            val gesture=android.accessibilityservice.GestureDescription.Builder().addStroke(
                android.accessibilityservice.GestureDescription.StrokeDescription(path,0,60)).build()
            lastNavigation=SystemClock.elapsedRealtime()
            val accepted=dispatchGesture(gesture,object: GestureResultCallback() {
                override fun onCompleted(gestureDescription: android.accessibilityservice.GestureDescription?) {
                    ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.SEARCH_TAP_COMPLETED)
                    if(ProductReadRequest.active(SystemClock.elapsedRealtime())) queueRead(400)
                }
                override fun onCancelled(gestureDescription: android.accessibilityservice.GestureDescription?) {
                    ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.SEARCH_TAP_CANCELLED)
                }
            },handler)
            if(accepted) ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.SEARCH_TAP_SENT)
            return accepted
        } finally { live.forEach { it.recycle() };root.recycle() }
    }

    private fun focusSearch(node: AccessibilityNodeInfo): Boolean =
        node.isEditable && node.isEnabled && !node.isPassword &&
            node.actionList.any { it.id==AccessibilityNodeInfo.ACTION_FOCUS } &&
            node.performAction(AccessibilityNodeInfo.ACTION_FOCUS).also { accepted ->
                ProductReadDiagnostics.record(if(accepted) ProductReadDiagnostics.Outcome.SEARCH_FOCUS_ACCEPTED else ProductReadDiagnostics.Outcome.SEARCH_FOCUS_REJECTED)
            }

    private fun submitSearch(node: AccessibilityNodeInfo): Boolean =
        android.os.Build.VERSION.SDK_INT>=30 && node.isEditable && node.isFocused &&
            node.actionList.any { it.id==AccessibilityNodeInfo.AccessibilityAction.ACTION_IME_ENTER.id } &&
            node.performAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_IME_ENTER.id)

    /** Search actions use semantic nodes only, never coordinates or order buttons. */
    private fun navigateMorning(root: AccessibilityNodeInfo, gold: Boolean = false): Boolean {
        val nodes=mutableListOf<AccessibilityNodeInfo>()
        val descriptions=mutableListOf<MorningReadPolicy.Node>()
        try {
            navigationTree(root,nodes,descriptions)
            val proposed=if(gold) MorningReadPolicy.discoverGold(descriptions) else MorningReadPolicy.decide(descriptions,MorningReadRun.target) {
                symbolMemory.getString(it, null)
            }
            val action=automaticSearchProgress.select(descriptions,proposed,root.windowId,SystemClock.elapsedRealtime())
            fun record(code:String) {
                if(gold) { GoldSearchRun.event(code,Instant.now().toString());PhoneDiagnostics.queue(this) }
                else MorningReadRun.event(this,code)
            }
            when(action.kind) {
                MorningReadPolicy.Kind.BLOCK -> {
                    if(action.code=="PROTECTED_ORDER_CONFIRM") ProductReadDiagnostics.launcher(MorningReadPolicy.launcherSearchIssue(descriptions))
                    if(gold) { lastNavigationIssue=action.code;record(action.code) }
                    else MorningReadRun.stop(this,action.code)
                    ProductReadRequest.cancel()
                }
                MorningReadPolicy.Kind.COLLECT -> {
                    check(gold && GoldSearchRun.running)
                    MorningReadRun.beginDiscovered(this,action.isins)
                    GoldSearchRun.clear()
                    ProductReadRequest.start(SystemClock.elapsedRealtime())
                    PhoneDiagnostics.queue(this)
                }
                MorningReadPolicy.Kind.READ -> { lastNavigationIssue="";MorningReadRun.reading=true; return false }
                MorningReadPolicy.Kind.WAIT -> {
                    if(action.code=="SEARCH_NO_PROGRESS" && !searchTapAttempted) {
                        searchTapAttempted=true
                        if(!tapRecognizedSearch(root.windowId)) ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.SEARCH_TAP_REJECTED)
                    }
                    if(lastNavigationIssue!=action.code) record(action.code)
                    lastNavigationIssue=action.code
                }
                MorningReadPolicy.Kind.BACK -> {
                    if(gold) { lastNavigationIssue="SEARCH_MISSING";ProductReadRequest.cancel() }
                    else if(++MorningReadRun.backSteps>4) finishBatchProduct("SEARCH_MISSING")
                    else performGlobalAction(GLOBAL_ACTION_BACK)
                }
                else -> {
                    val current=productRoot(false)
                    val safe=current?.windowId==root.windowId && current?.packageName?.toString()==ProductScreenEvidence.PACKAGE
                    current?.recycle()
                    if(!safe) return true
                    val node=nodes[action.index]
                    lastNavigation=SystemClock.elapsedRealtime()
                    val success=if(action.kind==MorningReadPolicy.Kind.QUERY) {
                        val args=android.os.Bundle().apply { putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,if(gold) "Gold" else MorningReadRun.target) }
                        node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,args)
                    } else if(action.kind==MorningReadPolicy.Kind.FOCUS) focusSearch(node)
                    else if(action.kind==MorningReadPolicy.Kind.SUBMIT) submitSearch(node)
                    else node.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                    if(success && action.kind==MorningReadPolicy.Kind.QUERY)
                        rememberWrittenSearch(node,if(gold) "Gold" else MorningReadRun.target)
                    if(action.kind in setOf(MorningReadPolicy.Kind.SEARCH,MorningReadPolicy.Kind.SUBMIT))automaticSearchProgress.record(action.index,lastNavigation)
                    if(!success) {
                        lastNavigationIssue="NAVIGATION_REJECTED"
                        record(lastNavigationIssue)
                    }
                }
            }
            return true
        } finally { nodes.forEach { it.recycle() } }
    }
}

