package ch.bob.degirocompanion

import android.content.Context
import android.os.Handler
import android.os.Looper
import org.json.JSONObject
import java.util.concurrent.Executors

/** Transfers saved observations only. Never starts or resumes a screen read. */
internal object ProductDetailDelivery {
    private val network=Executors.newSingleThreadExecutor()
    private val handler=Handler(Looper.getMainLooper())
    private var busy=false
    private fun pref(c:Context)=c.getSharedPreferences("detail_delivery_status",Context.MODE_PRIVATE)
    fun status(c:Context):String=pref(c).getString("status","").orEmpty()
    private fun record(c:Context,code:String) {
        // Fixed, local-only status. No original quotes, product identifiers,
        // secrets or server response text enter telemetry.
        pref(c).edit().putString("status",when(code) {
            "SENDING" -> "Gespeicherte Detailbeobachtungen werden an Bob übertragen."
            "SAVED" -> "Gespeicherte Detailbeobachtungen von Bob bestätigt."
            else -> "Detailübertragung noch nicht bestätigt. Die Originalbeobachtungen bleiben gespeichert."
        }).apply()
    }
    fun start(c:Context, completed:(()->Unit)? = null) {
        if(busy || MorningReadRun.running || !PhoneDiagnostics.paired(c)) { completed?.invoke();return }
        val raw=MorningReadRun.pending(c)
        if(raw==null) { completed?.invoke();return }
        val run=runCatching { JSONObject(raw) }.getOrNull()
        if(run==null) { completed?.invoke();return }
        val batch=run.optString("listBatchId")
        if(!batch.matches(Regex("[a-f0-9]{32}"))) { completed?.invoke();return }
        busy=true
        record(c,"SENDING")
        network.execute {
            val response=runCatching {
                PhoneDiagnostics.uploadDetails(c.applicationContext,JSONObject().put("batchId",batch).put("run",run))
            }.getOrNull()
            handler.post {
                busy=false
                val confirmed=response!=null && response.optBoolean("saved") && response.optString("batchId")==run.optString("batchId") && response.optInt("revision")==run.optInt("revision")
                if(confirmed && MorningReadRun.acknowledge(c,run.getString("batchId"),run.getInt("revision"))) {
                    record(c,"SAVED")
                    // Bounded outbox; acknowledge only the exact saved revision.
                    start(c,completed)
                } else {
                    record(c,"NOT_CONFIRMED")
                    completed?.invoke()
                }
                // Failed sends remain durable; the existing diagnostic job retries.
            }
        }
    }
}
