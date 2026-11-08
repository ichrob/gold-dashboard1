package ch.bob.degirocompanion

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.DocumentsContract
import android.provider.Settings
import android.speech.RecognizerIntent
import android.widget.*
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import org.json.JSONArray
import org.json.JSONObject
import java.util.Locale

/** Private editor: an external intent cannot populate or execute a plan. */
class WorkflowActivity : Activity() {
    private lateinit var name: EditText
    private lateinit var commands: EditText
    private lateinit var goal: EditText
    private var aiGeneration = 0
    private var aiBusy = false
    private lateinit var appLabel: TextView
    private lateinit var status: TextView
    private lateinit var output: TextView
    private lateinit var resultSummary: TextView
    private lateinit var history: LinearLayout
    private lateinit var detailsPanel: LinearLayout
    private lateinit var settingsPanel: LinearLayout
    private lateinit var attachmentRemove: Button
    private var revisionBase: List<WorkflowStep>? = null
    private var panelDialog: AlertDialog? = null
    private var shownDemonstration: Pair<String,List<WorkflowStep>>? = null
    private var expectedPrompt: WorkflowExpectedResultDialog? = null
    private var attachmentBoxes = emptyMap<String, android.graphics.Rect>()
    private var selectedApp = ""
    private lateinit var cloud: CheckBox
    private var updatingCloud = false
    private val autoPrefs by lazy { getSharedPreferences("workflow_auto_v1", MODE_PRIVATE) }
    private var attachmentUri: Uri? = null
    private var attachmentBitmap: android.graphics.Bitmap? = null
    private var attachmentLabels = emptyList<String>()
    private var attachmentBusy = false
    private var attachmentGeneration = 0
    private lateinit var attachmentPreview: ImageView
    private lateinit var attachmentStatus: TextView
    private var imageGeneration = 0
    private var fileBusy = false
    private var fileCancellation: android.os.CancellationSignal? = null
    @Volatile private var fileStream: java.io.InputStream? = null
    private val saved by lazy { getSharedPreferences("local_workflows_v1", MODE_PRIVATE) }
    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
        fun column() = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        fun label(parent: LinearLayout, text: String) = TextView(this).also {
            it.text = text; it.textSize = 16f; it.setPadding(0, dp(4), 0, dp(4)); parent.addView(it)
        }
        fun button(parent: LinearLayout, text: String, action: () -> Unit) = Button(this).also {
            it.text = text; it.isAllCaps = false; it.minHeight = dp(48); it.setOnClickListener { action() }; parent.addView(it)
        }
        fun weighted(parent: LinearLayout, view: android.view.View, weight: Float = 1f) {
            view.layoutParams = LinearLayout.LayoutParams(0, -2, weight)
        }
        val root = column().apply { setPadding(dp(12), dp(4), dp(12), dp(4)) }
        val header = LinearLayout(this); root.addView(header)
        weighted(header, label(header, "Bob · Meine Aufträge").apply { textSize = 20f })
        button(header, "STOPP") { ownerOverride(); refresh() }.apply {
            contentDescription = "STOPP · Auftrag und Lesesitzung beenden"
            setTextColor(android.graphics.Color.WHITE)
            backgroundTintList = android.content.res.ColorStateList.valueOf(android.graphics.Color.rgb(179,38,30))
        }
        appLabel = button(root, "App auswählen") { chooseApp() }
        val menus = LinearLayout(this); root.addView(menus)
        weighted(menus, button(menus, "Bob etwas beibringen") { learningMenu() })
        weighted(menus, button(menus, "Einstellungen") { showPanel("Einstellungen", settingsPanel) })
        button(root, "Aufzeichnung beenden / ansehen") { showRecordedDemonstration(true) }
        status = label(root, "Bereit").apply { maxLines = 2 }
        val scroll = ScrollView(this).apply { isFillViewport = true }
        history = column(); scroll.addView(history)
        root.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))
        resultSummary = TextView(this) // Detailed summary remains available in the result dialog.
        val composer = column(); root.addView(composer)
        attachmentPreview = ImageView(this).apply {
            adjustViewBounds = true; maxHeight = dp(96); contentDescription = "Screenshot zu deinem Auftrag"
            visibility = android.view.View.GONE; composer.addView(this)
        }
        val attachmentRow = LinearLayout(this); composer.addView(attachmentRow)
        attachmentStatus = label(attachmentRow, "").apply { textSize = 13f; maxLines = 2; visibility = android.view.View.GONE }
        weighted(attachmentRow, attachmentStatus)
        attachmentRemove = button(attachmentRow, "Entfernen") { clearAttachment() }.apply { visibility = android.view.View.GONE }
        goal = EditText(this).apply {
            hint = "Was soll Bob tun?"; contentDescription = "Auftrag eingeben"; minLines = 1; maxLines = 3; gravity = android.view.Gravity.TOP
            composer.addView(this)
        }
        val actions = LinearLayout(this); composer.addView(actions)
        button(actions, "+") { pickAttachment() }.apply {
            contentDescription = "Screenshot anhängen"; layoutParams = LinearLayout.LayoutParams(dp(56), -2)
        }
        weighted(actions, button(actions, "Sprechen") { speakGoal() })
        weighted(actions, button(actions, "Senden") { sendMessage() })

        settingsPanel = column().apply { setPadding(dp(12), 0, dp(12), 0) }
        label(settingsPanel, "Regel Nummer eins: Du bestimmst. Ein neuer Start ersetzt den bisherigen Auftrag; Stopp beendet ihn.")
        label(settingsPanel, "Besitzersteuerung · diese Ablaufgrenzen legst du selbst fest. Hochschutz, PIN-Schutz, Order- und Zahlungssperre bleiben fest aktiv.")
        fun ownerNumberSetting(title: String, min: Int, max: Int, suffix: String,
            current: (WorkflowOwnerLimits) -> Int,
            changed: (WorkflowOwnerLimits, Int) -> WorkflowOwnerLimits
        ) {
            val control = Button(this).apply {
                isAllCaps = false
                text = "$title: ${current(WorkflowOwnerSettings.load(this@WorkflowActivity))} $suffix"
            }
            settingsPanel.addView(control)
            control.setOnClickListener {
                val picker = NumberPicker(this).apply {
                    minValue = min; maxValue = max
                    value = current(WorkflowOwnerSettings.load(this@WorkflowActivity))
                    wrapSelectorWheel = false
                }
                AlertDialog.Builder(this).setTitle(title).setView(picker)
                    .setPositiveButton("Speichern") { _, _ ->
                        val next = changed(WorkflowOwnerSettings.load(this), picker.value)
                        if (WorkflowOwnerSettings.save(this, next)) {
                            control.text = "$title: ${current(WorkflowOwnerSettings.load(this))} $suffix"
                            ownerOverride() // Existing task cannot silently continue under changed settings.
                            status.text = "Einstellung gespeichert · für die nächsten Aufträge aktiv"
                        } else status.text = "Einstellung konnte nicht gespeichert werden"
                    }.setNegativeButton("Abbrechen", null).show()
            }
        }
        ownerNumberSetting("Maximale Ablaufschritte", 1, WorkflowOwnerLimits.MAX_STEPS, "Schritte",
            { it.maxSteps }, { old, value -> old.copy(maxSteps = value) })
        ownerNumberSetting("Maximale Laufzeit", 1, WorkflowOwnerLimits.MAX_SESSION_MINUTES, "Minuten",
            { it.sessionMinutes }, { old, value -> old.copy(sessionMinutes = value) })
        ownerNumberSetting("Wartezeit je Schritt", 10, WorkflowOwnerLimits.MAX_STEP_TIMEOUT_SECONDS, "Sekunden",
            { it.stepTimeoutSeconds }, { old, value -> old.copy(stepTimeoutSeconds = value) })
        ownerNumberSetting("Maximal gespeicherte Abläufe", 1, WorkflowOwnerLimits.MAX_SAVED_WORKFLOWS, "Abläufe",
            { it.maxSavedWorkflows }, { old, value -> old.copy(maxSavedWorkflows = value) })
        button(settingsPanel, "Hochschutzregeln verwalten") { showSecurityRules() }
        button(settingsPanel, "Bedienungshilfe einrichten") { startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) }
        cloud = CheckBox(this).apply { text = "Bei Bedarf KI automatisch nutzen · einmal je App freigeben"; settingsPanel.addView(this) }
        cloud.setOnCheckedChangeListener { _, checked ->
            if (!updatingCloud) {
                if (checked && !LocalWorkflow.allowedApp(selectedApp)) {
                    updatingCloud = true; cloud.isChecked = false; updatingCloud = false; status.text = "Zuerst eine App auswählen"
                } else if (checked && !autoPrefs.getBoolean("cloud:" + WorkflowAiPolicy.CONSENT + ":" + selectedApp, false)) allowAutomaticCloud()
                else if (!checked) { autoPrefs.edit().remove("cloud:" + WorkflowAiPolicy.CONSENT + ":" + selectedApp).apply(); WorkflowService.stop() }
            }
        }
        button(settingsPanel, "Kostenlosen KI-Zugang prüfen") { checkAi() }
        button(settingsPanel, "Selbsttest durchführen") { ownerOverride(); startActivity(Intent(this,WorkflowSelfTestActivity::class.java)) }
        button(settingsPanel, "Details / manuelle Schritte") { showPanel("Details / manuelle Schritte", detailsPanel) }
        label(settingsPanel, "Keine Orders, Anmeldung oder Zahlungen. Keine automatische kostenpflichtige Ausweichlösung.")

        detailsPanel = column().apply { setPadding(dp(12), 0, dp(12), 0) }
        label(detailsPanel, "Auftragsfolge · Schrittzahl unter Einstellungen festlegen")
        commands = EditText(this).apply { hint = "Schritte prüfen oder ergänzen"; minLines = 3; gravity = android.view.Gravity.TOP; detailsPanel.addView(this) }
        name = EditText(this).apply { hint = "Optionaler Name"; setSingleLine(); detailsPanel.addView(this) }
        button(detailsPanel, "Schritt hinzufügen") { composeStep("") }
        button(detailsPanel, "Schritt diktieren") { speak(103, "Schritt beschreiben; anschließend prüfen und ergänzen") }
        button(detailsPanel, "Auftragsfolge starten") { panelDialog?.dismiss(); launch(false, false) }
        button(detailsPanel, "Auftrag prüfen und speichern") { save() }
        button(detailsPanel, "Auftrag manuell vorbereiten") { propose() }
        label(detailsPanel, "Beispiel: Schreibe Gold in Suchfeld. Unbekannte Ergebnisse und Platzhalter vor dem Start ergänzen.")
        button(detailsPanel, "Bildschirm-Beschriftungen lesen") { panelDialog?.dismiss(); launch(true, false) }
        button(detailsPanel, "Screenshot der gewählten App lesen") { panelDialog?.dismiss(); launch(true, true) }
        button(detailsPanel, "Gelerntes Bildschirmziel übernehmen") { teach() }
        button(detailsPanel, "Screenshot auswählen und lesen") {
            startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).apply { type = "image/*"; addCategory(Intent.CATEGORY_OPENABLE) }, 101)
        }
        button(detailsPanel, "JSON-Datei im gewählten Ordner suchen") {
            if (!fileBusy) startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).apply { addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION) }, 102)
        }
        button(detailsPanel, "Ergebnis / Beschriftungen aktualisieren") { refresh() }
        output = label(detailsPanel, "").apply { setTextIsSelectable(true) }
        root.setOnApplyWindowInsetsListener { view, insets ->
            if (android.os.Build.VERSION.SDK_INT >= 30) {
                val bars = insets.getInsets(android.view.WindowInsets.Type.systemBars() or android.view.WindowInsets.Type.ime())
                view.setPadding(bars.left + dp(12), bars.top + dp(4), bars.right + dp(12), bars.bottom + dp(4))
            } else view.setPadding(insets.systemWindowInsetLeft + dp(12), insets.systemWindowInsetTop, insets.systemWindowInsetRight + dp(12), insets.systemWindowInsetBottom)
            insets
        }
        setContentView(root)
        selectedApp = autoPrefs.getString("lastApp", "").orEmpty().takeIf { WorkflowAppRoute.selectable(it) }.orEmpty()
        updateAppLabel(); updateCloud()
        goal.setText(state?.getString("draftGoal").orEmpty())
        commands.setText(state?.getString("draftCommands").orEmpty())
        revisionBase = state?.getString("draftRevision")?.let { LocalWorkflow.parse(it, WorkflowOwnerSettings.load(this).maxSteps) }
        state?.getString("draftImage")?.let { readImage(Uri.parse(it), true) }
        renderHistory()
    }

    private fun showSecurityRules() {
        panelDialog?.dismiss()
        val current = WorkflowSecuritySettings.load(this)
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(24, 12, 24, 12)
        }
        fun explain(message: String) {
            layout.addView(TextView(this).apply { text = message; textSize = 16f; setPadding(0, 8, 0, 12) })
        }
        explain("Du bestimmst die zusätzlichen Hochschutz-Einstellungen für Bobs allgemeine App-Bedienung.")
        val readOnly = CheckBox(this).apply {
            text = "Allgemeine App-Aufträge nur lesen · keine automatischen Klicks oder Eingaben"
            isChecked = current.readOnlyWorkflows; layout.addView(this)
        }
        val offline = CheckBox(this).apply {
            text = "Externe KI-Hilfe für die allgemeine App-Bedienung abschalten · ausschließlich lokal"
            isChecked = current.offlineAiOnly; layout.addView(this)
        }
        explain("Immer geschützt: STOPP, Bildschirm- und PIN-Sperre, Passwörter, Kontodaten, Order-/Zahlungssperre und eindeutige Zielprüfung. Diese Schalter sind keine Freigabe für Echtgeldhandel oder geschützte Aktionen.")
        val revoke = Button(this).apply {
            text = "Alle bisherigen KI-App-Freigaben widerrufen"
            isAllCaps = false; layout.addView(this)
        }
        val dialog = AlertDialog.Builder(this).setTitle("Hochschutz · Besitzerverwaltung")
            .setView(ScrollView(this).apply { addView(layout) })
            .setPositiveButton("Speichern", null)
            .setNegativeButton("Zurück", null).create()
        panelDialog = dialog
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val next = WorkflowSecurityPreferences(readOnly.isChecked, offline.isChecked)
                if (WorkflowSecuritySettings.save(this, next)) {
                    ownerOverride()
                    updateCloud()
                    status.text = "Hochschutz-Einstellungen gespeichert. Bestehende Aufträge gestoppt."
                    dialog.dismiss()
                } else status.text = "Hochschutz-Einstellungen konnten nicht gespeichert werden"
            }
            revoke.setOnClickListener {
                AlertDialog.Builder(this).setTitle("Alle KI-Freigaben widerrufen?")
                    .setMessage("Nur die ausdrücklichen Freigaben für externe KI bei der allgemeinen App-Bedienung werden entfernt. Gespeicherte Abläufe und Hochschutz bleiben erhalten.")
                    .setPositiveButton("Widerrufen") { _, _ ->
                        val editor = autoPrefs.edit()
                        autoPrefs.all.keys.filter { it.startsWith("cloud:" + WorkflowAiPolicy.CONSENT + ":") }
                            .forEach { editor.remove(it) }
                        if (editor.commit()) {
                            ownerOverride()
                            updateCloud()
                            status.text = "Alle KI-App-Freigaben widerrufen"
                            dialog.dismiss()
                        } else status.text = "Widerruf konnte nicht gespeichert werden"
                    }.setNegativeButton("Abbrechen", null).show()
            }
        }
        dialog.show()
    }
    private fun pickAttachment() {
        startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).apply { type = "image/*"; addCategory(Intent.CATEGORY_OPENABLE) }, 106)
    }
    private fun speak(request: Int, prompt: String) {
        runCatching { startActivityForResult(Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "de-DE"); putExtra(RecognizerIntent.EXTRA_PROMPT, prompt)
        }, request) }.onFailure { status.text = "Sprachdienst fehlt; Textfeld oder Tastaturmikrofon verwenden" }
    }
    private fun speakGoal() = speak(105, "Auftrag sagen; danach Senden drücken")
    private fun showPanel(title: String, panel: LinearLayout) {
        panelDialog?.dismiss()
        (panel.parent as? android.view.ViewGroup)?.removeView(panel)
        panelDialog = AlertDialog.Builder(this).setTitle(title)
            .setView(ScrollView(this).apply { addView(panel) })
            .setNegativeButton("Zurück", null).setNeutralButton("STOPP") { _, _ -> ownerOverride(); refresh() }.create()
        panelDialog?.show()
    }
    private fun learningMenu() {
        val options = arrayOf("Symbol erklären und lernen", "Ablauf vormachen und lernen", "Gelernte Symbole", "Gespeicherten Ablauf laden", "Gespeicherten Ablauf löschen", "Gespeicherten Ablauf per Sprache starten", "Schritte prüfen / ergänzen", "Bekannte DEGIRO-Funktionen", "DEGIRO-Anleitung und letzte Ansicht")
        AlertDialog.Builder(this).setTitle("Bob etwas beibringen").setItems(options) { _, which ->
            when(which) {
                0 -> if (attachmentBitmap == null) { status.text = "Zuerst über + einen Screenshot anhängen"; pickAttachment() } else teachSymbol()
                1 -> startDemonstration()
                2 -> manageSymbols()
                3 -> chooseSaved(false)
                4 -> chooseSaved(true)
                5 -> speak(104, "Name eines gespeicherten Auftrags. Ein erkannter Name startet ihn.")
                6 -> showPanel("Schritte prüfen / ergänzen", detailsPanel)
                7 -> showDegiroCapabilities()
                8 -> showDegiroGuide()
            }
        }.setNegativeButton("Zurück", null).setNeutralButton("STOPP") { _, _ -> ownerOverride(); refresh() }.show()
    }
    private fun showDegiroGuide() {
        val snapshot = DegiroGuide.observation(WorkflowService.observation,
            android.os.SystemClock.elapsedRealtime() - WorkflowService.observationAt)
        AlertDialog.Builder(this).setTitle("DEGIRO-Anleitung · " + DegiroGuide.reviewed)
            .setItems((listOf(snapshot) + DegiroGuide.topics.map { it.title }).toTypedArray()) { _, index ->
                if (index == 0) {
                    AlertDialog.Builder(this).setTitle("Letzte Beobachtung").setMessage(snapshot)
                        .setPositiveButton("OK", null).show()
                } else {
                    val topic = DegiroGuide.topics[index - 1]
                    AlertDialog.Builder(this).setTitle(topic.title)
                        .setMessage(topic.explanation + "\n\nQuelle: " + topic.source + "\nGeprüft: " + DegiroGuide.reviewed)
                        .setPositiveButton("OK", null).show()
                }
            }.setNegativeButton("Zurück", null).show()
    }
    private fun showDegiroCapabilities() {
        AlertDialog.Builder(this).setTitle("Das kann Bob bereits für DEGIRO")
            .setItems(WorkflowAppRoute.capabilities.map { it.command }.toTypedArray()) { _, index ->
                selectedApp = WorkflowAppRoute.DEGIRO; revisionBase = null; clearAttachment()
                autoPrefs.edit().putString("lastApp",selectedApp).apply()
                updateAppLabel(); updateCloud(); renderHistory()
                goal.setText(WorkflowAppRoute.capabilities[index].command)
                status.text = "Bekannter lokaler Ablauf · zum Start Senden drücken. Bob prüft die nötige Einrichtung."
            }.setNegativeButton("Zurück",null).show()
    }
    private fun appName(app: String): String = runCatching { packageManager.getApplicationLabel(packageManager.getApplicationInfo(app,0)).toString() }.getOrDefault(app)
    private fun updateAppLabel() { appLabel.text = if (selectedApp.isBlank()) "App auswählen ▾" else "App: ${appName(selectedApp)} ▾" }
    private fun renderHistory() {
        if (!::history.isInitialized) return
        history.removeAllViews()
        val entries = WorkflowResultStore.history(this, selectedApp)
        if (entries.isEmpty()) {
            history.addView(TextView(this).apply { text = "Dein Auftrag und Bobs Ergebnis erscheinen hier.\n\nText schreiben oder sprechen, bei Bedarf einen Screenshot mit + anhängen und senden."; textSize = 17f; setPadding(12,24,12,24) })
            return
        }
        entries.takeLast(10).forEach { entry ->
            val card = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(16,16,16,24) }
            card.addView(TextView(this).apply { text = "Du · ${entry.optString("request",entry.optString("commands"))}"; textSize = 17f; setTextIsSelectable(true) })
            card.addView(TextView(this).apply {
                text = "Bob · " + WorkflowResultStore.summary(entry); textSize = 16f; setPadding(0,12,0,8)
                setOnClickListener { AlertDialog.Builder(this@WorkflowActivity).setTitle("Auftragsergebnis").setMessage(WorkflowResultStore.detail(entry)).setPositiveButton("Schließen",null).show() }
            })
            val row = LinearLayout(this); card.addView(row)
            fun action(title: String, block: () -> Unit) = Button(this).also { it.text = title; it.isAllCaps = false; it.setOnClickListener { block() }; row.addView(it,LinearLayout.LayoutParams(0,-2,1f)) }
            action("Wiederholen") {
                if (entry.optString("app") == selectedApp) {
                    commands.setText(entry.optString("commands")); clearAttachment(); revisionBase = null
                    launch(false,false,entry.optString("request",entry.optString("commands")),true)
                }
            }.isEnabled = entry.optBoolean("success")
            action("Ändern") {
                if (entry.optString("app") == selectedApp) {
                    clearAttachment(); revisionBase = LocalWorkflow.parse(entry.optString("commands"), WorkflowOwnerSettings.load(this).maxSteps)
                    goal.setText(entry.optString("request",entry.optString("commands"))); goal.requestFocus(); goal.selectAll()
                    status.text = "Auftrag bearbeiten oder z. B. Nimm Silber statt Gold schreiben. Danach Senden."
                    (getSystemService(INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager).showSoftInput(goal,android.view.inputmethod.InputMethodManager.SHOW_IMPLICIT)
                }
            }
            history.addView(card)
        }
    }
    override fun onResume() {
        super.onResume()
        if (::output.isInitialized) {
            WorkflowService.endDemonstration(); refresh()
            showRecordedDemonstration(false)
        }
    }
    private fun showRecordedDemonstration(force: Boolean) {
        WorkflowService.endDemonstration()
        WorkflowDraftStore.restore(this)
        val draft = WorkflowService.demonstrationDraft
        if (!force && (draft == null || draft === shownDemonstration)) return
        shownDemonstration = draft
        panelDialog?.dismiss()
        if (draft == null || draft.second.isEmpty()) {
            val reason = WorkflowService.demonstrationError.ifBlank { "Bob hat keine Klicks oder Texteingaben erkannt." }
            val text = if (draft == null) "Noch keine Aufzeichnung vorhanden. Über Bob etwas beibringen → Ablauf vormachen und lernen starten." else
                "$reason\n\nEs wurde kein ausführbarer Schritt aufgenommen. Prüfe Bobs Auftrags-Bedienungshilfe. DEGIRO vor dem Vormachen entsperren; bei geschützten Ansichten oder unbeschrifteten Symbolen kann die Aufzeichnung abbrechen."
            status.text = "Keine Schritte aufgezeichnet"
            panelDialog = AlertDialog.Builder(this).setTitle("Keine Schritte aufgezeichnet").setMessage(text)
                .setPositiveButton("Vormachen öffnen") { _, _ -> learningMenu() }.setNegativeButton("Schließen",null).create()
            panelDialog?.show(); return
        }
        val (app,steps) = draft
        if (selectedApp != app) {
            status.text = "Aufzeichnung für ${appName(app)} vorhanden"
            panelDialog = AlertDialog.Builder(this).setTitle("Aufzeichnung öffnen?")
                .setMessage("Der gespeicherte Entwurf gehört zu ${appName(app)}.")
                .setPositiveButton("Öffnen") { _, _ ->
                    selectedApp = app; autoPrefs.edit().putString("lastApp",app).apply()
                    updateAppLabel(); updateCloud(); showRecordedDemonstration(true)
                }.setNegativeButton("Abbrechen",null).create()
            panelDialog?.show(); return
        }
        commands.setText(WorkflowAiPolicy.commands(steps)); goal.setText("")
        if (WorkflowService.demonstrationError.isNotBlank()) {
            status.text = "Aufzeichnung unvollständig: " + WorkflowService.demonstrationError
            showPanel("Unvollständigen Ablauf prüfen", detailsPanel)
        } else {
            status.text = "Aufzeichnung bereit · Zusammenfassung öffnen"
            reviewDemonstration(steps, WorkflowService.demonstrationChoices)
        }
    }
    private fun refresh() {
        status.text = WorkflowService.message
        resultSummary.text = WorkflowResultStore.summary(this)
        renderHistory()
        val frame = WorkflowService.observation
        output.text = buildString {
            if (frame != null) {
                append("Letzte lokale Beobachtung · ${frame.app}\n")
                if (frame.app == WorkflowAppRoute.DEGIRO) append(DegiroGuide.observation(frame, android.os.SystemClock.elapsedRealtime() - WorkflowService.observationAt)).append('\n')
                frame.nodes.filter { it.label.isNotBlank() || it.id.isNotBlank() }.take(100).forEach {
                    append(it.label).append(if (it.editable) " [Eingabefeld]" else if (it.clickable) " [anklickbar]" else "")
                    if (it.id.isNotBlank()) append(" · ").append(it.id)
                    append('\n')
                }
            }
            if (WorkflowService.screenshotText.isNotBlank()) append("\nScreenshot-Text (OCR, ungeprüft):\n").append(WorkflowService.screenshotText)
        }
    }
    private fun chooseApp() {
        val entries = packageManager.queryIntentActivities(Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER), 0)
            .filter { WorkflowAppRoute.selectable(it.activityInfo.packageName) }.distinctBy { it.activityInfo.packageName }
            .sortedBy { it.loadLabel(packageManager).toString() }
        AlertDialog.Builder(this).setTitle("App für diesen Auftrag")
            .setItems(entries.map { "${it.loadLabel(packageManager)} · ${it.activityInfo.packageName}" }.toTypedArray()) { _, i ->
                ownerOverride(); clearAttachment(); selectedApp = entries[i].activityInfo.packageName; revisionBase = null; updateAppLabel(); renderHistory()
                autoPrefs.edit().putString("lastApp", selectedApp).apply(); updateCloud()
                if (selectedApp == WorkflowAppRoute.DEGIRO) {
                    if (goal.text.isBlank()) goal.setText("Gold suchen")
                    status.text = "DEGIRO: Goldsuche nutzt den bisherigen Leser. Andere Aufträge nutzen die allgemeine Bedienung. Bereits angemeldet starten."
                }
            }.setNegativeButton("Abbrechen", null).show()
    }
    private fun updateCloud() {
        updatingCloud = true
        cloud.isEnabled = LocalWorkflow.allowedApp(selectedApp) && WorkflowSecuritySettings.permitsCloud(WorkflowSecuritySettings.load(this))
        cloud.isChecked = cloud.isEnabled && autoPrefs.getBoolean("cloud:" + WorkflowAiPolicy.CONSENT + ":" + selectedApp, false)
        updatingCloud = false
    }
    private fun allowAutomaticCloud() {
        val app = selectedApp
        AlertDialog.Builder(this).setTitle("Automatische KI-Hilfe für diese App")
            .setMessage("Bei jedem von dir gestarteten Auftrag darf Bob bei Bedarf genau eine Google Gemini-Anfrage senden. Übertragen werden dein Auftrag sowie erkannte Such-/Filterelemente mit passenden Feld-IDs. Erlaubte Beschriftungen: " +
                WorkflowAuto.labels.joinToString(", ") +
                ". Keine Bilder, OCR-Dumps, Dateiinhalte oder Eingabefeldwerte. Der Auftrag selbst darf keine privaten Daten enthalten. Die Texte werden bei Google verarbeitet. Bob prüft Vorschläge und führt zulässige Schritte ohne weitere Rückfrage aus. Kein kostenpflichtiger Fallback. Freigabe jederzeit über diesen Schalter widerrufbar.")
            .setPositiveButton("Für diese App erlauben") { _, _ ->
                if (selectedApp == app) autoPrefs.edit().putBoolean("cloud:" + WorkflowAiPolicy.CONSENT + ":" + app, true).apply()
                updateCloud()
            }.setNegativeButton("Abbrechen") { _, _ -> updateCloud() }
            .setOnCancelListener { updateCloud() }.show()
    }
    private fun startAutomatic() {
        ownerOverride()
        if (PhoneTaskPlanParser.isStop(goal.text.toString())) { refresh(); return }
        if (selectedApp == WorkflowAppRoute.DEGIRO && WorkflowAppRoute.goldRead(goal.text.toString())) {
            val task = goal.text.toString().trim()
            WorkflowService.stop()
            autoPrefs.edit().putString("lastApp", selectedApp).putString("lastGoal", task).apply()
            startActivity(Intent(this, ProductReadActivity::class.java)
                .putExtra(ProductReadActivity.EXTRA_START_GOLD_READ, true))
            return
        }
        if (!LocalWorkflow.allowedApp(selectedApp)) { status.text = "Bitte zuerst eine App auswählen"; return }
        val task = goal.text.toString().trim()
        if (LocalWorkflow.parse(task, WorkflowOwnerSettings.load(this).maxSteps) == null && !WorkflowAiPolicy.safe(task, 500)) { status.text = "Bitte einen kurzen Auftrag ohne private Daten eingeben"; return }
        val service = WorkflowService.instance ?: run { status.text = "Einmalig die Auftrags-Bedienungshilfe über Einrichtung aktivieren"; return }
        val intent = packageManager.getLaunchIntentForPackage(selectedApp) ?: run { status.text = "App nicht mehr installiert oder nicht startbar"; return }
        stopProductReader()
        autoPrefs.edit().putString("lastApp", selectedApp).putString("lastGoal", task).apply()
        val app = selectedApp
        val cloud = autoPrefs.getBoolean("cloud:" + WorkflowAiPolicy.CONSENT + ":" + app, false)
        beginAfterDegiroLogin(intent) { service.beginAutomatic(app, task, cloud) }
    }
    private fun ownerOverride() {
        expectedPrompt?.dismiss(); expectedPrompt = null
        aiGeneration++; imageGeneration++; aiBusy = false
        cancelFiles()
        WorkflowService.stop()
        stopProductReader()
        output.text = ""
    }
    private fun stopProductReader() {
        LoginToReadHandoff.clear()
        WorkflowLoginHandoff.clear()
        if (PinReadinessProbe.running) PinReadinessProbe.stop("Durch neuen Auftrag oder STOPP beendet.")
        PhoneRemote.stop(this, "USER_STOP")
        GoldSearchRun.stop("USER_STOP", java.time.Instant.now().toString())
        MorningReadRun.stop(this, "USER_STOP")
        ProductReadRequest.cancel()
    }
    private fun valid(): List<WorkflowStep>? {
        if (!LocalWorkflow.allowedApp(selectedApp)) { status.text = "Zuerst eine unterstützte App auswählen."; return null }
        if (commands.text.contains("\"TEXT\"") || commands.text.contains("\"ERGEBNISTEXT\"")) {
            status.text = "Bitte zuerst die Platzhalter TEXT und ERGEBNISTEXT ersetzen"; return null
        }
        val plan = LocalWorkflow.parse(commands.text.toString(), WorkflowOwnerSettings.load(this).maxSteps)
        if (plan == null) status.text = "Auftrag noch nicht ausführbar. Bitte jede Zeile nach dem Beispiel formulieren; keine Teil-Ausführung."
        return plan
    }
    private fun save() {
        if (valid() == null) return
        val key = name.text.toString().trim()
        if (key.length !in 1..60 || key.any { it.isISOControl() }) { status.text = "Bitte einen kurzen Auftragsnamen angeben"; return }
        if (saved.all.size >= WorkflowOwnerSettings.load(this).maxSavedWorkflows && !saved.contains(key)) {
            status.text = "Eingestellte Speichergrenze erreicht; unter Einstellungen erhöhen oder einen alten Ablauf löschen"; return
        }
        fun write() {
            val data = JSONObject().put("version", 1).put("app", selectedApp).put("commands", commands.text.toString())
            if (saved.edit().putString(key, data.toString()).commit()) status.text = "Auftrag lokal gespeichert: $key" else status.text = "Speichern fehlgeschlagen"
        }
        if (saved.contains(key)) AlertDialog.Builder(this).setTitle("Auftrag ersetzen?").setMessage(key)
            .setPositiveButton("Ersetzen") { _, _ -> write() }.setNegativeButton("Abbrechen", null).show() else write()
    }
    private fun chooseSaved(delete: Boolean) {
        val keys = saved.all.keys.sorted()
        if (keys.isEmpty()) { status.text = "Noch keine gespeicherten Aufträge"; return }
        AlertDialog.Builder(this).setTitle(if (delete) "Auftrag löschen" else "Auftrag laden").setItems(keys.toTypedArray()) { _, i ->
            val key = keys[i]
            if (delete) AlertDialog.Builder(this).setTitle("Diesen Auftrag löschen?").setMessage(key)
                .setPositiveButton("Löschen") { _, _ -> saved.edit().remove(key).apply(); status.text = "Auftrag gelöscht" }.setNegativeButton("Abbrechen", null).show()
            else loadSaved(key)
        }.setNegativeButton("Abbrechen", null).show()
    }
    private fun loadSaved(key: String): Boolean = runCatching {
        val data = JSONObject(saved.getString(key, "")!!)
        require(data.getInt("version") == 1 && LocalWorkflow.allowedApp(data.getString("app")))
        require(LocalWorkflow.parse(data.getString("commands"), WorkflowOwnerSettings.load(this).maxSteps) != null)
        clearAttachment(); selectedApp = data.getString("app"); revisionBase = null; updateAppLabel(); updateCloud()
        autoPrefs.edit().putString("lastApp",selectedApp).apply(); renderHistory()
        commands.setText(data.getString("commands")); goal.setText(data.optString("goal")); name.setText(key); status.text = "Geladen · noch nicht gestartet"; showPanel("Gespeicherten Ablauf prüfen",detailsPanel)
        true
    }.getOrElse { status.text = "Gespeicherter Auftrag ungültig; keine Ausführung"; false }
    private fun launch(observe: Boolean, screenshot: Boolean, displayRequest: String = "", replay: Boolean = false) {
        panelDialog?.dismiss()
        ownerOverride()
        if (!observe && PhoneTaskPlanParser.isStop(commands.text.toString())) { refresh(); return }
        val plan = if (observe) null else valid() ?: return
        if (!LocalWorkflow.allowedApp(selectedApp)) { status.text = "Bitte zuerst eine App wählen"; return }
        val service = WorkflowService.instance ?: run { status.text = "Bitte zuerst Bobs Auftrags-Bedienungshilfe aktivieren"; return }
        val intent = packageManager.getLaunchIntentForPackage(selectedApp) ?: run { status.text = "App nicht startbar"; return }
        stopProductReader()
        val app = selectedApp; val title = name.text.toString()
        beginAfterDegiroLogin(intent) {
            if (plan != null) service.beginReplay(app,plan,displayRequest)
            else service.begin(app, plan, screenshot, plan?.let { WorkflowAiPolicy.commands(it) }.orEmpty(), title, displayRequest)
        }
    }
    /** Generic text, screenshot and replay tasks share the same local login prerequisite. */
    private fun beginAfterDegiroLogin(intent: Intent, begin: () -> Boolean) {
        fun continueTask(openApp: Boolean) {
            if (isDestroyed) return
            if (!begin()) { status.text = "Auftrag konnte nicht gestartet werden"; return }
            runCatching {
                if (openApp) startActivity(intent)
                goal.setText(""); clearAttachment()
            }.onFailure { WorkflowService.stop(); status.text = "App konnte nicht geöffnet werden" }
        }
        if (selectedApp != WorkflowAppRoute.DEGIRO || !LocalPinVault.exists(this)) {
            continueTask(true); return
        }
        var secret: ByteArray? = null
        try {
            check(ProductReadDiagnostics.connected && getSharedPreferences("product_reader", MODE_PRIVATE).getBoolean("enabled", false)) {
                "Für die DEGIRO-Anmeldung zuerst den Lesedienst unter Einrichtung einschalten."
            }
            check(!PinReadinessProbe.running) { "Anmeldung läuft bereits." }
            check(PhoneDiagnostics.keypadTestVerified(this)) { "Lokale PIN-Einrichtung: Tastaturtest unter Einrichtung abschließen." }
            check(LocalPinVault.available(this)) { "Handy entsperren, damit die gespeicherte DEGIRO-PIN lokal verwendet werden kann." }
            secret = LocalPinVault.load(this)
            WorkflowLoginHandoff.arm(android.os.SystemClock.elapsedRealtime()) { continueTask(false) }
            PinReadinessProbe.startLocalLogin(secret)
            WorkflowService.message = "DEGIRO-Anmeldung prüfen · danach Auftrag automatisch fortsetzen"
            status.text = WorkflowService.message
            startActivity(intent)
        } catch (_: Exception) {
            WorkflowLoginHandoff.clear()
            if (PinReadinessProbe.running) PinReadinessProbe.stop("Start der lokalen Anmeldung abgebrochen.")
            WorkflowService.message = "DEGIRO-Anmeldung konnte nicht gestartet werden. Lesedienst, lokale PIN und Tastaturtest unter Einrichtung prüfen."
            status.text = WorkflowService.message
        } finally { secret?.fill(0) }
    }
    private fun aiStatus(code: String): String = when (code) {
        "gemini-ready" -> "Kostenloser Google Gemini-Zugang konfiguriert · noch keine KI-Anfrage getestet"
        "setup-required" -> "KI-Zugang noch nicht eingerichtet oder deaktiviert. Lokale Aufträge funktionieren weiterhin."
        "daily-limit" -> "Tagesgrenze erreicht · keine weitere KI-Anfrage und keine kostenpflichtige Ausweichlösung"
        "wait-one-minute" -> "Bitte mindestens eine Minute zwischen KI-Anfragen warten"
        "already-requested" -> "Anfrage wurde bereits verarbeitet · keine erneute KI-Abfrage"
        else -> "Kein geprüfter Vorschlag verfügbar · nichts gestartet, kein Anbieterwechsel"
    }
    private fun checkAi() {
        if (!WorkflowSecuritySettings.permitsCloud(WorkflowSecuritySettings.load(this))) {
            status.text = "Besitzer-Hochschutz: Externe KI-Hilfe abgeschaltet"; return
        }
        if (aiBusy) return
        aiBusy = true
        val token = ++aiGeneration
        status.text = "Prüfe Einrichtung ohne Modellaufruf …"
        Thread {
            val result = runCatching { PhoneDiagnostics.workflowPlan(applicationContext, JSONObject().put("version", 1).put("mode", "status")) }
            runOnUiThread {
                aiBusy = false
                if (!isDestroyed && token == aiGeneration)
                    status.text = result.fold({ aiStatus(it.optString("status")) }, { "Zugang nicht erreichbar; Bob-Handy-Kopplung und Verbindung prüfen" })
            }
        }.start()
    }
    private fun propose() {
        if (!WorkflowSecuritySettings.permitsCloud(WorkflowSecuritySettings.load(this))) {
            status.text = "Besitzer-Hochschutz: Externe KI-Hilfe abgeschaltet"; return
        }
        if (aiBusy) { status.text = "Eine Anfrage läuft bereits"; return }
        val app = selectedApp
        val task = goal.text.toString().trim()
        if (!LocalWorkflow.allowedApp(app) || !WorkflowAiPolicy.safe(task, 500)) {
            status.text = "App und kurzen Auftrag angeben; keine privaten Daten, Zugangsdaten oder geschützten Aktionen"; return
        }
        WorkflowLibrary.match(this, app, task)?.let {
            name.setText(it.first); commands.setText(it.second)
            status.text = "Erfolgreichen lokalen Ablauf geladen · keine KI-Anfrage. Mit Auftrag starten ausführen."; return
        }
        val frame = WorkflowService.observation
        if (frame == null || frame.app != app || LocalWorkflow.protected(frame) ||
            android.os.SystemClock.elapsedRealtime() - WorkflowService.observationAt !in 0..60_000) {
            status.text = "Zuerst Bildschirm lernen starten, gewünschte Ansicht öffnen und innerhalb einer Minute zu Bob zurückkehren"; return
        }
        val candidates = WorkflowAiPolicy.context(frame.nodes)
        if (candidates.isEmpty()) { status.text = "Keine geeigneten Beschriftungen für eine KI-Anfrage"; return }
        val chosen = BooleanArray(candidates.size)
        AlertDialog.Builder(this).setTitle("Welche Texte darf Google Gemini sehen?")
            .setMultiChoiceItems(candidates.map { it.label + " · " + it.id }.toTypedArray(), chosen) { _, i, value -> chosen[i] = value }
            .setPositiveButton("Vorschau") { _, _ ->
                val nodes = candidates.filterIndexed { i, _ -> chosen[i] }
                if (nodes.size !in 1..24) { status.text = "Bitte 1 bis 24 notwendige Beschriftungen auswählen"; return@setPositiveButton }
                val array = JSONArray()
                nodes.forEach { array.put(JSONObject().put("label", it.label).put("id", it.id).put("editable", it.editable).put("clickable", it.clickable)) }
                val body = JSONObject().put("version", 1).put("requestId", java.util.UUID.randomUUID().toString().replace("-", ""))
                    .put("consent", WorkflowAiPolicy.CONSENT).put("app", app).put("goal", task).put("nodes", array)
                val preview = "Nur der folgende Auftrag und die ausgewählten Beschriftungen gehen über Bob an Google Gemini. Prüfe, dass keine persönlichen Daten enthalten sind. Keine Bilder oder Feldinhalte werden angehängt. Die Texte werden bei Google verarbeitet.\n\n" +
                    JSONObject().put("goal", task).put("nodes", array).toString(2)
                AlertDialog.Builder(this).setTitle("Eine KI-Anfrage freigeben").setMessage(preview)
                    .setPositiveButton("Einmal an Google Gemini senden") { _, _ ->
                        if (selectedApp == app && goal.text.toString().trim() == task) requestPlan(body, nodes, app, task)
                        else status.text = "Auftrag geändert · bitte neu vorbereiten"
                    }.setNegativeButton("Abbrechen", null).show()
            }.setNegativeButton("Abbrechen", null).show()
    }
    private fun requestPlan(body: JSONObject, nodes: List<WorkflowNode>, app: String, task: String) {
        if (aiBusy) return
        aiBusy = true
        val token = ++aiGeneration
        val epoch = WorkflowService.epoch
        status.text = "KI schlägt Schritte vor · Bob führt noch nichts aus …"
        Thread {
            val result = runCatching {
                val response = PhoneDiagnostics.workflowPlan(applicationContext, body)
                if (response.optString("status") != "proposal") return@runCatching Pair(response.optString("status"), "")
                require(response.getBoolean("ok") && !response.getBoolean("paidFallback") &&
                    response.getString("requestId") == body.getString("requestId"))
                val raw = response.getJSONArray("steps")
                require(raw.length() in 1..12)
                val steps = (0 until raw.length()).map {
                    val s = raw.getJSONObject(it)
                    require(s.keys().asSequence().toSet() == setOf("action", "target", "value", "expected"))
                    listOf("action", "target", "value", "expected").forEach { key -> require(s.get(key) is String) }
                    WorkflowStep(WorkflowAction.valueOf(s.getString("action")), s.getString("target"), s.getString("value"), s.getString("expected"))
                }
                require(WorkflowAiPolicy.valid(task, nodes, steps))
                Pair("proposal", WorkflowAiPolicy.commands(steps))
            }
            runOnUiThread {
                aiBusy = false
                if (!isDestroyed && token == aiGeneration && epoch == WorkflowService.epoch &&
                    app == selectedApp && task == goal.text.toString().trim()) {
                    val answer = result.getOrNull()
                    if (answer?.first == "proposal") {
                        commands.setText(answer.second)
                        if (name.text.isBlank()) name.setText(task.take(60))
                        status.text = "Vorschlag lokal geprüft. Schritte prüfen und Auftrag starten. Erst bestätigter Erfolg wird automatisch gespeichert."
                    } else status.text = aiStatus(answer?.first.orEmpty())
                }
            }
        }.start()
    }
    private fun composeStep(initialTarget: String) {
        val layout = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(24, 8, 24, 8) }
        val kind = Spinner(this).apply {
            adapter = ArrayAdapter(this@WorkflowActivity, android.R.layout.simple_spinner_dropdown_item,
                listOf("Schaltfläche antippen", "Text oder Zahl eintragen", "Auf Text warten"))
            layout.addView(this)
        }
        val target = EditText(this).apply { hint = "Beschriftung oder Feld-ID"; setText(initialTarget); layout.addView(this) }
        val value = EditText(this).apply { hint = "Einzutragender Text oder Zahl"; layout.addView(this) }
        val expected = EditText(this).apply { hint = "Welcher neue Text erscheint nach dem Tippen?"; layout.addView(this) }
        val help = TextView(this).apply { layout.addView(this) }
        kind.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onNothingSelected(parent: AdapterView<*>?) {}
            override fun onItemSelected(parent: AdapterView<*>?, view: android.view.View?, position: Int, id: Long) {
                value.visibility = if (position == 1) android.view.View.VISIBLE else android.view.View.GONE
                expected.visibility = if (position == 0) android.view.View.VISIBLE else android.view.View.GONE
                help.text = if (position == 1) "Bob ersetzt den Feldinhalt und prüft anschließend den exakten Wert."
                    else "Bob sucht das Ziel auf dem aktuellen Bildschirm. Bei Mehrdeutigkeit oder fehlender Bestätigung stoppt er."
            }
        }
        val dialog = AlertDialog.Builder(this).setTitle("Schritt zur Auftragsfolge hinzufügen").setView(layout)
            .setPositiveButton("Hinzufügen", null).setNegativeButton("Abbrechen", null).create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                val action = listOf(WorkflowAction.CLICK, WorkflowAction.WRITE, WorkflowAction.WAIT)[kind.selectedItemPosition]
                val line = WorkflowComposer.command(action, target.text.toString(), value.text.toString(), expected.text.toString())
                val combined = line?.let { commands.text.toString().trim().let { old -> if (old.isEmpty()) it else old + "\n" + it } }
                if (combined == null || LocalWorkflow.parse(combined, WorkflowOwnerSettings.load(this).maxSteps) == null) {
                    help.text = "Bitte Ziel und benötigten Wert bzw. Ergebnistext angeben. Höchstens zwölf Schritte; keine geschützten Aktionen."
                } else {
                    commands.setText(combined); status.text = "Schritt hinzugefügt · noch nicht ausgeführt"
                    dialog.dismiss()
                }
            }
        }
        dialog.show()
    }
    private fun teach() {
        val frame = WorkflowService.observation?.takeIf { it.app == selectedApp } ?: run { status.text = "Zuerst Bildschirm lernen starten und zur gewünschten Ansicht wechseln"; return }
        val nodes = frame.nodes.filter { (it.clickable || it.editable) && (it.id.isNotBlank() || LocalWorkflow.safeText(it.label)) }.take(80)
        AlertDialog.Builder(this).setTitle("Ziel auswählen").setItems(nodes.map { "${it.label} · ${it.id}" }.toTypedArray()) { _, i ->
            val n = nodes[i]; val target = n.id.ifBlank { n.label }
            val line = if (n.editable) "Schreibe \"TEXT\" in \"$target\"" else "Tippe auf \"$target\" -> \"ERGEBNISTEXT\""
            commands.append((if (commands.text.isBlank()) "" else "\n") + line)
            status.text = "Schritt vorbereitet: TEXT / ERGEBNISTEXT durch deinen gewünschten Inhalt ersetzen"
        }.setNegativeButton("Abbrechen", null).show()
    }
    override fun onActivityResult(request: Int, result: Int, data: Intent?) {
        super.onActivityResult(request, result, data)
        if (result != RESULT_OK) return
        when (request) {
            105 -> data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull()?.let {
                if (PhoneTaskPlanParser.isStop(it)) { ownerOverride(); refresh() }
                else if (it.length <= 300) { goal.setText(it); status.text = "Auftrag übernommen · mit START ausführen" }
            }
            101 -> data?.data?.let { readImage(it) }
            106 -> data?.data?.let { readImage(it, true) }
            107 -> data?.data?.let { uri ->
                val prompt = expectedPrompt
                if (prompt != null) prompt.readImage(uri) else status.text = "Ergebnisrückfrage wurde beendet. Den erhaltenen Auftrag erneut senden und Ergebnisbild auswählen."
            }
            102 -> data?.data?.let { tree ->
                val query = EditText(this).apply { hint = "Dateiname oder Teil davon; leer = alle JSON-Dateien" }
                AlertDialog.Builder(this).setTitle("JSON suchen").setView(query).setPositiveButton("Suchen") { _, _ -> searchJson(tree, query.text.toString()) }.setNegativeButton("Abbrechen", null).show()
            }
            104 -> {
                val spoken = data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull().orEmpty()
                val key = saved.all.keys.singleOrNull { LocalWorkflow.normalize(it) == LocalWorkflow.normalize(spoken) }
                if (PhoneTaskPlanParser.isStop(spoken)) { ownerOverride(); refresh() }
                else if (key != null && loadSaved(key)) launch(false, false)
                else status.text = "Kein eindeutiger gespeicherter Auftragsname erkannt; nichts gestartet"
            }
            103 -> data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull()?.let {
                if (PhoneTaskPlanParser.isStop(it)) { ownerOverride(); refresh(); return }
                if (it.length <= 500) commands.append((if (commands.text.isBlank()) "" else "\n") + it)
                status.text = "Diktat übernommen. Vor dem Start prüfen; Anführungszeichen und erwartetes Ergebnis gegebenenfalls ergänzen."
            }
        }
    }
    private fun readImage(uri: Uri, attachment: Boolean = false) {
        if (attachment) { clearAttachment(); attachmentUri = uri; attachmentBusy = true; attachmentStatus.visibility = android.view.View.VISIBLE; attachmentRemove.visibility = android.view.View.VISIBLE; attachmentStatus.text = "Screenshot wird lokal gelesen …" }
        val attachmentToken = attachmentGeneration
        val token = ++imageGeneration
        status.text = "Screenshot wird lokal gelesen …"
        val reader = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
        val bitmap = runCatching {
            val options = android.graphics.BitmapFactory.Options().apply { inJustDecodeBounds = true }
            contentResolver.openInputStream(uri)?.use { android.graphics.BitmapFactory.decodeStream(it, null, options) }
            require(options.outWidth in 1..30000 && options.outHeight in 1..30000)
            var sample = 1
            while (options.outWidth / sample > 2048 || options.outHeight / sample > 2048) sample *= 2
            options.inJustDecodeBounds = false; options.inSampleSize = sample
            contentResolver.openInputStream(uri)?.use { android.graphics.BitmapFactory.decodeStream(it, null, options) } ?: error("image")
        }.getOrElse {
            reader.close(); status.text = "Bild konnte nicht geöffnet werden"
            if (attachment) { attachmentBusy = false; attachmentStatus.text = "Bild nicht lesbar · erneut anhängen oder entfernen" }
            return
        }
        if (attachment) {
            attachmentBitmap = bitmap; attachmentPreview.setImageBitmap(bitmap)
            attachmentPreview.visibility = android.view.View.VISIBLE
        }
        val image = InputImage.fromBitmap(bitmap, 0)
        reader.process(image).addOnSuccessListener {
            if ((if (attachment) attachmentToken == attachmentGeneration else token == imageGeneration) && !isDestroyed) {
                if (attachment) {
                    attachmentBoxes = it.textBlocks.flatMap { block -> block.lines }.groupBy { line -> line.text.trim() }
                        .mapNotNull { (text, lines) -> lines.singleOrNull()?.boundingBox?.let { box -> text to android.graphics.Rect(box) } }.toMap()
                    attachmentLabels = it.textBlocks.flatMap { block -> block.lines }.map { line -> line.text.trim() }
                        .filter { label -> WorkflowComposer.validText(label) }.distinct().take(80)
                    attachmentBusy = false
                    attachmentStatus.text = if (attachmentLabels.isEmpty()) "Keine Beschriftungen erkannt · anderes Bild anhängen oder entfernen"
                        else "Screenshot angehängt · ${attachmentLabels.size} Beschriftungen lokal erkannt · Text ergänzen und senden"
                    return@addOnSuccessListener
                }
                output.text = "Screenshot-Text (OCR, ungeprüft):\n${it.text.take(20_000)}"
                val labels = it.textBlocks.flatMap { block -> block.lines }.map { line -> line.text.trim() }
                    .filter { label -> WorkflowComposer.validText(label) }.distinct().take(80)
                status.text = "Screenshot lokal gelesen · Ziel auswählen, noch keine Ausführung"
                if (labels.isEmpty()) status.text = "Keine lesbare Beschriftung gefunden. Ziel über Schritt hinzufügen beschreiben."
                else AlertDialog.Builder(this).setTitle("Welche Beschriftung aus dem Screenshot?")
                    .setItems(labels.toTypedArray()) { _, i -> composeStep(labels[i]) }
                    .setNegativeButton("Abbrechen", null).show()
            }
        }.addOnFailureListener {
            if (attachment && attachmentToken == attachmentGeneration) {
                attachmentBusy = false; attachmentStatus.text = "Texterkennung fehlgeschlagen · erneut anhängen oder entfernen"
            } else if (!attachment && token == imageGeneration) status.text = "Texterkennung fehlgeschlagen"
        }.addOnCompleteListener {
            reader.close()
            if (!attachment || attachmentBitmap !== bitmap) bitmap.recycle()
        }
    }
    private fun reviewDemonstration(draft: List<WorkflowStep>, choices: Map<Int, List<String>>) {
        val plan = draft.toMutableList()
        val app = selectedApp; val token = imageGeneration
        fun label(step: WorkflowStep) = if (step.target.contains(":id/")) {
            if (step.action == WorkflowAction.WRITE) "gezeigtes Eingabefeld" else "gezeigte Schaltfläche"
        } else step.target
        fun current() = app == selectedApp && token == imageGeneration && !isDestroyed
        fun ready() {
            if (!current()) return
            commands.setText(WorkflowAiPolicy.commands(plan))
            val proposed = plan.lastOrNull { it.action == WorkflowAction.WRITE }?.let { "${it.value} eingeben" }
                ?: "Weg zu ${label(plan.last())}"
            var suggested = proposed.take(50); var suffix = 2
            while (saved.contains(suggested)) suggested = proposed.take(50) + " (${suffix++})"
            val title = EditText(this).apply { setSingleLine(); setText(suggested); hint = "Name des Ablaufs" }
            val summary = plan.joinToString("\n") { step -> when(step.action) {
                WorkflowAction.CLICK -> "• ${label(step)} antippen"
                WorkflowAction.WRITE -> "• ${step.value} in ${label(step)} eintragen"
                WorkflowAction.WAIT -> "• Auf ${step.target} warten"
            } }
            val layout = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(24, 8, 24, 8)
                addView(TextView(this@WorkflowActivity).apply { text = summary + "\n\nBob testet den Ablauf erst nach deinem Start. Ein gespeicherter Entwurf gilt noch nicht als erfolgreich gelernt." })
                addView(title)
            }
            val dialog = AlertDialog.Builder(this).setTitle("Weg aufgezeichnet · bereit zum Test")
                .setView(ScrollView(this).apply { addView(layout) })
                .setPositiveButton("Speichern und testen", null).setNeutralButton("Nur speichern", null)
                .setNegativeButton("Abbrechen", null).create()
            panelDialog = dialog
            dialog.setOnShowListener {
                fun store(start: Boolean) {
                    if (!current()) { dialog.dismiss(); return }
                    val key = title.text.toString().trim()
                    if (key.length !in 1..60 || key.any { it.isISOControl() }) { title.error = "Bitte einen kurzen Namen wählen"; return }
                    if (saved.contains(key)) { title.error = "Name bereits vergeben · bitte anderen Namen wählen"; return }
                    if (saved.all.size >= WorkflowOwnerSettings.load(this).maxSavedWorkflows) {
                        title.error = "Speichergrenze erreicht · unter Einstellungen erhöhen oder alten Ablauf löschen"; return
                    }
                    if (valid() == null) return
                    val data = JSONObject().put("version",1).put("app",app).put("commands",commands.text.toString())
                    if (!saved.edit().putString(key,data.toString()).commit()) { title.error = "Speichern fehlgeschlagen"; return }
                    name.setText(key); WorkflowDraftStore.clear(this); shownDemonstration = null; dialog.dismiss()
                    status.text = "Gespeichert: $key · noch nicht erfolgreich getestet"
                    if (start) launch(false,false,key,true)
                }
                dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener { store(true) }
                dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener { store(false) }
            }
            dialog.show()
        }
        fun resolve(index: Int) {
            if (!current()) return
            if (index >= plan.size) { ready(); return }
            val step = plan[index]
            if (step.action == WorkflowAction.WRITE && step.value == "TEXT") {
                val input = EditText(this).apply { hint = "Was soll in ${label(step)} stehen?" }
                val dialog = AlertDialog.Builder(this).setTitle("Eingabe ergänzen").setView(input)
                    .setPositiveButton("Weiter", null).setNegativeButton("Abbrechen", null).create()
                panelDialog = dialog
                dialog.setOnShowListener { dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                    val value = input.text.toString()
                    if (!current()) { dialog.dismiss(); return@setOnClickListener }
                    if (!WorkflowComposer.validText(value)) { input.error = "Bitte einen gültigen Eingabewert angeben"; return@setOnClickListener }
                    plan[index] = step.copy(value=value); dialog.dismiss(); resolve(index+1)
                } }; dialog.show(); return
            }
            if (step.expected != "ERGEBNISTEXT") { resolve(index+1); return }
            fun screenshot() {
                if (!current()) return
                expectedPrompt?.dismiss()
                expectedPrompt = WorkflowExpectedResultDialog(this,step.target,emptyList(),::current,
                    pickImage = { startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).apply { type="image/*"; addCategory(Intent.CATEGORY_OPENABLE) },107) },
                    submit = { command -> LocalWorkflow.parse(command, WorkflowOwnerSettings.load(this).maxSteps)?.singleOrNull()?.let { plan[index]=it; resolve(index+1) } })
                expectedPrompt!!.show()
            }
            val labels = choices[index].orEmpty().filter(WorkflowComposer::validText).distinct()
            if (labels.isEmpty()) { screenshot(); return }
            panelDialog = AlertDialog.Builder(this).setTitle("Nach ${label(step)}: Woran erkenne ich das Ziel?")
                .setItems(labels.toTypedArray()) { _, chosen -> if (current()) { plan[index]=step.copy(expected=labels[chosen]); resolve(index+1) } }
                .setNeutralButton("Screenshot / Text") { _, _ -> screenshot() }
                .setNegativeButton("Abbrechen", null).create()
            panelDialog?.show()
        }
        resolve(0)
    }
    private fun startDemonstration() {
        if (!LocalWorkflow.allowedApp(selectedApp)) { status.text = "Bitte zuerst eine App auswählen"; return }
        val app = selectedApp
        AlertDialog.Builder(this).setTitle("Ablauf einmal vormachen")
            .setMessage("Bob zeichnet deine Klicks und Texteingaben nur in dieser App lokal auf, höchstens zwölf Schritte und drei Minuten. Zurück zu Bob beendet die Aufzeichnung. Danach zeigt Bob dir eine kurze Zusammenfassung. Nur bei unklaren Ergebnissen wählst du einen erkannten Text oder einen Screenshot aus. Während des Vormachens führt Bob nichts selbst aus.")
            .setPositiveButton("Vormachen starten") { _, _ ->
                if (app != selectedApp) return@setPositiveButton
                ownerOverride()
                val service = WorkflowService.instance
                val intent = packageManager.getLaunchIntentForPackage(app)
                if (service == null || intent == null) { status.text = "Bedienungshilfe aktivieren und eine startbare App wählen"; return@setPositiveButton }
                if (service.beginDemonstration(app)) runCatching { startActivity(intent); goal.setText(""); clearAttachment() }.onFailure { WorkflowService.stop(); status.text = "App konnte nicht geöffnet werden" }
            }.setNegativeButton("Abbrechen", null).show()
    }
    private fun askScreenshotTarget(labels: List<String>, chosen: (String) -> Unit) {
        val layout = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(20, 8, 20, 8) }
        val selector = Spinner(this).apply {
            adapter = ArrayAdapter(this@WorkflowActivity, android.R.layout.simple_spinner_dropdown_item, labels)
            layout.addView(this)
        }
        val preview = ImageView(this).apply { adjustViewBounds = true; maxHeight = 360; contentDescription = "Bildstelle zum ausgewählten Ziel"; layout.addView(this) }
        var cropped: android.graphics.Bitmap? = null
        selector.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onNothingSelected(parent: AdapterView<*>?) {}
            override fun onItemSelected(parent: AdapterView<*>?, view: android.view.View?, position: Int, id: Long) {
                preview.setImageDrawable(null); if (cropped !== attachmentBitmap) cropped?.recycle(); cropped = null
                val bitmap = attachmentBitmap ?: return
                val box = attachmentBoxes[labels[position]]
                if (box == null) preview.setImageBitmap(bitmap)
                else {
                    val left = (box.left - 24).coerceAtLeast(0); val top = (box.top - 24).coerceAtLeast(0)
                    val right = (box.right + 24).coerceAtMost(bitmap.width); val bottom = (box.bottom + 24).coerceAtMost(bitmap.height)
                    if (right > left && bottom > top) {
                        cropped = android.graphics.Bitmap.createBitmap(bitmap, left, top, right - left, bottom - top)
                        preview.setImageBitmap(cropped)
                    }
                }
            }
        }
        val dialog = AlertDialog.Builder(this).setTitle("Meinst du diese Bildstelle?").setView(layout)
            .setPositiveButton("Dieses Ziel verwenden") { _, _ -> chosen(labels[selector.selectedItemPosition]) }
            .setNegativeButton("Abbrechen", null).create()
        dialog.setOnDismissListener { preview.setImageDrawable(null); if (cropped !== attachmentBitmap) cropped?.recycle() }
        dialog.show()
    }
    private fun teachSymbol() {
        if (!LocalWorkflow.allowedApp(selectedApp)) { status.text = "Bitte zuerst eine App auswählen"; return }
        val bitmap = attachmentBitmap ?: run { status.text = "Bitte zuerst einen Screenshot anhängen"; return }
        val app = selectedApp; val token = attachmentGeneration
        val layout = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(20, 8, 20, 8) }
        layout.addView(TextView(this).apply { text = "Ziehe einen engen Rahmen um das Symbol. Gespeichert wird nur sein lokales Bildmuster für diese App, nicht der ganze Screenshot." })
        val crop = WorkflowSymbolCrop(this, bitmap)
        layout.addView(crop, LinearLayout.LayoutParams(-1, (360 * resources.displayMetrics.density).toInt()))
        layout.addView(TextView(this).apply { text = "Zum Vergrößern + oder zwei Finger nutzen. Rahmen innen verschieben, an den Ecken seine Größe ändern." })
        layout.addView(LinearLayout(this).apply {
            listOf("−" to { crop.zoomBy(1f / 1.5f) }, "+" to { crop.zoomBy(1.5f) }, "Neu markieren" to { crop.resetSelection() }).forEach { (title, action) ->
                addView(Button(this@WorkflowActivity).apply { text = title; isAllCaps = false; setOnClickListener { action() } }, LinearLayout.LayoutParams(0, -2, 1f))
            }
        })
        val meaning = EditText(this).apply { hint = "Bedeutung / Name, z. B. Suche"; layout.addView(this) }
        val expected = EditText(this).apply { hint = "Was erscheint nach dem Tippen? Z. B. Suchfeld"; layout.addView(this) }
        val help = TextView(this).apply { layout.addView(this) }
        val dialog = AlertDialog.Builder(this).setTitle("Bob ein Symbol erklären")
            .setView(ScrollView(this).apply { addView(layout) }).setPositiveButton("Lernen", null).setNegativeButton("Abbrechen", null).create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                if (app != selectedApp || token != attachmentGeneration) { dialog.dismiss(); return@setOnClickListener }
                val box = crop.box()
                val pattern = box?.let { WorkflowSymbolMatch.pattern(WorkflowSymbols.gray(bitmap), bitmap.width, bitmap.height, it) }
                val name = meaning.text.toString().trim(); val result = expected.text.toString().trim()
                if (pattern == null || !WorkflowComposer.validText(name) || name.length > 60 || !WorkflowComposer.validText(result)) {
                    help.text = "Bitte ein deutliches Symbol eng einrahmen und Bedeutung sowie erwarteten Text angeben."
                } else {
                    val symbol = LearnedSymbol(name, result, pattern)
                    if (WorkflowSymbols.save(this, app, symbol)) {
                        goal.setText("Tippe auf $name")
                        status.text = "Symbol für diese App gelernt · mit Senden testen. Erst ein bestätigtes Ergebnis gilt als erfolgreich."
                        dialog.dismiss()
                    } else help.text = "Speichern fehlgeschlagen oder 20 Symbole gespeichert. Bitte ein altes Symbol vergessen."
                }
            }
        }
        dialog.show()
    }
    private fun manageSymbols() {
        val app = selectedApp
        val symbols = WorkflowSymbols.list(this, app)
        if (symbols.isEmpty()) { status.text = "Für diese App sind noch keine Symbole gelernt"; return }
        AlertDialog.Builder(this).setTitle("Symbole dieser App")
            .setItems(symbols.map { it.name + if (it.verifiedAt > 0) " · erfolgreich geprüft" else " · noch nicht geprüft" }.toTypedArray()) { _, i ->
                val symbol = symbols[i]
                AlertDialog.Builder(this).setTitle(symbol.name).setMessage("Nach dem Tippen erwartet Bob: ${symbol.expected}")
                    .setPositiveButton("Auftrag übernehmen") { _, _ -> if (app == selectedApp) goal.setText("Tippe auf ${symbol.name}") }
                    .setNeutralButton("Vergessen") { _, _ ->
                        ownerOverride(); WorkflowSymbols.forget(this, app, symbol.name); status.text = "Symbol vergessen"
                    }.setNegativeButton("Abbrechen", null).show()
            }.setNegativeButton("Schließen", null).show()
    }
    private fun clearAttachment() {
        attachmentGeneration++; attachmentBusy = false; attachmentUri = null; attachmentLabels = emptyList(); attachmentBoxes = emptyMap()
        attachmentPreview.setImageDrawable(null); attachmentPreview.visibility = android.view.View.GONE
        attachmentBitmap = null
        attachmentStatus.text = ""
        attachmentStatus.visibility = android.view.View.GONE; attachmentRemove.visibility = android.view.View.GONE
    }
    private fun sendMessage() {
        val text = goal.text.toString().trim()
        val editing = revisionBase; revisionBase = null
        panelDialog?.dismiss()
        ownerOverride()
        if (PhoneTaskPlanParser.isStop(text)) { refresh(); return }
        if (text.isBlank()) { status.text = "Was soll Bob mit dem Screenshot tun? Bitte einen Auftrag eingeben."; return }
        if (selectedApp == WorkflowAppRoute.DEGIRO) {
            DegiroGoal.productIsin(text)?.let { isin ->
                startActivity(Intent(this, ProductReadActivity::class.java)
                    .putExtra(ProductReadActivity.EXTRA_GOAL_QUERY, isin))
                goal.setText(""); goal.hint = "Was soll Bob tun?"; clearAttachment()
                return
            }
            if (DegiroGoal.needsProductIsin(text)) {
                goal.setText(""); goal.hint = "ISIN des Produkts eingeben"
                status.text = "Welche ISIN? Danach übernimmt Bob DEGIRO-Anmeldung, Suche und Produktöffnung."
                goal.requestFocus()
                return
            }
            if (DegiroGuide.requested(text)) { showDegiroGuide(); return }
            if (WorkflowAppRoute.asksCapabilities(text)) { showDegiroCapabilities(); return }
            WorkflowAppRoute.capability(text)?.let { capability ->
                // Local owner request only: reuse built-in handlers, never cloud planning.
                startActivity(Intent(this, ProductReadActivity::class.java)
                    .putExtra(ProductReadActivity.EXTRA_CAPABILITY, capability.title))
                goal.setText(""); clearAttachment()
                return
            }
        }
        if (WorkflowRevision.requested(text)) {
            val previous = editing ?: WorkflowResultStore.previous(this, selectedApp)
            val changed = previous?.let { WorkflowRevision.apply(text, it) }
            if (changed == null) {
                val choices = previous?.indices?.filter { WorkflowRevision.apply(text, previous, it) != null }.orEmpty()
                if (previous != null && choices.size > 1) {
                    val app = selectedApp; val token = imageGeneration
                    AlertDialog.Builder(this).setTitle("Welches Eingabefeld soll ich ändern?")
                        .setItems(choices.map { previous[it].target }.toTypedArray()) { _, i ->
                            if (app == selectedApp && token == imageGeneration && text == goal.text.toString().trim()) {
                                WorkflowRevision.apply(text, previous, choices[i])?.let { plan -> commands.setText(WorkflowAiPolicy.commands(plan)); launch(false, false, text, true) }
                            }
                        }.setNegativeButton("Abbrechen", null).show()
                    return
                }
                status.text = "Änderung nicht eindeutig: Es braucht einen erfolgreich geprüften Auftrag dieser App mit genau einem passenden Eingabewert. Bitte Feld und Wert ausdrücklich angeben."
                return
            }
            commands.setText(WorkflowAiPolicy.commands(changed)); launch(false, false, text, true); return
        }
        WorkflowSymbols.plan(this, selectedApp, text)?.let {
            commands.setText(WorkflowAiPolicy.commands(it)); launch(false, false, text); return
        }
        if (attachmentUri == null) { startAutomatic(); return }
        if (attachmentBusy) { status.text = "Screenshot wird noch gelesen. Danach erneut senden."; return }
        if (attachmentLabels.isEmpty()) { status.text = "Screenshot nicht lesbar. Bitte ersetzen oder entfernen."; return }
        if (!LocalWorkflow.allowedApp(selectedApp)) { status.text = "Bitte zuerst eine App auswählen"; return }
        val labels = attachmentLabels.toList()
        val app = selectedApp
        val token = imageGeneration
        val attachmentToken = attachmentGeneration
        fun submit(target: String?) {
            if (token != imageGeneration || attachmentToken != attachmentGeneration || app != selectedApp || text != goal.text.toString().trim()) return
            val resolved = WorkflowMessage.resolve(text, labels, target)
            if (resolved == null) {
                val clickTarget = WorkflowMessage.clickTarget(text, labels, target)
                if (clickTarget != null) {
                    expectedPrompt?.dismiss()
                    expectedPrompt = WorkflowExpectedResultDialog(this, clickTarget, labels,
                        current = { token == imageGeneration && attachmentToken == attachmentGeneration && app == selectedApp && text == goal.text.toString().trim() && !isDestroyed },
                        pickImage = { startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).apply { type = "image/*"; addCategory(Intent.CATEGORY_OPENABLE) }, 107) },
                        submit = { command -> commands.setText(command); launch(false, false, text) })
                    expectedPrompt!!.show(); return
                }
                status.text = "Bitte Ziel und Aktion beschreiben, z. B. Schreibe Silber in Suchfeld. Beim Tippen auch den erwarteten Ergebnistext angeben."
                return
            }
            commands.setText(resolved)
            launch(false, false, text)
        }
        val resolved = WorkflowMessage.resolve(text, labels)
        if (resolved != null) submit(null)
        else if (WorkflowMessage.needsTarget(text)) askScreenshotTarget(labels) { submit(it) }
        else submit(null)
    }
    override fun onSaveInstanceState(out: Bundle) {
        out.putString("draftGoal", goal.text.toString())
        out.putString("draftCommands", commands.text.toString())
        revisionBase?.let { out.putString("draftRevision", WorkflowAiPolicy.commands(it)) }
        attachmentUri?.let { out.putString("draftImage", it.toString()) }
        super.onSaveInstanceState(out)
    }
    private fun searchJson(tree: Uri, query: String) {
        if (fileBusy) return
        fileBusy = true; val token = imageGeneration
        val cancellation = android.os.CancellationSignal(); fileCancellation = cancellation
        status.text = "Suche ausschließlich im gewählten Ordner …"
        Thread {
            val found = mutableListOf<Pair<String, Uri>>()
            var visited = 0; var truncated = false
            val deadline = android.os.SystemClock.elapsedRealtime() + 15_000
            val seen = mutableSetOf<String>()
            fun scan(id: String, depth: Int) {
                cancellation.throwIfCanceled()
                if (depth > 5 || visited >= 300 || found.size >= 50 || android.os.SystemClock.elapsedRealtime() > deadline) { truncated = true; return }
                if (!seen.add(id)) return
                val children = DocumentsContract.buildChildDocumentsUriUsingTree(tree, id)
                contentResolver.query(children, arrayOf(DocumentsContract.Document.COLUMN_DOCUMENT_ID, DocumentsContract.Document.COLUMN_DISPLAY_NAME, DocumentsContract.Document.COLUMN_MIME_TYPE), null, null, null, cancellation)?.use { c ->
                    while (c.moveToNext()) {
                        if (++visited > 300 || found.size >= 50 || android.os.SystemClock.elapsedRealtime() > deadline) { truncated = true; break }
                        val child = c.getString(0); val title = c.getString(1).orEmpty(); val mime = c.getString(2)
                        if (mime == DocumentsContract.Document.MIME_TYPE_DIR) scan(child, depth + 1)
                        else if (title.endsWith(".json", true) && title.contains(query, true)) found += title to DocumentsContract.buildDocumentUriUsingTree(tree, child)
                    }
                }
            }
            val outcome = runCatching { scan(DocumentsContract.getTreeDocumentId(tree), 0) }
            runOnUiThread {
                fileBusy = false
                if (!isDestroyed && token == imageGeneration) {
                    status.text = if (outcome.isFailure) "Ordner nicht vollständig lesbar" else "${found.size} JSON-Dateien gefunden${if (truncated) " · Suchgrenze erreicht, ggf. Unterordner wählen" else ""}"
                    if (found.isNotEmpty()) AlertDialog.Builder(this).setTitle("JSON-Datei lesen (max. 1 MiB)").setItems(found.map { it.first }.toTypedArray()) { _, i -> readJson(found[i].second) }.setNegativeButton("Abbrechen", null).show()
                }
            }
        }.start()
    }
    private fun readJson(uri: Uri) {
        if (fileBusy) return
        fileBusy = true; val token = imageGeneration
        Thread {
            val result = runCatching {
                val bytes = contentResolver.openInputStream(uri)?.use { input ->
                    fileStream = input
                    val out = java.io.ByteArrayOutputStream(); val buffer = ByteArray(8192)
                    while (true) { val n = input.read(buffer); if (n < 0) break; require(out.size() + n <= 1_048_576); out.write(buffer, 0, n) }
                    out.toByteArray()
                } ?: error("unreadable")
                val text = bytes.toString(Charsets.UTF_8)
                // Strict streaming validation bounds nesting before the DOM parser.
                android.util.JsonReader(java.io.StringReader(text)).use { reader ->
                    reader.isLenient = false
                    var depth = 0; var tokens = 0
                    while (reader.peek() != android.util.JsonToken.END_DOCUMENT) {
                        require(++tokens <= 100_000)
                        when (reader.peek()) {
                            android.util.JsonToken.BEGIN_OBJECT -> { require(++depth <= 64); reader.beginObject() }
                            android.util.JsonToken.BEGIN_ARRAY -> { require(++depth <= 64); reader.beginArray() }
                            android.util.JsonToken.END_OBJECT -> { reader.endObject(); depth-- }
                            android.util.JsonToken.END_ARRAY -> { reader.endArray(); depth-- }
                            android.util.JsonToken.NAME -> reader.nextName()
                            android.util.JsonToken.STRING, android.util.JsonToken.NUMBER -> reader.nextString()
                            android.util.JsonToken.BOOLEAN -> reader.nextBoolean()
                            android.util.JsonToken.NULL -> reader.nextNull()
                            else -> error("json")
                        }
                    }
                    require(depth == 0)
                }
                val parsed = org.json.JSONTokener(text)
                val value = parsed.nextValue()
                require(value is JSONObject || value is JSONArray)
                require(parsed.nextClean() == '\u0000')
                (if (value is JSONObject) value.toString(2) else (value as JSONArray).toString(2)).take(20_000)
            }
            runOnUiThread {
                fileBusy = false; fileStream = null
                if (!isDestroyed && token == imageGeneration) {
                    status.text = if (result.isSuccess) "JSON gelesen · Vorschau bis 20.000 Zeichen · keine Ausführung" else "JSON ungültig, nicht lesbar oder größer als 1 MiB"
                    output.text = result.getOrDefault("")
                }
            }
        }.start()
    }
    private fun cancelFiles() { fileCancellation?.cancel(); runCatching { fileStream?.close() }; fileStream = null }
    override fun onStop() { aiGeneration++; super.onStop() }
    override fun onDestroy() { expectedPrompt?.dismiss(); expectedPrompt = null; WorkflowLoginHandoff.clear(); aiGeneration++; imageGeneration++; attachmentGeneration++; cancelFiles(); attachmentPreview.setImageDrawable(null); attachmentBitmap = null; super.onDestroy() }
}
