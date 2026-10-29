package ch.bob.degirocompanion

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.util.AtomicFile
import org.json.JSONObject
import java.io.File
import java.time.Instant
import java.util.concurrent.Executors

/** Durable image outbox. Retrying transport never authorizes a phone action. */
internal object MorningListDelivery {
    private val handler=Handler(Looper.getMainLooper())
    private val network=Executors.newSingleThreadExecutor()
    private var generation=0
    var waiting=false; private set
    var onConfirmed:((List<String>)->Unit)?=null
    private fun file(c:Context)=AtomicFile(File(c.filesDir,"morning-list-pending.json"))
    private fun prefs(c:Context)=c.getSharedPreferences("morning_list_delivery",Context.MODE_PRIVATE)
    fun status(c:Context)=prefs(c).getString("status","").orEmpty()
    private fun status(c:Context,text:String) { prefs(c).edit().putString("status",text).apply() }
    fun cancel() { generation++;waiting=false }
    fun save(c:Context,body:JSONObject) {
        val f=file(c);val stream=f.startWrite()
        try { stream.write(body.toString().toByteArray(Charsets.UTF_8));f.finishWrite(stream) }
        catch(e:Exception) { f.failWrite(stream);throw e }
    }
    fun resume(c:Context):Boolean {
        val body=runCatching { JSONObject(String(file(c).readFully(),Charsets.UTF_8)) }.getOrNull() ?: return false
        val images=body.optJSONArray("images") ?: return false
        val age=runCatching { System.currentTimeMillis()-Instant.parse(images.getJSONObject(0).getString("at")).toEpochMilli() }.getOrDefault(Long.MAX_VALUE)
        if(age !in 0..86400000) { status(c,"Gespeicherte Aufnahme abgelaufen; neuer Lauf möglich.");file(c).delete();return false }
        // Only an interrupted recent transfer resumes in place. A historic
        // outbox must never hold a newly requested morning list hostage.
        if(age>15*60*1000 || body.optInt("resumeCount")>=2) {
            val archive=File(c.filesDir,"morning-list-previous.json")
            archive.writeText(body.toString());file(c).delete()
            status(c,"Frühere Aufnahme gesichert; neuer Listenlauf startet.")
            return false
        }
        val resumes=body.optInt("resumeCount")+1
        body.put("sessionId",PhoneRemote.sessionId()).put("resumeCount",resumes)
        start(c,body);return true
    }
    fun start(c:Context,body:JSONObject) {
        save(c,body);cancel();waiting=true
        val id=++generation;val session=PhoneRemote.sessionId();val batch=body.getString("batchId")
        status(c,"Listenbilder gespeichert · Übertragung und Serverprüfung laufen.")
        fun poll(attempt:Int,uploaded:Boolean) {
            if(id!=generation)return
            network.execute {
                val result=runCatching {
                    if(!uploaded) { check(PhoneRemote.active() && PhoneRemote.sessionId()==session);PhoneDiagnostics.uploadList(c,JSONObject(body.toString()).apply { remove("resumeCount") }) }
                    PhoneDiagnostics.listStatus(c,JSONObject().put("batchId",batch))
                }
                handler.post {
                    if(id!=generation)return@post
                    val response=result.getOrNull();val receipt=response?.optJSONObject("import")
                    if(response?.optString("batchId")==batch && receipt?.optString("stage")=="synced" && receipt.optInt("count")==10) {
                        waiting=false;file(c).delete()
                        status(c,"✅ Fertig: 10 unterschiedliche Produkte in Bob gespeichert und bestätigt.")
                        val ids=response.optJSONArray("detailIsins")
                        val values=if(ids==null) emptyList() else (0 until ids.length()).map { ids.getString(it) }
                        if(PhoneRemote.active() && PhoneRemote.sessionId()==session && values.size<=10 && values.distinct()==values && values.all { SeriesEvidence.validIsin(it) }) {
                            runCatching { onConfirmed?.invoke(values) }.onFailure {
                                status(c,"✅ Liste in Bob gespeichert. Detailprüfung konnte nicht gestartet werden.")
                                PhoneRemote.stop(c,"STORAGE_ERROR")
                            }
                        } else PhoneRemote.stop(c,"COMPLETE")
                    } else if(receipt?.optString("stage")=="superseded") {
                        waiting=false;file(c).delete();status(c,"Neuere Liste bereits in Bob gespeichert; alte Aufnahme bleibt historisch.")
                        PhoneRemote.stop(c,"COMPLETE")
                    } else if(attempt>=100 || !PhoneRemote.active() || PhoneRemote.sessionId()!=session) {
                        waiting=false;status(c,"Aufnahme gespeichert. Serverbestätigung noch offen; Start setzt die Übertragung fort.")
                        PhoneRemote.stop(c,"LIST_UPLOAD_FAILED")
                    } else {
                        status(c,if(response==null) "Verbindung unterbrochen · gespeicherte Bilder werden erneut übertragen." else "Bilder bei Bob · Prüfung läuft; noch keine Abschlussbestätigung.")
                        handler.postDelayed({poll(attempt+1,uploaded||response!=null)},5000)
                    }
                }
            }
        }
        poll(0,false)
    }
}
