package ch.bob.degirocompanion

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * Private one-shot callback for CHECK only. Never inspect or retain stdout,
 * stderr, session transcript, error text or Termux files. LOCAL_ESCROW never
 * sends a PendingIntent at all. This receiver is not exported.
 */
class TermuxCheckResultReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent?) {
        if (intent?.action != TermuxBridge.CHECK_RESULT_ACTION) return
        val result = intent.getBundleExtra("result")
        val err = if (result?.containsKey("err") == true) result.getInt("err") else null
        val exit = if (result?.containsKey("exitCode") == true)
            result.getInt("exitCode") else null
        TermuxBridge.recordCheck(context,
            TermuxBridge.classifyCheckResult(err, exit))
    }
}
