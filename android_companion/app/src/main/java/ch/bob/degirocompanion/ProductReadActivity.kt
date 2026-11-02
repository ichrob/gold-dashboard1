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
    companion object {
        // Only our non-exported activity may receive this from a local UI tap.
        internal const val EXTRA_START_COMPLETE_FLOW = "ch.bob.degirocompanion.START_COMPLETE_FLOW"
    }
    private var startCompleteFlowOnFirstResume = false
    private var displayedRequestActive = false
    private val statusHandler = Handler(Looper.getMainLooper())
    private val statusTick = object : Runnable {
        override fun run() {
            if (PhoneRemote.active() || MorningReadRun.running || GoldSearchRun.running || displayedRequestActive != ProductReadRequest.active(SystemClock.elapsedRealtime())) refresh()
            statusHandler.postDelayed(this, 1000)
        }
    }
    private lateinit var result: TextView
    private lateinit var diagnostics: TextView
    private lateinit var primary: Button
    private val preferences by lazy { getSharedPreferences("product_reader", MODE_PRIVATE) }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Consume the one-shot local request before launching the broker.
        // A recreation, notification, or return from DEGIRO must not login again.
        startCompleteFlowOnFirstResume = savedInstanceState == null &&
            intent.getBooleanExtra(EXTRA_START_COMPLETE_FLOW, false)
        intent.removeExtra(EXTRA_START_COMPLETE_FLOW)
        val stack = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(24, 24, 24, 24) }
        var container=stack
        fun button(title: String, action: () -> Unit) {
            container.addView(Button(this).apply { text = title; isAllCaps = false; setOnClickListener { action() } })
        }
        container.addView(TextView(this).apply { text = "DEGIRO lesen · Produkt und Morgenliste"; textSize = 21f })
        primary=Button(this).apply { text="Gesamtablauf starten";isAllCaps=false;setOnClickListener { startAutomaticTest() } }
        container.addView(primary)
        button("Prüfung stoppen") {
            if(PinReadinessProbe.running) PinReadinessProbe.stop("PIN-Test gestoppt.")
            PhoneRemote.stop(this,"USER_STOP")
            GoldSearchRun.stop("USER_STOP",java.time.Instant.now().toString())
            MorningReadRun.stop(this,"USER_STOP")
            ProductReadRequest.cancel(); ProductReadSession.clear(); ProductReadDiagnostics.clear(); refresh()
        }
        result=TextView(this).apply { textSize=18f;setTextIsSelectable(true) }
        container.addView(result)
        container.addView(TextView(this).apply { tag = "pin_probe_status"; text = PinReadinessProbe.message; textSize = 18f })
        container.addView(TextView(this).apply { text="Morgenliste: Gold suchen, Hebelprodukte öffnen, Tastatur schließen, bis zu vier Listenbilder der zehn Top Ergebnisse mit Scrollen aufnehmen und an Bob übertragen. Android 14 oder neuer erforderlich." })
        container.addView(TextView(this).apply { text="Ein Start: DEGIRO öffnen, bekannte Fingerabdruck-Hinweise falls möglich schließen und eine sicher eingerichtete PIN einmal nur lokal eingeben. Erst wenn die Marktseite bestätigt ist, Gold und Hebelprodukte suchen, zehn Listenplätze übergeben und anhand des von Bob bestätigten Feldplans ausschließlich noch fehlende Produktangaben nachlesen. Ohne lokal eingerichtete PIN muss DEGIRO bereits angemeldet sein. Kein wiederholter PIN-Versuch. Bei unbekannter Login-Seite, Sperrbildschirm oder Orderansicht wird gestoppt. Die Kontokopfzeile wird bei Bildern ausgeschnitten. Bereits gespeicherte Originalbelege bleiben erhalten; ein fehlerhafter Lauf überschreibt keine gültige Liste. Handy entsperrt lassen, während des Laufs nicht bedienen. STOPP beendet den Ablauf. Keine Orders und keine automatische Handelsfreigabe." })
        val advanced=LinearLayout(this).apply { orientation=LinearLayout.VERTICAL;visibility=android.view.View.GONE }
        button("Einrichtung und weitere Möglichkeiten") {
            advanced.visibility=if(advanced.visibility==android.view.View.GONE) android.view.View.VISIBLE else android.view.View.GONE
        }
        container.addView(advanced)
        container=advanced
        button("DEGIRO-PIN nur auf diesem Handy einrichten") {
            when {
                PinReadinessProbe.running || PhoneRemote.active() || MorningReadRun.running || GoldSearchRun.running || ProductReadRequest.active(SystemClock.elapsedRealtime()) -> result.text = "Laufende Prüfung zuerst stoppen."
                !PhoneDiagnostics.keypadTestVerified(this) -> result.text = "Zuerst den Ein-Ziffer-Test erfolgreich abschließen."
                !LocalPinVault.available(this) -> result.text = "Für die lokale PIN werden Android 15 oder neuer und ein entsperrtes Handy mit Gerätesperre benötigt."
                else -> startActivity(Intent(this, LocalPinActivity::class.java))
            }
        }
        button("Gespeicherte PIN einmal eingeben") {
            AlertDialog.Builder(this).setTitle("Einmalige lokale PIN-Eingabe")
                .setMessage("Nur starten, wenn die gespeicherte PIN korrekt ist und alle fünf DEGIRO-Felder leer sind. Bob versucht höchstens diese eine PIN. Bob schließt eindeutig erkannte Fingerabdruck-, Hinweis- und TouchID/FaceID-Einrichtungsdialoge. Handy nicht bedienen. Bei unzugänglichen oder unbekannten Dialogen stoppt Bob. Keine Wiederholung bei Fehlern. Bei einer Unterbrechung verbliebene Eingaben selbst löschen. Die Marktseite muss anschließend tatsächlich erscheinen; Produktlesen startet separat.")
                .setNegativeButton("Abbrechen", null)
                .setPositiveButton("Fünf Felder leer · einmal starten") { _, _ ->
                    var secret: ByteArray? = null
                    var started = false
                    try {
                        check(preferences.getBoolean("enabled", false) && serviceEnabled() && ProductReadDiagnostics.connected)
                        check(!PinReadinessProbe.running && !PhoneRemote.active() && !MorningReadRun.running && !GoldSearchRun.running && !ProductReadRequest.active(SystemClock.elapsedRealtime()))
                        check(PhoneDiagnostics.keypadTestVerified(this) && LocalPinVault.available(this))
                        val launch = packageManager.getLaunchIntentForPackage(ProductScreenEvidence.PACKAGE) ?: error("App unavailable")
                        secret = LocalPinVault.load(this)
                        started = true
                        PinReadinessProbe.startLocalLogin(secret)
                        startActivity(launch)
                    } catch (_: Exception) {
                        if (started) PinReadinessProbe.stop("Lokale PIN-Eingabe gestoppt. Bitte DEGIRO prüfen.")
                        result.text = "Lokale PIN-Eingabe konnte nicht gestartet werden. Einrichtung, Gerätesperre und Lesedienst prüfen."
                    } finally { secret?.fill(0) }
                }.show()
        }
        button("Gespeicherte DEGIRO-PIN löschen") {
            AlertDialog.Builder(this).setTitle("Lokale PIN entfernen?")
                .setMessage("Entfernt die gespeicherte PIN und ihren Schlüssel von diesem Handy.")
                .setNegativeButton("Abbrechen", null).setPositiveButton("Löschen") { _, _ ->
                    if (PinReadinessProbe.running) PinReadinessProbe.stop("Lokale PIN-Einrichtung gelöscht.")
                    result.text = if (runCatching { LocalPinVault.delete(this) }.isSuccess) "Lokale PIN gelöscht." else "Löschen nicht vollständig bestätigt."
                }.show()
        }
        button("PIN-Anmeldeseite technisch prüfen · ohne PIN") {
            runCatching {
                check(preferences.getBoolean("enabled",false) && serviceEnabled() && ProductReadDiagnostics.connected) { "Lesedienst zuerst einschalten." }
                check(!PhoneRemote.active() && !MorningReadRun.running && !GoldSearchRun.running && !ProductReadRequest.active(SystemClock.elapsedRealtime())) { "Laufende Produktprüfung zuerst stoppen." }
                val launch = packageManager.getLaunchIntentForPackage(ProductScreenEvidence.PACKAGE) ?: error("DEGIRO-App fehlt.")
                PinReadinessProbe.start()
                startActivity(launch)
            }.onFailure {
                if(PinReadinessProbe.running) PinReadinessProbe.stop("PIN-Test konnte nicht gestartet werden.")
                result.text = it.message
            }
        }
        container.addView(TextView(this).apply {
            text = "PIN-Test: Bob öffnet DEGIRO. Fingerabdruckdialog abbrechen und den Hinweis schließen; keine PIN eingeben. Nach 30 Sekunden versucht Bob automatisch hierher zurückzukehren. Das Ergebnis steht oben. Bei aktivierter automatischer Diagnose wird nur der technische Ergebniscode mit Testkennung und Abschlusszeit an deinen privaten Bob übertragen; bei Verbindungsproblemen wird automatisch erneut versucht. Ziffernbeschriftungen, der feste Anmeldehinweis und die Löschtasten-Beschriftung werden nur lokal erkannt; keine Tasten gedrückt. Keine PINs, Bildschirmtexte oder Bilder werden gespeichert oder übertragen. Handy entsperrt lassen. Falls Android die Rückkehr verhindert, Bob selbst öffnen. Ein erkennbares Feld beweist noch keine funktionierende Anmeldung."
        })
        button("Eine Testziffer eingeben und löschen") {
            AlertDialog.Builder(this).setTitle("Einmaliger Tastaturtest · keine Anmeldung")
                .setMessage("Nur starten, wenn du zuvor in DEGIRO alle fünf PIN-Felder geleert und die Löschtaste rechts neben der Null geprüft hast. Bob berührt höchstens einmal die eindeutig erkannte Nulltaste und versucht diese Testziffer einmal zu löschen. Kein zweiter Zifferndruck. Keine echte PIN eingeben. Nach dem Abbrechen des Fingerabdruckdialogs und Schließen des Hinweises nicht weiter berühren. Bei einem Abbruch kann die Testziffer stehen bleiben: anschließend selbst prüfen und löschen. Es wird kein Eingabetext gelesen. Der Test bestätigt noch keine sichere automatische Anmeldung.")
                .setNegativeButton("Abbrechen", null)
                .setPositiveButton("Fünf Felder leer · Test starten") { _, _ ->
                    runCatching {
                        check(preferences.getBoolean("enabled",false) && serviceEnabled() && ProductReadDiagnostics.connected) { "Lesedienst zuerst einschalten." }
                        check(!PinReadinessProbe.running && !PhoneRemote.active() && !MorningReadRun.running && !GoldSearchRun.running && !ProductReadRequest.active(SystemClock.elapsedRealtime())) { "Laufende Prüfung zuerst stoppen." }
                        val launch = packageManager.getLaunchIntentForPackage(ProductScreenEvidence.PACKAGE) ?: error("DEGIRO-App fehlt.")
                        PinReadinessProbe.start(confirmedEmptyExercise = true)
                        startActivity(launch)
                    }.onFailure {
                        if (PinReadinessProbe.running) PinReadinessProbe.stop("Bedienungstest nicht gestartet; Eingabe selbst prüfen.")
                        result.text = it.message
                    }
                }.show()
        }
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
            var startedPhoneHere=false
            runCatching {
                check(preferences.getBoolean("enabled",false) && serviceEnabled() && ProductReadDiagnostics.connected) { "Lesedienst zuerst einschalten." }
                check(!MorningReadRun.running && !GoldSearchRun.running) { "Lauf zuerst beenden." }
                // This button starts a locally approved complete list read.
                // The guarded search-tap fallback and image upload require an
                // active PhoneRemote session. Never silently start a run that
                // cannot click the search or deliver its evidence.
                val session=GoldReadStartPolicy.decide(PhoneDiagnostics.paired(this),PhoneRemote.active())
                check(session!=GoldReadStartPolicy.Decision.BLOCK) {
                    "Zuerst die automatische Diagnose verbinden und in Bob freigeben."
                }
                val launch=packageManager.getLaunchIntentForPackage(ProductScreenEvidence.PACKAGE) ?: error("DEGIRO-App fehlt")
                ProductReadRequest.cancel();ProductReadSession.clear()
                if(session==GoldReadStartPolicy.Decision.START_SESSION) {
                    PhoneRemote.start(this)
                    startedPhoneHere=true
                }
                check(PhoneRemote.active()) { "Handy-Sitzung konnte nicht gestartet werden." }
                GoldSearchRun.start()
                startedHere=true
                ProductReadRequest.start(SystemClock.elapsedRealtime())
                startActivity(launch)
            }.onFailure {
                if(startedHere) { GoldSearchRun.stop("STOPPED",java.time.Instant.now().toString());ProductReadRequest.cancel() }
                if(startedPhoneHere) PhoneRemote.stop(this,"START_FAILED")
                result.text=it.message ?: "Goldsuche konnte nicht gestartet werden."
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
            runCatching {
                check(!MorningReadRun.running) { "Leseprüfung läuft noch; gespeicherten Abschluss abwarten." }
                val raw=MorningReadRun.pending(this)
                val listBatch=raw?.let { org.json.JSONObject(it).optString("listBatchId") }.orEmpty()
                if(listBatch.matches(Regex("[a-f0-9]{32}"))) {
                    // Imported Android-list observations use authenticated
                    // device upload, not the older browser deep-link.
                    check(PhoneDiagnostics.paired(this)) { "Automatische Diagnose erneut verbinden; lokale Details bleiben gespeichert." }
                    ProductDetailDelivery.start(this) { refresh() }
                    refresh()
                } else MorningReadTransfer.showResults(this)
            }.onFailure { result.text=it.message ?: "Übertragung nicht gestartet. Gespeicherte Daten bleiben erhalten." }
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
        val scroll = ScrollView(this).apply {
            addView(stack)
            // Keep the first/last controls outside system bars and cutouts on edge-to-edge Android.
            // Replace padding on every dispatch; never accumulate it when bars or rotation change.
            setOnApplyWindowInsetsListener { view, insets ->
                if (android.os.Build.VERSION.SDK_INT >= 30) {
                    val bars = insets.getInsets(android.view.WindowInsets.Type.systemBars() or
                        android.view.WindowInsets.Type.displayCutout())
                    view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
                } else {
                    view.setPadding(insets.systemWindowInsetLeft, insets.systemWindowInsetTop,
                        insets.systemWindowInsetRight, insets.systemWindowInsetBottom)
                }
                insets
            }
        }
        setContentView(scroll)
        scroll.requestApplyInsets()
    }
    override fun onResume() {
        super.onResume()
        if(PinReadinessProbe.running) PinReadinessProbe.stop("Prüfung beendet. " + PinReadinessProbe.message)
        PhoneDiagnostics.queue(this)
        refresh()
        statusHandler.post(statusTick)
        if(startCompleteFlowOnFirstResume) {
            // Starting in onCreate would run before this existing onResume
            // PIN-probe cleanup and could cancel the very login we started.
            startCompleteFlowOnFirstResume = false
            startAutomaticTest()
        }
    }
    override fun onPause() { statusHandler.removeCallbacks(statusTick); super.onPause() }
    /** One explicit start: local, once-only PIN if enrolled; Gold only after
     * the actual DEGIRO Markets screen has been recognized. No PIN transport. */
    private fun startAutomaticTest() {
        var startedHere=false
        var localPin: ByteArray?=null
        runCatching {
            check(!PinReadinessProbe.running && !LoginToReadHandoff.pending(SystemClock.elapsedRealtime()) &&
                !PhoneRemote.active() && !GoldSearchRun.running && !MorningReadRun.running &&
                !ProductReadRequest.active(SystemClock.elapsedRealtime())) { "Test läuft bereits. DEGIRO öffnen und abwarten." }
            check(preferences.getBoolean("enabled",false) && serviceEnabled() && ProductReadDiagnostics.connected) { "Unter Einrichtung den Lesedienst einmalig einschalten." }
            check(PhoneDiagnostics.paired(this)) { "Unter Einrichtung die automatische Diagnose einmalig verbinden." }
            val launch=packageManager.getLaunchIntentForPackage(ProductScreenEvidence.PACKAGE) ?: error("DEGIRO-App fehlt.")
            if(LocalPinVault.exists(this)) {
                check(PhoneDiagnostics.keypadTestVerified(this)) { "Lokale PIN ist vorhanden, aber der sichere Tastaturtest fehlt. Unter Einrichtung prüfen." }
                check(LocalPinVault.available(this)) { "Handy entsperren, damit der lokale PIN-Schlüssel genutzt werden kann." }
                localPin=LocalPinVault.load(this)
                LoginToReadHandoff.arm(SystemClock.elapsedRealtime())
                PinReadinessProbe.startLocalLogin(localPin!!)
                startedHere=true
                result.text="DEGIRO wird geöffnet. Bob prüft die Anmeldung und versucht die verschlüsselt gespeicherte PIN nur auf diesem Handy einmal. Erst nach bestätigter Marktseite beginnt die Goldsuche."
                startActivity(launch)
            } else {
                // A missing PIN never authorizes guessing or a login action.
                // The existing reader works when the broker is already logged in.
                PhoneRemote.start(this)
                startedHere=true
                check(PhoneRemote.active()) { PhoneRemote.message }
                GoldSearchRun.start()
                ProductReadRequest.start(SystemClock.elapsedRealtime())
                result.text="DEGIRO wird geöffnet. Wenn keine PIN lokal eingerichtet ist, muss DEGIRO bereits angemeldet sein. Bob sucht anschließend Goldprodukte."
                startActivity(launch)
            }
        }.onFailure {
            LoginToReadHandoff.clear()
            if(PinReadinessProbe.localLoginActive) PinReadinessProbe.stop("Einmalige Anmeldung konnte nicht gestartet werden.")
            if(startedHere) {
                PhoneRemote.stop(this,"START_FAILED")
                GoldSearchRun.stop("STOPPED",java.time.Instant.now().toString())
                ProductReadRequest.cancel()
            }
            result.text=it.message ?: "Test konnte nicht gestartet werden."
        }.also { localPin?.fill(0) }
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
        window.decorView.findViewWithTag<TextView>("pin_probe_status")?.text = PinReadinessProbe.message
        displayedRequestActive = ProductReadRequest.active(SystemClock.elapsedRealtime())
        val value = ProductReadSession.get(SystemClock.elapsedRealtime())
        primary.text=if(PhoneRemote.active() || GoldSearchRun.running || MorningReadRun.running) "Läuft · DEGIRO prüfen" else "Gesamtablauf starten"
        val delivery=MorningListDelivery.status(this)
        val current=when {
            GoldSearchRun.running -> "Goldsuche läuft · zehn Top Ergebnisse erfassen"
            MorningReadRun.running -> delivery+"\n\nFehlende Produktangaben lesen: "+MorningReadRun.summary()
            delivery.isNotBlank() -> delivery
            GoldSearchRun.lastCode!=null -> "Goldsuche beendet: "+MorningReadUiPolicy.reason(GoldSearchRun.lastCode.orEmpty())
            else -> MorningReadRun.summary()
        }
        val detailDelivery=ProductDetailDelivery.status(this)
        result.text=current+(if(detailDelivery.isNotBlank()) "\n\n"+detailDelivery else "")+
            "\n\n"+PhoneDiagnostics.status(this)+"\n\n"+PhoneRemote.message

        diagnostics.text = (if (preferences.getBoolean("enabled", false)) (if (serviceEnabled()) (if (ProductReadDiagnostics.connected) "Android-Lesedienst verbunden.\n" else "Dienst aktiviert, aber noch nicht mit Bob verbunden.\n") else "Android-Lesedienst noch ausgeschaltet.\n") else "Leseprüfung ausgeschaltet.\n") + (if (ProductReadRequest.active(SystemClock.elapsedRealtime())) "Prüfung wartet auf eine lesbare Produktseite (maximal 60 Sekunden).\n" else "Keine automatische Prüfung aktiv.\n") + MorningReadRun.savedStatus(this) + "\n\n" + value.message +
            (if (value.draft.isNotBlank()) "\n\n${value.draft}" else "") + "\n\n" + ProductReadDiagnostics.report(SystemClock.elapsedRealtime())
    }
}
