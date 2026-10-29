package ch.bob.degirocompanion

import android.accessibilityservice.AccessibilityServiceInfo
import android.view.accessibility.AccessibilityManager
import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.net.Uri
import android.os.Handler
import android.os.Looper
import android.os.Bundle
import android.os.SystemClock
import android.provider.Settings
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

/** User-started local reading with optional automatic return of structured fields to Bob. */
class ProductReadActivity : Activity() {
    private var displayedRequestActive = false
    private val statusHandler = Handler(Looper.getMainLooper())
    private val statusTick = object : Runnable {
        override fun run() {
            if (PhoneRemote.active() || MorningReadRun.running || GoldSearchRun.running || displayedRequestActive != ProductReadRequest.active(SystemClock.elapsedRealtime())) refresh()
            statusHandler.postDelayed(this, 1000)
        }
    }
    private val automaticTransfer=Runnable { runCatching { MorningReadTransfer.automaticResults(this) } }
    private lateinit var result: TextView
    private lateinit var diagnostics: TextView
    private lateinit var primary: Button
    private val preferences by lazy { getSharedPreferences("product_reader", MODE_PRIVATE) }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val stack = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(24, 24, 24, 24) }
        var container=stack
        fun button(title: String, action: () -> Unit) {
            container.addView(Button(this).apply { text = title; isAllCaps = false; setOnClickListener { action() } })
        }
        container.addView(TextView(this).apply { text = "DEGIRO lesen · Produkt und Morgenliste"; textSize = 21f })
        primary=Button(this).apply { text="Start";isAllCaps=false;setOnClickListener { startAutomaticTest() } }
        container.addView(primary)
        button("Prüfung stoppen") {
            PhoneRemote.stop(this,"USER_STOP")
            GoldSearchRun.stop("USER_STOP",java.time.Instant.now().toString())
            MorningReadRun.stop(this,"USER_STOP")
            ProductReadRequest.cancel(); ProductReadSession.clear(); ProductReadDiagnostics.clear(); refresh()
        }
        result=TextView(this).apply { textSize=18f;setTextIsSelectable(true) }
        container.addView(result)
        container.addView(TextView(this).apply { text="Goldsuche: bis zu zwölf sichtbare Goldhebel-Kandidaten mit ISIN suchen und lesen. Unvollständige Stichprobe; neue Kandidaten bleiben getrennte Lesebeobachtungen." })
        container.addView(TextView(this).apply { text="Start drücken, dann innerhalb einer Minute DEGIRO öffnen. Bob sucht Goldhebel-Produkte, liest sichtbare ISINs und prüft die gefundenen Produkte automatisch. Die gestartete Handy-Sitzung erlaubt ChatGPT bis zu 15 Minuten Produktdaten und Diagnose zu lesen sowie begrenzte Produktsuchschritte auszuführen. DEGIRO muss angemeldet sein. Handy entsperrt lassen und während des Tests nicht bedienen. STOPP oder Sperrtaste beendet den Test. Keine Orders. Ergebnisse werden bei aktivierter Rückgabe an Bob übergeben; die Browser-Übergabe kann einen Tipp benötigen." })
        val advanced=LinearLayout(this).apply { orientation=LinearLayout.VERTICAL;visibility=android.view.View.GONE }
        button("Einrichtung und weitere Möglichkeiten") {
            advanced.visibility=if(advanced.visibility==android.view.View.GONE) android.view.View.VISIBLE else android.view.View.GONE
        }
        container.addView(advanced)
        container=advanced
        button("Automatische Diagnose verbinden / Freigabe öffnen") {
            AlertDialog.Builder(this).setTitle("Automatische Diagnose freigeben")
                .setMessage("Bob Handy darf App-Version, Dienststatus und feste Fehlercodes direkt an deinen privaten Bob senden. Keine Bildschirmtexte, Kontowerte oder Zugangsdaten. Keine Fernsteuerung. Freigabe anschließend im angemeldeten Browser bestätigen. Android-Hintergrundmeldungen können verzögert eintreffen. Jederzeit hier abschaltbar.")
                .setNegativeButton("Abbrechen",null).setPositiveButton("Verbinden") { _,_ ->
                    runCatching { PhoneDiagnostics.connect(this) }.onFailure { result.text="Verbindung konnte nicht vorbereitet werden." }
                }.show()
        }
        button("Automatische Diagnose ausschalten") { PhoneDiagnostics.disable(this);refresh() }
        button("Gold-Produkte suchen und auslesen") {
            var startedHere=false
            runCatching {
                check(preferences.getBoolean("enabled",false) && serviceEnabled() && ProductReadDiagnostics.connected) { "Lesedienst zuerst einschalten." }
                check(!MorningReadRun.running && !GoldSearchRun.running) { "Lauf zuerst beenden." }
                val launch=packageManager.getLaunchIntentForPackage(ProductScreenEvidence.PACKAGE) ?: error("DEGIRO-App fehlt")
                ProductReadRequest.cancel();ProductReadSession.clear()
                GoldSearchRun.start()
                startedHere=true
                ProductReadRequest.start(SystemClock.elapsedRealtime())
                startActivity(launch)
            }.onFailure {
                if(startedHere) { GoldSearchRun.stop("STOPPED",java.time.Instant.now().toString());ProductReadRequest.cancel() }
                result.text=it.message
            }
        }
        button("ChatGPT-Handy-Sitzung starten · 15 Minuten") {
            AlertDialog.Builder(this).setTitle("Produktsuche mit ChatGPT bedienen")
                .setMessage("Für 15 Minuten darf ChatGPT Produktdaten, sichtbare ISINs und technische Diagnose lesen sowie Gold-/ISIN-Suchschritte und Produktlesen auslösen. Keine Kontoansicht wird übertragen; keine Orders, Passwörter oder freie Bildschirmbedienung. Die automatische Diagnose muss verbunden sein. Handy entsperrt lassen; STOPP, Sperrtaste oder eigene Bedienung beendet die Sitzung.")
                .setNegativeButton("Abbrechen",null).setPositiveButton("Sitzung starten") { _,_ ->
                    runCatching {
                        check(preferences.getBoolean("enabled",false)) { "Lesedienst zuerst einschalten." }
                        val launch=packageManager.getLaunchIntentForPackage(ProductScreenEvidence.PACKAGE) ?: error("DEGIRO fehlt")
                        PhoneRemote.start(this);startActivity(launch)
                    }.onFailure { PhoneRemote.stop(this,"START_FAILED");result.text=it.message }
                }.show()
        }
        button("Bisherige Morgenliste prüfen / übertragen") { primaryAction() }
        button("Leseprüfung einschalten / Android-Einstellungen") {
            AlertDialog.Builder(this).setTitle("Sichtbare Produktfelder lesen")
                .setMessage("Bob erhält über die Android-Bedienungshilfe Zugriff auf sichtbare DEGIRO-Texte. Nach „Prüfung starten“ prüft er höchstens eine Minute die geöffnete Produktseite und scrollt dafür automatisch nach unten und zur ISIN zurück; alternativ liest er nach deinem Tastendruck. Während der gestarteten Prüfung hält Bob den Bildschirm bis zu 60 Sekunden eingeschaltet; Abschluss oder Abbruch beendet dies. Die Sperrtaste bleibt wirksam. Er übernimmt nur strukturierte Produktfelder. Bei aktivierter automatischer Rückgabe öffnet er danach Bob und ordnet den Entwurf lokal anhand der ISIN deiner Produktliste zu. Beim Morgenlisten-Lauf wird die ISIN in die Produktsuche eingetragen; beim getrennten Goldsuchlauf zunächst nur das Wort Gold. Login- und Orderansichten stoppen den Lauf. DEGIRO beschränkt automatisierte Werkzeuge; dieser Gerätetest ist keine Zustimmung von DEGIRO. Ohne Freigabe bleibt manuelles Screenshot-Teilen die Alternative.")
                .setNegativeButton("Abbrechen", null)
                .setPositiveButton("Leseprüfung aktivieren") { _, _ ->
                    preferences.edit().putBoolean("enabled", true).apply()
                    startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
                }.show()
        }
        container.addView(android.widget.CheckBox(this).apply {
            text = "Ergebnisse und Fehler automatisch an Bob übertragen"
            isChecked = preferences.getBoolean("auto_return", true)
            setOnCheckedChangeListener { _, checked -> preferences.edit().putBoolean("auto_return", checked).apply() }
        })
        button("Morgenliste automatisch von Bob holen und lesen") {
            if (!preferences.getBoolean("enabled",false) || !serviceEnabled()) {
                result.text="Bitte zuerst die Leseprüfung und den Android-Dienst einschalten."
            } else runCatching { MorningReadTransfer.requestList(this) }.onFailure { result.text=it.message }
        }
        button("Unterbrochenen Listenlauf fortsetzen") {
            runCatching {
                check(preferences.getBoolean("enabled",false) && serviceEnabled() && ProductReadDiagnostics.connected) { "Leseprüfung und Android-Dienst zuerst einschalten." }
                val launch=packageManager.getLaunchIntentForPackage(ProductScreenEvidence.PACKAGE) ?: error("DEGIRO fehlt")
                MorningReadRun.resume(this)
                ProductReadRequest.start(SystemClock.elapsedRealtime())
                startActivity(launch)
            }.onFailure { MorningReadRun.stop(this,"TRANSFER_ERROR"); ProductReadRequest.cancel(); result.text=it.message }
        }
        button("Gespeicherten Listenlauf an Bob übertragen / erneut versuchen") {
            runCatching { MorningReadTransfer.showResults(this) }.onFailure { result.text="Browser nicht erreichbar. Ergebnisse bleiben gespeichert." }
        }
        container.addView(TextView(this).apply {
            text="Morgenliste: Bob lädt die zuletzt gespeicherte Liste (höchstens 24 Stunden alt), sucht jede ISIN und liest bis zu zwölf Produkte. DEGIRO muss angemeldet und das Handy entsperrt sein. Höchstens zwei Versuche je Produkt und 15 Minuten insgesamt. Nicht bedienen; STOPP oder Sperrtaste beendet den Lauf. Ergebnisse bleiben bis zur bestätigten Übertragung gespeichert. Login- und Orderansichten halten den Lauf an."
        })
        button("Seite prüfen · DEGIRO öffnen, automatisch scrollen und lesen") {
            if (!preferences.getBoolean("enabled", false) || !serviceEnabled()) {
                result.text = "Bitte zuerst die Leseprüfung und den Android-Dienst einschalten."
                return@button
            }
            MorningReadRun.stop(this,"USER_STOP")
            ProductReadSession.clear()
            ProductReadDiagnostics.reset(SystemClock.elapsedRealtime())
            ProductReadRequest.start(SystemClock.elapsedRealtime())
            val launch = packageManager.getLaunchIntentForPackage(ProductScreenEvidence.PACKAGE)
            if (launch == null) { ProductReadRequest.cancel(); result.text = "DEGIRO-App nicht gefunden." }
            else runCatching { startActivity(launch) }.onFailure { ProductReadRequest.cancel(); result.text = "DEGIRO konnte nicht geöffnet werden." }
        }
        button("Gelesene Werte in Bob prüfen") {
            val draft = ProductReadSession.get(SystemClock.elapsedRealtime()).draft
            if (draft.isBlank()) { refresh(); return@button }
            runCatching {
                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://bob-private-scanner.onrender.com/#bob-ocr=" + Uri.encode(draft))))
            }.onFailure { result.text = "Browser konnte nicht geöffnet werden. Entwurf bleibt lokal." }
        }
        diagnostics = TextView(this).apply { textSize = 16f; setTextIsSelectable(true) }
        container.addView(diagnostics)
        button("Technische Diagnose kopieren") {
            val clipboard = getSystemService(CLIPBOARD_SERVICE) as android.content.ClipboardManager
            clipboard.setPrimaryClip(android.content.ClipData.newPlainText("Bob-Lesediagnose", ProductReadDiagnostics.report(SystemClock.elapsedRealtime())))
            android.widget.Toast.makeText(this, "Diagnose ohne Kontodaten kopiert.", android.widget.Toast.LENGTH_SHORT).show()
        }
        container.addView(TextView(this).apply {
            text = "Einmalig: Leseprüfung und Android-Dienst aktivieren. Die Männchen-Taste ist optional.\n\n1. Prüfung starten.\n2. In DEGIRO das Produkt mit sichtbarer ISIN öffnen. Bob scrollt und liest automatisch, höchstens 60 Sekunden. Bob hält den Bildschirm während dieser Prüfung automatisch wach. Währenddessen bitte nicht bedienen; die Sperrtaste bricht ab.\n3. Bob öffnet sich nach erfolgreichem Lesen automatisch und speichert die Beobachtung beim passenden Listeneintrag. Falls die Rückgabe scheitert, bleibt der Entwurf hier über ‚Gelesene Werte in Bob prüfen‘ erreichbar.\n\nEinzelseitenprüfung: nur Scrollen der geöffneten Seite. Die Morgenlisten-Funktion oben übernimmt zusätzlich die ISIN-Suche. Keine Orderbedienung. Anmeldung selbst durchführen. Bei Zeitablauf erneut starten. Ohne zugängliche Bildschirmtexte: Screenshot teilen. Entwurf verfällt nach fünf Minuten."
            textSize = 16f
        })
        setContentView(ScrollView(this).apply { addView(stack) })
    }
    override fun onResume() {
        super.onResume();PhoneDiagnostics.queue(this);refresh();statusHandler.post(statusTick)
        statusHandler.postDelayed(automaticTransfer,600)
    }
    override fun onPause() { statusHandler.removeCallbacks(automaticTransfer);statusHandler.removeCallbacks(statusTick); super.onPause() }
    /** One explicit start authorizes the bounded local test and its remote observation. */
    private fun startAutomaticTest() {
        var startedHere=false
        runCatching {
            check(!PhoneRemote.active() && !GoldSearchRun.running && !MorningReadRun.running) { "Test läuft bereits. DEGIRO öffnen und abwarten." }
            check(preferences.getBoolean("enabled",false) && serviceEnabled() && ProductReadDiagnostics.connected) { "Unter Einrichtung den Lesedienst einmalig einschalten." }
            check(PhoneDiagnostics.paired(this)) { "Unter Einrichtung die automatische Diagnose einmalig verbinden." }
            check(packageManager.getLaunchIntentForPackage(ProductScreenEvidence.PACKAGE)!=null) { "DEGIRO-App fehlt." }
            PhoneRemote.start(this)
            startedHere=true
            check(PhoneRemote.active()) { PhoneRemote.message }
            GoldSearchRun.start()
            ProductReadRequest.start(SystemClock.elapsedRealtime())
            refresh()
            result.text="Jetzt DEGIRO öffnen. Bob übernimmt die Suche und das Lesen automatisch. Handy entsperrt lassen; nicht weiter bedienen."
        }.onFailure {
            if(startedHere) {
                PhoneRemote.stop(this,"START_FAILED")
                GoldSearchRun.stop("STOPPED",java.time.Instant.now().toString())
                ProductReadRequest.cancel()
            }
            result.text=it.message ?: "Test konnte nicht gestartet werden."
        }
    }
    private fun primaryAction() {
        runCatching {
            check(!GoldSearchRun.running) { "Goldsuche läuft bereits. Zuerst stoppen oder Abschluss abwarten." }
            when(MorningReadUiPolicy.action(MorningReadRun.running,false,
                preferences.getBoolean("enabled",false),serviceEnabled() && ProductReadDiagnostics.connected)) {
                MorningReadUiPolicy.Action.OPEN -> {
                    val launch=packageManager.getLaunchIntentForPackage(ProductScreenEvidence.PACKAGE) ?: error("DEGIRO-App nicht gefunden.")
                    startActivity(launch)
                }
                MorningReadUiPolicy.Action.SEND -> MorningReadTransfer.showResults(this)
                MorningReadUiPolicy.Action.SETUP -> {
                    preferences.edit().putBoolean("enabled",true).apply()
                    startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
                }
                MorningReadUiPolicy.Action.START -> MorningReadTransfer.requestList(this)
            }
        }.onFailure { result.text=it.message ?: "Start fehlgeschlagen; gespeichertes Protokoll bleibt erhalten." }
    }
    private fun serviceEnabled(): Boolean {
        val manager = getSystemService(ACCESSIBILITY_SERVICE) as AccessibilityManager
        return manager.getEnabledAccessibilityServiceList(AccessibilityServiceInfo.FEEDBACK_ALL_MASK)
            .any { it.resolveInfo.serviceInfo.packageName == packageName &&
                it.resolveInfo.serviceInfo.name == ProductReadService::class.java.name }
    }
    private fun refresh() {
        displayedRequestActive = ProductReadRequest.active(SystemClock.elapsedRealtime())
        val value = ProductReadSession.get(SystemClock.elapsedRealtime())
        primary.text=if(PhoneRemote.active() || GoldSearchRun.running || MorningReadRun.running) "Test läuft · DEGIRO öffnen" else "Start"
        result.text=(if(GoldSearchRun.running) "Goldsuche läuft · sichtbare ISIN-Kandidaten erfassen" else if(GoldSearchRun.lastCode!=null) "Goldsuche beendet: "+MorningReadUiPolicy.reason(GoldSearchRun.lastCode.orEmpty()) else MorningReadRun.summary())+"\n"+MorningReadRun.savedStatus(this)+"\n\n"+PhoneDiagnostics.status(this)+"\n\n"+PhoneRemote.message
        diagnostics.text = (if (preferences.getBoolean("enabled", false)) (if (serviceEnabled()) (if (ProductReadDiagnostics.connected) "Android-Lesedienst verbunden.\n" else "Dienst aktiviert, aber noch nicht mit Bob verbunden.\n") else "Android-Lesedienst noch ausgeschaltet.\n") else "Leseprüfung ausgeschaltet.\n") + (if (ProductReadRequest.active(SystemClock.elapsedRealtime())) "Prüfung wartet auf eine lesbare Produktseite (maximal 60 Sekunden).\n" else "Keine automatische Prüfung aktiv.\n") + value.message +
            (if (value.draft.isNotBlank()) "\n\n${value.draft}" else "") + "\n\n" + ProductReadDiagnostics.report(SystemClock.elapsedRealtime())
    }
}
