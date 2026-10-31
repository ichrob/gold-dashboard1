package ch.bob.degirocompanion

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.Context
import android.content.pm.ApplicationInfo
import android.graphics.Path
import android.graphics.Rect
import android.os.Build
import android.os.SystemClock
import android.view.Display
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo

/** Local-only exact dialog matching. No input traversal, screenshots or generic back. */
internal class LocalLoginDialogs {
    private val budget = LoginDialogBudget()
    var unrecognizedCheck: LoginDialogCheck? = null
        private set
    private val started = SystemClock.elapsedRealtime()
    private var unknownSince = 0L
    private var postSince = 0L
    private var homeSince = 0L
    private var pending = false
    private val queries = listOf("PassCode", "TouchID", "Face/Touch ID",
        "Abbrechen", "Cancel", "Schließen", "Bestätigen", "DEGIRO", "Fingerabdruck", "fingerprint",
        "Märkte", "News", "Terminkalender", "Favoriten", "Portfolio")
    private fun bounds(n: AccessibilityNodeInfo) = Rect().also { n.getBoundsInScreen(it) }
    private fun safe(n: AccessibilityNodeInfo, pkg: String, window: Int) = n.isVisibleToUser &&
        n.packageName?.toString() == pkg && n.windowId == window && !n.isPassword && !n.isEditable &&
        !(Build.VERSION.SDK_INT >= 34 && n.isAccessibilityDataSensitive)
    // Matched nodes are usable only if their entire ancestor chain is accessible in this root.
    private fun inRoot(n: AccessibilityNodeInfo, root: AccessibilityNodeInfo, pkg: String): Boolean {
        var current: AccessibilityNodeInfo? = AccessibilityNodeInfo.obtain(n)
        try {
            repeat(30) {
                val item = current ?: return false
                if (!safe(item, pkg, root.windowId)) return false
                if (item == root) return true
                val parent = item.parent
                item.recycle(); current = parent
            }
            return false
        } finally { current?.recycle() }
    }
    private fun ownsNegative(target: AccessibilityNodeInfo, root: AccessibilityNodeInfo, pkg: String,
        negatives: Set<String>): Boolean {
        var current: AccessibilityNodeInfo? = AccessibilityNodeInfo.obtain(target)
        var found = false
        try {
            repeat(3) {
                val node = current ?: return false
                if (!node.refresh() || !inRoot(node, root, pkg) || !node.isEnabled) return false
                val labels = listOf(LoginDialogPolicy.normalize(node.text), LoginDialogPolicy.normalize(node.contentDescription)).filter { it.isNotEmpty() }
                if (labels.any { it !in negatives }) return false
                found = found || labels.isNotEmpty()
                if (node.childCount == 0) return found
                if (node.childCount != 1) return false
                val child = node.getChild(0)
                node.recycle(); current = child
            }
            return false
        } finally { current?.recycle() }
    }
    private fun fail(code: String): Boolean { PinReadinessProbe.finishLogin(code); return true }
    /** true consumes this tick, including unknown/blocked dialogs. */
    fun inspect(service: AccessibilityService, afterEntry: Boolean): Boolean {
        if (!PinReadinessProbe.loginDialogsAllowed) return false
        val now = SystemClock.elapsedRealtime()
        if (afterEntry && postSince == 0L) postSince = now
        if (afterEntry && now - postSince >= 15_000) return fail("LOCAL_PIN_RESULT_UNVERIFIED")
        if (budget.expired(now)) return fail("LOCAL_PIN_DIALOG_UNCHANGED")
        if (pending) return true
        val root = service.rootInActiveWindow ?: run { homeSince = 0L; return true }
        val nodes = mutableListOf<AccessibilityNodeInfo>()
        try {
            val pkg = root.packageName?.toString().orEmpty()
            val degiro = pkg == ProductScreenEvidence.PACKAGE
            val owner = when (pkg) {
                ProductScreenEvidence.PACKAGE -> LoginDialogCheck.Owner.DEGIRO
                "com.android.systemui" -> LoginDialogCheck.Owner.SYSTEM_UI
                "com.samsung.android.biometrics.app.setting" -> LoginDialogCheck.Owner.SAMSUNG_BIOMETRICS
                else -> LoginDialogCheck.Owner.OTHER
            }
            val trustedSystem = pkg in setOf("com.android.systemui", "com.samsung.android.biometrics.app.setting") &&
                runCatching { service.packageManager.getApplicationInfo(pkg, 0).flags and ApplicationInfo.FLAG_SYSTEM != 0 }.getOrDefault(false)
            if (!degiro && !trustedSystem) {
                if (!afterEntry && pkg == service.packageName && now - started < 3_000) return true
                if (budget.awaitingFingerprintReturn(now, afterEntry)) {
                    budget.resetObservation(); homeSince = 0L
                    return true
                }
                unrecognizedCheck = LoginDialogCheck.ownerRejected(owner, afterEntry, ownerContext(service, root, now))
                return fail("LOCAL_PIN_DIALOG_UNRECOGNIZED")
            }
            if (!safe(root, pkg, root.windowId)) return fail("LOCAL_PIN_DIALOG_BLOCKED")
            val shown = service.windows
            val foreground: AccessibilityWindowInfo
            val associated: Boolean
            try {
                foreground = shown.singleOrNull { it.id == root.windowId && it.isActive && it.isFocused }
                    ?.let { AccessibilityWindowInfo.obtain(it) } ?: return true
                associated = degiro || shown.any { w ->
                    if (w.id == root.windowId || w.layer >= foreground.layer || w.type != AccessibilityWindowInfo.TYPE_APPLICATION) false
                    else { val below = w.root; try { below?.packageName?.toString() == ProductScreenEvidence.PACKAGE } finally { below?.recycle() } }
                }
            } finally { shown.forEach { it.recycle() } }
            try {
                for (query in queries) {
                    // Query known static labels only. Never enumerate fields or inspect event text.
                    val matches = root.findAccessibilityNodeInfosByText(query).orEmpty()
                    for (n in matches) {
                        if (nodes.size < 80 && inRoot(n, root, pkg) && nodes.none { it == n }) nodes += n else n.recycle()
                    }
                }
                val labels = nodes.flatMap { listOf(LoginDialogPolicy.normalize(it.text), LoginDialogPolicy.normalize(it.contentDescription)) }.toSet()
                val kind = LoginDialogPolicy.identify(degiro, trustedSystem, associated, labels, afterEntry, owner)
                if (kind == null) {
                    budget.resetObservation()
                    val waiting = budget.waiting
                    val suspicious = trustedSystem || labels.any { it in setOf("Abbrechen", "Cancel", "Schließen", LoginDialogPolicy.OFFER, LoginDialogPolicy.NOTICE) }
                    if (suspicious) {
                        homeSince = 0L
                        if (unknownSince == 0L) unknownSince = now
                        if (now - unknownSince >= 6_000) {
                            unrecognizedCheck = LoginDialogCheck.markersRejected(owner, afterEntry, trustedSystem, associated, labels)
                            return fail("LOCAL_PIN_DIALOG_UNRECOGNIZED")
                        }
                        return true
                    }
                    unknownSince = 0L
                    if (waiting != null) budget.gone()
                    if (afterEntry) {
                        val home = degiro && labels.containsAll(setOf("Märkte", "News", "Terminkalender", "Favoriten", "Portfolio"))
                        if (!home) homeSince = 0L
                        else if (homeSince == 0L) homeSince = now
                        else if (now - homeSince >= 1_000) return fail("LOCAL_PIN_HOME_VISIBLE")
                        return true
                    }
                    return false
                }
                unknownSince = 0L; homeSince = 0L
                if (budget.waiting != null) {
                    if (budget.waiting == kind) return true
                    budget.gone()
                }
                val negatives = if (kind == LoginDialogPolicy.Kind.NOTICE) setOf("Schließen") else setOf("Abbrechen", "Cancel")
                val candidates = mutableListOf<AccessibilityNodeInfo>()
                try {
                    for (label in nodes.filter { LoginDialogPolicy.normalize(it.text) in negatives || LoginDialogPolicy.normalize(it.contentDescription) in negatives }) {
                        var target: AccessibilityNodeInfo? = AccessibilityNodeInfo.obtain(label)
                        try {
                            // A lone text child may belong to its button; never widen to a shared container.
                            for (depth in 0..2) {
                                val n = target ?: break
                                if (!inRoot(n, root, pkg) || !n.isEnabled) break
                                val ownLabels = listOf(LoginDialogPolicy.normalize(n.text), LoginDialogPolicy.normalize(n.contentDescription)).filter { it.isNotEmpty() }
                                if (ownLabels.any { it !in negatives }) break
                                if (n.isClickable && n.actionList.any { it.id == AccessibilityNodeInfo.ACTION_CLICK }) {
                                    if (candidates.none { it == n }) candidates += AccessibilityNodeInfo.obtain(n)
                                    break
                                }
                                val parent = n.parent ?: break
                                if (parent.childCount != 1) { parent.recycle(); break }
                                n.recycle(); target = parent
                            }
                        } finally { target?.recycle() }
                    }
                    val target = candidates.singleOrNull() ?: return fail("LOCAL_PIN_DIALOG_BLOCKED")
                    val box = bounds(target)
                    val signature = "$kind:${root.windowId}:${target.viewIdResourceName}:${target.className}:$box"
                    if (!budget.stable(signature, now)) return true
                    if (!budget.reserve(kind, now)) return fail("LOCAL_PIN_DIALOG_REPEATED")
                    // Re-read the complete fixed-label match immediately before the one action.
                    if (!target.refresh() || !ownsNegative(target, root, pkg, negatives) || bounds(target) != box || !target.isEnabled || !target.isClickable || target.actionList.none { it.id == AccessibilityNodeInfo.ACTION_CLICK })
                        return fail("LOCAL_PIN_DIALOG_BLOCKED")
                    val currentLabels = nodes.filter { it.refresh() && inRoot(it, root, pkg) }.flatMap {
                        listOf(LoginDialogPolicy.normalize(it.text), LoginDialogPolicy.normalize(it.contentDescription)) }.toSet()
                    if (LoginDialogPolicy.identify(degiro, trustedSystem, associated, currentLabels, afterEntry, owner) != kind)
                        return fail("LOCAL_PIN_DIALOG_BLOCKED")
                    if (!dispatch(service, target, root, foreground, box, trustedSystem)) return fail("LOCAL_PIN_DIALOG_ACTION_FAILED")
                    budget.accepted(kind)
                    return true
                } finally { candidates.forEach { it.recycle() } }
            } finally { foreground.recycle() }
        } finally { nodes.forEach { it.recycle() }; root.recycle() }
    }
    // Failure-only metadata: do not query labels or search for actionable nodes in another app.
    private fun ownerContext(service: AccessibilityService, root: AccessibilityNodeInfo, now: Long): LoginOwnerContext {
        var focusedKind = LoginOwnerContext.RootKind.UNAVAILABLE
        var sameWindow = false
        runCatching {
            val shown = service.windows
            try {
                val focused = shown.filter { it.isActive && it.isFocused }
                if (focused.size > 1) focusedKind = LoginOwnerContext.RootKind.AMBIGUOUS
                else focused.singleOrNull()?.let { window ->
                    sameWindow = window.id == root.windowId
                    val focusedRoot = window.root
                    try {
                        if (focusedRoot != null) focusedKind = LoginOwnerContext.classify(
                            focusedRoot.packageName?.toString(), service.packageName)
                    } finally { focusedRoot?.recycle() }
                }
            } finally { shown.forEach { it.recycle() } }
        }
        val pkg = root.packageName?.toString()
        val kind = LoginOwnerContext.classify(pkg, service.packageName)
        // The OTHER category hid the remaining cause. Record only this root's Android
        // package metadata; no app inventory, labels or field contents are inspected.
        val packageEvidence = if (kind == LoginOwnerContext.RootKind.OTHER && LoginPackageEvidence.validName(pkg)) {
            val info = runCatching { service.packageManager.getApplicationInfo(pkg!!, 0) }.getOrNull()
            val resolution = when {
                info == null || info.packageName != pkg -> LoginPackageEvidence.Resolution.NOT_RESOLVED
                info.flags and ApplicationInfo.FLAG_SYSTEM != 0 -> LoginPackageEvidence.Resolution.INSTALLED_SYSTEM
                else -> LoginPackageEvidence.Resolution.INSTALLED_APP
            }
            LoginPackageEvidence.create(pkg, resolution)
        } else null
        return LoginOwnerContext(kind, focusedKind, sameWindow, budget.fingerprintProgress(now), packageEvidence)
    }
    private fun dispatch(service: AccessibilityService, target: AccessibilityNodeInfo, root: AccessibilityNodeInfo,
        foreground: AccessibilityWindowInfo, box: Rect, system: Boolean): Boolean {
        if (!PinReadinessProbe.loginDialogsAllowed || !LocalPinVault.available(service) || PhoneRemote.active() ||
            MorningReadRun.running || GoldSearchRun.running || ProductReadRequest.active(SystemClock.elapsedRealtime()) ||
            !service.getSharedPreferences("product_reader", Context.MODE_PRIVATE).getBoolean("enabled", false)) return false
        val screen = bounds(root)
        val point = SearchTapPolicy.center(SearchTapPolicy.Box(box.left, box.top, box.right, box.bottom),
            SearchTapPolicy.Box(screen.left, screen.top, screen.right, screen.bottom)) ?: return false
        val shown = service.windows
        try {
            val current = shown.singleOrNull { it.id == foreground.id && it.isActive && it.isFocused } ?: return false
            if (Build.VERSION.SDK_INT >= 30 && current.displayId != Display.DEFAULT_DISPLAY) return false
            if (shown.any { it.id != current.id && it.layer >= current.layer && Rect().also { r -> it.getBoundsInScreen(r) }.contains(point.first, point.second) }) return false
        } finally { shown.forEach { it.recycle() } }
        val active = service.rootInActiveWindow ?: return false
        try { if (active.windowId != root.windowId || active.packageName != root.packageName || !safe(active, root.packageName.toString(), root.windowId)) return false }
        finally { active.recycle() }
        // System dialogs: only the exposed negative action, never a coordinate fallback.
        if (system) return target.performAction(AccessibilityNodeInfo.ACTION_CLICK)
        pending = true
        val run = PinReadinessProbe.reportId
        val path = Path().apply { moveTo(point.first.toFloat(), point.second.toFloat()) }
        val accepted = service.dispatchGesture(GestureDescription.Builder().addStroke(GestureDescription.StrokeDescription(path, 0, 60)).build(),
            object : AccessibilityService.GestureResultCallback() {
                override fun onCompleted(gestureDescription: GestureDescription?) { pending = false }
                override fun onCancelled(gestureDescription: GestureDescription?) {
                    pending = false
                    if (PinReadinessProbe.running && PinReadinessProbe.reportId == run) fail("LOCAL_PIN_DIALOG_ACTION_FAILED")
                }
            }, null)
        if (!accepted) pending = false
        return accepted
    }
}
