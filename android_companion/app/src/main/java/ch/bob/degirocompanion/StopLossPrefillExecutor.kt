package ch.bob.degirocompanion

import android.os.Build
import android.os.Bundle
import android.view.accessibility.AccessibilityNodeInfo

/**
 * The ONLY broker form actions used by the owner-started Stop-Loss helper.
 * Kept separate from the read-only product reader's audited action budget.
 * All actions fail closed; there is deliberately no submit, buy or order API.
 */
internal object StopLossPrefillExecutor {
    private const val DEGIRO = "nl.degiro.trader"
    private val valuePattern = Regex("[0-9]{1,7}(?:,[0-9]{2})?")

    fun execute(
        target: AccessibilityNodeInfo,
        observedLabel: String,
        decision: StopLossPrefillPolicy.Decision,
        stage: StopLossPrefillPolicy.Stage
    ): Boolean {
        if (!target.isVisibleToUser || !target.isEnabled || target.isPassword ||
            target.packageName?.toString() != DEGIRO ||
            (Build.VERSION.SDK_INT >= 34 && target.isAccessibilityDataSensitive)) return false

        return when(decision.kind) {
            StopLossPrefillPolicy.Kind.CLICK -> {
                // Explicitly allow only: detail -> VERKAUF, order type dropdown,
                // and the Stop Loss option. Never the final order button.
                val allowed = when(stage) {
                    StopLossPrefillPolicy.Stage.OPEN_FORM ->
                        observedLabel.equals("VERKAUF", ignoreCase=true)
                    StopLossPrefillPolicy.Stage.ORDER_TYPE -> observedLabel == "Limit"
                    StopLossPrefillPolicy.Stage.CHOOSE_STOP -> observedLabel == "Stop Loss"
                    else -> false
                }
                allowed && target.isClickable &&
                    target.performAction(AccessibilityNodeInfo.ACTION_CLICK)
            }
            StopLossPrefillPolicy.Kind.WRITE ->
                stage in setOf(StopLossPrefillPolicy.Stage.WRITE_STOP,
                    StopLossPrefillPolicy.Stage.WRITE_QUANTITY) &&
                target.isEditable && valuePattern.matches(decision.text) &&
                target.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, Bundle().apply {
                    putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,
                        decision.text)
                })
            else -> false
        }
    }
}
