package ch.bob.degirocompanion

import android.accessibilityservice.AccessibilityService
import android.app.KeyguardManager
import android.graphics.Bitmap
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.Display
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions

/** Locally started service; automatic cloud proposals require a per-app owner opt-in. */
class WorkflowService : AccessibilityService() {
    companion object {
        internal var instance: WorkflowService? = null
        internal var run: WorkflowRun? = null
        internal var observation: WorkflowFrame? = null
        internal var observationAt = 0L
        internal var epoch = 0
        internal var screenshotText = ""
        internal var message = "Kein Auftrag aktiv"
        internal var demonstrationAllEvents = 0
        internal var demonstrationEvents = 0
        internal var demonstrationCheck = "NONE"
        internal var demonstrationDraft: Pair<String, List<WorkflowStep>>? = null
        internal fun endDemonstration() { instance?.let { if (it.demonstration != null) it.finish("Vormachen beendet · Entwurf prüfen") } }
        internal fun stop() { WorkflowLoginHandoff.clear(); epoch++; instance?.finish("Gestoppt"); run?.stop("Gestoppt"); run = null; observation = null; screenshotText = "" }
    }
    private val handler = Handler(Looper.getMainLooper())
    private var selected = ""
    private var until = 0L
    private var recipeGoal = ""
    private var displayRequest = ""
    private var recipeTitle = ""
    private var recorded = true
    private var capture = false
    private var captureObservation: WorkflowAutoObservation? = null
    private var demonstration: WorkflowDemonstration? = null
    private var demonstrationSeen = false
    private var symbolPending = false
    private var symbolMatch: Pair<WorkflowFrame, Int>? = null
    private var symbolBounds = emptyList<SymbolBox>()
    private var symbolMatchedAt = 0L
    private var symbolIssuedStep = -1
    private var generation = 0
    private var replaySteps: List<WorkflowStep>? = null
    private var automatic = false
    private var autoCloud = false
    private var autoObservation: WorkflowAutoObservation? = null
    private var healthActive = false
    private var healthSource = "NONE"
    private var planning = false
    private var proposalContext: List<WorkflowNode>? = null
    private val poll = object : Runnable {
        override fun run() {
            if (selected.isEmpty()) return
            if (selected == packageName && !WorkflowSelfTestActivity.active) { finish("Gestoppt: andere App im Vordergrund"); return }
            if (SystemClock.elapsedRealtime() > until) { finish("Sitzung beendet"); return }
            val unlocked = !(getSystemService(KEYGUARD_SERVICE) as KeyguardManager).isKeyguardLocked
            if (!unlocked) { finish("Gestoppt: Bildschirm gesperrt"); return }
            autoObservation?.let {
                it.next(null, SystemClock.elapsedRealtime(), unlocked)
                if (it.reason.isNotEmpty()) { finish("Gestoppt: " + it.reason); return }
            }
            run?.tick(null, SystemClock.elapsedRealtime(), unlocked) { _, _ -> false }
            run?.let { if (it.finished) { finish(it.status); return } }
            val root = rootInActiveWindow
            if (root != null && root.packageName?.toString() != selected) {
                if (demonstration != null && demonstrationSeen) { finish("Vormachen beendet: andere App geöffnet"); return }
                if (automatic && (autoObservation?.seen == true || planning)) { finish("Gestoppt: andere App im Vordergrund"); return }
                run?.tick(WorkflowFrame(root.packageName?.toString().orEmpty(), root.windowId, emptyList()), SystemClock.elapsedRealtime(), unlocked) { _, _ -> false }
                run?.let { if (it.finished) { finish(it.status); return } }
                handler.postDelayed(this, 500); return
            }
            if (root != null) {
                val refs = mutableListOf<AccessibilityNodeInfo>()
                var truncated = false
                var visited = 0
                fun visit(n: AccessibilityNodeInfo, depth: Int) {
                    if (++visited > 400 || depth > 30 || n.childCount > 100) { truncated = true; return }
                    if (n.isVisibleToUser) refs.add(n)
                    for (i in 0 until n.childCount.coerceAtMost(100)) n.getChild(i)?.let { visit(it, depth + 1) }
                }
                visit(root, 0)
                if (truncated) { finish("Bildschirm zu komplex: keine eindeutige Prüfung möglich"); return }
                val frame = WorkflowFrame(root.packageName?.toString().orEmpty(), root.windowId, refs.map {
                    WorkflowNode(it.text?.toString()?.takeIf { text -> text.isNotBlank() }?.take(500) ?: it.hintText?.toString()?.take(500) ?: it.contentDescription?.toString()?.take(500).orEmpty(),
                        it.viewIdResourceName.orEmpty(), it.isEditable && it.isEnabled, it.isClickable && it.isEnabled, it.isPassword, if (it.isEditable) { if (it.isShowingHintText) "" else it.text?.toString().orEmpty() } else null, selected=it.isSelected || it.isChecked)
                })
                if (frame.app == selected && !LocalWorkflow.protected(frame)) {
                    observation = frame; observationAt = SystemClock.elapsedRealtime()
                    // A new window can expose its tree before the app has drawn it.
                    // Wait for stable content before capturing, just as automatic planning does.
                    if (capture && captureObservation?.next(frame, SystemClock.elapsedRealtime(), unlocked) != null) {
                        capture = false; captureObservation = null; captureScreen(generation, frame.window)
                    }
                }
                demonstration?.let { recorder ->
                    demonstrationSeen = true
                    if (LocalWorkflow.protected(frame)) { finish("Geschützte Ansicht: Aufzeichnung beendet"); return }
                    recorder.observe(frame)
                    if (recorder.error.isNotEmpty()) { finish(recorder.error); return }
                    message = "Vormachen aktiv · ${recorder.steps.size} Schritte · zurück zu Bob beendet die Aufzeichnung"
                }
                if (ConnectionErrorPolicy.detected(frame.nodes.map { it.label })) {
                    finish("Verbindungsfehler: Auftrag angehalten"); return
                }
                if (automatic && LocalWorkflow.protected(frame)) { finish("Geschützte Ansicht: Auftrag gestoppt"); return }
                if (automatic && run == null && !planning) {
                    val ready = autoObservation?.next(frame, SystemClock.elapsedRealtime(), unlocked)
                    if (ready != null) prepareAutomatic(ready)
                    if (autoObservation?.reason?.isNotEmpty() == true) { finish("Gestoppt: " + autoObservation?.reason); return }
                    if (selected.isEmpty()) return
                }
                if (planning && proposalContext != WorkflowAuto.context(frame)) {
                    finish("Ansicht während KI-Anfrage geändert; nichts ausgeführt"); return
                }
                var actionFrame = frame
                val active = run
                val step = active?.steps?.getOrNull(active.index)
                if (step?.target?.startsWith("Symbol: ") == true && symbolIssuedStep != active?.index) {
                    if (step.action != WorkflowAction.CLICK || LocalWorkflow.protected(frame)) { finish("Symbolauftrag nicht zulässig"); return }
                    val bounds = refs.map { n -> android.graphics.Rect().let { n.getBoundsInScreen(it); SymbolBox(it.left, it.top, it.right, it.bottom) } }
                    val match = symbolMatch
                    if (match != null) {
                        if (frame != match.first || bounds != symbolBounds || SystemClock.elapsedRealtime() - symbolMatchedAt > 1200) {
                            finish("Ansicht geändert: Symbol erneut prüfen"); return
                        }
                        actionFrame = frame.copy(nodes = frame.nodes.mapIndexed { i, node -> if (i == match.second) node.copy(label = step.target) else node })
                    } else {
                        if (!symbolPending) captureSymbol(frame, bounds, step.target)
                        if (selected.isNotEmpty()) handler.postDelayed(this, 500)
                        return
                    }
                }
                run?.tick(actionFrame, SystemClock.elapsedRealtime(), unlocked) { step, index ->
                    val n = refs.getOrNull(index)
                    // Frame and action originate from the same freshly read tree.
                    val currentRoot = rootInActiveWindow
                    if (n == null || currentRoot?.windowId != frame.window || currentRoot.packageName?.toString() != selected) false
                    else if (step.action == WorkflowAction.CLICK) n.performAction(AccessibilityNodeInfo.ACTION_CLICK).also { success ->
                        if (success && step.target.startsWith("Symbol: ")) { symbolIssuedStep = run?.index ?: -1; symbolMatch = null }
                    }
                    else n.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, Bundle().apply {
                        putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, step.value)
                    })
                }
                run?.let { message = it.status; if (it.finished) { finish(it.status); return } }
                if (frame.app == selected && LocalWorkflow.protected(frame)) { finish("Geschützte Ansicht: Lesen und Bedienung gestoppt"); return }
            }
            handler.postDelayed(this, 500)
        }
    }
    internal fun begin(app: String, steps: List<WorkflowStep>?, screenshot: Boolean = false, goal: String = "", title: String = "", request: String = ""): Boolean {
        if (!LocalWorkflow.allowedApp(app)) { stop(); return false }
        return beginInternal(app,steps,screenshot,goal,title,request)
    }
    // No caller-selected target or commands: only the non-exported local test surface.
    internal fun beginSelfTest(screenshot: Boolean): Boolean {
        if (!WorkflowSelfTestActivity.active) return false
        val steps = if (screenshot) null else listOf(
            WorkflowStep(WorkflowAction.CLICK,"Suche",opensSearch=true),
            WorkflowStep(WorkflowAction.WRITE,WorkflowSearch.FIELD,"Gold"))
        return beginInternal(packageName,steps,screenshot,"","")
    }
    private fun beginInternal(app: String, steps: List<WorkflowStep>?, screenshot: Boolean, goal: String, title: String, request: String = ""): Boolean {
        epoch++ // Invalidate activity proposals from every preceding owner request.
        finish("Neue Sitzung")
        run = null
        recipeGoal = goal; recipeTitle = title; displayRequest = request.ifBlank { goal }; recorded = false
        selected = app; until = SystemClock.elapsedRealtime() + if (steps == null) 45_000 else 180_000
        capture = screenshot; captureObservation = if (screenshot) WorkflowAutoObservation(app, SystemClock.elapsedRealtime()) else null
        observation = null; screenshotText = ""
        run = steps?.let { WorkflowRun(app, it, SystemClock.elapsedRealtime()) }
        healthActive = steps != null
        healthSource = if (steps == null) "NONE" else "LOCAL"
        if (healthActive) WorkflowHealth.record(this,"STARTED",healthSource,0,steps!!.size)
        serviceInfo = serviceInfo.apply { packageNames = arrayOf(app, packageName) }
        message = if (steps == null) "Lese die gewählte App; danach zu Bob zurückkehren" else "Auftrag gestartet"
        handler.post(poll)
        return true
    }
    internal fun beginDemonstration(app: String): Boolean {
        if (!begin(app, null)) return false
        demonstrationDraft = null; demonstration = WorkflowDemonstration(app); demonstrationSeen = false
        demonstrationAllEvents = 0; demonstrationEvents = 0; demonstrationCheck = "STARTED"
        serviceInfo = serviceInfo.apply {
            eventTypes = eventTypes or AccessibilityEvent.TYPE_VIEW_CLICKED or AccessibilityEvent.TYPE_VIEW_TEXT_CHANGED
            notificationTimeout = 0
        }
        until = SystemClock.elapsedRealtime() + 180_000
        message = "Vormachen aktiv · nur gewählte App · keine automatische Ausführung"
        return true
    }
    internal fun beginAutomatic(app: String, goal: String, cloud: Boolean): Boolean {
        if (!LocalWorkflow.allowedApp(app) || (LocalWorkflow.parse(goal) == null && !WorkflowAiPolicy.safe(goal, 500))) { stop(); return false }
        if (!begin(app, null, goal=goal, title=goal.take(60))) return false
        automatic = true; autoCloud = cloud
        healthActive = true
        WorkflowHealth.record(this,"STARTED","NONE",0,0)
        until = SystemClock.elapsedRealtime() + 180_000
        autoObservation = WorkflowAutoObservation(app, SystemClock.elapsedRealtime())
        message = "Automatisch: öffne App und lese den Bildschirm"
        return true
    }
    internal fun beginReplay(app: String, steps: List<WorkflowStep>, request: String): Boolean {
        val text = WorkflowAiPolicy.commands(steps)
        if (LocalWorkflow.parse(text) != steps || !beginAutomatic(app,text,false)) return false
        replaySteps = steps; displayRequest = request.ifBlank { text }
        return true
    }
    private fun prepareAutomatic(frame: WorkflowFrame) {
        replaySteps?.let {
            val steps = WorkflowReplay.prepare(it,frame)
            if (steps.isEmpty()) { finish("Ziel bereits erreicht · keine weitere Aktion nötig"); return }
            run = WorkflowRun(selected,steps,SystemClock.elapsedRealtime()); healthSource = "LOCAL"
            return
        }
        WorkflowSymbols.plan(this, selected, recipeGoal)?.let {
            run = WorkflowRun(selected, it, SystemClock.elapsedRealtime()); healthSource = "LOCAL"
            message = "Prüfe gelerntes Symbol auf dem aktuellen Bildschirm"; return
        }
        WorkflowAuto.local(recipeGoal, frame)?.let {
            run = WorkflowRun(selected, it, SystemClock.elapsedRealtime())
            healthSource = "LOCAL"
            message = "Automatisch lokal erkannt · prüfe jeden Schritt"; return
        }
        WorkflowLibrary.match(this, selected, recipeGoal)?.second?.let { LocalWorkflow.parse(it) }?.let {
            run = WorkflowRun(selected, it, SystemClock.elapsedRealtime())
            healthSource = "CACHE"
            message = "Automatisch: bestätigter gespeicherter Ablauf · keine KI nötig"; return
        }
        if (!autoCloud) { finish("Lokal kein passender Ablauf; KI-Hilfe für diese App ist ausgeschaltet"); return }
        val nodes = WorkflowAuto.context(frame)
        if (nodes.isEmpty()) { finish("Keine freigegebenen Such-/Filterelemente erkannt; Details manuell prüfen"); return }
        val app = selected; val goal = recipeGoal; val token = generation
        healthSource = "AI"
        planning = true; proposalContext = nodes
        message = "Automatisch: eine KI-Anfrage · danach lokale Prüfung"
        Thread {
            val result = runCatching { WorkflowPlanner.request(applicationContext,app,goal,nodes) }
            handler.post {
                if (token != generation || selected != app || !planning) return@post
                val root = rootInActiveWindow
                if (root?.packageName?.toString() != app || root.windowId != frame.window ||
                    (getSystemService(KEYGUARD_SERVICE) as KeyguardManager).isKeyguardLocked ||
                    observation?.let { WorkflowAuto.context(it) } != nodes) {
                    finish("Ansicht geändert; KI-Antwort verworfen"); return@post
                }
                planning = false
                val answer = result.getOrNull()
                if (answer?.first == "proposal" && answer.second.isNotEmpty()) {
                    run = WorkflowRun(app, answer.second, SystemClock.elapsedRealtime())
                    message = "KI-Vorschlag geprüft · führe lokal aus"
                } else finish(WorkflowPlanner.error(answer?.first.orEmpty()) + " · kein Anbieterwechsel")
            }
        }.start()
    }
    private fun finish(reason: String) {
        demonstration?.let { demonstrationDraft = it.app to it.draft() }
        demonstration = null; demonstrationSeen = false
        val notify = automatic && reason != "Neue Sitzung"
        replaySteps = null; automatic = false; planning = false; autoCloud = false; autoObservation = null; proposalContext = null
        symbolPending = false; symbolMatch = null; symbolBounds = emptyList(); symbolIssuedStep = -1
        generation++; handler.removeCallbacks(poll); selected = ""; capture = false; captureObservation = null
        run?.let { if (!it.finished) it.stop(reason) }; message = reason
        run?.let {
            if (!recorded) {
                recorded = true
                WorkflowResultStore.record(this, it, reason, displayRequest)
                if (WorkflowAiPolicy.verified(it)) it.steps.filter { step -> step.target.startsWith("Symbol: ") }.forEach { step -> WorkflowSymbols.verified(this, it.app, step.target) }
                if (!WorkflowAiPolicy.verified(it)) WorkflowLibrary.failed(this, it.app, recipeGoal)
                message += runCatching { WorkflowLibrary.record(this, it, recipeGoal, recipeTitle) }
                    .getOrDefault(" · Speichern fehlgeschlagen")
            }
        }
        if (healthActive) {
            healthActive = false
            val current = run
            WorkflowHealth.record(this, if (current != null && WorkflowAiPolicy.verified(current)) "SUCCEEDED" else "STOPPED",
                healthSource, current?.index ?: 0, current?.steps?.size ?: 0,
                if (current != null && WorkflowAiPolicy.verified(current)) "NONE" else WorkflowFailure.code(reason))
        }
        if (notify) android.widget.Toast.makeText(this, message, android.widget.Toast.LENGTH_LONG).show()
        serviceInfo?.let { serviceInfo = it.apply { packageNames = arrayOf(packageName); notificationTimeout = 150 } }
    }
    override fun onServiceConnected() { instance = this; finish("Bereit · lokal starten") }
    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        val recorder = demonstration
        if (recorder != null) demonstrationAllEvents++
        if (recorder != null && event?.packageName?.toString() == selected &&
            event.eventType in listOf(AccessibilityEvent.TYPE_VIEW_CLICKED, AccessibilityEvent.TYPE_VIEW_TEXT_CHANGED)) {
            demonstrationEvents++
            val frame = observation
            val source = event.source
            if (frame == null || frame.app != selected || !symbolSafe(frame)) { demonstrationCheck = "FRAME_REJECTED"; return }
            demonstrationCheck = if (source == null) "NO_SOURCE" else "SOURCE_${event.eventType}_${source.isEditable}_${source.isEnabled}"
            if (event.eventType == AccessibilityEvent.TYPE_VIEW_CLICKED && source == null) {
                val label = event.text.map { it.toString() }.singleOrNull()
                val candidate = frame.nodes.singleOrNull { it.clickable && !it.editable && it.label == label }
                if (candidate != null) recorder.click(candidate.id.ifBlank { candidate.label }, frame)
            } else if (source != null && !source.isPassword && source.isEnabled) {
                val target = source.viewIdResourceName.orEmpty().ifBlank {
                    source.contentDescription?.toString().orEmpty().ifBlank { if (!source.isEditable) source.text?.toString().orEmpty() else source.hintText?.toString().orEmpty() }
                }
                if (event.eventType == AccessibilityEvent.TYPE_VIEW_CLICKED && !source.isEditable) recorder.click(target, frame)
                if (event.eventType == AccessibilityEvent.TYPE_VIEW_TEXT_CHANGED && source.isEditable)
                    recorder.write(target, if (source.isShowingHintText) "" else source.text?.toString().orEmpty())
            }
            if (recorder.error.isNotEmpty()) finish(recorder.error)
            return
        }
        // User touch aborts execution; observation mode permits the owner to navigate.
        if (event?.eventType == AccessibilityEvent.TYPE_TOUCH_INTERACTION_START && (run?.finished == false || (automatic && autoObservation?.seen == true)))
            finish("Gestoppt: eigene Bildschirmbedienung")
    }
    override fun onInterrupt() { WorkflowLoginHandoff.clear(); finish("Dienst unterbrochen") }
    override fun onDestroy() { WorkflowLoginHandoff.clear(); finish("Dienst beendet"); instance = null; observation = null; screenshotText = ""; super.onDestroy() }
    private fun symbolSafe(frame: WorkflowFrame): Boolean {
        val root = rootInActiveWindow ?: return false
        if (root.packageName?.toString() != frame.app || root.windowId != frame.window ||
            (getSystemService(KEYGUARD_SERVICE) as KeyguardManager).isKeyguardLocked) return false
        var count = 0
        fun safe(n: AccessibilityNodeInfo, depth: Int): Boolean {
            if (++count > 400 || depth > 30 || n.childCount > 100 || n.isPassword) return false
            val label = n.text?.toString().orEmpty() + " " + n.contentDescription?.toString().orEmpty()
            if (LocalWorkflow.protected(WorkflowFrame(frame.app, frame.window, listOf(WorkflowNode(label, "", false, false))))) return false
            return (0 until n.childCount).all { n.getChild(it)?.let { child -> safe(child, depth + 1) } ?: false }
        }
        return safe(root, 0)
    }
    private fun captureSymbol(frame: WorkflowFrame, bounds: List<SymbolBox>, target: String) {
        val learned = WorkflowSymbols.find(this, frame.app, target)
        if (learned == null) { finish("Symbol nicht mehr gespeichert; bitte erneut erklären"); return }
        if (Build.VERSION.SDK_INT < 30 || !symbolSafe(frame)) { finish("Symbolprüfung nicht verfügbar oder Ansicht geschützt"); return }
        val candidates = frame.nodes.indices.filter { frame.nodes[it].clickable && !frame.nodes[it].editable }
        if (candidates.isEmpty() || candidates.size > 80) { finish("Kein eindeutig bedienbares Symbol erkannt"); return }
        val token = generation
        symbolPending = true; message = "Vergleiche gelerntes Symbol lokal mit dem aktuellen Bildschirm"
        takeScreenshot(Display.DEFAULT_DISPLAY, mainExecutor, object : TakeScreenshotCallback {
            override fun onFailure(errorCode: Int) { if (token == generation) finish("Symbol-Screenshot nicht verfügbar; nichts angetippt") }
            override fun onSuccess(result: ScreenshotResult) {
                val buffer = result.hardwareBuffer
                val wrapped = Bitmap.wrapHardwareBuffer(buffer, result.colorSpace)
                val original = wrapped?.copy(Bitmap.Config.ARGB_8888, false)
                wrapped?.recycle(); buffer.close()
                if (original == null) { if (token == generation) finish("Symbol-Screenshot nicht lesbar"); return }
                if (token != generation || observation != frame || !symbolSafe(frame)) {
                    original.recycle(); if (token == generation) finish("Ansicht geändert; Symbolprüfung verworfen"); return
                }
                Thread {
                    val matched = runCatching {
                        val factor = minOf(1.0, 720.0 / original.width)
                        val image = Bitmap.createScaledBitmap(original, (original.width * factor).toInt(), (original.height * factor).toInt(), true)
                        try {
                            val boxes = candidates.map { index -> bounds[index].let { b -> SymbolBox((b.left * factor).toInt(), (b.top * factor).toInt(), (b.right * factor).toInt(), (b.bottom * factor).toInt()) } }
                            WorkflowSymbolMatch.match(learned.pattern, WorkflowSymbols.gray(image), image.width, image.height, boxes)?.let { candidates[it] }
                        } finally { if (image !== original) image.recycle() }
                    }.getOrNull()
                    original.recycle()
                    handler.post {
                        if (token != generation) return@post
                        symbolPending = false
                        if (observation != frame || !symbolSafe(frame)) { finish("Ansicht geändert; Symbolprüfung verworfen"); return@post }
                        if (matched == null) { finish("Symbol fehlt oder ist nicht eindeutig. Bitte erneut erklären; nichts angetippt."); return@post }
                        symbolMatch = frame to matched; symbolBounds = bounds; symbolMatchedAt = SystemClock.elapsedRealtime()
                    }
                }.start()
            }
        })
    }
    private fun captureScreen(token: Int, window: Int) {
        if (Build.VERSION.SDK_INT < 30) { message = "Direkte Screenshots benötigen Android 11; Bildauswahl verwenden"; return }
        val app = selected
        fun currentSafe(): Boolean {
            if (app == packageName && !WorkflowSelfTestActivity.active) return false
            val root = rootInActiveWindow ?: return false
            if (root.packageName?.toString() != app || root.windowId != window ||
                (getSystemService(KEYGUARD_SERVICE) as KeyguardManager).isKeyguardLocked) return false
            var checked = 0
            fun safe(n: AccessibilityNodeInfo, depth: Int): Boolean {
                if (++checked > 400 || depth > 30 || n.childCount > 100 || n.isPassword) return false
                val text = n.text?.toString().orEmpty() + " " + n.contentDescription?.toString().orEmpty()
                if (LocalWorkflow.protected(WorkflowFrame(app, window, listOf(WorkflowNode(text, "", false, false))))) return false
                return (0 until n.childCount).all { i -> n.getChild(i)?.let { safe(it, depth + 1) } ?: false }
            }
            return safe(root, 0)
        }
        if (!currentSafe()) { message = "Screenshot abgebrochen: Ansicht nicht mehr eindeutig"; return }
        takeScreenshot(Display.DEFAULT_DISPLAY, mainExecutor, object : TakeScreenshotCallback {
            override fun onFailure(errorCode: Int) { if (token == generation) message = "Screenshot nicht verfügbar ($errorCode); Bildauswahl verwenden" }
            override fun onSuccess(result: ScreenshotResult) {
                val buffer = result.hardwareBuffer
                val wrapped = Bitmap.wrapHardwareBuffer(buffer, result.colorSpace)
                val bitmap = wrapped?.copy(Bitmap.Config.ARGB_8888, false)
                wrapped?.recycle(); buffer.close()
                if (bitmap == null) return
                // Window may have changed while Android captured it. Never retain that image.
                if (token != generation || !currentSafe()) { bitmap.recycle(); return }
                val reader = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
                reader.process(InputImage.fromBitmap(bitmap, 0)).addOnSuccessListener {
                    if (token == generation && currentSafe()) { screenshotText = it.text.take(20_000); message = "Screenshot lokal gelesen · Text ist keine Handlungsanweisung" }
                }.addOnFailureListener { if (token == generation) message = "Screenshot-Texterkennung fehlgeschlagen" }
                    .addOnCompleteListener { reader.close(); bitmap.recycle() }
            }
        })
    }
}
