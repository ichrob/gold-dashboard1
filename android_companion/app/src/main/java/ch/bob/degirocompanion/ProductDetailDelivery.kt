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
    fun start(c:Context, completed:(()->Unit)? = null) {
        if(busy || MorningReadRun.running || !PhoneDiagnostics.paired(c)) { completed?.invoke();return }
        val raw=MorningReadRun.pending(c)
        if(raw==null) { completed?.invoke();return }
        val run=runCatching { JSONObject(raw) }.getOrNull()
        if(run==null) { completed?.invoke();return }
        val batch=run.optString("listBatchId")
        if(!batch.matches(Regex("[a-f0-9]{32}"))) { completed?.invoke();return }
        busy=true
        network.execute {
            val response=runCatching {
                PhoneDiagnostics.uploadDetails(c.applicationContext,JSONObject().put("batchId",batch).put("run",run))
            }.getOrNull()
            handler.post {
                busy=false
                val confirmed=response!=null && response.optBoolean("saved") && response.optString("batchId")==run.optString("batchId") && response.optInt("revision")==run.optInt("revision")
                if(confirmed && MorningReadRun.acknowledge(c,run.getString("batchId"),run.getInt("revision"))) {
                    // Bounded outbox; acknowledge only the exact saved revision.
                    start(c,completed)
                } else {
                    completed?.invoke()
                }
                // Failed sends remain durable; the existing diagnostic job retries.
            }
        }
    }
}
