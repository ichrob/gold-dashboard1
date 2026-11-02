package ch.bob.degirocompanion

import android.content.Context
import android.os.Handler
import android.os.Looper
import org.json.JSONObject
import java.util.concurrent.Executors

/** Transfers previously saved product observations only; never navigates DEGIRO. */
internal object ProductDetailDelivery {
    private val network=Executors.newSingleThreadExecutor()
    private val handler=Handler(Looper.getMainLooper())
    private const val MAX_PER_ATTEMPT=120
    private var busy=false

    private fun pref(c:Context)=c.getSharedPreferences("detail_delivery_status",Context.MODE_PRIVATE)
    fun status(c:Context):String=pref(c).getString("status","").orEmpty()
    private fun record(c:Context, message:String) {
        // Local privacy-safe fixed descriptions; no HTTP body, original prices,
        // access tokens, ISINs or images are included in status/telemetry.
        pref(c).edit().putString("status",message).apply()
    }

    private enum class Outcome { SAVED, UNAVAILABLE, NOT_READY, NOT_CONFIRMED }
    private data class Progress(var saved:Int=0, var deferred:Int=0)

    fun start(c:Context, completed:(()->Unit)? = null) {
        if(busy) { completed?.invoke();return }
        if(MorningReadRun.running || !PhoneDiagnostics.paired(c)) {
            record(c,"Detailübertragung nicht gestartet: Leselauf läuft oder Diagnosefreigabe fehlt. Alle lokalen Berichte bleiben erhalten.")
            completed?.invoke();return
        }
        busy=true
        next(c.applicationContext,mutableSetOf(),Progress(),completed)
    }

    private fun finish(c:Context,p:Progress,completed:(()->Unit)?,limited:Boolean=false) {
        busy=false
        record(c,when {
            limited -> "Übertragungsprüfung begrenzt. ${p.saved} Bericht(e) bestätigt, ${p.deferred} ältere zurückgestellt. Alle übrigen Berichte bleiben lokal gespeichert."
            p.deferred>0 -> "${p.saved} Detailbericht(e) von Bob bestätigt; ${p.deferred} ältere ohne gültigen ursprünglichen Listen-Nachweis zurückgestellt. Originale bleiben lokal gespeichert."
            p.saved>0 -> "${p.saved} Detailbericht(e) von Bob bestätigt. Kein weiterer offener nachgewiesener Listenbericht."
            else -> "Keine neuen Detailberichte übertragen. Bestehende Originalbeobachtungen bleiben erhalten."
        })
        completed?.invoke()
    }

    private fun next(c:Context,visited:MutableSet<String>,p:Progress,completed:(()->Unit)?) {
        if(!PhoneDiagnostics.paired(c) || MorningReadRun.running) {
            busy=false
            record(c,"Weitere Detailübertragung angehalten; Diagnosefreigabe oder abgeschlossener Leselauf erforderlich. Originale bleiben lokal.")
            completed?.invoke();return
        }
        if(visited.size>=MAX_PER_ATTEMPT) { finish(c,p,completed,limited=true);return }
        val entry=MorningReadRun.pendingForDelivery(c,visited) ?: run {
            finish(c,p,completed);return
        }
        visited.add(entry.first)
        val run=runCatching { JSONObject(entry.second) }.getOrNull()
        val batch=run?.optString("listBatchId").orEmpty()
        if(run==null || !batch.matches(Regex("[a-f0-9]{32}"))) {
            // Legacy browser-saved reports are intentionally NOT reattached to
            // newer Android screenshots. They remain in the original outbox.
            p.deferred++
            next(c,visited,p,completed)
            return
        }
        record(c,"Vorhandene Detailberichte werden anhand ihres ursprünglichen Listen-Nachweises geprüft.")
        network.execute {
            val outcome=runCatching {
                val status=PhoneDiagnostics.listStatus(c,JSONObject().put("batchId",batch))
                val receipt=status.optJSONObject("import")
                when(DetailBatchReceiptPolicy.decide(batch,status.optString("batchId"),
                    receipt?.optString("stage"))) {
                    DetailBatchReceiptPolicy.Decision.DEFER_UNAVAILABLE -> Outcome.UNAVAILABLE
                    DetailBatchReceiptPolicy.Decision.RETRY_LATER -> Outcome.NOT_READY
                    DetailBatchReceiptPolicy.Decision.UPLOAD -> {
                        val response=PhoneDiagnostics.uploadDetails(c,JSONObject().put("batchId",batch).put("run",run))
                        if(response.optBoolean("saved") &&
                            response.optString("batchId")==run.getString("batchId") &&
                            response.optInt("revision")==run.getInt("revision"))
                            Outcome.SAVED else Outcome.NOT_CONFIRMED
                    }
                }
            }.getOrDefault(Outcome.NOT_CONFIRMED)
            handler.post {
                when(outcome) {
                    Outcome.SAVED -> {
                        // Only the exact server-confirmed revision is removed.
                        if(MorningReadRun.acknowledge(c,run.getString("batchId"),run.getInt("revision"))) {
                            p.saved++
                            next(c,visited,p,completed)
                        } else {
                            busy=false
                            record(c,"Serverbestätigung vorhanden, aber lokaler Versionsabgleich fehlgeschlagen. Original bleibt erhalten.")
                            completed?.invoke()
                        }
                    }
                    Outcome.UNAVAILABLE -> {
                        // Old batches may have expired or belong to a different
                        // paired key. Preserve evidence and try other entries.
                        p.deferred++
                        next(c,visited,p,completed)
                    }
                    else -> {
                        busy=false
                        record(c,if(outcome==Outcome.NOT_READY)
                            "Ursprünglicher Listen-Nachweis noch nicht abgeschlossen. Detailbericht bleibt lokal für einen späteren Versuch."
                            else "Detailübertragung nicht bestätigt. Kopplung oder Listen-Nachweis prüfen; Originalbericht bleibt lokal.")
                        completed?.invoke()
                    }
                }
            }
        }
    }
}
