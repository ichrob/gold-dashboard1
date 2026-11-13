package ch.bob.degirocompanion
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Non-exported, one-shot result capability; never receives local escrow prompts. */
class TermuxMaintenanceResultReceiver:BroadcastReceiver() {
    override fun onReceive(context:Context,intent:Intent?) {
        if(intent?.action==TermuxMaintenance.RESULT_ACTION)TermuxMaintenance.receive(intent)
    }
}
