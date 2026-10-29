package ch.bob.degirocompanion

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import org.json.JSONObject
import java.net.URL
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.concurrent.Executors
import javax.net.ssl.HttpsURLConnection

/** Ephemeral session key, separate from persistent write-only diagnostics. No UI text transport. */
internal object PhoneRemote {
    private const val BASE = "https://bob-private-scanner.onrender.com"
    private val handler = Handler(Looper.getMainLooper())
    private val worker = Executors.newSingleThreadExecutor()
    private var secret: String? = null
    private var until = 0L
    private var execute: ((String) -> String)? = null
    private var cancel: (() -> Unit)? = null
    private var context: Context? = null
    private var busy = false
    private val seen = mutableSetOf<String>()
    private var ackId: String? = null
    private var ackCode: String? = null
    var status = "Keine Fernsitzung aktiv."; private set
    fun active() = secret != null && SystemClock.elapsedRealtime() < until
    fun attach(c: Context, action: (String) -> String, stop: () -> Unit) {
        context=c.applicationContext;execute=action;cancel=stop
    }
    fun detach() { stop();execute=null;cancel=null;context=null }
    fun start(c: Context) {
        check(ProductReadDiagnostics.connected) { "Zuerst den Android-Lesedienst verbinden." }
        stop()
        val token=ByteArray(32).also { SecureRandom().nextBytes(it) }.joinToString("") { "%02x".format(it.toInt() and 255) }
        secret=token;until=SystemClock.elapsedRealtime()+900000;seen.clear();ackId=null;ackCode=null
        val digest=MessageDigest.getInstance("SHA-256").digest(token.toByteArray()).joinToString("") { "%02x".format(it.toInt() and 255) }
        status="Browserfreigabe ausstehend · Vergleichscode: "+digest.take(12)
        handler.removeCallbacks(tick);handler.postDelayed(tick,3000)
        c.startActivity(Intent(Intent.ACTION_VIEW,Uri.parse(BASE+"/handy/remote#"+digest)))
    }
    fun stop() {
        val old=secret;secret=null;until=0;handler.removeCallbacks(tick)
        cancel?.invoke();status="Fernsitzung beendet."
        if(old!=null)worker.execute { runCatching { request(old,JSONObject().put("op","revoke")) } }
    }
    private val tick=object:Runnable {
        override fun run() {
            if(!active()) { if(secret!=null)stop();return }
            val c=context ?: return
            val token=secret ?: return
            if(busy) { handler.postDelayed(this,2000);return }
            busy=true
            val snap=JSONObject().put("version",c.packageManager.getPackageInfo(c.packageName,0).versionCode)
                .put("running",ProductReadRequest.active(SystemClock.elapsedRealtime()))
                .put("serviceConnected",ProductReadDiagnostics.connected)
                .put("report",JSONObject(ProductReadDiagnostics.counters()))
                .put("ackId",ackId ?: JSONObject.NULL).put("ackCode",ackCode ?: JSONObject.NULL)
            worker.execute {
                val response=runCatching { request(token,JSONObject().put("op","poll").put("snapshot",snap)) }.getOrNull()
                handler.post {
                    busy=false
                    if(secret!=token || !active()) { if(secret==token)stop();return@post }
                    if(response==null)status="Fernsitzung: Serverfreigabe oder Verbindung noch nicht bestätigt."
                    else {
                        status="Fernsitzung verbunden · noch "+((until-SystemClock.elapsedRealtime())/60000+1)+" Minuten"
                        val command=response.optJSONObject("command")
                        if(command!=null) {
                            val id=command.optString("requestId");val action=command.optString("action")
                            if(Regex("[a-f0-9]{32}").matches(id) && seen.add(id)) {
                                val remaining=command.optLong("expiresAt")-System.currentTimeMillis()
                                ackId=id
                                ackCode=if(remaining !in 1..25000) "EXPIRED" else if(action !in PhoneRemotePolicy.actions) "REJECTED"
                                    else runCatching { execute?.invoke(action) ?: "REJECTED" }.getOrDefault("REJECTED")
                            }
                        }
                    }
                    handler.postDelayed(tick,3000)
                }
            }
        }
    }
    private fun request(token:String,body:JSONObject):JSONObject? {
        val conn=URL(BASE+"/api/android-remote/device").openConnection() as HttpsURLConnection
        try {
            conn.instanceFollowRedirects=false;conn.connectTimeout=5000;conn.readTimeout=5000
            conn.requestMethod="POST";conn.doOutput=true
            conn.setRequestProperty("Authorization","Bearer $token");conn.setRequestProperty("Content-Type","application/json")
            val bytes=body.toString().toByteArray();check(bytes.size<=8192);conn.setFixedLengthStreamingMode(bytes.size)
            conn.outputStream.use { it.write(bytes) }
            if(conn.responseCode!=200)return null
            val output=java.io.ByteArrayOutputStream()
            conn.inputStream.use { input ->
                val buffer=ByteArray(1024)
                while(true) { val n=input.read(buffer);if(n<0)break;check(output.size()+n<=8192);output.write(buffer,0,n) }
            }
            return JSONObject(output.toString("UTF-8")).takeIf { it.optBoolean("ok") }
        } finally { conn.disconnect() }
    }
}
