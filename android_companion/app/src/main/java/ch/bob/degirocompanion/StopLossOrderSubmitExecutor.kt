package ch.bob.degirocompanion

import android.os.Build
import android.view.accessibility.AccessibilityNodeInfo

/**
 * Dedicated irreversible action: one exact broker button only, after a fresh
 * local owner approval and a fresh complete broker form re-read. No retries.
 */
internal object StopLossOrderSubmitExecutor {
    fun executeOnce(target: AccessibilityNodeInfo, observedLabel: String): Boolean =
        target.packageName?.toString() == "nl.degiro.trader" &&
            observedLabel.trim().equals("Order platzieren", ignoreCase = true) &&
            target.isVisibleToUser && target.isEnabled && target.isClickable &&
            !target.isPassword &&
            (Build.VERSION.SDK_INT < 34 || !target.isAccessibilityDataSensitive) &&
            target.performAction(AccessibilityNodeInfo.ACTION_CLICK)
}
