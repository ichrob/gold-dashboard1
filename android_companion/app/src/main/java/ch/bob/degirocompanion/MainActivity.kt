package ch.bob.degirocompanion

import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.SystemClock
import android.text.Editable
import android.text.TextWatcher
import android.provider.Settings
import android.speech.RecognizerIntent
import android.speech.tts.TextToSpeech
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.view.View
import android.view.inputmethod.InputMethodManager
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import java.util.Locale

/**
 * Device-local evidence and UI test harness, not a DEGIRO automation client.
 * No network permission, background worker, trade/order controls or credentials.
 */
class MainActivity : Activity() {
    private val selectImageRequest = 42
    private val recognizeSpeechRequest = 43
    private lateinit var status: TextView
    private lateinit var mockSearch: EditText
    private lateinit var demoResult: TextView
    private var evidenceDraft = ""
    private var imageReadSequence = 0
    private lateinit var commandInput: EditText
    private lateinit var commandStatus: TextView
    private lateinit var executeButton: Button
    private val taskApproval = PhoneTaskApproval()
    private val chatShareApproval = PhoneTaskApproval()
    private var chatShareTask: PhoneTask? = null
    private lateinit var chatShareSection: LinearLayout
    private lateinit var mainScroll: ScrollView
    private lateinit var chatShareStatus: TextView
    private val remoteAudit by lazy { RemoteAuditStore(this) }
    private val remoteCoupling by lazy {
        RemoteCoupling(audit = { event, task ->
            remoteAudit.append(System.currentTimeMillis(), event, task)
        })
    }
    private lateinit var remoteStatus: TextView
    private lateinit var remoteInput: EditText
    private lateinit var remoteAuditView: TextView
    private var remotePendingTask: PhoneTask? = null
    private val conversation = PhoneConversation()
    private var speaker: TextToSpeech? = null
    private var speakerReady = false
    private var pendingSpeech: String? = null
    // An untrusted transcript is never executed. Plans exist only in memory;
    // every step requires a NEW one-shot confirmation after an explicit preview.
    private var voiceSteps = emptyList<PhoneTask>()
    private var voiceStepIndex = 0
    private var internalCommandChange = false
    // Ephemeral, coarse status only: never store transcripts or screenshots.
    private var commandOutcome = DeviceDiagnosticShare.Outcome.NOT_TESTED
    private var speechOutcome = DeviceDiagnosticShare.Outcome.NOT_TESTED
    private var imageOutcome = DeviceDiagnosticShare.Outcome.NOT_TESTED
    private var lastDiagnosticImageCount = 0

    private fun clearVoicePlan() {
        voiceSteps = emptyList()
        voiceStepIndex = 0
    }

    private fun setCommandTextInternally(text: String) {
        internalCommandChange = true
        try { commandInput.setText(text) } finally { internalCommandChange = false }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val stack = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(28, 32, 28, 32)
        }
        fun label(text: String, parent: LinearLayout = stack): TextView = TextView(this).also {
            it.text = text
            it.textSize = 17f
            it.setPadding(0, 10, 0, 12)
            parent.addView(it)
        }
        fun button(title: String, parent: LinearLayout = stack, onClick: () -> Unit) = Button(this).also {
            it.text = title
            it.isAllCaps = false
            it.setOnClickListener { onClick() }
            parent.addView(it)
        }

