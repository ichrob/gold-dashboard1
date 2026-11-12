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
    fun currentSnapshot(): String? = data?.toString()
    fun refreshSourceSnapshot(c: Context): String? = prefs(c).getString("refreshSource",null) ?: latestSnapshot(c)
    fun rememberRefreshSource(c: Context, raw: String) { check(prefs(c).edit().putString("refreshSource",raw).commit()) }
    fun latestSnapshot(c: Context): String? = RunOutbox.resumable(entries(c))
    fun importedListRun() = running && data?.optString("listBatchId").orEmpty().matches(Regex("[a-f0-9]{32}"))
    /** Only a server-planned, authenticated list follow-up may omit a quote pair. */
    fun requestedTermsOnly(): Set<String> {
        if(!importedListRun()) return emptySet()
        val values=data?.optJSONObject("requestedFields")?.optJSONArray(target) ?: return emptySet()
        val names=(0 until values.length()).map { values.optString(it) }.toSet()
        val terms=setOf("Hebel","KO-Schwelle","Basispreis","Bv","Währung")
        if(names.isEmpty() || !terms.containsAll(names)) return emptySet()
        return names
    }
    fun requestedLeverage(): Boolean {
        if(!importedListRun()) return false
        val arr=data?.optJSONObject("requestedFields")?.optJSONArray(target) ?: return false
        return (0 until arr.length()).any { arr.optString(it)=="Hebel" }
    }
    fun summary(): String = if (running) "Produkt ${index+1} von $count · $target · Versuch $attempt/2" else "Listenlauf nicht aktiv."
    fun expired(now: Long = SystemClock.elapsedRealtime()) = now < started || now-started >= 15*60*1000
    private fun entries(c: Context): Map<String,String> = prefs(c).all.filterKeys {
        it == RunOutbox.CURRENT || it == RunOutbox.RESUME || it.startsWith(RunOutbox.PREFIX)
    }.mapValues { it.value as String }
    fun pending(c: Context): String? = entries(c).let { it[RunOutbox.pendingKey(it)] }
    fun outboxGeneration(c: Context): String = RunOutbox.generation(entries(c))
    /** An upload attempt may skip an unavailable historical batch in memory
     * without deleting or rewriting any saved original observation. */
    fun pendingForDelivery(c: Context, excludedKeys: Set<String>): Pair<String,String>? {
        val saved=entries(c)
        val key=RunOutbox.candidateKeys(saved).firstOrNull { it !in excludedKeys } ?: return null
        return key to saved.getValue(key)
    }
    private fun saveEntries(c: Context, before: Map<String,String>, after: Map<String,String>): Boolean {
        val edit=prefs(c).edit()
        (before.keys-after.keys).forEach { edit.remove(it) }
        after.forEach { (key,value) -> if(before[key]!=value) edit.putString(key,value) }
        return edit.commit()
    }
    fun savedStatus(c: Context): String {
        val raw=latestSnapshot(c)
        if(raw==null) return if(prefs(c).getString("lastDelivered",null)!=null) "Letztes Protokoll von Bob bestätigt. Die Diagnose ist dort abrufbar." else "Noch kein Listenprotokoll übertragen."
        return runCatching {
            val d=JSONObject(raw);val rows=d.getJSONArray("results")
            val codes=(0 until rows.length()).map { rows.getJSONObject(it).optString("code") }
            val read=codes.count { it=="COMPLETE" }
            val partial=codes.count { it=="PARTIAL" }
            val noQuotes=codes.count { it in setOf("NO_QUOTES","QUOTES_UNAVAILABLE") }
            val confirmed=prefs(c).getString("lastDeliveredBatch",null)==d.optString("batchId") &&
                prefs(c).getInt("lastDeliveredRevision",-1)==d.optInt("revision")
            val receipt=if(confirmed) "Übertragung dieses Laufs bestätigt. " else "Endgültige Übertragung dieses Laufs noch nicht bestätigt. "
            val events=d.getJSONArray("events");val last=events.optJSONObject(events.length()-1)
            "$read vollständig · $partial teilweise · $noQuotes ohne Kurspaar · ${rows.length()} von ${d.getJSONArray("isins").length()} geprüft.\n"+
                (if(last!=null) "Zuletzt: ${MorningReadUiPolicy.reason(last.optString("code"))}.\n" else "Noch kein Produkt gelesen.\n")+
                receipt+"${RunOutbox.candidateKeys(entries(c)).size} Protokoll(e) zur Übertragung gespeichert; neuer Start bleibt möglich."
        }.getOrDefault("Lokales Protokoll vorhanden; bitte an Bob übertragen.")
    }
    fun challenge(c: Context): String {
        check(!running) { "Listenlauf läuft bereits." }
        val nonce = UUID.randomUUID().toString().replace("-", "")
        check(prefs(c).edit().putString("challenge", nonce).putLong("challengeAt", System.currentTimeMillis()).commit())
        return nonce
    }
    fun begin(c: Context, nonce: String, payload: String) {
        val p = prefs(c)
        check(nonce.matches(Regex("[a-f0-9]{32}")) && nonce == p.getString("challenge", null) &&
            System.currentTimeMillis()-p.getLong("challengeAt",0) in 0..600000) { "Listenübergabe abgelaufen. In Bob Handy neu starten." }
        check(!running && payload.length <= 12000)
        val source = JSONObject(payload)
        val at = source.getString("listUploadedAt")
        check(System.currentTimeMillis()-Instant.parse(at).toEpochMilli() in 0..86400000) { "Morgenliste ist älter als 24 Stunden. Bitte in Bob aktualisieren." }
        val ids = source.getJSONArray("isins")
        check(ids.length() in 1..12)
        val values = (0 until ids.length()).map { ids.getString(it) }
        check(values.all { SeriesEvidence.validIsin(it) } && values.toSet().size == values.size)
        GoldSearchRun.clear()
        data = JSONObject().put("batchId", nonce).put("listUploadedAt", at)
            .put("appVersionCode",c.packageManager.getPackageInfo(c.packageName,0).versionCode)
            .put("revision",0).put("isins", JSONArray(values)).put("results", JSONArray()).put("events", JSONArray())
        index=0; attempt=1; reading=false; backSteps=0; started=SystemClock.elapsedRealtime()
        persist(c, newRun=true)
        p.edit().remove("challenge").remove("challengeAt").commit()
        running=true
        PhoneDiagnostics.queue(c)
    }
    fun beginDiscovered(c: Context, values: List<String>, listBatchId: String? = null,
                        requested: Map<String, List<String>>? = null, originalListAt: String? = null) {
        check(!running) { "Listenlauf läuft bereits." }
        check(values.size in 1..12 && values.distinct()==values && values.all { SeriesEvidence.validIsin(it) })
        check(listBatchId==null || listBatchId.matches(Regex("[a-f0-9]{32}")))
        if(requested!=null) check(requested.keys==values.toSet() &&
            requested.values.all { v -> v.isNotEmpty() && v.size<=SelectiveDetailPlan.fields.size &&
                v.distinct()==v && v.all { it in SelectiveDetailPlan.fields } })
        if(originalListAt!=null) check(System.currentTimeMillis()-Instant.parse(originalListAt).toEpochMilli() in 0..14*60*60*1000L)
        data=JSONObject().put("batchId",UUID.randomUUID().toString().replace("-",""))
            .put("listUploadedAt",originalListAt ?: Instant.now().toString()).put("listSource","degiro-gold-search")
            .put("appVersionCode",c.packageManager.getPackageInfo(c.packageName,0).versionCode)
            .put("revision",0).put("isins",JSONArray(values)).put("results",JSONArray()).put("events",JSONArray())
        if(listBatchId!=null)data!!.put("listBatchId",listBatchId)
        if(originalListAt==null) rememberRefreshSource(c,data!!.toString())
        if(requested!=null) data!!.put("requestedFields",JSONObject().apply {
            values.forEach { put(it,JSONArray(requested.getValue(it))) }
        })
        index=0;attempt=1;reading=false;backSteps=0;started=SystemClock.elapsedRealtime()
        persist(c, newRun=true)
        running=true
        PhoneDiagnostics.queue(c)
    }
    private fun persist(c: Context, newRun: Boolean = false) {
        data?.put("revision", (data?.optInt("revision") ?: 0)+1)
        val before=entries(c)
        val after=if(newRun) RunOutbox.start(before,data.toString(),RunOutbox.PREFIX+UUID.randomUUID().toString())
            else before + (RunOutbox.CURRENT to data.toString())
        check(saveEntries(c,before,RunOutbox.checkpoint(after,data.toString()))) { "Lokale Speicherung fehlgeschlagen. Lesen gestoppt." }
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
        val requested=data!!.optJSONObject("requestedFields")?.optJSONArray(target)
        val required=if(requested!=null)
            (0 until requested.length()).map { requested.getString(it) }
            else listOf("Geld","Brief","Anzeigezeit","Hebel","KO-Schwelle","Basispreis","Bv")
        val missing=required.filterNot { draft.contains("$it (Anzeige ungeprüft): ") }
        val finalCode=if(draft.isNotEmpty()) (if(missing.isEmpty()) "COMPLETE"
            else if(draft.lineSequence().any { it == "Kursstatus (Anzeige ungeprüft): Geld/Brief nicht angezeigt" } &&
                !draft.contains("Geld (Anzeige ungeprüft): ") && !draft.contains("Brief (Anzeige ungeprüft): ")) "QUOTES_UNAVAILABLE"
            else "PARTIAL") else code
        val results=data!!.getJSONArray("results")
        val entry=JSONObject().put("isin",target).put("code",finalCode).put("attempts",attempt)
            .put("draft",draft).put("missingFields",JSONArray(missing))
        val previous=(0 until results.length()).firstOrNull { results.getJSONObject(it).getString("isin")==target }
        // A failed retry never erases a partial observation already saved.
        if(previous == null) results.put(entry)
        else {
            val prior=results.getJSONObject(previous)
            // A retry must not replace observed fields with a different partial
            // set of equal size. Keep the prior observation unless the new one
            // contains *all* its fields; never join quotes from different reads.
            val priorMissing=prior.getJSONArray("missingFields")
            val priorNames=(0 until priorMissing.length()).map { priorMissing.getString(it) }
            if(prior.optString("draft").isEmpty() || (draft.isNotEmpty() &&
                    ProductDraftQuality.noRegression(priorNames, missing))) results.put(previous,entry)
            else prior.put("attempts",attempt)
        }
        event(c,finalCode)
        ProductDetailDelivery.streamCurrent(c)
        if(MorningReadRetryPolicy.retry(finalCode,draft.isNotEmpty(),missing,attempt)) {
            attempt++; reading=false;backSteps=0;return true
        }
        index++;skipCompleted();attempt=(savedResult()?.optInt("attempts") ?: 0)+1;reading=false;backSteps=0
        if(index>=count) { running=false;return false }
        return true
    }
    private fun savedResult(): JSONObject? {
        val rows=data!!.getJSONArray("results")
        return (0 until rows.length()).map { rows.getJSONObject(it) }.firstOrNull { it.optString("isin")==target }
    }
    private fun skipCompleted() {
        while(index<count) {
            val row=savedResult() ?: break
            val missing=row.optJSONArray("missingFields") ?: JSONArray()
            if(MorningReadRetryPolicy.retry(row.optString("code"),row.optString("draft").isNotEmpty(),
                    (0 until missing.length()).map { missing.optString(it) },row.optInt("attempts"))) break
            index++
        }
    }
    /** Called only from the locally requested Start, after the usual session/login gates. */
    fun resumeRecent(c: Context): Boolean {
        val raw=RunOutbox.resumable(entries(c)) ?: return false
        val saved=runCatching { JSONObject(raw) }.getOrNull() ?: return false
        val age=runCatching { System.currentTimeMillis()-Instant.parse(saved.getString("listUploadedAt")).toEpochMilli() }.getOrNull() ?: return false
        val events=saved.optJSONArray("events") ?: return false
        if(!MorningResumePolicy.eligible(age,saved.optInt("resumeCount"),
                events.optJSONObject(events.length()-1)?.optString("code").orEmpty())) return false
        val ids=saved.optJSONArray("isins") ?: return false
        val results=saved.optJSONArray("results") ?: return false
        // Resume only when at least one product has never been visited. Exhausted
        // partial results go to the existing source recovery, not another loop.
        val visited=(0 until results.length()).map { results.getJSONObject(it).optString("isin") }.toSet()
        if((0 until ids.length()).all { ids.optString(it) in visited }) return false
        resume(c)
        return true
    }
    fun resume(c: Context) {
        check(!running) { "Listenlauf läuft bereits." }
        val before=entries(c)
        val raw=RunOutbox.resumable(before)
            ?: error("Kein fortsetzbarer aktueller Lauf. Bitte Gold-Produkte suchen und auslesen starten. Ältere Übertragungsberichte bleiben erhalten.")
        val saved=JSONObject(raw)
        check(System.currentTimeMillis()-Instant.parse(saved.getString("listUploadedAt")).toEpochMilli() in 0..86400000) { "Liste abgelaufen. Ergebnisse zuerst übertragen und neue Liste holen." }
        data=saved;index=0;skipCompleted()
        check(index<count) { "Keine weiteren Leseversuche offen. Gespeicherte Ergebnisse an Bob übertragen." }
        GoldSearchRun.clear()
        attempt=(savedResult()?.optInt("attempts") ?: 0)+1
        reading=false;backSteps=0;started=SystemClock.elapsedRealtime()
        data!!.put("resumeCount",data!!.optInt("resumeCount")+1)
        persist(c)
        running=true
        PhoneDiagnostics.queue(c)
    }
    fun stop(c: Context, code: String) {
        val wasRunning=running
        try { if(running) runCatching { event(c,code) } } finally { running=false;reading=false }
        PhoneDiagnostics.queue(c)
        if(wasRunning && code!="USER_STOP") onStopped?.invoke()
    }
    fun acknowledge(c: Context, batchId: String, revision: Int): Boolean {
        val before=entries(c)
        val match=before.filterKeys { it in RunOutbox.candidateKeys(before) }.entries.firstOrNull { (_,raw) -> runCatching {
            val saved=JSONObject(raw)
            saved.optString("batchId")==batchId && saved.optInt("revision")==revision
        }.getOrDefault(false) } ?: return false
        val after=RunOutbox.acknowledge(before,match.key,match.value,running) ?: return false
        if(!saveEntries(c,before,after))return false
        prefs(c).edit().putString("lastDelivered",Instant.now().toString())
            .putString("lastDeliveredBatch",batchId).putInt("lastDeliveredRevision",revision).commit()
        return true
    }
}
