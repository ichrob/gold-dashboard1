package ch.bob.degirocompanion

import android.accessibilityservice.AccessibilityServiceInfo
import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.SystemClock
import android.provider.Settings
import android.view.accessibility.AccessibilityManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

/**
 * Integrated signed Bob-Handy activity, not a second sideloaded app.
 * Owner's single local tap starts a 45-second read-only DEGIRO observation.
 * Existing accessibility grant is reused only if already enabled.
 */
class DegiroReadOnlyActivity:Activity() {
    companion object { const val EXTRA_START_ONCE="start_degiro_readonly_once" }
    private lateinit var status:TextView
    private lateinit var grant:TextView

    private fun readerEnabled():Boolean {
        val manager=getSystemService(ACCESSIBILITY_SERVICE) as AccessibilityManager
        return manager.getEnabledAccessibilityServiceList(
            AccessibilityServiceInfo.FEEDBACK_ALL_MASK).any {
            it.resolveInfo.serviceInfo.packageName==packageName &&
                it.resolveInfo.serviceInfo.name==ProductReadService::class.java.name
        }
    }

    override fun onCreate(savedInstanceState:Bundle?) {
        super.onCreate(savedInstanceState)
        val column=LinearLayout(this).apply {
            orientation=LinearLayout.VERTICAL
            setPadding(28,36,28,36)
        }
        fun label(s:String)=TextView(this).also {
            it.text=s;it.textSize=18f;it.setPadding(0,9,0,14);column.addView(it)
        }
        label("BOB HANDY · DEGIRO NUR LESEN")
        // Primary action and STOP are always visible on a small Samsung display.
        column.addView(Button(this).apply {
            isAllCaps=false
            text="DEGIRO nur lesen · 45 Sekunden · keine Order"
            setOnClickListener { start() }
        })
        column.addView(Button(this).apply {
            isAllCaps=false
            text="STOPP · Nur-Lesen-Prüfung beenden"
            setOnClickListener {
                DegiroReadOnlySession.finish("STOPP");showStatus()
            }
        })
        grant=label("Lesedienst wird geprüft.")
        status=label(DegiroReadOnlySession.status)
        label(if(BuildConfig.DEBUG)
            "Android-Labor (Test) ist eine EIGENE App. Sie braucht eine eigene Bedienungshilfe-Freigabe. Graue Einträge mit „Gesteuert durch eingeschränkte Einstellung“ lassen sich NICHT direkt hier aktivieren. Zuerst unten die App-Info DIESES Labors öffnen, dort ggf. über ⋮ „Eingeschränkte Einstellungen zulassen“ auswählen (nur wenn du der Test-App vertraust). Danach erst die Bedienungshilfe prüfen. Die normale Bob-Handy-App bleibt unverändert. Maximal 45 Sekunden; keine PIN-Eingabe, keine Klicks oder Orders."
            else
            "Diese signierte Bob-Handy-App verwendet nur ihren eigenen bereits freigegebenen Lesedienst. Maximal 45 Sekunden, keine PIN-Eingabe, keine Klicks oder Orders. Eine echte Position ist nicht erforderlich.")
        column.addView(Button(this).apply {
            isAllCaps=false
            text="1 · App-Info DIESER Bob-App öffnen"
            setOnClickListener {
                // Direct system-owned settings route. Never grant restricted
                // accessibility privileges programmatically or on a timer.
                startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                    data=Uri.fromParts("package",packageName,null)
                })
            }
        })
        column.addView(Button(this).apply {
            isAllCaps=false
            text="2 · Bedienungshilfe prüfen / Android-Einstellungen"
            setOnClickListener { startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) }
        })
        column.addView(Button(this).apply {
            isAllCaps=false
            text="Prüfergebnis anzeigen"
            setOnClickListener { showStatus() }
        })
        column.addView(Button(this).apply {
            isAllCaps=false
            text="Ergebnis bewusst an ChatGPT teilen · nur Status"
            setOnClickListener {
                // Codes and static messages only: no ISIN, quotes, holdings,
                // screenshots or service data. Sharesheet requires user choice.
                val share=Intent(Intent.ACTION_SEND).apply {
                    type="text/plain"
                    putExtra(Intent.EXTRA_TEXT,
                        "Bob DEGIRO Nur-Lesen · "+DegiroReadOnlySession.lastCode+
                        "\n"+DegiroReadOnlySession.status)
                }
                startActivity(Intent.createChooser(share,"Ergebnis teilen"))
            }
        })
        setContentView(ScrollView(this).apply { addView(column) })
        if(savedInstanceState==null && intent.getBooleanExtra(EXTRA_START_ONCE,false)) {
            intent.removeExtra(EXTRA_START_ONCE)
            // One explicit tap on the non-exported Bob-Handy main button
            // is sufficient. No restart on resume or process restoration.
            status.post { start() }
        }
    }
    override fun onResume() { super.onResume();if(::status.isInitialized)showStatus() }
    private fun showStatus() {
        // Expire even if no further accessibility window events arrive.
        DegiroReadOnlySession.active(SystemClock.elapsedRealtime())
        val enabled=readerEnabled()
        grant.text=when {
            enabled && ProductReadDiagnostics.connected ->
                "Lesedienst bereit: Bob – Handy: Produkte lesen."
            enabled -> "Android-Freigabe vorhanden, aber Lesedienst noch nicht verbunden."
            else -> "Produkt-Lesedienst für DIESE App nicht aktiviert. Bei einem grauen Eintrag zuerst die App-Info DIESER App öffnen, dort die Android-Einschränkung prüfen; danach freiwillig die Bedienungshilfe einschalten."
        }
        status.text=DegiroReadOnlySession.status+
            "\nStatus: "+DegiroReadOnlySession.lastCode+
            "\nKeine Order oder Freigabe zum Handel."
    }
    private fun start() {
        val now=SystemClock.elapsedRealtime()
        if(!readerEnabled() || !ProductReadDiagnostics.connected) {
            showStatus()
            status.text="Der Produktlesedienst DIESER App fehlt oder ist nicht verbunden. Bei grauem Eintrag erst über App-Info dieser App die Android-Freigabe prüfen, dann die Bedienungshilfe. Keine automatische Umgehung."
            return
        }
        if(PhoneRemote.active() || PinReadinessProbe.running ||
            MorningReadRun.running || GoldSearchRun.running ||
            ProductReadRequest.active(now) || BobTradeDimMode.running) {
            status.text="Ein anderer Bob-Lese- oder Tradeauftrag ist aktiv. Dieser bleibt unverändert; Nur-Lesen nicht gestartet."
            return
        }
        val launch=packageManager.getLaunchIntentForPackage("nl.degiro.trader")
        if(launch==null) {
            status.text="DEGIRO-App nicht installiert oder kein offizieller App-Start möglich. Keine Prüfung gestartet."
            return
        }
        if(!DegiroReadOnlySession.start(now)) {
            status.text="Die Nur-Lesen-Prüfung läuft bereits."
            return
        }
        showStatus()
        runCatching { startActivity(launch) }.onFailure {
            DegiroReadOnlySession.finish("DEGIRO_NICHT_GEÖFFNET")
            showStatus()
        }
    }
}
