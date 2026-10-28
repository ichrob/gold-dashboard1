package ch.bob.degirocompanion

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.SystemClock
import android.util.Base64
import android.widget.Toast

/** Browser-mediated transport: APK remains offline; callbacks need a local nonce. */
class MorningReadTransfer : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        var startedHere=false
        runCatching {
            val uri=intent.data ?: error("Übergabe fehlt")
            check(uri.scheme=="bobhandy" && uri.host=="list-reader" && uri.userInfo==null && uri.port == -1)
            when(uri.path) {
                "/list" -> {
                    check(ProductReadDiagnostics.connected && getSharedPreferences("product_reader",MODE_PRIVATE).getBoolean("enabled",false)) { "Leseprüfung zuerst in Bob Handy einschalten." }
                    val raw=uri.fragment.orEmpty();check(raw.length in 1..16000)
                    val payload=String(Base64.decode(raw,Base64.URL_SAFE or Base64.NO_WRAP),Charsets.UTF_8)
                    MorningReadRun.begin(this,uri.getQueryParameter("nonce").orEmpty(),payload)
                    startedHere=true
                    val launch=packageManager.getLaunchIntentForPackage(ProductScreenEvidence.PACKAGE) ?: error("DEGIRO-App fehlt")
                    ProductReadDiagnostics.reset(SystemClock.elapsedRealtime())
                    ProductReadRequest.start(SystemClock.elapsedRealtime())
                    startActivity(launch)
                }
                "/ack" -> {
                    check(MorningReadRun.acknowledge(this,uri.getQueryParameter("batch").orEmpty(),uri.getQueryParameter("revision")?.toIntOrNull() ?: -1)) { "Keine passende offene Übertragung." }
                    Toast.makeText(this,"Leselauf in Bob gespeichert.",Toast.LENGTH_LONG).show()
                    startActivity(Intent(this,ProductReadActivity::class.java))
                }
                "/open" -> startActivity(Intent(this,ProductReadActivity::class.java))
                else -> error("Ungültige Übergabe")
            }
        }.onFailure {
            if(startedHere) { runCatching { MorningReadRun.stop(this,"TRANSFER_ERROR") };ProductReadRequest.cancel() }
            Toast.makeText(this,it.message ?: "Listenübergabe fehlgeschlagen.",Toast.LENGTH_LONG).show()
            startActivity(Intent(this,ProductReadActivity::class.java))
        }
        finish()
    }
    companion object {
        private const val BASE="https://bob-private-scanner.onrender.com/"
        fun requestList(c: Context) {
            val nonce=MorningReadRun.challenge(c)
            c.startActivity(Intent(Intent.ACTION_VIEW,Uri.parse(BASE+"#bob-read-list="+nonce)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        }
        fun showResults(c: Context) {
            check(!MorningReadRun.running) { "Leselauf läuft noch. Zuerst stoppen oder Abschluss abwarten." }
            val raw=MorningReadRun.pending(c) ?: return
            val encoded=Base64.encodeToString(raw.toByteArray(Charsets.UTF_8),Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
            c.startActivity(Intent(Intent.ACTION_VIEW,Uri.parse(BASE+"#bob-read-results="+encoded)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        }
    }
}
