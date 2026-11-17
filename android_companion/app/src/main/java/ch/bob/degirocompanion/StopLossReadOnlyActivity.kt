package ch.bob.degirocompanion

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.os.SystemClock
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView

/**
 * Owner-initiated, broker-READ-ONLY screen recognition. No real position
 * required, no PIN read, no order, no OCR upload, no account data retained.
 */
class StopLossReadOnlyActivity: Activity() {
    companion object { const val EXTRA_START_ON_OPEN="start_local_readonly_probe" }
    private lateinit var result:TextView

    override fun onCreate(savedInstanceState:Bundle?) {
        super.onCreate(savedInstanceState)
        val page=LinearLayout(this).apply {
            orientation=LinearLayout.VERTICAL
            setPadding(28,44,28,32)
        }
        fun label(text:String)=TextView(this).also {
            it.text=text;it.textSize=18f;it.setPadding(0,8,0,16)
            page.addView(it)
        }
        label("BOB · DEGIRO-MASKE NUR ERKENNEN")
        label("Reine Sichtprüfung: maximal 45 Sekunden. Bob öffnet nur DEGIRO; er tippt keine Felder an, gibt nichts ein und versendet keine Orders. Eine echte Position ist für diese Prüfung nicht erforderlich. Anmeldung bei Bedarf nur durch dich selbst.")
        result=label("Noch kein Erkennungstest gestartet.")
        page.addView(Button(this).apply {
            isAllCaps=false
            text="DEGIRO jetzt nur lesen · 45 Sekunden"
            setOnClickListener { begin() }
        })
        page.addView(Button(this).apply {
            isAllCaps=false
            text="Ergebnis aktualisieren"
            setOnClickListener { showStatus() }
        })
        page.addView(Button(this).apply {
            isAllCaps=false
            text="STOPP · Prüfung beenden"
            setOnClickListener {
                StopLossReadOnlySession.finish("STOPP")
                showStatus()
            }
        })
        setContentView(page)
        if(savedInstanceState==null && intent.getBooleanExtra(EXTRA_START_ON_OPEN,false)) {
            // A one-time explicit tap on MainActivity is sufficient; never
            // resume after process restart, Activity recreation or background.
            intent.removeExtra(EXTRA_START_ON_OPEN)
            result.post { begin() }
        }
    }
    override fun onResume() {
        super.onResume()
        if(::result.isInitialized)showStatus()
    }
    private fun showStatus() {
        result.text=StopLossReadOnlySession.status+
            "\nAussage nur zur sichtbaren Oberfläche, keine Handelserlaubnis."
    }
    private fun begin() {
        val now=SystemClock.elapsedRealtime()
        if(!ProductReadDiagnostics.connected ||
            !getSharedPreferences("product_reader",MODE_PRIVATE).getBoolean("enabled",false)) {
            result.text="DEGIRO-Lesedienst nicht aktiviert. Kein Zugriff, keine Order."
            return
        }
        if(StopLossPrefillSession.active(now) || PhoneRemote.active() ||
            MorningReadRun.running || GoldSearchRun.running ||
            PinReadinessProbe.running || ProductReadRequest.active(now)) {
            result.text="Ein anderer DEGIRO-Leseauftrag läuft. Bitte zuerst beenden."
            return
        }
        val launch=packageManager.getLaunchIntentForPackage("nl.degiro.trader")
        if(launch==null) {
            result.text="DEGIRO-App nicht gefunden. Keine Prüfung gestartet."
            return
        }
        if(!StopLossReadOnlySession.start(now)) {
            result.text="Prüfung läuft bereits. Keine weitere gestartet."
            return
        }
        showStatus()
        runCatching { startActivity(launch) }.onFailure {
            StopLossReadOnlySession.finish("APP_NICHT_GESTARTET")
            showStatus()
        }
    }
}
