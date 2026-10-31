package ch.bob.degirocompanion

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.app.KeyguardManager
import android.content.Context
import android.graphics.Path
import android.graphics.Rect
import android.os.Build
import android.os.PowerManager
import android.os.SystemClock
import android.view.Display
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo

/** Only the already validated, stable ZERO node of a locally confirmed empty-field test.
 * No remembered coordinates, alternate targets, fallback click, retries or input reads.
 * All checks run before dispatch. Existing touch/window interruption handling stays active. */
internal fun AccessibilityService.dispatchPinTestZero(node: AccessibilityNodeInfo, expectedBounds: Rect,
    expectedWindow: Int, completed: (Boolean) -> Unit): Boolean {
    fun active() = PinReadinessProbe.running && PinReadinessProbe.exerciseArmed &&
        !PhoneRemote.active() && !MorningReadRun.running && !GoldSearchRun.running &&
        !ProductReadRequest.active(SystemClock.elapsedRealtime()) &&
        getSharedPreferences("product_reader", Context.MODE_PRIVATE).getBoolean("enabled", false) &&
        (getSystemService(Context.POWER_SERVICE) as PowerManager).isInteractive &&
        !(getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager).isKeyguardLocked
    fun allowed(n: AccessibilityNodeInfo) = n.packageName?.toString() == ProductScreenEvidence.PACKAGE &&
        n.windowId == expectedWindow && n.isVisibleToUser && !n.isPassword && !n.isEditable &&
        !(Build.VERSION.SDK_INT >= 34 && n.isAccessibilityDataSensitive)
    fun validZero() = node.refresh() && allowed(node) && node.isEnabled && node.isClickable &&
        node.actionList.any { it.id == AccessibilityNodeInfo.ACTION_CLICK } &&
        (PinKeypadPolicy.digit(node.text) ?: PinKeypadPolicy.digit(node.contentDescription)) == 0 &&
        Rect().also { node.getBoundsInScreen(it) } == expectedBounds
    if (!active() || !validZero()) return false
    val root = rootInActiveWindow ?: return false
    try {
        if (!allowed(root)) return false
        val screen = Rect().also { root.getBoundsInScreen(it) }
        val point = SearchTapPolicy.center(
            SearchTapPolicy.Box(expectedBounds.left, expectedBounds.top, expectedBounds.right, expectedBounds.bottom),
            SearchTapPolicy.Box(screen.left, screen.top, screen.right, screen.bottom)) ?: return false
        val currentWindows = windows
        try {
            val app = currentWindows.singleOrNull { it.id == expectedWindow && it.isActive && it.isFocused &&
                it.type == AccessibilityWindowInfo.TYPE_APPLICATION } ?: return false
            if (Build.VERSION.SDK_INT >= 30 && app.displayId != Display.DEFAULT_DISPLAY) return false
            if (currentWindows.any { w -> w.id != app.id && w.layer >= app.layer &&
                    Rect().also { w.getBoundsInScreen(it) }.contains(point.first, point.second) }) return false
        } finally { currentWindows.forEach { it.recycle() } }
        if (!active() || !validZero()) return false
        val foreground = rootInActiveWindow
        val same = foreground?.let { allowed(it) } == true
        foreground?.recycle()
        if (!same) return false
        val path = Path().apply { moveTo(point.first.toFloat(), point.second.toFloat()) }
        val gesture = GestureDescription.Builder().addStroke(GestureDescription.StrokeDescription(path, 0, 60)).build()
        return dispatchGesture(gesture, object : AccessibilityService.GestureResultCallback() {
            override fun onCompleted(gestureDescription: GestureDescription?) { completed(true) }
            override fun onCancelled(gestureDescription: GestureDescription?) { completed(false) }
        }, null)
    } finally { root.recycle() }
}
