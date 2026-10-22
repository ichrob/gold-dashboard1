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
    private val taskApproval = PhoneTaskApproval()
    private val conversation = PhoneConversation()
    private var speaker: TextToSpeech? = null
    private var speakerReady = false
    private var pendingSpeech: String? = null
    // An untrusted transcript is never executed. Plans exist only in memory;
    // every step requires a NEW one-shot confirmation after an explicit preview.
    private var voiceSteps = emptyList<PhoneTask>()
    private var voiceStepIndex = 0
    private var internalCommandChange = false

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

        label("BOB ANDROID-LABOR: Produktbild teilen, automatisch erkennen und in Bob prüfen. Keine Handelsorders.")
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

        label("HANDYSTEUERUNG – Bob öffnen ist vorausgewählt. Nur auf Prüfen und danach auf Ausführen tippen. Keine Fernsteuerung oder Broker-Klicks.")
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
                    if (::commandStatus.isInitialized) {
                        commandStatus.text = "Auftrag geändert. Vor der Ausführung erneut prüfen."
                    }
                }
                override fun afterTextChanged(s: Editable?) {}
            })
            stack.addView(this)
        }
        commandStatus = label("Noch kein Handy-Auftrag geprüft. Erst prüfen, dann jede Aktion einzeln bestätigen.")
        button("🎤 Auftrag sprechen") { openSpeechRecognizer() }
        button("🔊 Bobs Rückmeldung vorlesen") { speakCurrentStatus() }
        button("Bob öffnen auswählen") { commandInput.setText("Bob öffnen") }
        button("Produktbilder auswählen – Auftrag vorbereiten") {
            commandInput.setText("Produktbilder auswählen")
        }
        button("Android-Einstellungen – Auftrag vorbereiten") {
            commandInput.setText("Android-Einstellungen öffnen")
        }
        button("Goldprodukte – Auftrag vorbereiten") { commandInput.setText("Goldprodukte anzeigen") }
        button("Goldmarkt – Auftrag vorbereiten") { commandInput.setText("Goldmarkt anzeigen") }
        button("Mein Trade – Auftrag vorbereiten") { commandInput.setText("Mein Trade anzeigen") }
        button("Simulationen – Auftrag vorbereiten") { commandInput.setText("Simulationen anzeigen") }
        label("Sprich zum Beispiel: „Zeige meine Goldprodukte und danach die Simulationen“. Du kannst später „Und jetzt die Recherche“ oder „Nochmal“ sagen. Jeder Schritt braucht Prüfen und Ausführen. Der Gesprächskontext bleibt nur kurz im Speicher. Kein dauerhaftes Zuhören; Androids Sprachanbieter und die optionale Sprachausgabe können Online-Dienste nutzen.")
        button("Handy-Auftrag prüfen") {
            previewTask(commandInput.text.toString())
        }
        button("Geprüften Handy-Auftrag einmalig ausführen") {
            val current = parseDisplayedTask(commandInput.text.toString())
            if (current == null || !taskApproval.consume(current, SystemClock.elapsedRealtime())) {
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
                    PhoneTask.OPEN_TRADE -> openBobPage("trade")
                    PhoneTask.OPEN_SIMULATION -> openBobPage("simulation")
                    PhoneTask.OPEN_LEARNING -> openBobPage("learning")
                    PhoneTask.OPEN_RESEARCH -> openBobPage("research")
                    PhoneTask.OPEN_MARKET -> openBobPage("overview")
                }
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
        button("STOPP – Auftrag verwerfen") {
            taskApproval.clear()
            clearVoicePlan()
            conversation.clear()
            speaker?.stop()
            setCommandTextInternally("Bob öffnen")
            commandStatus.text = "Gestoppt. Keine weiteren Schritte geplant. Eine schon geöffnete App wird nicht rückgängig gemacht."
        }
        label("Freigaben gelten einmalig und höchstens 60 Sekunden. Bei Textänderung, App-Wechsel oder STOPP werden sie ungültig.")
        setContentView(ScrollView(this).apply { addView(stack) })
        processUserShare(intent)
    }

    override fun onPause() {
        // No unfinished command survives a switch to another app or the background.
        taskApproval.clear()
        super.onPause()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        processUserShare(intent)
    }

    private fun processUserShare(incoming: Intent?) {
        if (incoming == null) return
        if (incoming.action == Intent.ACTION_SEND && incoming.type == "text/plain") {
            // Untrusted text coming from Android Sharesheet: only preview it.
            // No shared text is ever executed or relayed automatically.
            val received = incoming.getStringExtra(Intent.EXTRA_TEXT).orEmpty()
            commandInput.setText(received.take(100))
            previewTask(received)
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
                commandStatus.text = "Sprachauftrag abgebrochen. Nichts ausgeführt."
                return
            }
            val spoken = data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)
                ?.firstOrNull().orEmpty()
            clearVoicePlan()
            if (PhoneTaskPlanParser.isStop(spoken)) {
                conversation.clear()
                speaker?.stop()
                setCommandTextInternally("Bob öffnen")
                commandStatus.text = "STOPP erkannt. Alle noch offenen Aufträge verworfen."
                return
            }
            val plan = conversation.interpret(spoken, SystemClock.elapsedRealtime())
            if (plan == null) {
                setCommandTextInternally(spoken.take(100))
                commandStatus.text = "Sprachauftrag unklar oder nicht erlaubt. Nichts ausgeführt. Erlaubt sind nur bekannte Bob-Seiten, lokale Bildauswahl und Einstellungen. Zum Beispiel: Zeige Goldprodukte und danach Simulationen."
            } else {
                voiceSteps = plan.steps
                voiceStepIndex = 0
                setCommandTextInternally(PhoneTaskProtocol.displayLabel(plan.steps.first()))
                commandStatus.text = "Erkannter Sprachplan: ${plan.summary()}. " +
                    "Schritt 1 von ${plan.steps.size}: ${plan.steps.first().description}. " +
                    "Noch NICHT freigegeben. Bitte PRÜFEN und danach einzeln AUSFÜHREN. " +
                    "Alle weiteren Schritte ebenfalls neu prüfen. STOPP bricht ab."
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
        clearVoicePlan()
        commandStatus.text = "Spracherkennung gestartet. Keine Aktion wird automatisch ausgeführt."
        val request = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.GERMAN.toLanguageTag())
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
            // Only a preference: the installed speech provider may still use the internet.
            putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true)
            putExtra(RecognizerIntent.EXTRA_PROMPT, "Zum Beispiel: Öffne Bob und danach wähle Produktbilder aus")
        }
        try {
            startActivityForResult(request, recognizeSpeechRequest)
        } catch (_: Exception) {
            commandStatus.text = "Auf diesem Samsung ist keine passende Spracherkennung verfügbar. Du kannst weiterhin die beiden Buttons verwenden."
        }
    }

    // Friendly labels are UI conveniences. Shared text remains strictly limited
    // to the existing BOB-AUFTRAG protocol.
    private fun parseDisplayedTask(text: String): PhoneTask? =
        PhoneTaskProtocol.parseDisplayed(text)

    private fun previewTask(text: String) {
        val task = parseDisplayedTask(text)
        taskApproval.clear()
        commandStatus.text = if (task == null) {
            if (text.isBlank()) {
                "Noch kein Auftrag eingegeben. Bitte einen Auftrag eintippen oder einfügen."
            } else {
                "Nicht erlaubter Auftrag. Zulässig sind nur: ${PhoneTaskProtocol.OPEN_BOB}, ${PhoneTaskProtocol.PICK_IMAGES}, ${PhoneTaskProtocol.OPEN_SETTINGS}. Keine Brokerbedienung."
            }
        } else {
            taskApproval.approve(task, SystemClock.elapsedRealtime())
            val context = if (voiceSteps.getOrNull(voiceStepIndex) == task) {
                " Gesamtplan: ${PhoneTaskPlan(voiceSteps).summary()}. " +
                    "Schritt ${voiceStepIndex + 1} von ${voiceSteps.size}. "
            } else ""
            "Prüfung OK: ${task.description}.$context Innerhalb von 60 Sekunden einmalig ausführen oder STOPP drücken."
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

    private fun openBobHome(): Boolean = openBobPage("overview")

    /** Only documented, read-only sections of Bob itself. No untrusted URL or
     * third-party package can be selected by speech. Login stays manual. */
    private fun openBobPage(section: String): Boolean {
        val safeUrl = BobNavigation.urlForSection(section) ?: return false
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
        evidenceDraft = ""
        if (uris.isEmpty() || uris.size > 4) {
            status.text = "Bitte ein bis vier Produktbilder auswählen."
            return
        }
        status.text = "${uris.size} Bild(er) werden lokal gelesen. Nichts wird hochgeladen."
        val recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
        val texts = mutableListOf<String>()
        val observations = mutableListOf<Map<String, String>>()

        fun fail(reason: String) {
            if (serial == imageReadSequence) {
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
