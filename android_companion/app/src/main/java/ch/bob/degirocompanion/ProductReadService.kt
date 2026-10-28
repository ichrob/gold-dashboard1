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
    private var batchTransition = false
    private var lastNavigation = 0L
    private var lastNavigationIssue = ""
    private val pageReader = ProductPageReader()
    private val handler = Handler(Looper.getMainLooper())
    private var screenReceiverRegistered = false
    private val screenOff = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if(intent?.action == Intent.ACTION_USER_PRESENT) {
                handler.postDelayed({ runCatching { MorningReadTransfer.automaticResults(this@ProductReadService) } },1000)
                return
            }
            if (intent?.action != Intent.ACTION_SCREEN_OFF || !ProductReadRequest.active(SystemClock.elapsedRealtime())) return
            MorningReadRun.stop(this@ProductReadService,"SCREEN_LOCKED")
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
        }
        ProductReadRequest.onStarted = {
            lastNavigationIssue=""
            pageReader.reset()
            handler.removeCallbacks(pendingRead)
            readQueued = false
            keepScreenForRequest()
            queueRead(600)
        }
        keepScreenForRequest()
        queueRead(600)
    }
    // Only package/type metadata is used. Never read or retain event text.
    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (!ProductReadRequest.active(SystemClock.elapsedRealtime())) return
        if(MorningReadRun.running && event?.eventType==AccessibilityEvent.TYPE_TOUCH_INTERACTION_START) {
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
    override fun onInterrupt() { ProductReadRequest.cancel(); handler.removeCallbacks(pendingRead); readQueued = false; ProductReadSession.clear() }
    override fun onDestroy() {
        MorningReadRun.onStopped=null
        MorningReadRun.stop(this,"SERVICE_INTERRUPTED")
        ProductReadDiagnostics.connected = false
        ProductReadDiagnostics.canRead = false
        ProductReadDiagnostics.windowAccess = false
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
                        requireParameters = MorningReadRun.running)
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
            if (automatic && getSharedPreferences("product_reader", MODE_PRIVATE).getBoolean("auto_return", true)) {
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

    /** Search actions use semantic nodes only, never coordinates or order buttons. */
    private fun navigateMorning(root: AccessibilityNodeInfo): Boolean {
        val nodes=mutableListOf<AccessibilityNodeInfo>()
        val descriptions=mutableListOf<MorningReadPolicy.Node>()
        try {
            fun walk(n: AccessibilityNodeInfo, depth: Int): String {
                check(depth<=30 && nodes.size<500)
                if(!n.isVisibleToUser || n.packageName?.toString()!=ProductScreenEvidence.PACKAGE) return ""
                val sensitiveNode=n.isPassword || (android.os.Build.VERSION.SDK_INT>=34 && n.isAccessibilityDataSensitive)
                val hint=n.hintText?.toString().orEmpty()
                var id=n.viewIdResourceName.orEmpty()
                if(Regex("(?i)suche|suchen|search").containsMatchIn(hint)) id+="/search"
                val searchInput=n.isEditable && Regex("(?i)search").containsMatchIn(id)
                val text=if(sensitiveNode || (n.isEditable && !searchInput)) "" else (n.text ?: n.contentDescription)?.toString().orEmpty().take(2000)
                val index=nodes.size;nodes+=AccessibilityNodeInfo.obtain(n)
                descriptions+=MorningReadPolicy.Node(text,id,n.isClickable,n.isEditable,sensitiveNode)
                val children=mutableListOf<String>()
                if(!sensitiveNode && !n.isEditable) for(i in 0 until n.childCount) {
                    val child=n.getChild(i) ?: continue
                    try { children+=walk(child,depth+1) } finally { child.recycle() }
                }
                val row=(listOf(text)+children).filter { it.isNotEmpty() }.joinToString("\n").take(4000)
                descriptions[index]=descriptions[index].copy(row=row, containsInput=n.isEditable || descriptions.subList(index+1,descriptions.size).any { it.editable })
                return row
            }
            walk(root,0)
            val action=MorningReadPolicy.decide(descriptions,MorningReadRun.target)
            when(action.kind) {
                MorningReadPolicy.Kind.BLOCK -> { MorningReadRun.stop(this,action.code);ProductReadRequest.cancel() }
                MorningReadPolicy.Kind.READ -> { lastNavigationIssue="";MorningReadRun.reading=true; return false }
                MorningReadPolicy.Kind.WAIT -> {
                    if(lastNavigationIssue!=action.code) MorningReadRun.event(this,action.code)
                    lastNavigationIssue=action.code
                }
                MorningReadPolicy.Kind.BACK -> {
                    if(++MorningReadRun.backSteps>4) finishBatchProduct("SEARCH_MISSING")
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
                        val args=android.os.Bundle().apply { putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,MorningReadRun.target) }
                        node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,args)
                    } else node.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                    if(!success) MorningReadRun.event(this,"NAVIGATION_REJECTED")
                }
            }
            return true
        } finally { nodes.forEach { it.recycle() } }
    }
}
