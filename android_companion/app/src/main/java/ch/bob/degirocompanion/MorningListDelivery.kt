package ch.bob.degirocompanion

import android.content.Context
import android.app.KeyguardManager
import android.os.PowerManager
import android.os.Handler
import android.os.Looper
import android.util.AtomicFile
import org.json.JSONObject
import java.io.File
import java.time.Instant
import java.util.concurrent.Executors

/** Durable image outbox. Retrying transport never authorizes a phone action. */
internal object MorningListDelivery {
    // Revision 12 captures missing edge rows after ten visible ISIN labels.
    // An older outbox must not prevent an explicit start from using that capture policy.
    private const val CAPTURE_REVISION = 12
    private val handler=Handler(Looper.getMainLooper())
    private val network=Executors.newSingleThreadExecutor()
    private var generation=0
    private var screenLease:PowerManager.WakeLock?=null
    var waiting=false
        private set(value) {
            field=value
            if(!value) {
                screenLease?.let { if(it.isHeld) it.release() }
                screenLease=null
            }
        }
    @Suppress("DEPRECATION")
    private fun keepScreenWhileWaiting(c:Context) {
        val power=c.getSystemService(Context.POWER_SERVICE) as PowerManager
        val keyguard=c.getSystemService(Context.KEYGUARD_SERVICE) as KeyguardManager
        val duration=ListWaitScreenPolicy.duration(PhoneRemote.active(),power.isInteractive,keyguard.isKeyguardLocked)
        if(duration==0L)return
        // No wake-up/unlock flags. Separate from the cancelled capture request;
        // every completed/cancelled wait releases this lease via waiting=false.
        runCatching {
            power.newWakeLock(PowerManager.SCREEN_DIM_WAKE_LOCK,"Bob:ListReceipt").also {
                screenLease=it;it.setReferenceCounted(false);it.acquire(duration)
            }
        }.onFailure {
            screenLease?.let { if(it.isHeld) it.release() };screenLease=null
            ProductReadDiagnostics.record(ProductReadDiagnostics.Outcome.SCREEN_HOLD_FAILED)
        }
    }
    /** Anonymized server recognition counts: never an accepted product list. */
    internal fun rejectedListHint(receipt:JSONObject?):String {
        val counts=receipt?.optJSONObject("verificationCounts") ?: return ""
        if(counts.optInt("version",-1)!=1 || counts.optInt("expectedRows",-1)!=10) return ""
        val recognized=counts.optInt("uniqueRows",-1)
        val images=counts.optInt("imagesTotal",-1)
        if(recognized !in 0..10 || images !in 1..4) return ""
        val conflict=counts.optInt("conflictingRows",0)>0
        return " · Diagnose: $recognized von 10 Produktzeilen vorläufig erkannt" +
            (if(conflict) ", widersprüchliche Zeilen vorhanden" else "") +
            ". Keine Produktfreigabe."
    }
    var onConfirmed:((List<SelectiveDetailPlan.Entry>,String)->Unit)?=null
    /** Local-only, owner-started diagnostic reads when exactly 9 of 10
     * complete original Gold list rows fail server validation. NEVER a list
     * confirmation, server detail plan, or trading permission. */
    var onProvisionalResearch:((List<String>)->Unit)?=null
    /** Same user-opened session only. Original rejected images are archived
     * by resume() before the fresh capture; no silent new session is started. */
    var onFreshCaptureRequired:(()->Unit)?=null
    private fun file(c:Context)=AtomicFile(File(c.filesDir,"morning-list-pending.json"))
    private fun prefs(c:Context)=c.getSharedPreferences("morning_list_delivery",Context.MODE_PRIVATE)
    fun status(c:Context)=prefs(c).getString("status","").orEmpty()
    private fun status(c:Context,text:String) { prefs(c).edit().putString("status",text).apply() }
    fun cancel() { generation++;waiting=false }
    fun save(c:Context,body:JSONObject) {
        val f=file(c);val stream=f.startWrite()
        try { stream.write(JSONObject(body.toString()).put("localRecognitionRevision",CAPTURE_REVISION).toString().toByteArray(Charsets.UTF_8));f.finishWrite(stream) }
        catch(e:Exception) { f.failWrite(stream);throw e }
    }
    fun resume(c:Context):Boolean {
        val body=runCatching { JSONObject(String(file(c).readFully(),Charsets.UTF_8)) }.getOrNull() ?: return false
        val images=body.optJSONArray("images") ?: return false
        if(body.optInt("localRecognitionRevision")<CAPTURE_REVISION) {
            // Only reached on a new user-started run. Keep the exact legacy
            // capture locally; do not let old recognition output monopolize
            // an updated reader's explicit fresh start.
            val batch=body.optString("batchId")
            if(!batch.matches(Regex("[a-f0-9]{32}"))) return false
            val archive=AtomicFile(File(c.filesDir,"morning-list-legacy-"+batch+".json"))
            val stream=archive.startWrite()
            try { stream.write(body.toString().toByteArray(Charsets.UTF_8));archive.finishWrite(stream) }
            catch(e:Exception) { archive.failWrite(stream);throw e }
            cancel();file(c).delete()
            status(c,"Frühere Aufnahme gesichert; aktualisierte lokale Erkennung startet neu.")
            return false
        }
        val age=runCatching { System.currentTimeMillis()-Instant.parse(images.getJSONObject(0).getString("at")).toEpochMilli() }.getOrDefault(Long.MAX_VALUE)
        val mode=MorningListResumePolicy.mode(age,body.optInt("resumeCount"),
            body.optBoolean("verificationFailed",false))
        if(mode==MorningListResumePolicy.Mode.NEW_LIST) {
            val batch=body.optString("batchId")
            if(!batch.matches(Regex("[a-f0-9]{32}"))) return false
            // Preserve each original separately; a later failed run must not
            // overwrite a previous capture. Delete only after atomic archival.
            val archive=AtomicFile(File(c.filesDir,"morning-list-previous-"+batch+".json"))
            val stream=archive.startWrite()
            try { stream.write(body.toString().toByteArray(Charsets.UTF_8));archive.finishWrite(stream) }
            catch(e:Exception) { archive.failWrite(stream);throw e }
            cancel();file(c).delete()
            status(c,"Frühere Aufnahme gesichert; neuer Listenlauf startet.")
            return false
        }
        // A new explicit, unlocked start is mandatory. Prior session IDs
        // never authorize a phone action or quote read.
        val resumes=body.optInt("resumeCount")+1
        body.put("sessionId",PhoneRemote.sessionId()).put("resumeCount",resumes)
        start(c,body,receiptOnly=mode==MorningListResumePolicy.Mode.CHECK_RECEIPT_ONLY,
            resumeSavedCapture=true)
        return true
    }
    fun start(c:Context,body:JSONObject,receiptOnly:Boolean=false,
              resumeSavedCapture:Boolean=false) {
        save(c,body);cancel();waiting=true
        keepScreenWhileWaiting(c)
        val id=++generation;val session=PhoneRemote.sessionId();val batch=body.getString("batchId")
        status(c,if(receiptOnly) "Gespeicherte Goldliste · nur Serverbestätigung prüfen."
            else "Listenbilder gespeichert · Übertragung und Serverprüfung laufen.")
        fun poll(attempt:Int,uploaded:Boolean) {
            if(id!=generation)return
            network.execute {
                val result=runCatching {
                    if(!uploaded) { check(PhoneRemote.active() && PhoneRemote.sessionId()==session);PhoneDiagnostics.uploadList(c,JSONObject(body.toString()).apply {
                        remove("resumeCount");remove("localRecognitionRevision");remove("verificationFailed")
                        // Captured candidate identity hints stay on this
                        // handset, never enter the authenticated 10-row API.
                        remove("localCandidates")
                    }) }
                    PhoneDiagnostics.listStatus(c,JSONObject().put("batchId",batch))
                }
                handler.post {
                    if(id!=generation)return@post
                    val response=result.getOrNull();val receipt=response?.optJSONObject("import")
                    if(response?.optString("batchId")==batch && receipt?.optString("stage")=="synced" && receipt.optInt("count")==10) {
                        waiting=false;file(c).delete()
                        val ids=response.optJSONArray("detailIsins")
                        val values=if(ids==null) null else (0 until ids.length()).map { ids.optString(it) }
                        val plan=values?.let { SelectiveDetailPlan.parse(response.optJSONArray("detailPlan"),it) }
                        if(PhoneRemote.active() && PhoneRemote.sessionId()==session && plan!=null && plan.isNotEmpty()) {
                            status(c,"✅ Goldliste: 10 Produkte bei Bob bestätigt. Fehlende Felder von " +
                                plan.size + " Produkten werden jetzt gezielt in DEGIRO nachgelesen.")
                            runCatching { onConfirmed?.invoke(plan,batch) }.onFailure {
                                status(c,"✅ Liste in Bob gespeichert. Detailprüfung konnte nicht gestartet werden; vorhandene Belege bleiben erhalten.")
                                PhoneRemote.stop(c,"STORAGE_ERROR")
                            }
                        } else {
                            status(c,when {
                                plan==null -> "✅ Goldliste mit 10 Produkten bestätigt. Detailplan nicht verifizierbar; Nachlesen gestoppt."
                                plan.isEmpty() -> "✅ Goldliste mit 10 Produkten bestätigt. Keine fehlenden Felder für einen neuen Detail-Leselauf."
                                else -> "✅ Goldliste mit 10 Produkten bestätigt. Die Lesesitzung ist abgelaufen; Detailprüfung nicht gestartet."
                            })
                            PhoneRemote.stop(c,"COMPLETE")
                        }
                    } else if(response?.optString("batchId")==batch &&
                        MorningListResumePolicy.terminalVerificationFailed(
                            receipt?.optString("stage"),receipt?.optString("error"),
                            receipt?.optBoolean("enhancedVerification",false)==true)) {
                        // The ORIGINAL enhanced two-pass OCR has definitively
                        // rejected this list. Re-polling it is not a new read.
                        // Archive this rejected batch before requesting any
                        // new screenshot; never relabel its old data as current.
                        val archivedReady=runCatching {
                            save(c,JSONObject(body.toString()).put("verificationFailed",true))
                        }.isSuccess
                        waiting=false
                        // Never accept this incomplete batch as a valid list.
                        // A separate, *local-only* read may still inspect the
                        // exact product ISINs observed on this phone. Broker
                        // searches, ranking and purchase eligibility remain
                        // independently gated throughout the whole flow.
                        val raw=body.optJSONArray("localCandidates")
                        val local=if(raw==null) emptyList() else
                            (0 until raw.length()).map { raw.optString(it) }
                        val counts=receipt.optJSONObject("verificationCounts")
                        val provisional=if(counts==null || resumeSavedCapture) null else
                            ProvisionalIsinReadPolicy.candidates(
                                local,
                                serverBatchMatches=response.optString("batchId")==batch,
                                stage=receipt.optString("stage"),
                                error=receipt.optString("error"),
                                enhanced=receipt.optBoolean("enhancedVerification",false),
                                recognized=counts.optInt("uniqueRows",-1),
                                expected=counts.optInt("expectedRows",-1),
                                images=counts.optInt("imagesTotal",-1),
                                conflicts=counts.optInt("conflictingRows",-1))
                        if(archivedReady && provisional!=null && PhoneRemote.active() &&
                            PhoneRemote.sessionId()==session && onProvisionalResearch!=null) {
                            status(c,"Goldliste nicht vollständig bestätigt" +
                                rejectedListHint(receipt) +
                                " Nur lokal erfasste ISINs werden für eine " +
                                "getrennte, nicht handelsfähige Recherche gelesen.")
                            runCatching { onProvisionalResearch?.invoke(provisional) }.onFailure {
                                status(c,"Lokale ISIN-Recherche konnte nicht sicher starten. " +
                                    "Originalbilder und Fehlerbericht bleiben gespeichert.")
                                PhoneRemote.stop(c,"LIST_UPLOAD_FAILED")
                            }
                        } else if(archivedReady && PhoneRemote.active() &&
                            PhoneRemote.sessionId()==session && onFreshCaptureRequired!=null) {
                            status(c,"Gespeicherte Liste endgültig abgelehnt" +
                                rejectedListHint(receipt) +
                                " Bob startet einen frischen Gold-Einleselauf in derselben bestätigten Sitzung.")
                            runCatching { onFreshCaptureRequired?.invoke() }.onFailure {
                                status(c,"Frischer Gold-Lesestart fehlgeschlagen. Alte Belege bleiben gespeichert.")
                                PhoneRemote.stop(c,"LIST_UPLOAD_FAILED")
                            }
                        } else {
                            status(c,"Gespeicherte Liste nicht bestätigt" +
                                rejectedListHint(receipt) +
                                " Ein neuer Gold-Lesestart ist erforderlich; alte Bilder bleiben erhalten.")
                            PhoneRemote.stop(c,"LIST_UPLOAD_FAILED")
                        }
                    } else if(MorningListFallbackPolicy.memoryDeferred(
                            receipt?.optString("stage"),receipt?.optString("error")) &&
                        (attempt>=18 || resumeSavedCapture) &&
                        PhoneRemote.active() && PhoneRemote.sessionId()==session) {
                        val earlier=response?.optString("existingListBatchId").orEmpty()
                        val ids=response?.optJSONArray("existingDetailIsins")
                        val values=if(ids==null) null else (0 until ids.length()).map { ids.optString(it) }
                        val plan=values?.let { SelectiveDetailPlan.parse(response?.optJSONArray("existingDetailPlan"),it) }
                        if(MorningListFallbackPolicy.allowed(attempt,batch,earlier,plan,
                                resumedSavedCapture=resumeSavedCapture)) {
                            // The currently captured images remain durable and
                            // unconfirmed. ONLY the previous verified daily
                            // list supplies the ISINs, attached to its real
                            // batch identifier and original evidence time.
                            waiting=false
                            status(c,"⚠️ Neue Goldliste wegen Serverspeicher nicht bestätigt. Bob liest fehlende Felder aus der bereits bestätigten heutigen Zehnerliste nach; neue Bilder bleiben gespeichert.")
                            runCatching { onConfirmed?.invoke(plan!!,earlier) }.onFailure {
                                status(c,"Bestätigte Tagesliste erhalten; Detailprüfung konnte nicht gestartet werden.")
                                PhoneRemote.stop(c,"STORAGE_ERROR")
                            }
                        } else {
                            if(MorningListFallbackPolicy.pollingFinished(attempt,
                                    receipt?.optString("stage"),receipt?.optString("reason"))) {
                                waiting=false
                                status(c,"Bilder gespeichert · Speicherwartezeit beendet. Neue Liste nicht bestätigt; kein passender Tageslisten-Ausweichweg verfügbar.")
                                PhoneRemote.stop(c,"LIST_UPLOAD_FAILED")
                            } else {
                                status(c,"Texterfassung unvollständig · Bilderkennung wartet auf freien Serverspeicher.")
                                handler.postDelayed({poll(attempt+1,uploaded||response!=null)},5000)
                            }
                        }
                    } else if(receipt?.optString("stage")=="superseded") {
                        waiting=false;file(c).delete();status(c,"Neuere Liste bereits in Bob gespeichert; alte Aufnahme bleibt historisch.")
                        PhoneRemote.stop(c,"COMPLETE")
                    } else if(MorningListFallbackPolicy.pollingFinished(attempt,
                            receipt?.optString("stage"),receipt?.optString("reason")) ||
                            !PhoneRemote.active() || PhoneRemote.sessionId()!=session) {
                        // Only after the bounded handset wait/session ends,
                        // remember the last authenticated rejection. During
                        // polling the server's enhanced retry may still succeed.
                        val rejected=response?.optString("batchId")==batch &&
                            MorningListResumePolicy.verificationFailed(
                                receipt?.optString("stage"),receipt?.optString("error"))
                        val restartReady=rejected && runCatching {
                            save(c,JSONObject(body.toString()).put("verificationFailed",true))
                        }.isSuccess
                        waiting=false;status(c,if(restartReady)
                            "Listenbilder angekommen, aber Goldliste noch nicht bestätigt" +
                                rejectedListHint(receipt) +
                                " Aufnahme bleibt gespeichert. Bob starten nimmt eine neue Liste auf."
                            else if(receipt?.optString("reason")=="OCR_MEMORY_WAIT_EXHAUSTED")
                            "Bilder gespeichert · Speicherwartezeit beendet. Neue Liste nicht bestätigt; frische lokale Erkennung erforderlich."
                            else "Aufnahme gespeichert. Serverbestätigung noch offen; Start setzt die Übertragung fort.")
                        PhoneRemote.stop(c,"LIST_UPLOAD_FAILED")
                    } else {
                        status(c,if(response==null) "Verbindung unterbrochen · gespeicherte Bilder werden erneut übertragen." else if(MorningListFallbackPolicy.memoryDeferred(
                            receipt?.optString("stage"),receipt?.optString("error"))) "Texterfassung unvollständig · Bilderkennung wartet auf freien Serverspeicher." else if(MorningListResumePolicy.verificationFailed(
                            receipt?.optString("stage"),receipt?.optString("error")))
                            "Listenprüfung fehlgeschlagen · Bob wartet auf den begrenzten erneuten Erkennungsversuch. Noch keine vollständige Goldliste bestätigt."
                            else "Liste bei Bob · Prüfung läuft; noch keine Abschlussbestätigung.")
                        handler.postDelayed({poll(attempt+1,uploaded||response!=null)},5000)
                    }
                }
            }
        }
        // A late confirmed list is checked via the authenticated receipt only:
        // no second screenshot upload, no silent old-session reuse.
        poll(0,receiptOnly)
    }
}
