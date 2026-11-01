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
    private var resultTapAttempted = false
    private var inputTapAttempted = false
    private var categorySteps = 0
    private var listGeneration = 0
    private var listBusy = false
    private var listScrolled = false
    private var listScrollTries = 0
    private var listFirstIds = emptyList<String>()
    private val listSeenIds = mutableSetOf<String>()
    private var listCropTop: Int? = null
    private var listWindowId: Int? = null
    private val listImages = org.json.JSONArray()
    private var listBatch = ""
    private var listResumeChecked = false
    private var listTopSeekSteps = 0
    private fun resetListCapture() {
        listGeneration++; listResumeChecked=false; listTopSeekSteps=0; listBusy=false; listScrolled=false; listScrollTries=0
        listFirstIds=emptyList(); listSeenIds.clear(); listCropTop=null; listWindowId=null; while(listImages.length()>0) listImages.remove(0)
        listBatch=java.util.UUID.randomUUID().toString().replace("-","")
    }
    private var batchTransition = false
    private var lastNavigation = 0L
    private var lastNavigationIssue = ""
    private val pageReader = ProductPageReader()
    private var batchReadWindow: Int? = null
    private var batchResultOpened = false
    private val productReturnTransition = ProductReturnTransition()
    private val remoteSearchProgress = SearchClickProgress()
    private val automaticSearchProgress = SearchClickProgress()
    private val handler = Handler(Looper.getMainLooper())
    private val pinProbeTick = object : Runnable {
        override fun run() {
            if (!PinReadinessProbe.active()) return
            if (!(getSystemService(POWER_SERVICE) as PowerManager).isInteractive ||
                (getSystemService(KEYGUARD_SERVICE) as KeyguardManager).isKeyguardLocked) {
                PinReadinessProbe.stop("Bildschirm gesperrt. PIN-Test beendet.", PinKeypadExerciseTrace.Reason.SCREEN_LOCKED); return
            }
            if (!getSharedPreferences("product_reader", MODE_PRIVATE).getBoolean("enabled", false)) {
                PinReadinessProbe.stop("Lesefreigabe beendet. PIN-Test beendet.", PinKeypadExerciseTrace.Reason.ACCESS_DISABLED); return
            }
            runCatching {
                if (!PinReadinessProbe.inspectLoginDialogs(this@ProductReadService)) {
                    val root = productRoot(record = false)
                    try { PinReadinessProbe.inspect(root) } finally { root?.recycle() }
                }
            }.onFailure { PinReadinessProbe.stop("Ansicht nicht zugänglich. PIN-Test beendet.", PinKeypadExerciseTrace.Reason.EXCEPTION) }
            if (PinReadinessProbe.running) handler.postDelayed(this, 1000)
        }
    }
    private var screenReceiverRegistered = false
    private val screenOff = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if(intent?.action == Intent.ACTION_USER_PRESENT) {
                handler.postDelayed({ runCatching { MorningReadTransfer.automaticResults(this@ProductReadService) } },1000)
                return
            }
            if(intent?.action==Intent.ACTION_SCREEN_OFF && PinReadinessProbe.running) PinReadinessProbe.stop("Bildschirm ausgeschaltet. PIN-Test beendet.", PinKeypadExerciseTrace.Reason.SCREEN_LOCKED)
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
        override fun onClicked(controller: AccessibilityButtonController) { if(!PinReadinessProbe.running) readOnce() }
    }
    private fun localLoginEventScope(active: Boolean) {
        // System event metadata is needed only for cancellation/user-interruption in the explicit local run.
        val info = serviceInfo
        info.packageNames = if (active) arrayOf(ProductScreenEvidence.PACKAGE,
            "com.android.systemui", "com.samsung.android.biometrics.app.setting")
            else arrayOf(ProductScreenEvidence.PACKAGE)
        serviceInfo = info
    }
    override fun onServiceConnected() {
        PinReadinessProbe.onLoginTouch = { node, bounds, window, completed -> dispatchLocalPinTouch(node, bounds, window, completed) }
        PinReadinessProbe.onDigitTouch = { node, bounds, window, completed -> dispatchPinTestZero(node, bounds, window, completed) }
        PinReadinessProbe.onDeleteTouch = { node, bounds, window, completed -> dispatchPinTestDelete(node, bounds, window, completed) }
        PinReadinessProbe.onStop = {
            // Consume the one-start intent on EVERY termination, including
            // failure and user STOP. Only verified Markets can continue.
            val proceed = LoginToReadHandoff.consume(PinReadinessProbe.resultCode, SystemClock.elapsedRealtime())
            runCatching { localLoginEventScope(false) }
            handler.removeCallbacks(pinProbeTick)
            PhoneDiagnostics.recordPinProbe(this)
            if (proceed) handler.post {
                runCatching {
                    check(!PinReadinessProbe.running && !PhoneRemote.active() &&
                        !GoldSearchRun.running && !MorningReadRun.running &&
                        !ProductReadRequest.active(SystemClock.elapsedRealtime()))
                    check(getSharedPreferences("product_reader", MODE_PRIVATE).getBoolean("enabled", false))
                    check((getSystemService(POWER_SERVICE) as PowerManager).isInteractive &&
                        !(getSystemService(KEYGUARD_SERVICE) as KeyguardManager).isKeyguardLocked)
                    // The previous tick verified an authenticated DEGIRO Markets
                    // screen. Recheck app ownership before starting any read.
                    val root = rootInActiveWindow ?: error("DEGIRO nicht mehr im Vordergrund.")
                    try { check(root.packageName?.toString() == ProductScreenEvidence.PACKAGE) }
                    finally { root.recycle() }
                    PhoneRemote.start(this)
                    GoldSearchRun.start()
                    ProductReadRequest.start(SystemClock.elapsedRealtime())
                    PhoneDiagnostics.queue(this)
                }.onFailure {
                    PhoneRemote.stop(this,"START_FAILED")
                    GoldSearchRun.stop("START_FAILED",Instant.now().toString())
                    ProductReadRequest.cancel()
                    PhoneDiagnostics.queue(this)
                }
            }
        }
        PinReadinessProbe.onTimeout = {
            // Return only from the app explicitly opened for this test, never another foreground app.
            val unlocked = (getSystemService(POWER_SERVICE) as PowerManager).isInteractive &&
                !(getSystemService(KEYGUARD_SERVICE) as KeyguardManager).isKeyguardLocked
            if (unlocked) runCatching {
                val foreground = rootInActiveWindow
                val inDegiro = try { foreground?.packageName?.toString() == ProductScreenEvidence.PACKAGE }
                    finally { foreground?.recycle() }
                if (inDegiro) startActivity(Intent(this, ProductReadActivity::class.java)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP))
            }
        }
        PinReadinessProbe.onStart = {
            handler.removeCallbacks(pinProbeTick)
            if (runCatching { localLoginEventScope(PinReadinessProbe.localLoginActive) }.isSuccess)
                handler.postDelayed(pinProbeTick, 700)
            else PinReadinessProbe.stop("Dialogfreigabe nicht verfügbar. Lokale Anmeldung beendet.")
        }
        PhoneRemote.reader={command -> remoteRead(command)}
        MorningListDelivery.onConfirmed={ plan, batch ->
            if(plan.isNotEmpty() && PhoneRemote.active()) {
                MorningReadRun.beginDiscovered(this,plan.map { it.isin },batch,
                    plan.associate { it.isin to it.missingFields })
                ProductReadRequest.start(SystemClock.elapsedRealtime())
            } else PhoneRemote.stop(this,"COMPLETE")
        }
        PhoneRemote.onStop={ code ->
            if(PinReadinessProbe.running) PinReadinessProbe.stop("PIN-Test gestoppt.")
            MorningListDelivery.cancel()
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
            resetListCapture()
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
                else MorningReadRun.stop(this, lastNavigationIssue.ifEmpty { "STOPPED" })
            }
            PhoneDiagnostics.queue(this)
        }
        ProductReadRequest.onStarted = {
            batchReadWindow = null
            batchResultOpened = false
            if(PinReadinessProbe.running) PinReadinessProbe.stop("Produktprüfung gestartet. PIN-Test beendet.")
            resetListCapture()
            clearWrittenSearch()
            searchTapAttempted = false
            inputTapAttempted = false
            resultTapAttempted = false
            categorySteps = 0
            automaticSearchProgress.clear()
            lastNavigationIssue=""
            pageReader.reset()
            handler.removeCallbacks(pendingRead)
            readQueued = false
            keepScreenForRequest()
            if(GoldSearchRun.running && MorningListDelivery.resume(this)) {
                GoldSearchRun.stop("LIST_IMAGES_DELIVERED",Instant.now().toString())
                ProductReadRequest.cancel()
            } else {
                queueRead(600)
            }
        }
        keepScreenForRequest()
        queueRead(600)
        PhoneDiagnostics.queue(this)
    }
    // Only package/type metadata is used. Never read or retain event text.
    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (PinReadinessProbe.running) {
            if (PinReadinessProbe.loginArmed && event?.eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) {
                PinReadinessProbe.loginWindowChanged(); return
            }
            if (PinReadinessProbe.exerciseArmed && event?.eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) {
                PinReadinessProbe.stop("Fensterwechsel erkannt. Bedienungstest beendet; Eingabe selbst prüfen.", PinKeypadExerciseTrace.Reason.WINDOW_EVENT)
                return
            }
            if ((PinReadinessProbe.exerciseArmed || PinReadinessProbe.localLoginActive) && event?.eventType == AccessibilityEvent.TYPE_TOUCH_INTERACTION_START) {
                PinReadinessProbe.stop("Berührung erkannt. Bedienungstest beendet; eventuell verbliebene Testziffer selbst löschen.", PinKeypadExerciseTrace.Reason.USER_TOUCH)
                return
            }
            if (event?.eventType == AccessibilityEvent.TYPE_VIEW_TEXT_CHANGED &&
                event.packageName?.toString() == ProductScreenEvidence.PACKAGE) {
                if (!PinReadinessProbe.exerciseArmed && !PinReadinessProbe.loginArmed)
                    PinReadinessProbe.stop("Eingabeänderung erkannt. PIN-Test beendet; kein Eingabetext gelesen.")
            }
            return
        }
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
    override fun onInterrupt() { LoginToReadHandoff.clear(); if(PinReadinessProbe.running) PinReadinessProbe.stop("Lesedienst unterbrochen. PIN-Test beendet.", PinKeypadExerciseTrace.Reason.SERVICE_STOPPED); PhoneRemote.stop(this,"SERVICE_INTERRUPTED"); GoldSearchRun.stop("SERVICE_INTERRUPTED",Instant.now().toString()); MorningReadRun.stop(this,"SERVICE_INTERRUPTED"); ProductReadRequest.cancel(); handler.removeCallbacks(pendingRead); readQueued = false; ProductReadSession.clear() }
    override fun onDestroy() { LoginToReadHandoff.clear(); if(PinReadinessProbe.running) PinReadinessProbe.stop("Lesedienst beendet. PIN-Test beendet.", PinKeypadExerciseTrace.Reason.SERVICE_STOPPED);PinReadinessProbe.onStart=null;PinReadinessProbe.onLoginTouch=null;PinReadinessProbe.onDigitTouch=null;PinReadinessProbe.onDeleteTouch=null;PinReadinessProbe.onStop=null;PinReadinessProbe.onTimeout=null;handler.removeCallbacks(pinProbeTick); MorningListDelivery.onConfirmed=null;PhoneRemote.stop(this,"SERVICE_STOPPED");PhoneRemote.reader=null;PhoneRemote.onStop=null;
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
        // WebView scrolls can leave cached offscreen nodes marked visible. Re-read the
        // tree before detail navigation; never use a failed refresh to authorize a tap.
        if(record && MorningReadRun.importedListRun() && !MorningReadRun.reading && android.os.Build.VERSION.SDK_INT>=33) {
            val refreshed=runCatching { clearCache() }.getOrDefault(false)
            ProductReadDiagnostics.record(if(refreshed) ProductReadDiagnostics.Outcome.NAVIGATION_CACHE_CLEARED
                else ProductReadDiagnostics.Outcome.NAVIGATION_CACHE_FAILED)
            if(!refreshed)return null
        }
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
                        ProductSymbolMemory.probeHeaderSymbol(value)?.let { symbolContainers += it to containers }
                        val evidence = ProductScrollPolicy.evidence(value)
                        for (index in containers) capabilities[index] = capabilities[index].copy(evidence = capabilities[index].evidence or evidence)
                    }
                    for (i in 0 until node.childCount) {
                        val child = node.getChild(i) ?: continue
                        try { collect(child, depth + 1, containers) } finally { child.recycle() }
                    }
                }
                collect(root, 0, emptyList())
                val detailNodes=mutableListOf<AccessibilityNodeInfo>()
                val detailView=mutableListOf<MorningReadPolicy.Node>()
                try {
                    navigationTree(root,detailNodes,detailView)
                    val target=if(MorningReadRun.running) MorningReadRun.target else
                        Regex("\\b[A-Z]{2}[A-Z0-9]{9}[0-9]\\b").findAll(lines.joinToString("\n") { it.text.uppercase() })
                            .map { it.value }.toSet().singleOrNull().orEmpty()
                    val readable=MorningReadPolicy.detailReadLines(detailView,lines,target,
                        MorningReadRun.running && MorningReadRun.reading && pageReader.sameWindow(root.windowId),
                        symbolProbe=MorningReadRun.importedListRun())
                    if(readable !== lines) { lines.clear();lines.addAll(readable) }
                } finally { detailNodes.forEach { it.recycle() } }
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
                    if (identityHint != null || (MorningReadRun.importedListRun() && !sensitive &&
                        ProductSymbolMemory.detailSymbol(lines.map { it.text })!=null)) for ((_, containers) in symbolContainers)
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
                    val previousReadWindow = pageReader.sameWindow(root.windowId)
                    val step = pageReader.inspect(root.windowId, lines.distinct(), Instant.now().toString(), sensitive,
                        forwardIndex != null, backwardIndex != null,
                        scrollAmbiguous = capabilities.size > 1 && surface == null,
                        requireParameters = MorningReadRun.running, identityHint = identityHint,
                        allowSymbolProbe = MorningReadRun.importedListRun(),
                        requestedTermsOnly = MorningReadRun.requestedTermsOnly(),
                        seekLeverage = MorningReadRun.requestedLeverage(),
                        expectedIsin = if (MorningReadRun.running) MorningReadRun.target else null)
                    // Move.FINISHED resets ProductPageReader's anchor. Retain
                    // this verified product window before the next request,
                    // otherwise the guarded BACK cannot leave the completed
                    // detail and the new target sees a stale order launcher.
                    val validFinishedRead = step.move == ProductPageReader.Move.FINISHED
                    batchReadWindow = if (ProductBatchReadWindow.keep(
                            previousReadWindow,pageReader.sameWindow(root.windowId),
                            validFinishedRead,step.result.draft,MorningReadRun.target,
                            sensitive,step.cause in setOf(
                                ProductPageReader.Cause.UNSAFE_VIEW,
                                ProductPageReader.Cause.IDENTITY_CHANGED))) root.windowId else null
                    ProductReadDiagnostics.page(step.cause)
                    ProductReadDiagnostics.rejected(step.result.reason)
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
            val priorTarget=MorningReadRun.target
            val priorWindow=batchReadWindow
            val more=MorningReadRun.outcome(this,code,draft)
            var returnAcknowledged=false
            if (more) {
                val root=productRoot(record=false)
                if (root!=null) {
                    val refs=mutableListOf<AccessibilityNodeInfo>()
                    val view=mutableListOf<MorningReadPolicy.Node>()
                    try {
                        navigationTree(root,refs,view)
                        if (MorningReadPolicy.returnAfterRead(view,priorTarget,root.windowId,priorWindow,code) &&
                            performGlobalAction(GLOBAL_ACTION_BACK))
                            {
                                productReturnTransition.begin(priorTarget,root.windowId,SystemClock.elapsedRealtime())
                                returnAcknowledged=true
                            }
                    } finally { refs.forEach { it.recycle() };root.recycle() }
                }
            }
            batchTransition=true
            try { ProductReadRequest.cancel() } finally { batchTransition=false }
            if(more) {
                // A failed/unsafe BACK must never open the following ISIN from
                // the previous product's detail or an unverified order surface.
                if(!returnAcknowledged) {
                    MorningReadRun.stop(this,"RETURN_NOT_CONFIRMED")
                    ProductReadRequest.cancel()
                    return
                }
                Toast.makeText(this,MorningReadRun.summary(),Toast.LENGTH_SHORT).show()
                ProductReadRequest.start(SystemClock.elapsedRealtime())
            } else {
                productReturnTransition.clear()
                PhoneRemote.stop(this,"COMPLETE")
                MorningReadTransfer.automaticResults(this)
            }
        }.onFailure {
            MorningReadRun.stop(this,"STORAGE_ERROR");ProductReadRequest.cancel()
            Toast.makeText(this,"Leselauf gestoppt. Gespeicherte Ergebnisse bleiben in Bob Handy.",Toast.LENGTH_LONG).show()
        }
    }

    private fun navigationTree(root:AccessibilityNodeInfo,nodes:MutableList<AccessibilityNodeInfo>,descriptions:MutableList<MorningReadPolicy.Node>) {
            fun walk(n: AccessibilityNodeInfo, depth: Int, parent: Int = -1, insideInput: Boolean = false): String {
                check(depth<=30 && nodes.size<500)
                if(!n.isVisibleToUser || n.packageName?.toString()!=ProductScreenEvidence.PACKAGE) return ""
                val sensitiveNode=n.isPassword || (android.os.Build.VERSION.SDK_INT>=34 && n.isAccessibilityDataSensitive)
                if(!sensitiveNode) {
                    if(n.isEditable) {
                        ProductReadDiagnostics.searchShape(ProductReadDiagnostics.SearchSource.INPUT_TEXT,n.text?.toString().orEmpty())
                        ProductReadDiagnostics.searchShape(ProductReadDiagnostics.SearchSource.INPUT_HINT,n.hintText?.toString().orEmpty())
                        ProductReadDiagnostics.searchShape(ProductReadDiagnostics.SearchSource.INPUT_DESCRIPTION,n.contentDescription?.toString().orEmpty())
                        ProductReadDiagnostics.searchShape(ProductReadDiagnostics.SearchSource.INPUT_ID,n.viewIdResourceName.orEmpty())
                    } else ProductReadDiagnostics.searchShape(ProductReadDiagnostics.SearchSource.PAGE_LABEL,
                        listOf(n.text,n.hintText,n.contentDescription).joinToString(" "))
                }
                val writtenQueryExpected=n.isEditable && writtenSearchQuery.isNotEmpty()
                val writtenQueryPresent=writtenQueryExpected && n.text?.toString()==writtenSearchQuery
                val writtenNodeIdentity=writtenQueryPresent && n==writtenSearchNode &&
                    n.windowId==writtenSearchNode?.windowId
                val hint=if(sensitiveNode) "" else MorningReadPolicy.inputHint(
                    n.hintText?.toString().orEmpty(),
                    n.text?.toString().orEmpty(),
                    n.isShowingHintText).ifBlank {
                    // Retain only the exact input Bob just wrote, and only while
                    // it still contains that exact query. All page guards run again.
                    if(writtenNodeIdentity) "Mit Namen, ISIN oder Symbol suchen" else ""
                }
                val id=if(writtenNodeIdentity) "bob:search_input" else n.viewIdResourceName.orEmpty()
                val description=if(sensitiveNode) "" else n.contentDescription?.toString().orEmpty().take(2000)
                val searchInput=n.isEditable && MorningReadPolicy.isSearchInput(id,description,hint)
                val explicitPrompt=SearchInputCluster.explicitPrompt(n.text?.toString().orEmpty())
                val text=if(sensitiveNode || (insideInput && !explicitPrompt) || (n.isEditable && !searchInput && !explicitPrompt)) "" else n.text?.toString().orEmpty().ifBlank { description }.take(2000)
                val index=nodes.size;nodes+=AccessibilityNodeInfo.obtain(n)
                descriptions+=MorningReadPolicy.Node(text,id,n.isClickable,n.isEditable,sensitiveNode,description=description,hint=hint,password=n.isPassword,
                    clickAction=n.actionList.any { it.id==AccessibilityNodeInfo.ACTION_CLICK },enabled=n.isEnabled,parent=parent,focused=n.isFocused,
                    focusAction=n.actionList.any { it.id==AccessibilityNodeInfo.ACTION_FOCUS },
                    imeEnter=android.os.Build.VERSION.SDK_INT>=30 && n.isFocused && n.actionList.any { it.id==AccessibilityNodeInfo.AccessibilityAction.ACTION_IME_ENTER.id },
                    writtenQueryExpected=writtenQueryExpected,writtenQueryPresent=writtenQueryPresent,
                    writtenNodeIdentity=writtenNodeIdentity,selected=n.isSelected || n.isChecked,
                    scrollRight=n.actionList.any { it.id==AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_RIGHT.id } ||
                        (n.className?.toString()=="android.widget.HorizontalScrollView" && n.actionList.any { it.id==AccessibilityNodeInfo.ACTION_SCROLL_FORWARD }))
                val children=mutableListOf<String>()
                // Some input wrappers expose their placeholder in a child.
                // Retain only the fixed product prompt from text below an input.
                if(!sensitiveNode) for(i in 0 until n.childCount) {
                    val child=n.getChild(i) ?: continue
                    try { children+=walk(child,depth+1,index,insideInput || n.isEditable) } finally { child.recycle() }
                }
                val row=(listOf(text)+children).filter { it.isNotEmpty() }.joinToString("\n").take(4000)
                descriptions[index]=descriptions[index].copy(row=row, containsInput=n.isEditable || descriptions.subList(index+1,descriptions.size).any { it.editable })
                return row
            }
            walk(root,0)
            fun box(n:AccessibilityNodeInfo):SearchInputCluster.Box {
                val r=android.graphics.Rect();n.getBoundsInScreen(r)
                return SearchInputCluster.Box(r.left,r.top,r.right,r.bottom)
            }
            // Count only identities whose complete label fits between the sticky
            // category strip and the bottom navigation, not clipped last rows.
            val rootBounds=Rect();root.getBoundsInScreen(rootBounds)
            fun bounds(i:Int)=Rect().also { nodes[i].getBoundsInScreen(it) }
            val top=descriptions.indices.filter { descriptions[it].text.trim().equals("Hebelprodukte",true) }
                .maxOfOrNull { bounds(it).bottom } ?: rootBounds.top
            val bottom=descriptions.indices.filter { descriptions[it].text.trim() in setOf("Märkte","Favoriten","Portfolio","Inbox") }
                .map { bounds(it).top }.filter { it>rootBounds.centerY() }.minOrNull() ?: rootBounds.bottom
            descriptions.indices.forEach { i ->
                val r=bounds(i)
                descriptions[i]=descriptions[i].copy(captureComplete=r.height()>0 && r.top>=top && r.bottom<=bottom)
            }
            for(index in SearchInputCluster.spatial(descriptions,nodes.map(::box),box(root))) {
                ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.SEARCH_INPUT_SPATIAL)
                // Preserve original labels so login/order guards still inspect them.
                descriptions[index]=descriptions[index].copy(id="bob:search_input",
                    text=nodes[index].text?.toString().orEmpty().take(2000))
            }
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
            // Inspect the previous product context while Android finishes BACK.
            // Return no draft or identifiers from this transitional screen.
            if(MorningReadRun.running) {
                when(productReturnTransition.poll(descriptions,root.windowId,SystemClock.elapsedRealtime())) {
                    ProductReturnTransition.State.WAITING -> return observation("BUSY")
                    ProductReturnTransition.State.FAILED -> {
                        MorningReadRun.stop(this,"RETURN_NOT_CONFIRMED")
                        ProductReadRequest.cancel()
                        return observation("RETURN_NOT_CONFIRMED")
                    }
                    else -> Unit
                }
            }
            val actionName=command?.optString("action") ?: "inspect"
            val target=command?.optString("isin").orEmpty()
            val observedTarget=if(MorningReadRun.running) MorningReadRun.target else
                Regex("\\b[A-Z]{2}[A-Z0-9]{9}[0-9]\\b").findAll(descriptions.joinToString("\n") { it.text.uppercase() })
                    .map { it.value }.toSet().singleOrNull().orEmpty()
            val anchoredDetail=MorningReadRun.running && MorningReadRun.reading && pageReader.sameWindow(root.windowId)
            val detailLauncher=MorningReadPolicy.detailLauncherIndex(descriptions,observedTarget,anchoredDetail,
                symbolProbe=MorningReadRun.importedListRun())
            ProductReadDiagnostics.detailProduct(descriptions,detailLauncher!=null)
            val restoring=MorningReadPolicy.detailSearchRestore(descriptions,MorningReadRun.importedListRun())
            val proposed=if(actionName=="inspect" && detailLauncher!=null) MorningReadPolicy.Action(MorningReadPolicy.Kind.READ)
                else if(actionName=="inspect" && restoring!=null) restoring
                else if(actionName=="inspect" && MorningReadRun.running) MorningReadPolicy.detailDecision(descriptions,MorningReadRun.target,MorningReadRun.importedListRun(),keyboardVisible(),resultOpened=batchResultOpened) { symbolMemory.getString(it,null) }
                else if(actionName=="search_isin") MorningReadPolicy.decide(descriptions,target) { symbolMemory.getString(it,null) }
                else if(((GoldSearchRun.running && listImages.length()>0 && root.windowId==listWindowId) || MorningListDelivery.waiting) && actionName=="inspect")
                    MorningReadPolicy.captureGoldList(descriptions,true)
                else MorningReadPolicy.discoverGold(descriptions)
            val decision=remoteSearchProgress.select(descriptions,proposed,root.windowId,SystemClock.elapsedRealtime())
            if(decision.kind==MorningReadPolicy.Kind.BLOCK) {
                if(decision.code=="PROTECTED_ORDER_CONFIRM") MorningReadPolicy.detailLauncherIndex(
                    descriptions,observedTarget,anchoredDetail,MorningReadRun.importedListRun(),ProductReadDiagnostics::detailGuard)
                if(decision.code=="PROTECTED_ORDER_CONFIRM") ProductReadDiagnostics.launcher(MorningReadPolicy.launcherSearchIssue(descriptions),descriptions)
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
                val readable=MorningReadPolicy.detailReadLines(descriptions,lines,observedTarget,anchoredDetail,
                    symbolProbe=MorningReadRun.importedListRun())
                val data=ProductScreenEvidence.read(ProductScreenEvidence.PACKAGE,readable,Instant.now().toString(),false)
                result.put("draft",data.draft.take(8000))
            }
            val collected=ProductReadSession.get(SystemClock.elapsedRealtime()).draft
            if(ids.size==1 && collected.contains(ids.single()))result.put("draft",collected.take(8000))
            if(command==null || actionName=="inspect")return result
            if(MorningListDelivery.waiting || ProductReadRequest.active(SystemClock.elapsedRealtime()) || MorningReadRun.running || GoldSearchRun.running)return result.put("code","BUSY")
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
                MorningReadPolicy.Kind.SEARCH, MorningReadPolicy.Kind.RESULT, MorningReadPolicy.Kind.CATEGORY -> nodes[decision.index].performAction(AccessibilityNodeInfo.ACTION_CLICK)
                MorningReadPolicy.Kind.CATEGORY_SCROLL -> scrollCategories(nodes[decision.index])
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
    private fun tapRecognizedSearch(expectedWindow: Int, input: Boolean = false, category: Boolean = false, productResult: Boolean = false): Boolean {
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
            val action=if(MorningReadRun.running) MorningReadPolicy.detailDecision(descriptions,MorningReadRun.target,MorningReadRun.importedListRun(),keyboardVisible())
                else MorningReadPolicy.discoverGold(descriptions)
            val required=if(category) MorningReadPolicy.Kind.CATEGORY else if(input) MorningReadPolicy.Kind.FOCUS else MorningReadPolicy.Kind.SEARCH
            val targetIndex=if(productResult) {
                if(input || category || !MorningReadRun.running) return false
                MorningReadPolicy.resultTapIndex(descriptions,MorningReadRun.target) ?: return false
            } else {
                if(action.kind!=required || (input && category)) return false
                action.index
            }
            val target=live[targetIndex]
            if(!target.isVisibleToUser || !target.isEnabled || target.isEditable!=input || target.isPassword) return false
            val resultLabel=if(productResult) (target.text ?: target.contentDescription)?.toString() else null
            val bounds=Rect();target.getBoundsInScreen(bounds)
            val screen=Rect();root.getBoundsInScreen(screen)
            val point=SearchTapPolicy.center(
                SearchTapPolicy.Box(bounds.left,bounds.top,bounds.right,bounds.bottom),
                SearchTapPolicy.Box(screen.left,screen.top,screen.right,screen.bottom)) ?: return false
            if(productResult && live.indices.any { i ->
                val label=descriptions[i].text.trim().lowercase()
                label in setOf("k","v","kauf","verkauf","kaufen","verkaufen","buy","sell") &&
                    Rect().also { live[i].getBoundsInScreen(it) }.contains(point.first,point.second)
            }) return false
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
            if(productResult && (target.text ?: target.contentDescription)?.toString()!=resultLabel) return false
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


    private fun keyboardVisible():Boolean {
        val list=windows
        return try { list.any { it.type==AccessibilityWindowInfo.TYPE_INPUT_METHOD } }
        finally { list.forEach { it.recycle() } }
    }

    // Capture only the validated product-list window (Android 14+), after the
    // keyboard has disappeared. Never capture the full display or secure windows.
    private fun captureMorningList(root:AccessibilityNodeInfo,nodes:List<AccessibilityNodeInfo>,
                                  descriptions:List<MorningReadPolicy.Node>,action:MorningReadPolicy.Action) {
        if(listBusy || listSeenIds.size==10) return
        fun fail(code:String) { lastNavigationIssue=code;ProductReadRequest.cancel() }
        if(android.os.Build.VERSION.SDK_INT<34) { fail("LIST_CAPTURE_ANDROID_VERSION");return }
        if(!PhoneRemote.active() || !GoldSearchRun.running || keyboardVisible()) return
        if(listImages.length()>0 && !listScrolled) {
            val candidates=nodes.indices.filter { i ->
                val n=nodes[i]; val d=descriptions[i]
                n.isVisibleToUser && n.isEnabled && !n.isEditable && !n.isPassword &&
                    n.className?.toString()!="android.widget.HorizontalScrollView" &&
                    n.actionList.any { it.id==AccessibilityNodeInfo.ACTION_SCROLL_FORWARD } &&
                    action.isins.any { d.row.contains(it) }
            }
            val chosen=candidates.filter { ancestor -> candidates.none { child ->
                var cursor=descriptions[child].parent;var steps=0;var found=false
                while(cursor in descriptions.indices && steps++<descriptions.size) {
                    if(cursor==ancestor) { found=true;break };cursor=descriptions[cursor].parent
                };child!=ancestor && found
            } }.singleOrNull()
            if(chosen==null || ++listScrollTries>2) { fail("LIST_SCROLL_UNAVAILABLE");return }
            lastNavigation=SystemClock.elapsedRealtime()
            listScrolled=nodes[chosen].performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD)
            if(listScrolled) ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.LIST_SCROLL_SENT)
            if(!listScrolled) fail("LIST_SCROLL_REJECTED")
            return
        }
        if(listImages.length()>0 && action.isins==listFirstIds) {
            if(++listScrollTries>4) fail("LIST_SCROLL_NO_PROGRESS")
            return
        }
        if(listImages.length()==0 && !descriptions.any { n ->
            listOf(n.text,n.description,n.row).any { value -> value.lines().any { it.trim().equals("Top Ergebnisse",true) } }
        }) { fail("LIST_TOP_RESULTS_MISSING");return }
        if((listSeenIds+action.isins).size>10) { fail("LIST_TOP_RESULTS_OVERFLOW");return }
        if(listImages.length()>=4) { fail("LIST_TOP_RESULTS_INCOMPLETE");return }
        val windowId=root.windowId;val generation=listGeneration
        val rect=Rect();root.getBoundsInScreen(rect)
        val input=descriptions.indexOfFirst { it.editable }
        val cropTop=if(input>=0) {
            val search=Rect();nodes[input].getBoundsInScreen(search)
            search.top-rect.top
        } else listCropTop ?: run { fail("LIST_CAPTURE_SEARCH_MISSING");return }
        if(rect.width()<=0 || cropTop<0 || cropTop>=rect.height()/2) { fail("LIST_CAPTURE_BOUNDS");return }
        val current=windows
        val safe=try {
            val app=current.singleOrNull { it.id==windowId && it.isActive && it.isFocused && it.type==AccessibilityWindowInfo.TYPE_APPLICATION }
            app!=null && app.displayId==android.view.Display.DEFAULT_DISPLAY && current.none {
                it.id!=windowId && it.layer>app.layer && it.type!=AccessibilityWindowInfo.TYPE_SYSTEM
            }
        } finally { current.forEach { it.recycle() } }
        if(!safe) { fail("LIST_CAPTURE_WINDOW_CHANGED");return }
        listBusy=true
        val ids=action.isins.toList();val capturedAt=Instant.now().toString()
        val textBefore=MorningListText.capture(descriptions,ids)
        takeScreenshotOfWindow(windowId,mainExecutor,object:TakeScreenshotCallback {
            override fun onFailure(errorCode:Int) {
                if(generation!=listGeneration)return
                listBusy=false;fail("LIST_CAPTURE_FAILED")
            }
            override fun onSuccess(result:ScreenshotResult) {
                val buffer=result.hardwareBuffer
                try {
                    if(generation!=listGeneration || !PhoneRemote.active() || !GoldSearchRun.running ||
                        !ProductReadRequest.active(SystemClock.elapsedRealtime()) || keyboardVisible())return
                    val live=rootInActiveWindow ?: return
                    val refs=mutableListOf<AccessibilityNodeInfo>();val view=mutableListOf<MorningReadPolicy.Node>()
                    var textAfter:List<String>?=null
                    val unchanged=try {
                        navigationTree(live,refs,view)
                        textAfter=MorningListText.capture(view,ids)
                        val decision=MorningReadPolicy.captureGoldList(view,listImages.length()>0)
                        live.windowId==windowId && live.packageName?.toString()==ProductScreenEvidence.PACKAGE &&
                            decision.kind==MorningReadPolicy.Kind.COLLECT && decision.isins==ids
                    } finally { refs.forEach { it.recycle() };live.recycle() }
                    if(!unchanged) { fail("LIST_CAPTURE_WINDOW_CHANGED");return }
                    val hardware=android.graphics.Bitmap.wrapHardwareBuffer(buffer,result.colorSpace) ?: error("bitmap")
                    val bitmap=try { hardware.copy(android.graphics.Bitmap.Config.ARGB_8888,false) } finally { hardware.recycle() }
                    try {
                        check(bitmap.width==rect.width() && bitmap.height==rect.height())
                        val cropped=android.graphics.Bitmap.createBitmap(bitmap,0,cropTop,bitmap.width,bitmap.height-cropTop)
                        val bytes=try { java.io.ByteArrayOutputStream().use { out ->
                            check(cropped.compress(android.graphics.Bitmap.CompressFormat.PNG,100,out));out.toByteArray()
                        } } finally { if(cropped!==bitmap)cropped.recycle() }
                        check(bytes.size<=1500000)
                        val image=org.json.JSONObject().put("at",capturedAt).put("png",android.util.Base64.encodeToString(bytes,android.util.Base64.NO_WRAP))
                        if(textBefore!=null && textAfter==textBefore) image.put("appText",org.json.JSONObject()
                            .put("before",org.json.JSONArray(textBefore)).put("after",org.json.JSONArray(textAfter)))
                        listImages.put(image)
                        listCropTop=cropTop
                        listWindowId=windowId
                        ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.LIST_IMAGE_CAPTURED)
                        listFirstIds=ids;listSeenIds.addAll(ids);listScrolled=false;listScrollTries=0
                        saveListCheckpoint()
                    } finally { bitmap.recycle() }
                    if(listSeenIds.size==10) deliverMorningList(generation)
                    else if(listImages.length()>=4) fail("LIST_TOP_RESULTS_INCOMPLETE")
                    else GoldSearchRun.event("LIST_FIRST_CAPTURED",capturedAt)
                } catch(_:Exception) { if(generation==listGeneration)fail("LIST_CAPTURE_FAILED") }
                finally { buffer.close();if(generation==listGeneration)listBusy=false }
            }
        })
    }
    private fun checkpoint()=android.util.AtomicFile(java.io.File(filesDir,"morning-list-checkpoint.json"))
    private fun saveListCheckpoint() {
        val value=org.json.JSONObject().put("at",System.currentTimeMillis()).put("batch",listBatch)
            .put("window",listWindowId).put("crop",listCropTop).put("images",org.json.JSONArray(listImages.toString()))
            .put("seen",org.json.JSONArray(listSeenIds.toList())).put("last",org.json.JSONArray(listFirstIds))
        val f=checkpoint();val stream=f.startWrite()
        try { stream.write(value.toString().toByteArray());f.finishWrite(stream) }
        catch(e:Exception) { f.failWrite(stream);throw e }
    }
    private fun restoreListCheckpoint() {
        if(!GoldSearchRun.running)return
        runCatching {
            val value=org.json.JSONObject(String(checkpoint().readFully()))
            check(System.currentTimeMillis()-value.getLong("at") in 0..120000)
            val root=productRoot(true) ?: return
            val refs=mutableListOf<AccessibilityNodeInfo>();val view=mutableListOf<MorningReadPolicy.Node>()
            try {
                check(root.packageName?.toString()==ProductScreenEvidence.PACKAGE && root.windowId==value.getInt("window"))
                navigationTree(root,refs,view)
                val decision=MorningReadPolicy.captureGoldList(view,true)
                val last=value.getJSONArray("last");val ids=(0 until last.length()).map { last.getString(it) }
                check(decision.kind==MorningReadPolicy.Kind.COLLECT && decision.isins==ids)
                val images=value.getJSONArray("images");check(images.length() in 1..4)
                val batch=value.getString("batch");check(batch.matches(Regex("[a-f0-9]{32}")))
                val seen=value.getJSONArray("seen");val seenIds=(0 until seen.length()).map { seen.getString(it) }
                check(seenIds.size in 1..10 && seenIds.distinct()==seenIds && seenIds.all { SeriesEvidence.validIsin(it) } && seenIds.containsAll(ids))
                val crop=value.getInt("crop");check(crop>=0)
                val savedImages=(0 until images.length()).map { images.getJSONObject(it) }
                listBatch=batch;listWindowId=root.windowId;listCropTop=crop
                savedImages.forEach { listImages.put(it) };listSeenIds.addAll(seenIds)
                listFirstIds=ids;listScrolled=false
                if(listSeenIds.size==10)deliverMorningList(listGeneration)
            } finally { refs.forEach { it.recycle() };root.recycle() }
        }
    }
    /** A validated list has been captured locally. Return to the search header
     * while remote OCR is pending; DO NOT type any ISIN until ten rows are
     * confirmed by the existing server gate. Bound the scroll and window. */
    private fun returnToSearchWhileImporting(expectedWindow:Int, captured:Set<String>, attempt:Int) {
        if(attempt>=4 || !MorningListDelivery.waiting || !PhoneRemote.active() ||
            MorningReadRun.running || GoldSearchRun.running) return
        if(!(getSystemService(POWER_SERVICE) as PowerManager).isInteractive ||
            (getSystemService(KEYGUARD_SERVICE) as KeyguardManager).isKeyguardLocked) return
        val root=productRoot(false) ?: return
        val live=mutableListOf<AccessibilityNodeInfo>()
        val descriptions=mutableListOf<MorningReadPolicy.Node>()
        try {
            if(root.windowId!=expectedWindow || root.packageName?.toString()!=ProductScreenEvidence.PACKAGE) return
            navigationTree(root,live,descriptions)
            if(descriptions.any { it.editable && MorningReadPolicy.isSearchInput(it.id,it.description,it.hint) }) return
            val backward=live.indices.filter { i ->
                val n=live[i]
                n.isVisibleToUser && n.isEnabled && !n.isEditable && !n.isPassword &&
                    n.className?.toString()!="android.widget.HorizontalScrollView" &&
                    n.actionList.any { it.id==AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD }
            }.toSet()
            val index=MorningReadPolicy.listReturnScrollTarget(descriptions,backward,captured) ?: return
            val target=live[index]
            if(!target.refresh() || !target.isVisibleToUser || !target.isEnabled) return
            val current=rootInActiveWindow
            val same=current?.windowId==expectedWindow &&
                current?.packageName?.toString()==ProductScreenEvidence.PACKAGE
            current?.recycle()
            if(!same) return
            lastNavigation=SystemClock.elapsedRealtime()
            if(target.performAction(AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD)) {
                ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.LIST_RETURN_SCROLL_SENT)
                handler.postDelayed({ returnToSearchWhileImporting(expectedWindow,captured,attempt+1) },650)
            }
        } finally { live.forEach { it.recycle() };root.recycle() }
    }

    private fun deliverMorningList(generation:Int) {
        if(generation!=listGeneration)return
        val body=org.json.JSONObject().put("batchId",listBatch).put("sessionId",PhoneRemote.sessionId())
            .put("images",org.json.JSONArray(listImages.toString()))
        val captured=listSeenIds.toSet()
        val capturedWindow=listWindowId
        MorningListDelivery.start(this,body)
        checkpoint().delete()
        GoldSearchRun.stop("LIST_IMAGES_DELIVERED",Instant.now().toString())
        ProductReadRequest.cancel();PhoneDiagnostics.queue(this)
        // Do not wait for native OCR just to scroll back up. Still require
        // the server's ten-row receipt before touching any ISIN search.
        if(capturedWindow!=null) handler.postDelayed({ returnToSearchWhileImporting(capturedWindow,captured,0) },650)
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

    private fun scrollCategories(node:AccessibilityNodeInfo):Boolean {
        val right=AccessibilityNodeInfo.AccessibilityAction.ACTION_SCROLL_RIGHT.id
        val action=if(node.actionList.any { it.id==right }) right else AccessibilityNodeInfo.ACTION_SCROLL_FORWARD
        if(!node.isVisibleToUser || !node.isEnabled || node.isEditable || node.isPassword ||
            (action!=right && node.className?.toString()!="android.widget.HorizontalScrollView") ||
            node.actionList.none { it.id==action }) return false
        return node.performAction(action)
    }

    /** Search actions use semantic nodes only, never coordinates or order buttons. */
    private fun navigateMorning(root: AccessibilityNodeInfo, gold: Boolean = false): Boolean {
        if(gold && !listResumeChecked) {
            listResumeChecked=true
            restoreListCheckpoint()
            if(!GoldSearchRun.running)return true
        }
        val nodes=mutableListOf<AccessibilityNodeInfo>()
        val descriptions=mutableListOf<MorningReadPolicy.Node>()
        try {
            navigationTree(root,nodes,descriptions)
            if(!gold) {
                when(productReturnTransition.poll(descriptions,root.windowId,SystemClock.elapsedRealtime())) {
                    ProductReturnTransition.State.WAITING -> return true
                    ProductReturnTransition.State.FAILED -> {
                        MorningReadRun.stop(this,"RETURN_NOT_CONFIRMED")
                        ProductReadRequest.cancel()
                        return true
                    }
                    else -> Unit
                }
            }
            if(gold && listImages.length()>0 && root.windowId!=listWindowId) {
                lastNavigationIssue="LIST_CAPTURE_WINDOW_CHANGED";ProductReadRequest.cancel();return true
            }
            if(gold && listImages.length()>0 && descriptions.none { it.editable }) {
                ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.LIST_HEADER_SCROLLED_AWAY)
                if(descriptions.none { it.selected && it.text.trim().equals("Hebelprodukte",true) })
                    ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.LIST_TAB_SELECTION_UNREPORTED)
            }
            // A fresh run can begin on yesterday's scrolled list. Only scroll
            // backwards here; no capture is accepted before Top Ergebnisse is visible.
            if(!gold) ProductReadDiagnostics.detailHeader(descriptions)
            val detailRestore=MorningReadPolicy.detailSearchRestore(descriptions,MorningReadRun.importedListRun())
            if(detailRestore!=null || (gold && listImages.length()==0 && descriptions.none { it.text.trim().equals("Top Ergebnisse",true) })) {
                val seek=detailRestore ?: MorningReadPolicy.captureGoldList(descriptions,true)
                if(seek.kind==MorningReadPolicy.Kind.COLLECT) {
                    val targets=nodes.indices.filter { i ->
                        val n=nodes[i]
                        n.isVisibleToUser && n.isEnabled && !n.isEditable && !n.isPassword &&
                            n.className?.toString()!="android.widget.HorizontalScrollView" &&
                            n.actionList.any { it.id==AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD } &&
                            seek.isins.any { descriptions[i].row.contains(it) }
                    }
                    val inner=targets.filter { parent -> targets.none { child ->
                        var at=descriptions[child].parent;var steps=0;var found=false
                        while(at in descriptions.indices && steps++<descriptions.size) {
                            if(at==parent) { found=true;break };at=descriptions[at].parent
                        };child!=parent && found
                    } }.singleOrNull()
                    val failure=when {
                        inner==null -> "LIST_RESTORE_NO_TARGET"
                        ++listTopSeekSteps>4 -> "LIST_RESTORE_LIMIT"
                        !nodes[inner].performAction(AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD) -> "LIST_RESTORE_REJECTED"
                        else -> null
                    }
                    if(failure!=null) {
                        lastNavigationIssue=failure
                        if(!gold) MorningReadRun.event(this,failure)
                        ProductReadRequest.cancel()
                    } else if(!gold) ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.DETAIL_HEADER_SCROLL_SENT)
                    lastNavigation=SystemClock.elapsedRealtime()
                    return true
                }
            }
            val proposed=if(gold) MorningReadPolicy.captureGoldList(descriptions,listImages.length()>0) else MorningReadPolicy.detailDecision(descriptions,MorningReadRun.target,MorningReadRun.importedListRun(),keyboardVisible(),resultOpened=batchResultOpened) {
                symbolMemory.getString(it, null)
            }
            val action=automaticSearchProgress.select(descriptions,proposed,root.windowId,SystemClock.elapsedRealtime())
            fun record(code:String) {
                if(gold) { GoldSearchRun.event(code,Instant.now().toString());PhoneDiagnostics.queue(this) }
                else MorningReadRun.event(this,code)
            }
            if(gold && action.kind in setOf(MorningReadPolicy.Kind.CATEGORY,MorningReadPolicy.Kind.COLLECT) && keyboardVisible()) {
                lastNavigation=SystemClock.elapsedRealtime()
                if(!performGlobalAction(GLOBAL_ACTION_BACK)) { lastNavigationIssue="KEYBOARD_HIDE_FAILED";ProductReadRequest.cancel() }
                return true
            }
            val resultTarget=if(!gold) MorningReadPolicy.resultTapIndex(descriptions,MorningReadRun.target) else null
            if(!gold && action.code=="RESULT_MISSING" && resultTarget==null) {
                ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.RESULT_TARGET_MISSING)
                if(descriptions.any { !it.editable && it.row.contains(MorningReadRun.target) })
                    ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.RESULT_IDENTITY_PRESENT)
                if(descriptions.any { !it.editable && Regex("(?iu)\\b(gold|xau)\\b").containsMatchIn(it.text) })
                    ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.RESULT_NAME_PRESENT)
            }
            if(!gold && !resultTapAttempted && resultTarget!=null) {
                resultTapAttempted=true
                val tapped=tapRecognizedSearch(root.windowId,productResult=true)
                val code=if(tapped) "RESULT_TAP_SENT" else "RESULT_TAP_REJECTED"
                record(code);lastNavigationIssue=code
                if(tapped) { batchResultOpened=true;return true }
            }
            when(action.kind) {
                MorningReadPolicy.Kind.BLOCK -> {
                    if(!gold && action.code=="PROTECTED_ORDER_CONFIRM") MorningReadPolicy.detailLauncherIndex(
                        descriptions,MorningReadRun.target,symbolProbe=MorningReadRun.importedListRun(),rejected=ProductReadDiagnostics::detailGuard)
                    if(action.code=="PROTECTED_ORDER_CONFIRM") ProductReadDiagnostics.launcher(MorningReadPolicy.launcherSearchIssue(descriptions),descriptions)
                    if(gold) { lastNavigationIssue=action.code;record(action.code) }
                    else MorningReadRun.stop(this,action.code)
                    ProductReadRequest.cancel()
                }
                MorningReadPolicy.Kind.COLLECT -> {
                    check(gold && GoldSearchRun.running)
                    captureMorningList(root,nodes,descriptions,action)
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
                    // A result card can enclose K/V order controls. The only
                    // permitted product-result gesture is the independently
                    // validated isolated title from resultTapIndex above.
                    // Never fall through to ACTION_CLICK on the aggregate card,
                    // even after a gesture was already attempted this window.
                    if(!gold && action.kind==MorningReadPolicy.Kind.RESULT) {
                        if(resultTarget==null && lastNavigationIssue!="RESULT_TARGET_UNSAFE") {
                            lastNavigationIssue="RESULT_TARGET_UNSAFE"
                            record(lastNavigationIssue)
                            ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.RESULT_TARGET_MISSING)
                        }
                        return true
                    }
                    if(action.kind in setOf(MorningReadPolicy.Kind.CATEGORY,MorningReadPolicy.Kind.CATEGORY_SCROLL) && ++categorySteps>4) {
                        lastNavigationIssue="CATEGORY_NO_PROGRESS";record(lastNavigationIssue)
                        ProductReadRequest.cancel();return true
                    }
                    val current=productRoot(false)
                    val safe=current?.windowId==root.windowId && current?.packageName?.toString()==ProductScreenEvidence.PACKAGE
                    current?.recycle()
                    if(!safe) return true
                    val node=nodes[action.index]
                    lastNavigation=SystemClock.elapsedRealtime()
                    val success=if(action.kind==MorningReadPolicy.Kind.QUERY) {
                        val args=android.os.Bundle().apply { putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,if(gold) "Gold" else MorningReadRun.target) }
                        node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,args)
                    } else if(action.kind==MorningReadPolicy.Kind.FOCUS) {
                        if(!inputTapAttempted) {
                            inputTapAttempted=true
                            val tapped=tapRecognizedSearch(root.windowId,input=true)
                            ProductReadDiagnostics.record(if(tapped) ProductReadDiagnostics.Outcome.SEARCH_INPUT_TAP_SENT else ProductReadDiagnostics.Outcome.SEARCH_INPUT_TAP_REJECTED)
                            tapped
                        } else focusSearch(node)
                    }
                    else if(action.kind==MorningReadPolicy.Kind.SUBMIT) submitSearch(node)
                    else if(action.kind==MorningReadPolicy.Kind.CATEGORY_SCROLL) scrollCategories(node)
                    else if(action.kind==MorningReadPolicy.Kind.CATEGORY) tapRecognizedSearch(root.windowId,category=true)
                    else node.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                    if(success && action.kind==MorningReadPolicy.Kind.RESULT) batchResultOpened=true
                    if(success && action.kind==MorningReadPolicy.Kind.CATEGORY) ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.CATEGORY_CLICK_SENT)
                    if(success && action.kind==MorningReadPolicy.Kind.CATEGORY_SCROLL) ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.CATEGORY_SCROLL_SENT)
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
