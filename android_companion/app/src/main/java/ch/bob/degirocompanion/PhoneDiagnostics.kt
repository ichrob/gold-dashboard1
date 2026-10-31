package ch.bob.degirocompanion

import android.app.job.JobInfo
import android.app.job.JobScheduler
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import android.view.accessibility.AccessibilityManager
import android.accessibilityservice.AccessibilityServiceInfo
import org.json.JSONObject
import java.security.KeyStore
import java.security.MessageDigest
import java.security.SecureRandom
import java.time.Instant
import java.util.UUID
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import javax.net.ssl.HttpsURLConnection
import java.net.URL

/** Opt-in, write-only status transport. Never sends screen text, ISINs or drafts. */
internal object PhoneDiagnostics {
    private const val BASE="https://bob-private-scanner.onrender.com"
    private const val ALIAS="bob_diagnostic_key_v1"
    private const val PERIODIC=8201
    private const val NOW=8202
    private val lock=Any()
    private fun prefs(c:Context)=c.getSharedPreferences("phone_diagnostics_v1",Context.MODE_PRIVATE)
    fun paired(c:Context)=enabled(c) && prefs(c).getBoolean("paired",false)
    fun enabled(c:Context)=prefs(c).getBoolean("enabled",false)
    private fun key():SecretKey {
        val ks=KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getKey(ALIAS,null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder(ALIAS,KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
        }.generateKey()
    }
    private fun token(c:Context):String {
        val p=prefs(c);val cipher=Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE,key(),GCMParameterSpec(128,Base64.decode(p.getString("iv","").orEmpty(),Base64.NO_WRAP)))
        return String(cipher.doFinal(Base64.decode(p.getString("secret","").orEmpty(),Base64.NO_WRAP)),Charsets.UTF_8)
    }
    private fun digest(value:String)=MessageDigest.getInstance("SHA-256").digest(value.toByteArray()).joinToString(""){"%02x".format(it.toInt() and 255)}
    fun connect(c:Context) = synchronized(lock) {
        val p=prefs(c)
        if(!enabled(c)) {
            val value=ByteArray(32).also { SecureRandom().nextBytes(it) }.joinToString(""){"%02x".format(it.toInt() and 255)}
            val cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.ENCRYPT_MODE,key())
            val encrypted=cipher.doFinal(value.toByteArray())
            check(p.edit().clear().putString("secret",Base64.encodeToString(encrypted,Base64.NO_WRAP))
                .putString("iv",Base64.encodeToString(cipher.iv,Base64.NO_WRAP)).putBoolean("enabled",true)
                .putLong("pairingAt",System.currentTimeMillis()).commit())
        }
        if(!p.getBoolean("paired",false))p.edit().putLong("pairingAt",System.currentTimeMillis()).commit()
        val hash=digest(token(c));p.edit().putString("comparison",hash.take(12)).commit()
        queue(c)
        c.startActivity(Intent(Intent.ACTION_VIEW,Uri.parse(BASE+"/handy/diagnostics#"+hash)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }
    fun remoteExchange(c:Context, body:JSONObject):JSONObject = sendDevice(c,body,"/api/android-remote/exchange",false)
    fun uploadList(c:Context,body:JSONObject):JSONObject = sendDevice(c,body,"/api/android-list/upload",true)
    fun listStatus(c:Context,body:JSONObject):JSONObject = sendDevice(c,body,"/api/android-list/status",false)
    fun uploadDetails(c:Context,body:JSONObject):JSONObject = sendDevice(c,body,"/api/android-list/details",false)
    private fun sendDevice(c:Context, body:JSONObject, path:String, list:Boolean):JSONObject {
        check(paired(c))
        val credential=token(c)
        val conn=URL(BASE+path).openConnection() as HttpsURLConnection
        try {
            conn.instanceFollowRedirects=false;conn.connectTimeout=8000;conn.readTimeout=8000
            conn.requestMethod="POST";conn.doOutput=true
            conn.setRequestProperty("Authorization","Bearer "+credential)
            conn.setRequestProperty("Content-Type","application/json")
            val bytes=body.toString().toByteArray(Charsets.UTF_8);check(bytes.size<=if(list) 8100000 else if(path=="/api/android-list/details") 66000 else 24576)
            conn.setFixedLengthStreamingMode(bytes.size)
            check(paired(c) && token(c)==credential)
            conn.outputStream.use { it.write(bytes) }
            check(conn.responseCode==200)
            val text=conn.inputStream.use { stream ->
                val out=java.io.ByteArrayOutputStream();val buffer=ByteArray(1024)
                while(true) { val n=stream.read(buffer);if(n<0)break;check(out.size()+n<=32768);out.write(buffer,0,n) }
                String(out.toByteArray(),Charsets.UTF_8)
            }
            return JSONObject(text).also { check(it.optBoolean("ok")) }
        } finally { conn.disconnect() }
    }
    fun disable(c:Context) = synchronized(lock) {
        PhoneRemote.stop(c,"PAIRING_DISABLED")
        // Local opt-out takes effect before any further worker may send.
        prefs(c).edit().clear().putString("delivery","Ausgeschaltet").commit()
        val jobs=c.getSystemService(Context.JOB_SCHEDULER_SERVICE) as JobScheduler
        jobs.cancel(PERIODIC);jobs.cancel(NOW)
    }
    fun status(c:Context):String {
        val p=prefs(c)
        if(!enabled(c))return "Automatische Diagnose ausgeschaltet."
        return "Automatische Diagnose: "+p.getString("delivery","Freigabe im Browser ausstehend")+
            "\nVergleichscode: "+p.getString("comparison","")+
            (p.getString("lastAck",null)?.let { "\nLetzte Serverbestätigung: $it" } ?: "")
    }
    /** Local capability evidence only; no PIN or remote trigger. Migrates the completed 10338 test. */
    fun keypadTestVerified(c: Context): Boolean {
        val p = prefs(c)
        if (p.getBoolean("localKeypadVerified", false)) return true
        val old = runCatching { JSONObject(p.getString("pinProbe", "{}") ?: "{}") }.getOrNull()
        val valid = old != null && old.optString("result") == "KEYPAD_TEST_STATE_CYCLE_OBSERVED" && old.optBoolean("completed") &&
            old.optJSONObject("exerciseTrace")?.optString("reason") == "STATE_CYCLE"
        if (valid) p.edit().putBoolean("localKeypadVerified", true).commit()
        return valid
    }
    /** Fixed technical summary only, under the existing opt-in diagnostic authorization. */
    fun recordPinProbe(c:Context) {
        if (PinReadinessProbe.finished && PinReadinessProbe.resultCode == "KEYPAD_TEST_STATE_CYCLE_OBSERVED")
            prefs(c).edit().putBoolean("localKeypadVerified", true).commit()
        if (!enabled(c) || PinReadinessProbe.reportId.isEmpty()) return
        val summary = JSONObject().put("runId", PinReadinessProbe.reportId)
            .put("endedAt", Instant.now().toString())
            .put("result", PinReadinessProbe.resultCode)
            .put("completed", PinReadinessProbe.finished)
        PinReadinessProbe.symbolFlags?.let { flags ->
            summary.put("symbolFlags", JSONObject().put("enabled", flags.enabled)
                .put("labelled", flags.labelled).put("clickableFlag", flags.clickableFlag)
                .put("clickAction", flags.clickAction).put("nearbyParentAction", flags.nearbyParentAction))
        }
        PinReadinessProbe.loginMarketStatus?.let { summary.put("marketStatus", it) }
        PinReadinessProbe.loginDialogCheck?.let { check ->
            summary.put("dialogCheck", JSONObject().put("phase", check.phase.name)
                .put("owner", check.owner.name).put("stage", check.stage.name)
                .put("systemVerified", check.systemVerified).put("degiroContext", check.degiroContext)
                .put("degiroLabel", check.degiroLabel).put("biometricLabel", check.biometricLabel)
                .put("cancelLabel", check.cancelLabel).put("cancelAmbiguous", check.cancelAmbiguous).also { detail ->
                    check.ownerContext?.let { context ->
                        detail.put("ownerContext", JSONObject().put("rootKind", context.rootKind.name)
                            .put("focusedKind", context.focusedKind.name).put("sameWindow", context.sameWindow)
                            .put("fingerprintProgress", context.fingerprintProgress.name)
                            .put("lastDegiroScan", context.lastDegiroScan.name).also { owner ->
                                context.packageEvidence?.let { evidence ->
                                    owner.put("packageEvidence", JSONObject().put("name", evidence.name)
                                        .put("resolution", evidence.resolution.name))
                                }
                            })
                    }
                })
        }
        PinReadinessProbe.exerciseTrace?.let { trace ->
            summary.put("exerciseTrace", JSONObject().put("stage", trace.stage.name).put("reason", trace.reason.name))
        }
        prefs(c).edit().putString("pinProbe", summary.toString()).commit()
        queue(c)
    }
    fun snapshot(c:Context):String {
        val p=prefs(c)
        val event=runCatching { JSONObject(MorningReadRun.pending(c) ?: "{}").optJSONArray("events")?.let { it.optJSONObject(it.length()-1) } }.getOrNull()
        if(GoldSearchRun.lastCode!=null) p.edit().putString("lastCode",GoldSearchRun.lastCode)
            .putString("lastEventAt",GoldSearchRun.lastEventAt).commit()
        else if(event!=null) p.edit().putString("lastCode",PhoneDiagnosticPolicy.code(event.optString("code")))
            .putString("lastEventAt",event.optString("at")).commit()
        val manager=c.getSystemService(Context.ACCESSIBILITY_SERVICE) as AccessibilityManager
        val active=manager.getEnabledAccessibilityServiceList(AccessibilityServiceInfo.FEEDBACK_ALL_MASK).any {
            it.resolveInfo.serviceInfo.packageName==c.packageName && it.resolveInfo.serviceInfo.name==ProductReadService::class.java.name
        }
        return JSONObject().put("reportId",UUID.randomUUID().toString().replace("-",""))
            .put("observedAt",Instant.now().toString()).put("appVersionCode",c.packageManager.getPackageInfo(c.packageName,0).versionCode)
            .put("serviceEnabled",active).put("serviceConnectedInProcess",ProductReadDiagnostics.connected)
            .put("textAccess",ProductReadDiagnostics.canRead).put("windowAccess",ProductReadDiagnostics.windowAccess)
            .put("running",MorningReadRun.running || GoldSearchRun.running).put("pendingRun",MorningReadRun.pending(c)!=null)
            .put("lastCode",p.getString("lastCode","NONE"))
            .put("lastEventAt",p.getString("lastEventAt",null)?.takeIf { it.isNotBlank() } ?: JSONObject.NULL)
            .also { report ->
                p.getString("pinProbe", null)?.let { raw ->
                    runCatching { JSONObject(raw) }.getOrNull()?.let { probe ->
                        val recent = runCatching { System.currentTimeMillis() -
                            Instant.parse(probe.getString("endedAt")).toEpochMilli() in 0..86400000 }.getOrDefault(false)
                        if (recent) report.put("pinProbe", probe)
                    }
                }
            }.toString()
    }
    fun nextReport(c:Context):String {
        val p=prefs(c);val old=p.getString("outbox",null)
        if(old!=null && runCatching { System.currentTimeMillis()-Instant.parse(JSONObject(old).getString("observedAt")).toEpochMilli() in 0..3600000 }.getOrDefault(false))return old
        val current=snapshot(c);check(p.edit().putString("outbox",current).commit());return current
    }
    fun hasPending(c:Context)=prefs(c).contains("outbox")
    fun queue(c:Context) {
        if(!enabled(c))return
        runCatching {
            check(prefs(c).edit().putString("outbox",snapshot(c)).commit())
            val jobs=c.getSystemService(Context.JOB_SCHEDULER_SERVICE) as JobScheduler
            val component=ComponentName(c,PhoneDiagnosticJob::class.java)
            if(jobs.getPendingJob(PERIODIC)==null) jobs.schedule(JobInfo.Builder(PERIODIC,component)
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY).setPeriodic(15*60*1000L).setPersisted(true).build())
            if(jobs.getPendingJob(NOW)==null) jobs.schedule(JobInfo.Builder(NOW,component)
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY).setMinimumLatency(1000)
                .setBackoffCriteria(30000,JobInfo.BACKOFF_POLICY_EXPONENTIAL).build())
        }.onFailure { prefs(c).edit().putString("delivery","Lokale Planung fehlgeschlagen; App erneut öffnen").commit() }
    }
    // Background thread only. No redirects or user supplied URLs; local opt-out never waits for network.
    fun deliver(c:Context, report:String):Boolean {
        if(!enabled(c))return false
        val p=prefs(c)
        if(!p.getBoolean("paired",false) && System.currentTimeMillis()-p.getLong("pairingAt",0)>10*60*1000) {
            disable(c);return false
        }
        val session=p.getString("secret",null) ?: return false
        var connection:HttpsURLConnection?=null
        return try {
            val conn=URL(BASE+"/api/android-diagnostics/report").openConnection() as HttpsURLConnection;connection=conn
            conn.instanceFollowRedirects=false;conn.connectTimeout=8000;conn.readTimeout=8000
            conn.requestMethod="POST";conn.doOutput=true
            conn.setRequestProperty("Authorization","Bearer "+token(c));conn.setRequestProperty("Content-Type","application/json")
            val bytes=report.toByteArray(Charsets.UTF_8);check(bytes.size<=4096);conn.setFixedLengthStreamingMode(bytes.size)
            if(!enabled(c) || p.getString("secret",null)!=session)return false
            conn.outputStream.use { it.write(bytes) }
            val response=conn.responseCode
            if(!enabled(c) || p.getString("secret",null)!=session)return false
            if(response==401) {
                if(p.getBoolean("paired",false)) { disable(c);return false }
                p.edit().putString("delivery","Freigabe im Browser fehlt noch").commit();return false
            }
            if(response!=200) {
                p.edit().putString("delivery","Nicht bestätigt; nächster Versuch automatisch").commit()
                return response>=500 || response==429
            }
            val body=conn.inputStream.use { stream ->
                val out=java.io.ByteArrayOutputStream();val buffer=ByteArray(1024)
                while(true) { val n=stream.read(buffer);if(n<0)break;check(out.size()+n<=8192);out.write(buffer,0,n) }
                out.toByteArray()
            }
            val answer=JSONObject(String(body,Charsets.UTF_8));val sent=JSONObject(report)
            check(answer.optBoolean("ok") && answer.optBoolean("saved") && answer.optString("reportId")==sent.getString("reportId"))
            if(!enabled(c) || p.getString("secret",null)!=session)return false
            val edit=p.edit().putBoolean("paired",true).putString("delivery","Verbunden · Status bei Bob gespeichert")
                .putString("lastAck",Instant.now().toString()).putString("lastAckId",sent.getString("reportId"))
            if(p.getString("outbox",null)==report)edit.remove("outbox")
            edit.commit();false
        } catch(_:Exception) {
            if(!enabled(c) || p.getString("secret",null)!=session)return false
            p.edit().putString("delivery","Verbindung nicht bestätigt; nächster Versuch automatisch").commit();true
        } finally { connection?.disconnect() }
    }
}