        val appHeadline = if (packageName == "ch.bob.degirocompanion.stable") {
            "BOB HANDY: Produktbild teilen, automatisch erkennen und in Bob prüfen. Keine Handelsorders."
        } else {
            "BOB ANDROID-LABOR: Produktbild teilen, automatisch erkennen und in Bob prüfen. Keine Handelsorders."
        }
        label(appHeadline)
        button("🛑 NOT-STOPP – alle Handy- und Fernaufträge sperren") { emergencyStop() }
        button("DEGIRO-Produktseite lesen") {
            startActivity(Intent(this, ProductReadActivity::class.java))
        }
        button("📋 Kopierten ChatGPT-Auftrag prüfen") {
            // Explicit tap only. Never monitor or persist the clipboard.
            // Read plain text only, not URIs, images, account files or links.
            val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            val clip = clipboard.primaryClip
            val shared = if (clip != null && clip.itemCount == 1 &&
                clip.getItemAt(0).uri == null && clip.getItemAt(0).intent == null)
                clip.getItemAt(0).text?.toString().orEmpty() else ""
            previewChatShare(shared)
        }
        // A shared ChatGPT message is an UNTRUSTED proposal, not remote permission.
        // Place the one required confirmation near the TOP on small Samsung screens.
        chatShareSection = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            visibility = View.GONE
            stack.addView(this)
        }
        label("CHATGPT → BOB – freigegebenen Anzeigeauftrag übernehmen", chatShareSection)
        chatShareStatus = label("Noch kein gültiger geteilter Anzeigeauftrag.", chatShareSection)
        button("✅ Geteilten Anzeigeauftrag einmalig öffnen", chatShareSection) {
            val proposed = chatShareTask
            chatShareTask = null
            val approved = chatShareApproval.consume(proposed, SystemClock.elapsedRealtime())
            if (!approved || proposed == null) {
                chatShareStatus.text = "Geteilter Auftrag abgelaufen, verworfen oder nicht erlaubt. Nichts gestartet."
                remoteAudit.append(System.currentTimeMillis(), RemoteAuditEvent.SHARE_REJECTED, null)
            } else {
                remoteAudit.append(System.currentTimeMillis(), RemoteAuditEvent.SHARE_APPROVED, proposed)
                val page = BobNavigation.pageFor(proposed)
                val launched = if (page == null) false else openBobPage(page)
                remoteAudit.append(System.currentTimeMillis(),
                    if (launched) RemoteAuditEvent.SHARE_LAUNCHED_NOT_VERIFIED
                    else RemoteAuditEvent.SHARE_LAUNCH_FAILED, proposed)
                chatShareStatus.text = if (launched)
                    "Erlaubte Bob-Anzeige geöffnet. Browser-Inhalt noch nicht verifiziert. Keine Folgeaktion."
                else "Bob konnte nicht geöffnet werden. Keine Folgeaktion."
            }
        }
        label("Nur bewusst über Android-Teilen empfangene, harmlose Einzelaufträge. Keine automatische Ausführung, keine Fernkopplung und keine Echtgeldorders.", chatShareSection)
        button("Produktbilder auswählen (falls Teilen nicht klappt)") { openImagePicker() }
        status = label("Noch kein Bild ausgewählt. OCR-Werte sind niemals automatisch ein Handelsnachweis.")
        button("In Bob anzeigen – ohne Kopieren") {
            if (evidenceDraft.isBlank()) {
                status.text = "Zuerst ein einzelnes Produktbild auswählen oder teilen."
            } else openInBob(evidenceDraft)
        }
        val additional = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            visibility = View.GONE
        }
        button("Weitere Funktionen und Demo") {
            additional.visibility = if (additional.visibility == View.VISIBLE) View.GONE else View.VISIBLE
        }
        stack.addView(additional)
        button("OCR-Entwurf kopieren (zum Einfügen in Bob)", additional) {
            if (evidenceDraft.isBlank()) {
                status.text = "Zuerst genau ein Produkt auf einem Bild auswählen."
            } else {
                val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                clipboard.setPrimaryClip(ClipData.newPlainText("Bob OCR ungeprüft", evidenceDraft))
                status.text = "Nur der unbestätigte Text wurde kopiert. In Bob unter Mehr → DEGIRO einfügen. Die Zwischenablage kann auch von anderen Apps gelesen werden."
            }
        }
        button("OCR-Entwurf über Android teilen", additional) {
            if (evidenceDraft.isBlank()) {
                status.text = "Zuerst ein Bild auswählen und auswerten."
            } else {
                val intent = Intent(Intent.ACTION_SEND).apply {
                    type = "text/plain"
                    putExtra(Intent.EXTRA_TEXT, evidenceDraft)
                }
                startActivity(Intent.createChooser(intent, "Unbestätigten OCR-Entwurf teilen"))
            }
        }

        label("Unabhängiger Bedienungstest: nur künstliche Produktdaten", additional)
        mockSearch = EditText(this).apply {
            hint = "ISIN in Demo suchen"
            contentDescription = "Mock ISIN Eingabe"
            setSingleLine(true)
            setText("DE000FG14AV8")
            additional.addView(this)
        }
        button("DEMO: Produkt suchen", additional) {
            val query = mockSearch.text.toString().trim().uppercase(Locale.ROOT)
            demoResult.text = if (query == "DE000FG14AV8") {
                "DEMO-TREFFER: DE000FG14AV8 | Handelsplatz TEST | KEIN ECHTER HANDEL"
            } else {
                "Kein Treffer in den künstlichen Testdaten. KEIN ECHTER HANDEL"
            }
        }
        demoResult = label("Demo bereit. Ein UIAutomator-Test kann Eingaben und Klicks simulieren.", additional)

        label("SAMSUNG-FERNKOPPLUNG – freiwillige, zeitlich begrenzte Übergabe. Keine dauerhafte Fernsteuerung.")
        remoteStatus = label("Nicht gekoppelt. Kein Fernauftrag ist zulässig. Alle vorgeschlagenen Aktionen brauchen einen eigenen Tastendruck.")
        button("🔗 Kopplung 30 Minuten freigeben und Einladung bewusst teilen") {
            val invitation = remoteCoupling.pair(SystemClock.elapsedRealtime())
            remotePendingTask = null
            remoteStatus.text = "Temporär gekoppelt. Einladung nur an ein eigenes, vertrauenswürdiges Gerät teilen. Niemals in öffentlichen Chats senden. Ohne manuelle Freigabe startet nichts."
            val share = Intent(Intent.ACTION_SEND).apply {
                type = "text/plain"
                putExtra(Intent.EXTRA_TEXT, invitation)
            }
            try {
                startActivity(Intent.createChooser(share, "Geheime Kopplung nur bewusst teilen"))
            } catch (_: Exception) {
                remoteCoupling.revoke()
                remoteStatus.text = "Teilen nicht möglich: Kopplung sicherheitshalber widerrufen."
            }
        }
        remoteInput = EditText(this).apply {
            hint = "Signierten BOB-FERN/1-Auftrag einfügen oder per Teilen empfangen"
            contentDescription = "Bob Fernauftrag"
            setSingleLine(true)
            maxLines = 1
            stack.addView(this)
        }
        button("Signierten Fernauftrag prüfen – niemals automatisch ausführen") {
            previewRemote(remoteInput.text.toString())
        }
        button("✅ Geprüften Fernauftrag EINMAL erlauben") {
            val task = remotePendingTask
            remotePendingTask = null
            remoteInput.setText("")
            // Always pass even a missing proposal through the audited gate.
            // Short-circuiting on task == null used to show "rejected" without
            // recording REJECTED in the privacy-minimal local security log.
            val approved = remoteCoupling.consume(task, SystemClock.elapsedRealtime())
            if (!approved || task == null) {
                remoteStatus.text = "Fernauftrag nicht erlaubt, geändert, abgelaufen oder widerrufen. Nichts gestartet."
            } else {
                val page = BobNavigation.pageFor(task)
                // Fixed Bob-owned read-only page. No arbitrary URI, settings,
                // other apps, input events, trade dialogs or broker access.
                val launched = if (page == null) false else openBobPage(page)
                remoteCoupling.recordLaunchResult(task, launched)
                remoteStatus.text = if (launched)
                    "Erlaubte Anzeige wurde geöffnet (Browser-Erfolg nicht verifiziert). Kein Folgeschritt."
                else "Aufruf fehlgeschlagen. Keine weitere Aktion."
            }
        }
        button("🛑 FERN-STOPP – laufende Kopplung sofort sperren") {
            remoteCoupling.stopped()
            remotePendingTask = null
            remoteInput.setText("")
            remoteStatus.text = "FERN-STOPP aktiv. Alle bisherigen Kopplungsschlüssel ungültig. Nur neue bewusste Kopplung möglich."
        }
        button("Kopplung und Berechtigungen widerrufen") {
            remoteCoupling.revoke()
            remotePendingTask = null
            remoteInput.setText("")
            remoteStatus.text = "Widerrufen. Alte Nachrichten und Schlüssel sind unbrauchbar."
        }
        button("Lokales Fernkopplungs-Protokoll ansehen") {
            remoteAuditView.text = remoteAudit.summary()
        }
        remoteAuditView = label("Protokoll lokal. Keine Schlüssel, Sprachtexte, Bilder oder Kontodaten.")
        label("Wichtig: Die Übergabe erfolgt derzeit nur bewusst per Android-Teilen oder Einfügen. Kein Netzempfang, keine Hintergrundsteuerung, keine Bedienung von DEGIRO und keine Echtgeldorders. Der Freigabeschlüssel bleibt nur bis zum App-Neustart oder maximal 30 Minuten im Speicher.")

        label("HANDYSTEUERUNG – Bob öffnen ist vorausgewählt. Nur auf Prüfen und danach auf Ausführen tippen. Keine Broker-Klicks.")
        commandInput = EditText(this).apply {
            hint = "Bob öffnen oder erlaubten Auftrag eingeben"
            contentDescription = "Bob Handy-Auftrag"
            setSingleLine(true)
            // Actual field value, never a placeholder: tapping 'Prüfen' works
            // immediately for the harmless default action, but still requires
            // a second explicit confirmation before any Android intent starts.
            setText("Bob öffnen")
            addTextChangedListener(object : TextWatcher {
                override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
                override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                    taskApproval.clear()
                    if (!internalCommandChange) clearVoicePlan()
                    // Programmatic updates (voice preview, completed task)
                    // must not overwrite the meaningful outcome message.
                    if (!internalCommandChange && ::commandStatus.isInitialized) {
                        commandStatus.text = "Auftrag geändert. Vor der Ausführung erneut prüfen."
                    }
                }
                override fun afterTextChanged(s: Editable?) {}
            })
            stack.addView(this)
        }
        commandStatus = label("Noch kein Handy-Auftrag geprüft. Erst prüfen, dann jede Aktion einzeln bestätigen.")
        // User must deliberately select a recipient in Android's share sheet.
        button("🔎 Diagnose an ChatGPT teilen") { shareDeviceDiagnostics() }
        button("🎤 Bob zuhören lassen – einmal tippen") { openSpeechRecognizer() }
        button("🎙️ Über Tastatur-Mikrofon sprechen (Alternative)") {
            taskApproval.clear()
            clearVoicePlan()
            commandInput.requestFocus()
            commandInput.selectAll()
            val keyboard = getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager
            keyboard.showSoftInput(commandInput, InputMethodManager.SHOW_IMPLICIT)
            commandStatus.text = "Falls Google-Sprachsuche nicht verfügbar ist: " +
                "Tippe auf das Mikrofon der Samsung- oder Google-Tastatur, sprich deinen Auftrag " +
                "und wähle dann 'Handy-Auftrag prüfen'. Keine automatische Ausführung."
        }
        button("🔊 Bobs Rückmeldung vorlesen") { speakCurrentStatus() }
        // A deliberate tap on these view-only shortcuts is the approval.
        // No microphone, broker command, hidden automation or follow-up is involved.
        button("Bob direkt öffnen") { quickOpen(PhoneTask.OPEN_BOB) }
        button("Goldprodukte direkt öffnen") { quickOpen(PhoneTask.OPEN_PRODUCTS) }
        button("Mein Trade direkt öffnen") { quickOpen(PhoneTask.OPEN_TRADE) }
        button("Simulationen direkt öffnen") { quickOpen(PhoneTask.OPEN_SIMULATION) }
        button("Fehlerdiagnose direkt öffnen") { quickOpen(PhoneTask.OPEN_PROBLEMS) }
        button("Produktbilder auswählen – Auftrag vorbereiten") {
            commandInput.setText("Produktbilder auswählen")
        }
        button("Android-Einstellungen – Auftrag vorbereiten") {
            commandInput.setText("Android-Einstellungen öffnen")
        }
        button("Goldmarkt – Auftrag vorbereiten") { commandInput.setText("Goldmarkt anzeigen") }
        label("Drücke das Mikrofon und sage z. B.: „Zeige meine Goldprodukte“, „Welches hat den höchsten Hebel?“ oder nach einer Produkterklärung „Warum?“. Einzelne bekannte Bob-Anzeigen öffnen direkt. Unklare Anfragen und mehrteilige Aufträge werden NICHT automatisch ausgeführt. Bei STOPP, Textaufträgen, Bildauswahl und Einstellungen gelten gesonderte Prüfungen. Keine Daueraufnahme; der Android-Sprachanbieter kann online arbeiten.")
        button("Handy-Auftrag prüfen") {
            previewTask(commandInput.text.toString())
        }
        executeButton = button("Geprüften Handy-Auftrag einmalig ausführen") {
            val current = parseDisplayedTask(commandInput.text.toString())
            if (current == null || !taskApproval.consume(current, SystemClock.elapsedRealtime())) {
                commandOutcome = DeviceDiagnosticShare.Outcome.REJECTED
                commandStatus.text = "Auftrag fehlt, wurde geändert, ist abgelaufen oder ist unzulässig. Erneut prüfen."
            } else {
                // No next step is ever launched automatically. On return from
                // the external app the user must review and confirm again.
                val launched = when (current) {
                    PhoneTask.OPEN_BOB -> openBobHome()
                    PhoneTask.PICK_IMAGES -> openImagePicker()
                    PhoneTask.OPEN_SETTINGS -> try {
                        startActivity(Intent(Settings.ACTION_SETTINGS))
                        true
                    } catch (_: Exception) { false }
                    PhoneTask.OPEN_PRODUCTS -> openBobPage("products")
                    PhoneTask.OPEN_LONG_REVIEW -> openBobPage("products-long")
                    PhoneTask.OPEN_LEVERAGE_REVIEW -> openBobPage("products-leverage")
                    PhoneTask.OPEN_TRADE -> openBobPage("trade")
                    PhoneTask.OPEN_SIMULATION -> openBobPage("simulation")
                    PhoneTask.OPEN_PROBLEMS -> openBobPage("problems")
                    PhoneTask.OPEN_LEARNING -> openBobPage("learning")
                    PhoneTask.OPEN_RESEARCH -> openBobPage("research")
                    PhoneTask.OPEN_MARKET -> openBobPage("overview")
                }
                commandOutcome = if (launched) DeviceDiagnosticShare.Outcome.STARTED_NOT_VERIFIED
                    else DeviceDiagnosticShare.Outcome.FAILED
                if (!launched) {
                    commandStatus.text = "Der Auftrag konnte nicht gestartet werden. Keine weitere Aktion ausgelöst. Erneut prüfen."
                } else if (voiceSteps.getOrNull(voiceStepIndex) == current) {
                    conversation.recordLaunched(current, SystemClock.elapsedRealtime())
                    voiceStepIndex++
                    if (voiceStepIndex < voiceSteps.size) {
                        val next = voiceSteps[voiceStepIndex]
                        setCommandTextInternally(PhoneTaskProtocol.displayLabel(next))
                        commandStatus.text = "Schritt $voiceStepIndex von ${voiceSteps.size} angestoßen. " +
                            "Nächster Schritt ${voiceStepIndex + 1}: ${next.description}. " +
                            "Bitte wieder PRÜFEN und danach einzeln AUSFÜHREN. STOPP verwirft den Rest."
                    } else {
                        clearVoicePlan()
                        setCommandTextInternally("Bob öffnen")
                        commandStatus.text = "Alle erkannten Schritte wurden einzeln angestoßen. Keine weitere Aktion geplant."
                    }
                } else {
                    conversation.recordLaunched(current, SystemClock.elapsedRealtime())
                    clearVoicePlan()
                    setCommandTextInternally("Bob öffnen")
                    commandStatus.text = "Einmaliger Auftrag angestoßen: ${current.description}. Keine Folgeaktion."
                }
            }
        }
        button("STOPP – Auftrag verwerfen") { emergencyStop() }
        // Keep the ONE required action tap directly under the recognized
        // transcript/status, instead of far below all other navigation buttons.
        // Multi-step plans still need a fresh explicit check for each next step.
        stack.removeView(executeButton)
        stack.addView(executeButton, stack.indexOfChild(commandStatus) + 1)
        label("Freigaben gelten einmalig und höchstens 60 Sekunden. Bei Textänderung, App-Wechsel oder STOPP werden sie ungültig.")
        mainScroll = ScrollView(this).apply { addView(stack) }
        setContentView(mainScroll)
        processUserShare(intent)
    }

    override fun onPause() {
        // No unfinished command survives a switch to another app or the background.
        taskApproval.clear()
        chatShareApproval.clear()
        chatShareTask = null
        if (::chatShareSection.isInitialized && chatShareSection.visibility == View.VISIBLE) {
            chatShareStatus.text = "Die Freigabe wurde beim App-Wechsel verworfen. Auftrag bitte erneut teilen."
        }
        if (::remoteStatus.isInitialized) {
            remoteCoupling.discardPending()
            remotePendingTask = null
        }
        super.onPause()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        processUserShare(intent)
    }

    private fun processUserShare(incoming: Intent?) {
        if (incoming == null) return
        if (incoming.action == Intent.ACTION_VIEW) {
            // One explicitly opened HTTPS App Link can show ONLY a fixed
            // read-only page on Bob's own origin. This is not a command or
            // broker authorization. The exact-link parser rejects all other
            // hosts, paths, parameters and multi-action inputs.
            val direct = BobHandyDeepLink.directHttpsDisplay(incoming.dataString)
            if (direct != null) {
                val section = BobNavigation.pageFor(direct)
                val launched = section != null && openBobPage(section)
                commandOutcome = if (launched) DeviceDiagnosticShare.Outcome.STARTED_NOT_VERIFIED
                    else DeviceDiagnosticShare.Outcome.FAILED
                remoteAudit.append(System.currentTimeMillis(),
                    if (launched) RemoteAuditEvent.SHARE_LAUNCHED_NOT_VERIFIED
                    else RemoteAuditEvent.SHARE_LAUNCH_FAILED, direct)
                if (launched) {
                    commandStatus.text = "HTTPS-Anzeigelink: Bob-Seite angestoßen. " +
                        "Browser-Anzeige nicht verifiziert; Anmeldung bleibt erforderlich."
                    return
                }
                // Browser unavailable: show the ordinary approved fallback.
                // Never silently claim the target website loaded.
            }
            // Legacy custom scheme (or failed HTTPS browser navigation)
            // only proposes one local action with an explicit second approval.
            val task = BobHandyDeepLink.parse(incoming.dataString)
            previewChatShare(task?.let { "BOB-HANDY/1|" + it.name } ?: "")
            return
        }
        if (incoming.action == Intent.ACTION_SEND && incoming.type == "text/plain") {
            // Untrusted text coming from Android Sharesheet: only preview it.
            // No shared text is ever executed or relayed automatically.
            val received = incoming.getStringExtra(Intent.EXTRA_TEXT).orEmpty()
            if (received.startsWith("BOB-FERN/1|")) {
                // Android sharing is UNTRUSTED transport. Signed proposal only;
                // it cannot trigger a browser launch without a later local tap.
                previewRemote(received)
                return
            }
            // Ordinary Android share is NOT authenticated ChatGPT remote control.
            // Exact allowlisted, harmless single action; owner must tap approval.
            previewChatShare(received)
            return
        }
        if (incoming.action !in listOf(Intent.ACTION_SEND, Intent.ACTION_SEND_MULTIPLE) ||
            !incoming.type.orEmpty().startsWith("image/")) return
        @Suppress("DEPRECATION")
        val direct: List<Uri> = if (incoming.action == Intent.ACTION_SEND_MULTIPLE) {
            incoming.getParcelableArrayListExtra<Uri>(Intent.EXTRA_STREAM)?.toList().orEmpty()
        } else {
            listOfNotNull(incoming.getParcelableExtra<Uri>(Intent.EXTRA_STREAM))
        }
        val clip = incoming.clipData
        val viaClip = (0 until (clip?.itemCount ?: 0)).mapNotNull { clip?.getItemAt(it)?.uri }
        readImages((direct + viaClip).distinct(), openAfterRead = true)
    }

    @Deprecated("Android's activity-result API retained here to avoid framework dependencies in the lab.")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == recognizeSpeechRequest) {
            taskApproval.clear()
            if (resultCode != RESULT_OK) {
                speechOutcome = DeviceDiagnosticShare.Outcome.UNAVAILABLE
                commandStatus.text = "Android hat keinen Sprachtext zurückgegeben. " +
                    "Falls Google 'Sprachsuche nicht verfügbar' meldet, benutze " +
                    "'Über Tastatur-Mikrofon sprechen (Alternative)'. Nichts ausgeführt."
                return
            }
            val spoken = data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)
                ?.firstOrNull().orEmpty()
            speechOutcome = DeviceDiagnosticShare.Outcome.RECOGNIZED
            val inquiry = spoken.lowercase(Locale.GERMAN).trim()
                .replace(Regex("[.!?]+$"), "").replace(Regex("\\s+"), " ")
            if (inquiry in setOf("was kannst du", "bob was kannst du",
                    "was kann ich sagen", "hilfe", "sprachhilfe")) {
                commandStatus.text = "Du kannst sagen: Zeige Goldprodukte, analysiere den Goldmarkt, " +
                    "öffne Mein Trade, zeige Simulationen, Lernen oder Recherche, " +
                    "wähle Produktbilder aus. Auch mehrere Schritte mit 'und danach'. " +
                    "Nach einer ausgeführten Aktion kannst du 'Nochmal' sagen. " +
                    "Einzelne reine Anzeigeaufträge starten nach Mikrofontipp direkt. " +
                    "Für mehrere Schritte, Bildauswahl und Einstellungen bleibt die Bestätigung nötig."
                return
            }
            if (inquiry in setOf("was kommt als nächstes", "was ist als nächstes dran",
                    "welcher schritt kommt als nächstes", "was ist der nächste schritt")) {
                val currentNext = voiceSteps.getOrNull(voiceStepIndex)
                commandStatus.text = if (currentNext == null)
                    "Momentan ist keine weitere Schrittfolge geplant." else
                    "Noch offen: Schritt ${voiceStepIndex + 1} von ${voiceSteps.size}: " +
                    "${currentNext.description}. Bitte neu PRÜFEN, dann einzeln AUSFÜHREN."
                return
            }
            clearVoicePlan()
            if (PhoneTaskPlanParser.isStop(spoken)) {
                emergencyStop()
                speechOutcome = DeviceDiagnosticShare.Outcome.STOPPED
                commandStatus.text = "STOPP erkannt. Alle noch offenen lokalen und Fernaufträge verworfen."
                return
            }
            val plan = conversation.interpret(spoken, SystemClock.elapsedRealtime())
            if (plan == null) {
                speechOutcome = DeviceDiagnosticShare.Outcome.REJECTED
                setCommandTextInternally(spoken.take(100))
                commandStatus.text = "Sprachauftrag unklar oder nicht erlaubt. Nichts ausgeführt. Erlaubt sind nur bekannte Bob-Seiten, lokale Bildauswahl und Einstellungen. Zum Beispiel: Zeige Goldprodukte und danach Simulationen."
            } else {
                voiceSteps = plan.steps
                voiceStepIndex = 0
                setCommandTextInternally(PhoneTaskProtocol.displayLabel(plan.steps.first()))
                val safeNavigation = VoiceAutoNavigation.allowed(plan)
                if (safeNavigation != null) {
                    // The user's ONE microphone tap activates only this one
                    // locally validated Bob page. Never launch other apps,
                    // screenshots, settings, passwords, or broker actions.
                    val section = BobNavigation.pageFor(safeNavigation)
                    val launched = section != null && openBobPage(section)
                    commandOutcome = if (launched) DeviceDiagnosticShare.Outcome.STARTED_NOT_VERIFIED
                        else DeviceDiagnosticShare.Outcome.FAILED
                    if (launched) {
                        conversation.recordLaunched(safeNavigation, SystemClock.elapsedRealtime())
                        commandStatus.text = "Sprachauftrag erkannt und Bob-Seite geöffnet: " +
                            safeNavigation.description + ". " +
                            "Ob die angezeigten Produktdaten aktuell sind, prüfst du in Bob."
                        clearVoicePlan()
                        setCommandTextInternally("Bob öffnen")
                    } else {
                        commandStatus.text = "Sprachauftrag verstanden, aber Bob konnte nicht " +
                            "geöffnet werden. Keine weitere Aktion ausgeführt."
                    }
                } else {
                    executeButton.text = "Geprüften Handy-Auftrag einmalig ausführen"
                    commandStatus.text = "Sprachplan erkannt: ${plan.summary()}. " +
                        "Keine automatische Ausführung (mehrere Schritte oder geschützte Aktion). " +
                        "Bitte PRÜFEN und jeden Schritt ausdrücklich AUSFÜHREN. STOPP bricht ab."
                }
            }
            return
        }
        if (requestCode != selectImageRequest || resultCode != RESULT_OK) return
        val clip = data?.clipData
        val viaClip = (0 until (clip?.itemCount ?: 0)).mapNotNull { clip?.getItemAt(it)?.uri }
        val all = (listOfNotNull(data?.data) + viaClip).distinct()
        readImages(all)
    }

    /** Speech recognition is requested only after a user taps the mic button. */
    private fun openSpeechRecognizer() {
        // A previous approval must never survive launching an external activity.
        taskApproval.clear()
        executeButton.text = "Geprüften Handy-Auftrag einmalig ausführen"
        commandStatus.text = "Bob hört nur für diesen einen Sprachauftrag zu. Eine erlaubte Bob-Seite kann anschließend direkt geöffnet werden; keine Handelsorders."
        val request = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.GERMANY.toLanguageTag())
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
            // Never force the offline speech path: some Samsung Google providers
            // fail with "Die Sprachsuche ist nicht verfügbar" when requested.
            // Android's chosen voice provider may still use online processing.
            putExtra(RecognizerIntent.EXTRA_PROMPT, "Zum Beispiel: Zeige Goldprodukte oder erkläre den höchsten Hebel")
        }
        try {
            startActivityForResult(request, recognizeSpeechRequest)
        } catch (_: Exception) {
            speechOutcome = DeviceDiagnosticShare.Outcome.UNAVAILABLE
            commandStatus.text = "Android-Sprachdialog nicht verfügbar. Benutze " +
                "'Über Tastatur-Mikrofon sprechen (Alternative)' oder das Textfeld."
        }
    }

    // Friendly labels are UI conveniences. Shared text remains strictly limited
    // to the existing BOB-AUFTRAG protocol.
    private fun parseDisplayedTask(text: String): PhoneTask? =
        PhoneTaskProtocol.parseDisplayed(text)

    private fun previewTask(text: String) {
        if (PhoneTaskPlanParser.isStop(text)) {
            emergencyStop()
            return
        }
        // Accept only a fully validated bounded plan from keyboard dictation.
        // If any clause is unknown, no action is approved.
        val single = parseDisplayedTask(text)
        val dictatedPlan = if (single == null) PhoneTaskPlanParser.parse(text) else null
        taskApproval.clear()
        if (dictatedPlan != null) {
            clearVoicePlan()
            voiceSteps = dictatedPlan.steps
            voiceStepIndex = 0
            setCommandTextInternally(PhoneTaskProtocol.displayLabel(dictatedPlan.steps.first()))
        }
        val task = single ?: dictatedPlan?.steps?.firstOrNull()
        commandStatus.text = if (task == null) {
            if (text.isBlank()) {
                "Noch kein Auftrag eingegeben. Du kannst auch das Tastatur-Mikrofon verwenden."
            } else {
                "Dieser Auftrag ist unklar oder nicht erlaubt. Keine Aktion. " +
                    "Erlaubt sind nur bekannte Bob-Bereiche, Bildauswahl und Einstellungen."
            }
        } else {
            taskApproval.approve(task, SystemClock.elapsedRealtime())
            val context = if (voiceSteps.getOrNull(voiceStepIndex) == task) {
                " Gesamtplan: ${PhoneTaskPlan(voiceSteps).summary()}. " +
                    "Schritt ${voiceStepIndex + 1} von ${voiceSteps.size}. "
            } else ""
            "Prüfung OK: ${task.description}.$context " +
                "Innerhalb von 60 Sekunden einmalig ausführen oder STOPP drücken."
        }
    }

    private fun openImagePicker(): Boolean = try {
        val picker = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "image/*"
            putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
        }
        startActivityForResult(picker, selectImageRequest)
        true
    } catch (_: Exception) { false }

    private fun quickOpen(task: PhoneTask) {
        val section = BobNavigation.pageFor(task) ?: return
        taskApproval.clear()
        clearVoicePlan()
        if (openBobPage(section)) {
            commandOutcome = DeviceDiagnosticShare.Outcome.STARTED_NOT_VERIFIED
            conversation.recordLaunched(task, SystemClock.elapsedRealtime())
            commandStatus.text = "${task.description} wurde gestartet. Ob die Seite vollständig geladen ist, siehst du im Browser. Keine Folgeaktion."
        } else {
            commandOutcome = DeviceDiagnosticShare.Outcome.FAILED
            commandStatus.text = "Bob konnte diese Seite nicht öffnen. Keine Folgeaktion."
        }
    }

    private fun openBobHome(): Boolean = openBobPage("overview")

    /** Only documented, read-only sections of Bob itself. No untrusted URL or
     * third-party package can be selected by speech. Login stays manual. */
    private fun openBobPage(section: String): Boolean {
        // Fresh nonce avoids reopening an existing browser tab at the last
        // viewed Gold card when the user repeats the voice navigation.
        val safeUrl = BobNavigation.urlForSection(section, SystemClock.elapsedRealtimeNanos()) ?: return false
        return try {
            val browser = Intent(Intent.ACTION_VIEW, Uri.parse(safeUrl)).apply {
                addCategory(Intent.CATEGORY_BROWSABLE)
            }
            startActivity(browser)
            true
        } catch (_: Exception) {
            commandStatus.text = "Bob konnte im Browser nicht geöffnet werden."
            false
        }
    }

    private fun emergencyStop() {
        getSharedPreferences("product_reader", MODE_PRIVATE).edit().putBoolean("enabled", false).apply()
        ProductReadRequest.cancel(); ProductReadSession.clear(); ProductReadDiagnostics.clear()
        remoteCoupling.stopped()
        remotePendingTask = null
        if (::remoteInput.isInitialized) remoteInput.setText("")
        if (::remoteStatus.isInitialized) remoteStatus.text =
            "STOPP aktiv: Kopplung widerrufen und Fernaufträge gesperrt."
        taskApproval.clear()
        chatShareApproval.clear()
        chatShareTask = null
        if (::chatShareSection.isInitialized && chatShareSection.visibility == View.VISIBLE) {
            chatShareStatus.text = "STOPP: geteilter Auftrag gesperrt. Neue ausdrückliche Freigabe erforderlich."
        }
        clearVoicePlan()
        conversation.clear()
        speaker?.stop()
        if (::commandInput.isInitialized) setCommandTextInternally("Bob öffnen")
        commandOutcome = DeviceDiagnosticShare.Outcome.STOPPED
        if (::commandStatus.isInitialized) commandStatus.text =
            "STOPP: alle offenen lokalen und Fernaufträge verworfen. Bereits geöffnete Apps werden nicht rückgängig gemacht."
    }

    private fun previewChatShare(raw: String) {
        if (!::chatShareSection.isInitialized) return
        chatShareApproval.clear()
        chatShareTask = null
        chatShareSection.visibility = View.VISIBLE
        // Bring user-proposed command and its explicit confirmation into view
        // on an already-scrolled Samsung; no click or activity is triggered.
        if (::mainScroll.isInitialized) mainScroll.post { mainScroll.smoothScrollTo(0, 0) }
        val task = ChatShareHandoff.parse(raw)
        if (task == null) {
            chatShareStatus.text = "Geteilter Auftrag abgelehnt. Erlaubt ist nur eine bekannte Bob-Anzeige. Nichts gestartet."
            remoteAudit.append(System.currentTimeMillis(), RemoteAuditEvent.SHARE_REJECTED, null)
            return
        }
        chatShareTask = task
        chatShareApproval.approve(task, SystemClock.elapsedRealtime())
        remoteAudit.append(System.currentTimeMillis(), RemoteAuditEvent.SHARE_PREVIEWED, task)
        chatShareStatus.text = "Per Link/Android-Teilen vorgeschlagen: " +
            PhoneTaskProtocol.displayLabel(task) +
            ". Wenn du es möchtest, innerhalb von 60 Sekunden auf „Geteilten Anzeigeauftrag einmalig öffnen“ tippen."
    }

    private fun previewRemote(raw: String) {
        if (!::remoteStatus.isInitialized) return
        remotePendingTask = null
        val verified = remoteCoupling.receive(
            raw, SystemClock.elapsedRealtime(), System.currentTimeMillis())
        // Clear raw material from UI. Never copy an authenticated envelope
        // into the ordinary voice parser, persistent storage or audit trail.
        remoteInput.setText("")
        if (verified == null) {
            remoteStatus.text = "Fernauftrag abgelehnt: Signatur, Sitzung, Uhrzeit, Wiederholung oder erlaubte Aktion ungültig. Keine Ausführung."
            return
        }
        remotePendingTask = verified
        remoteStatus.text = "Signiert geprüft: " +
            PhoneTaskProtocol.displayLabel(verified) +
            ". Nur diese einmalige, harmlose Anzeige. Tippe zur Freigabe ausdrücklich auf „Geprüften Fernauftrag EINMAL erlauben“. Wechseln der App oder STOPP verwirft den Auftrag."
    }

    private fun shareDeviceDiagnostics() {
        // The app has no network permission. This only opens the chooser.
        val version = runCatching {
            packageManager.getPackageInfo(packageName, 0).versionName.orEmpty()
        }.getOrDefault("unknown")
        val message = DeviceDiagnosticShare.report(
            version, commandOutcome, speechOutcome, imageOutcome,
            lastDiagnosticImageCount,
            if (voiceSteps.isEmpty()) 0 else
                (voiceSteps.size - voiceStepIndex).coerceIn(0, 5)
        )
        val share = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_TEXT, message)
        }
        try {
            startActivity(Intent.createChooser(share, "Diagnoseziel bewusst auswählen"))
        } catch (_: Exception) {
            commandStatus.text = "Diagnose konnte nicht geteilt werden. Keine Übertragung."
        }
    }

    private fun speakCurrentStatus() {
        // Local status strings only; never read private screenshots, OCR, PINs,
        // broker data, passwords, or text from other apps.
        val words = commandStatus.text.toString().take(480)
        if (words.isBlank()) return
        if (speakerReady) {
            speaker?.speak(words, TextToSpeech.QUEUE_FLUSH, null, "bob-status")
        } else {
            pendingSpeech = words
            if (speaker == null) {
                speaker = TextToSpeech(this) { outcome ->
                    val languageResult = if (outcome == TextToSpeech.SUCCESS)
                        speaker?.setLanguage(Locale.GERMAN) else null
                    speakerReady = languageResult != null && languageResult >= 0
                    if (speakerReady) {
                        pendingSpeech?.let {
                            speaker?.speak(it, TextToSpeech.QUEUE_FLUSH, null, "bob-status")
                        }
                    } else if (::commandStatus.isInitialized) {
                        commandStatus.text = "Deutsche Sprachausgabe ist auf diesem Samsung nicht verfügbar."
                    }
                    pendingSpeech = null
                }
            }
        }
    }

    override fun onDestroy() {
        speaker?.stop()
        speaker?.shutdown()
        speaker = null
        super.onDestroy()
    }

    private fun openInBob(draft: String) {
        // Single checksum-valid ISIN plus narrowly captured non-secret fields only.
        // The URL *fragment* is not sent as part of HTTPS requests to the Bob server.
        // Bob removes the fragment immediately after opening its authenticated UI.
        if (draft.isBlank() || draft.length > 1600) {
            status.text = "Entwurf nicht übertragbar; bitte das Bild lokal prüfen."
            return
        }
        try {
            val target = Uri.parse(
                "https://bob-private-scanner.onrender.com/#bob-ocr=" + Uri.encode(draft)
            )
            val browser = Intent(Intent.ACTION_VIEW, target).apply {
                addCategory(Intent.CATEGORY_BROWSABLE)
            }
            startActivity(browser)
            status.text = "Bob geöffnet. Werte bleiben unbestätigt und werden nicht als Kursnachweis gespeichert."
        } catch (_: Exception) {
            status.text = "Bob konnte nicht geöffnet werden. Du kannst den Entwurf weiterhin kopieren."
        }
    }

    private fun readImages(uris: List<Uri>, openAfterRead: Boolean = false) {
        val serial = ++imageReadSequence
        imageOutcome = DeviceDiagnosticShare.Outcome.NOT_TESTED
        lastDiagnosticImageCount = uris.size.takeIf { it in 1..4 } ?: 0
        evidenceDraft = ""
        if (uris.isEmpty() || uris.size > 4) {
            status.text = "Bitte ein bis vier Produktbilder auswählen."
            return
        }
        imageOutcome = DeviceDiagnosticShare.Outcome.STARTED_NOT_VERIFIED
        status.text = "${uris.size} Bild(er) werden lokal gelesen. Nichts wird hochgeladen."
        val recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
        val texts = mutableListOf<String>()
        val observations = mutableListOf<Map<String, String>>()

        fun fail(reason: String) {
            if (serial == imageReadSequence) {
                imageOutcome = DeviceDiagnosticShare.Outcome.FAILED
                evidenceDraft = ""
                status.text = reason
            }
            recognizer.close()
        }
        fun scan(index: Int) {
            if (serial != imageReadSequence) {
                recognizer.close()
                return
            }
            if (index == uris.size) {
                // One unambiguous valid ISIN anchors a deliberately selected
                // series. Neighboring screenshots without OCR-identifiable ISIN
                // remain only provisionally associated. A different readable
                // instrument blocks the entire series.
                val series = SeriesEvidence.analyze(texts)
                if (series == null) {
                    fail("Die Bildserie hat keine eindeutige gemeinsame ISIN oder zeigt widersprüchliche Produkte. Bitte ein Bild mit sichtbarer ISIN ergänzen.")
                    return
                }
                val fieldNames = listOf("Geld", "Brief", "Hebel", "KO-Schwelle", "Handelsplatz", "Zuletzt", "Anzeigezeit")
                val fields = linkedMapOf<String, String>()
                val conflicting = mutableListOf<String>()
                for (name in fieldNames) {
                    val values = observations.mapNotNull { it[name] }.distinct()
                    if (values.size > 1) conflicting += name
                    else if (values.size == 1) fields[name] = values.single()
                }
                if (conflicting.isNotEmpty()) {
                    fail("Die Bilder haben unterschiedliche Werte für: " + conflicting.joinToString(", ") +
                        ". Bitte nur zeitgleiche Bilder desselben Produkts wählen.")
                    return
                }
                evidenceDraft = runCatching {
                    draftFromOcr(
                        series.isin, fields,
                        imageCount = series.imageCount,
                        anchorCount = series.anchorCount
                    )
                }.getOrDefault("")
                imageOutcome = if (evidenceDraft.isBlank()) DeviceDiagnosticShare.Outcome.REJECTED
                    else DeviceDiagnosticShare.Outcome.RECOGNIZED
                status.text = if (evidenceDraft.isBlank()) {
                    "OCR-Daten uneindeutig oder widersprüchlich. Bitte Bilder einzeln prüfen."
                } else {
                    val matched = series.anchorCount
                    val note = if (series.provisional)
                        "Die übrigen Bilder wurden als bewusst ausgewählte Serie vorläufig zugeordnet."
                    else "Die gleiche ISIN wurde auf allen Bildern erkannt."
                    "Bildserie: ${series.imageCount} Bilder · ISIN ${series.isin} · ${matched} mit eindeutig erkannter ISIN. $note\n\n$evidenceDraft"
                }
                recognizer.close()
                if (openAfterRead && evidenceDraft.isNotBlank()) openInBob(evidenceDraft)
                return
            }
            val input = try {
                InputImage.fromFilePath(this, uris[index])
            } catch (_: Exception) {
                fail("Mindestens ein Bild konnte nicht gelesen werden.")
                return
            }
            recognizer.process(input)
                .addOnSuccessListener {
                    if (serial == imageReadSequence) {
                        texts.add(it.text)
                        val coordinates = it.textBlocks.flatMap { block ->
                            block.lines.flatMap { line ->
                                // ML Kit may group several visual columns into one line.
                                // Element geometry keeps left/right quotes separate.
                                (listOf(line.text to line.boundingBox) +
                                    line.elements.map { element -> element.text to element.boundingBox })
                                    .mapNotNull { (word, bounds) ->
                                        if (bounds == null) null else QuoteLayout.Line(
                                            word, bounds.left, bounds.top, bounds.right, bounds.bottom
                                        )
                                    }
                            }
                        }
                        observations.add(QuoteLayout.extract(coordinates))
                        scan(index + 1)
                    }
                }
                .addOnFailureListener { fail("Texterkennung fehlgeschlagen. Keine Daten übernommen.") }
        }
        scan(0)
    }

    private fun draftFromOcr(
        isin: String, fields: Map<String, String>, imageCount: Int, anchorCount: Int
    ): String {
        if (!SeriesEvidence.validIsin(isin) || imageCount !in 1..4 ||
            anchorCount !in 1..imageCount) return ""

        fun observed(label: String, kind: String): String {
            val value = fields[label] ?: return ""
            val valid = when (kind) {
                "amount" -> Regex("[0-9]{1,5},[0-9]{2,4}").matches(value)
                "venue" -> Regex("[A-ZÀ-Ÿ0-9 ._/-]{2,48}").matches(value)
                "time" -> Regex("\\d{2}/\\d{2}/20\\d{2} \\d{2}:\\d{2}").matches(value)
                else -> false
            }
            if (!valid) return ""
            return "\n$label (OCR ungeprüft): $value"
        }

        val evidence = listOf(
            observed("Geld", "amount"), observed("Brief", "amount"),
            observed("Hebel", "amount"), observed("KO-Schwelle", "amount"),
            observed("Handelsplatz", "venue"), observed("Zuletzt", "amount"),
            observed("Anzeigezeit", "time")
        ).joinToString("")
        return "BOB OCR-ENTWURF – NICHT VERIFIZIERT\nISIN: $isin$evidence\n" +
            "Bildserie (OCR ungeprüft): $imageCount Bilder, $anchorCount mit gültiger ISIN\n" +
            "Bildzeit/Originalquelle wurden nicht verifiziert. " +
            "Kein automatischer Handelsnachweis, keine Freigabe, keine Order."
    }

    private fun validIsin(isin: String): Boolean {
        if (!Regex("[A-Z]{2}[A-Z0-9]{9}[0-9]").matches(isin)) return false
        val digits = buildString {
            for (char in isin) {
                if (char in 'A'..'Z') append((char.code - 'A'.code + 10).toString())
                else append(char)
            }
        }
        var total = 0
        for ((index, char) in digits.reversed().withIndex()) {
            val value = char.digitToInt() * if (index % 2 == 1) 2 else 1
            total += (value / 10) + (value % 10)
        }
        return total % 10 == 0
    }
}
