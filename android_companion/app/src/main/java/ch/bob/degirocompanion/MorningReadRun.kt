package ch.bob.degirocompanion

import android.content.Context
import android.os.SystemClock
import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant
import java.util.UUID

/** App-private durable outbox. No credentials, screenshots or account contents. */
internal object MorningReadRun {
    private fun prefs(c: Context) = c.getSharedPreferences("morning_reader_v1", Context.MODE_PRIVATE)
    private var data: JSONObject? = null
    var onStopped: (() -> Unit)? = null
    var running = false; private set
    var reading = false
    var index = 0; private set
    var attempt = 1; private set
    var backSteps = 0
    private var started = 0L
    val target: String get() = data?.getJSONArray("isins")?.optString(index).orEmpty()
    val count: Int get() = data?.getJSONArray("isins")?.length() ?: 0
    fun summary(): String = if (running) "Produkt ${index+1} von $count · $target · Versuch $attempt/2" else "Listenlauf nicht aktiv."
    fun expired(now: Long = SystemClock.elapsedRealtime()) = now < started || now-started >= 15*60*1000
    fun pending(c: Context): String? = prefs(c).getString("outbox", null)
    fun savedStatus(c: Context): String {
        val raw=pending(c)
        if(raw==null) return if(prefs(c).getString("lastDelivered",null)!=null) "Letztes Protokoll von Bob bestätigt. Die Diagnose ist dort abrufbar." else "Noch kein Listenprotokoll übertragen."
        return runCatching {
            val d=JSONObject(raw);val rows=d.getJSONArray("results")
            val read=(0 until rows.length()).count { rows.getJSONObject(it).optString("draft").isNotEmpty() }
            val events=d.getJSONArray("events");val last=events.optJSONObject(events.length()-1)
            "$read Produkte gelesen · ${rows.length()} geprüft · ${d.getJSONArray("isins").length()} angefragt.\n"+
                (if(last!=null) "Zuletzt: ${MorningReadUiPolicy.reason(last.optString("code"))}.\n" else "Noch kein Produkt gelesen.\n")+
                "Protokoll lokal gespeichert; Bestätigung von Bob steht noch aus."
        }.getOrDefault("Lokales Protokoll vorhanden; bitte an Bob übertragen.")
    }
    fun challenge(c: Context): String {
        check(!running) { "Listenlauf läuft bereits." }
        check(pending(c) == null) { "Zuerst die gespeicherten Ergebnisse an Bob übertragen." }
        val nonce = UUID.randomUUID().toString().replace("-", "")
        check(prefs(c).edit().putString("challenge", nonce).putLong("challengeAt", System.currentTimeMillis()).commit())
        return nonce
    }
    fun begin(c: Context, nonce: String, payload: String) {
        val p = prefs(c)
        check(nonce.matches(Regex("[a-f0-9]{32}")) && nonce == p.getString("challenge", null) &&
            System.currentTimeMillis()-p.getLong("challengeAt",0) in 0..600000) { "Listenübergabe abgelaufen. In Bob Handy neu starten." }
        check(!running && pending(c) == null && payload.length <= 12000)
        val source = JSONObject(payload)
        val at = source.getString("listUploadedAt")
        check(System.currentTimeMillis()-Instant.parse(at).toEpochMilli() in 0..86400000) { "Morgenliste ist älter als 24 Stunden. Bitte in Bob aktualisieren." }
        val ids = source.getJSONArray("isins")
        check(ids.length() in 1..12)
        val values = (0 until ids.length()).map { ids.getString(it) }
        check(values.all { SeriesEvidence.validIsin(it) } && values.toSet().size == values.size)
        data = JSONObject().put("batchId", nonce).put("listUploadedAt", at)
            .put("appVersionCode",c.packageManager.getPackageInfo(c.packageName,0).versionCode)
            .put("revision",0).put("isins", JSONArray(values)).put("results", JSONArray()).put("events", JSONArray())
        index=0; attempt=1; reading=false; backSteps=0; started=SystemClock.elapsedRealtime()
        persist(c)
        p.edit().remove("challenge").remove("challengeAt").commit()
        running=true
        PhoneDiagnostics.queue(c)
    }
    private fun persist(c: Context) {
        data?.put("revision", (data?.optInt("revision") ?: 0)+1)
        check(prefs(c).edit().putString("outbox", data.toString()).commit()) { "Lokale Speicherung fehlgeschlagen. Lesen gestoppt." }
    }
    fun event(c: Context, code: String) {
        val d=data ?: return
        val events=d.getJSONArray("events")
        events.put(JSONObject().put("isin",target).put("code",code).put("attempt",attempt).put("at",Instant.now().toString()))
        while(events.length()>48) events.remove(0)
        persist(c)
        PhoneDiagnostics.queue(c)
    }
    fun outcome(c: Context, code: String, draft: String = ""): Boolean {
        check(running)
        if (draft.isNotEmpty()) check(draft.lineSequence().any { it == "ISIN: $target" })
        val required=listOf("Geld","Brief","Anzeigezeit","Hebel","KO-Schwelle","Basispreis","Bv")
        val missing=required.filterNot { draft.contains("$it (Anzeige ungeprüft): ") }
        val finalCode=if(draft.isNotEmpty()) (if(missing.isEmpty()) "COMPLETE" else "PARTIAL") else code
        val results=data!!.getJSONArray("results")
        val entry=JSONObject().put("isin",target).put("code",finalCode).put("attempts",attempt)
            .put("draft",draft).put("missingFields",JSONArray(missing))
        val previous=(0 until results.length()).firstOrNull { results.getJSONObject(it).getString("isin")==target }
        // A failed retry never erases a partial observation already saved.
        if(previous == null) results.put(entry)
        else {
            val prior=results.getJSONObject(previous)
            if(prior.optString("draft").isEmpty() || (draft.isNotEmpty() && missing.size<=prior.getJSONArray("missingFields").length())) results.put(previous,entry)
            else prior.put("attempts",attempt)
        }
        event(c,finalCode)
        if(finalCode!="COMPLETE" && attempt<2) { attempt++; reading=false;backSteps=0;return true }
        index++;skipCompleted();attempt=1;reading=false;backSteps=0
        if(index>=count) { running=false;return false }
        return true
    }
    private fun skipCompleted() {
        val rows=data!!.getJSONArray("results")
        while(index<count && (0 until rows.length()).any { rows.getJSONObject(it).optString("isin")==target && rows.getJSONObject(it).optString("code")=="COMPLETE" }) index++
    }
    fun resume(c: Context) {
        check(!running) { "Listenlauf läuft bereits." }
        val raw=pending(c) ?: error("Kein gespeicherter Lauf.")
        val saved=JSONObject(raw)
        check(System.currentTimeMillis()-Instant.parse(saved.getString("listUploadedAt")).toEpochMilli() in 0..86400000) { "Liste abgelaufen. Ergebnisse zuerst übertragen und neue Liste holen." }
        data=saved;index=0;skipCompleted()
        check(index<count) { "Alle Produkte vollständig. Ergebnisse an Bob übertragen." }
        attempt=1;reading=false;backSteps=0;started=SystemClock.elapsedRealtime();running=true
    }
    fun stop(c: Context, code: String) {
        val wasRunning=running
        try { if(running) runCatching { event(c,code) } } finally { running=false;reading=false }
        PhoneDiagnostics.queue(c)
        if(wasRunning && code!="USER_STOP") onStopped?.invoke()
    }
    fun acknowledge(c: Context, batchId: String, revision: Int): Boolean {
        val raw=pending(c) ?: return false
        if(JSONObject(raw).optString("batchId")!=batchId || JSONObject(raw).optInt("revision")!=revision || running) return false
        return prefs(c).edit().remove("outbox").putString("lastDelivered",Instant.now().toString()).commit()
    }
}
