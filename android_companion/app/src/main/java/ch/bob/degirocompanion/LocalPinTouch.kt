package ch.bob.degirocompanion

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.Context
import android.graphics.Path
import android.graphics.Rect
import android.os.Build
import android.os.SystemClock
import android.view.Display
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo

/** Only a reserved local-login digit on an original cached node. Never reads labels or input values. */
internal fun AccessibilityService.dispatchLocalPinTouch(node: AccessibilityNodeInfo, expected: Rect,
    expectedWindow: Int, completed: (Boolean) -> Unit): Boolean {
    val type = node.className?.toString()
    val id = node.viewIdResourceName
    fun active() = PinReadinessProbe.running && PinReadinessProbe.loginTouchExpected && LocalPinVault.available(this) &&
        !PhoneRemote.active() && !MorningReadRun.running && !GoldSearchRun.running &&
        !ProductReadRequest.active(SystemClock.elapsedRealtime()) &&
        getSharedPreferences("product_reader", Context.MODE_PRIVATE).getBoolean("enabled", false)
    fun allowed(n: AccessibilityNodeInfo) = n.packageName?.toString() == ProductScreenEvidence.PACKAGE &&
        n.windowId == expectedWindow && n.isVisibleToUser && !n.isPassword && !n.isEditable &&
        !(Build.VERSION.SDK_INT >= 34 && n.isAccessibilityDataSensitive)
    fun target() = node.refresh() && allowed(node) && node.isEnabled && node.isClickable &&
        node.className?.toString() == type && node.viewIdResourceName == id &&
        node.actionList.any { it.id == AccessibilityNodeInfo.ACTION_CLICK } && Rect().also { node.getBoundsInScreen(it) } == expected
    if (!active() || !target()) return false
    val root = rootInActiveWindow ?: return false
    try {
        if (!allowed(root)) return false
        val screen = Rect().also { root.getBoundsInScreen(it) }
        val point = SearchTapPolicy.center(SearchTapPolicy.Box(expected.left, expected.top, expected.right, expected.bottom),
            SearchTapPolicy.Box(screen.left, screen.top, screen.right, screen.bottom)) ?: return false
        val shown = windows
        try {
            val app = shown.singleOrNull { it.id == expectedWindow && it.isActive && it.isFocused &&
                it.type == AccessibilityWindowInfo.TYPE_APPLICATION } ?: return false
            if (Build.VERSION.SDK_INT >= 30 && app.displayId != Display.DEFAULT_DISPLAY) return false
            if (shown.any { w -> w.id != app.id && w.layer >= app.layer &&
                    Rect().also { w.getBoundsInScreen(it) }.contains(point.first, point.second) }) return false
        } finally { shown.forEach { it.recycle() } }
        if (!active() || !target()) return false
        val foreground = rootInActiveWindow
        val same = foreground?.let { allowed(it) } == true
        foreground?.recycle()
        if (!same) return false
        val path = Path().apply { moveTo(point.first.toFloat(), point.second.toFloat()) }
        return dispatchGesture(GestureDescription.Builder().addStroke(GestureDescription.StrokeDescription(path, 0, 60)).build(),
            object : AccessibilityService.GestureResultCallback() {
                override fun onCompleted(gestureDescription: GestureDescription?) { completed(true) }
                override fun onCancelled(gestureDescription: GestureDescription?) { completed(false) }
            }, null)
    } finally { root.recycle() }
}
