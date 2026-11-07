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
    private var selectedApp = ""
    private lateinit var cloud: CheckBox
    private var updatingCloud = false
    private val autoPrefs by lazy { getSharedPreferences("workflow_auto_v1", MODE_PRIVATE) }
    private var imageGeneration = 0
    private var fileBusy = false
    private var fileCancellation: android.os.CancellationSignal? = null
    @Volatile private var fileStream: java.io.InputStream? = null
    private val saved by lazy { getSharedPreferences("local_workflows_v1", MODE_PRIVATE) }
    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        val stack = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(24, 20, 24, 20) }
        var section = stack
        fun label(s: String) = TextView(this).also { it.text = s; it.textSize = 17f; section.addView(it) }
        fun button(s: String, block: () -> Unit) = Button(this).also { it.text = s; it.isAllCaps = false; it.setOnClickListener { block() }; section.addView(it) }
        label("Meine Aufträge")
        status = label("Lokal auf deinem Handy · keine ChatGPT-Verbindung nötig")
        button("STOPP · Auftrag und Lesesitzung beenden") { WorkflowService.stop()
            if (selectedApp == WorkflowAppRoute.DEGIRO) {
                PhoneRemote.stop(this,"USER_STOP")
                GoldSearchRun.stop("USER_STOP",java.time.Instant.now().toString())
                MorningReadRun.stop(this,"USER_STOP")
                ProductReadRequest.cancel()
            }
            aiGeneration++; imageGeneration++; cancelFiles(); output.text = ""; refresh() }
        label("App wählen, Auftrag sagen oder eingeben, Start. Bob liest und prüft selbst. Erfolgreiche Abläufe bleiben lokal gespeichert. Keine Orders, Anmeldung oder Zahlungen.")
        button("Selbsttest · Klicken, Schreiben und Screenshot prüfen") {
            WorkflowService.stop()
            startActivity(Intent(this,WorkflowSelfTestActivity::class.java))
        }
        button("Einrichtung · Auftrags-Bedienungshilfe öffnen") { startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) }
        appLabel = label("Noch keine App gewählt")
        button("App auswählen") { chooseApp() }
        goal = EditText(this).apply { hint = "Was soll Bob tun? Zum Beispiel: Schreibe Gold in das Suchfeld"; minLines = 2; stack.addView(this) }
        button("Auftrag sprechen") {
            runCatching { startActivityForResult(Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                putExtra(RecognizerIntent.EXTRA_LANGUAGE, "de-DE")
                putExtra(RecognizerIntent.EXTRA_PROMPT, "Auftrag sagen; danach Start drücken")
            }, 105) }.onFailure { status.text = "Sprachdienst fehlt; Textfeld oder Tastaturmikrofon verwenden" }
        }
        cloud = CheckBox(this).apply { text = "Bei Bedarf KI automatisch nutzen · einmal je App freigeben"; stack.addView(this) }
        cloud.setOnCheckedChangeListener { _, checked ->
            if (!updatingCloud) {
                if (checked && !LocalWorkflow.allowedApp(selectedApp)) {
                    updatingCloud = true; cloud.isChecked = false; updatingCloud = false
                    status.text = "Zuerst eine App auswählen"
                } else if (checked && !autoPrefs.getBoolean("cloud:" + WorkflowAiPolicy.CONSENT + ":" + selectedApp, false)) allowAutomaticCloud()
                else if (!checked) { autoPrefs.edit().remove("cloud:" + WorkflowAiPolicy.CONSENT + ":" + selectedApp).apply(); WorkflowService.stop() }
            }
        }
        button("START · Bob erledigt den Auftrag") { startAutomatic() }
        button("Kostenlosen KI-Zugang prüfen") { checkAi() }
        label("Auftragsfolge · bis zu zwölf Schritte")
        commands = EditText(this).apply {
            hint = "Schritte über die Schaltfläche oder aus einem Screenshot hinzufügen"
            minLines = 3; gravity = android.view.Gravity.TOP; stack.addView(this)
        }
        button("Schritt hinzufügen · Tippen, Schreiben oder Warten") { composeStep("") }
        button("Schaltfläche oder Feld aus Screenshot wählen") {
            startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).apply { type = "image/*"; addCategory(Intent.CATEGORY_OPENABLE) }, 101)
        }
        button("Auftragsfolge starten") { launch(false, false) }
        val advanced = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; visibility = android.view.View.GONE }
        button("Details / manuelle Schritte ein- oder ausblenden") {
            advanced.visibility = if (advanced.visibility == android.view.View.VISIBLE) android.view.View.GONE else android.view.View.VISIBLE
        }
        stack.addView(advanced); section = advanced
        name = EditText(this).apply { hint = "Optionaler Name für manuelle Aufträge"; setSingleLine(); advanced.addView(this) }
        button("Auftrag manuell vorbereiten · Texte einzeln freigeben") { propose() }
        label("Zuerst wird ein erfolgreicher lokaler Ablauf gesucht. Eine neue KI-Anfrage benötigt deine Auswahl und Freigabe der Texte. Keine automatische kostenpflichtige Ausweichlösung.")
        label("Ein Schritt pro Zeile. Tippe auf \"Beschriftung\" -> \"neuer Ergebnistext\"; Schreibe \"Text\" in \"Feldbeschriftung\"; Warte auf \"Text\". Auch eine angezeigte Feld-ID ist möglich. Bis zu zwölf Schritte. Bei doppelten Zielen stoppt Bob.")
        button("Schritt diktieren") {
            runCatching { startActivityForResult(Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.GERMAN.toLanguageTag())
                putExtra(RecognizerIntent.EXTRA_PROMPT, "Schritt beschreiben; anschließend prüfen und ergänzen")
            }, 103) }.onFailure { status.text = "Sprachdienst fehlt; Textfeld oder Tastaturmikrofon verwenden" }
        }
        button("Auftrag prüfen und speichern") { save() }
        button("Gespeicherten Auftrag laden") { chooseSaved(false) }
        button("Gespeicherten Auftrag löschen") { chooseSaved(true) }
        button("Gespeicherten Auftrag per Sprache starten") {
            runCatching { startActivityForResult(Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                putExtra(RecognizerIntent.EXTRA_LANGUAGE, "de-DE")
                putExtra(RecognizerIntent.EXTRA_PROMPT, "Name eines gespeicherten Auftrags. Ein erkannter Name startet diesen Auftrag.")
            }, 104) }.onFailure { status.text = "Sprachdienst fehlt; gespeicherten Auftrag laden und starten" }
        }
        button("Auftrag starten · alle Schritte ausführen") { launch(false, false) }
        button("Bildschirm lernen · Beschriftungen ansehen") { launch(true, false) }
        button("Screenshot der gewählten App lesen") { launch(true, true) }
        button("Ergebnis / gelernte Beschriftungen anzeigen") { refresh() }
        label("Zurück in Bob zeigt die gelesenen Beschriftungen. Tippe unten auf eine Beschriftung, um daraus einen Schritt vorzubereiten. Das erwartete Ergebnis ergänzt du im Auftrag.")
        button("Gelerntes Bildschirmziel in Auftrag übernehmen") { teach() }
        button("Vorhandenen Screenshot auswählen und lesen") {
            startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).apply { type = "image/*"; addCategory(Intent.CATEGORY_OPENABLE) }, 101)
        }
        button("JSON-Datei im gewählten Ordner suchen") {
            if (!fileBusy) startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT_TREE).apply {
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            }, 102)
        }
        output = label("").apply { setTextIsSelectable(true) }
        val scroll = ScrollView(this).apply { addView(stack) }
        scroll.setOnApplyWindowInsetsListener { view, insets ->
            if (android.os.Build.VERSION.SDK_INT >= 30) {
                val bars = insets.getInsets(android.view.WindowInsets.Type.systemBars() or android.view.WindowInsets.Type.ime())
                view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            } else view.setPadding(insets.systemWindowInsetLeft, insets.systemWindowInsetTop, insets.systemWindowInsetRight, insets.systemWindowInsetBottom)
            insets
        }
        setContentView(scroll)
        selectedApp = autoPrefs.getString("lastApp", "").orEmpty().takeIf { WorkflowAppRoute.selectable(it) }.orEmpty()
        appLabel.text = selectedApp.ifBlank { "Noch keine App gewählt" }
        updateCloud()
        goal.setText(autoPrefs.getString("lastGoal", ""))
    }
    override fun onResume() { super.onResume(); if (::output.isInitialized) refresh() }
    private fun refresh() {
        status.text = WorkflowService.message
        val frame = WorkflowService.observation
        output.text = buildString {
            if (frame != null) {
                append("Letzte lokale Beobachtung · ${frame.app}\n")
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
                WorkflowService.stop(); selectedApp = entries[i].activityInfo.packageName; appLabel.text = selectedApp
                autoPrefs.edit().putString("lastApp", selectedApp).apply(); updateCloud()
                if (selectedApp == WorkflowAppRoute.DEGIRO) {
                    if (goal.text.isBlank()) goal.setText("Gold suchen")
                    status.text = "DEGIRO: Goldsuche nutzt den bisherigen Leser. Andere Aufträge nutzen die allgemeine Bedienung. Bereits angemeldet starten."
                }
            }.setNegativeButton("Abbrechen", null).show()
    }
    private fun updateCloud() {
        updatingCloud = true
        cloud.isEnabled = LocalWorkflow.allowedApp(selectedApp)
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
        if (LocalWorkflow.parse(task) == null && !WorkflowAiPolicy.safe(task, 500)) { status.text = "Bitte einen kurzen Auftrag ohne private Daten eingeben"; return }
        val service = WorkflowService.instance ?: run { status.text = "Einmalig die Auftrags-Bedienungshilfe über Einrichtung aktivieren"; return }
        val intent = packageManager.getLaunchIntentForPackage(selectedApp) ?: run { status.text = "App nicht mehr installiert oder nicht startbar"; return }
        stopProductReader()
        autoPrefs.edit().putString("lastApp", selectedApp).putString("lastGoal", task).apply()
        if (service.beginAutomatic(selectedApp, task, autoPrefs.getBoolean("cloud:" + WorkflowAiPolicy.CONSENT + ":" + selectedApp, false))) {
            runCatching { startActivity(intent) }.onFailure { WorkflowService.stop(); status.text = "App konnte nicht geöffnet werden" }
        } else status.text = "Auftrag konnte nicht gestartet werden"
    }
    private fun stopProductReader() {
        if (selectedApp != WorkflowAppRoute.DEGIRO) return
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
        val plan = LocalWorkflow.parse(commands.text.toString())
        if (plan == null) status.text = "Auftrag noch nicht ausführbar. Bitte jede Zeile nach dem Beispiel formulieren; keine Teil-Ausführung."
        return plan
    }
    private fun save() {
        if (valid() == null) return
        val key = name.text.toString().trim()
        if (key.length !in 1..60 || key.any { it.isISOControl() }) { status.text = "Bitte einen kurzen Auftragsnamen angeben"; return }
        if (saved.all.size >= 20 && !saved.contains(key)) { status.text = "20 Aufträge gespeichert; zuerst einen löschen"; return }
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
        require(LocalWorkflow.parse(data.getString("commands")) != null)
        selectedApp = data.getString("app"); appLabel.text = selectedApp; updateCloud()
        commands.setText(data.getString("commands")); goal.setText(data.optString("goal")); name.setText(key); status.text = "Geladen · noch nicht gestartet"
        true
    }.getOrElse { status.text = "Gespeicherter Auftrag ungültig; keine Ausführung"; false }
    private fun launch(observe: Boolean, screenshot: Boolean) {
        val plan = if (observe) null else valid() ?: return
        if (!LocalWorkflow.allowedApp(selectedApp)) { status.text = "Bitte zuerst eine App wählen"; return }
        val service = WorkflowService.instance ?: run { status.text = "Bitte zuerst Bobs Auftrags-Bedienungshilfe aktivieren"; return }
        val intent = packageManager.getLaunchIntentForPackage(selectedApp) ?: run { status.text = "App nicht startbar"; return }
        stopProductReader()
        if (service.begin(selectedApp, plan, screenshot, goal.text.toString().trim().ifBlank { name.text.toString().trim() }.take(500), name.text.toString())) runCatching { startActivity(intent) }
            .onFailure { WorkflowService.stop(); status.text = "App konnte nicht geöffnet werden" }
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
                if (combined == null || LocalWorkflow.parse(combined) == null) {
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
                if (PhoneTaskPlanParser.isStop(it)) { WorkflowService.stop(); refresh() }
                else if (it.length <= 300) { goal.setText(it); status.text = "Auftrag übernommen · mit START ausführen" }
            }
            101 -> data?.data?.let { readImage(it) }
            102 -> data?.data?.let { tree ->
                val query = EditText(this).apply { hint = "Dateiname oder Teil davon; leer = alle JSON-Dateien" }
                AlertDialog.Builder(this).setTitle("JSON suchen").setView(query).setPositiveButton("Suchen") { _, _ -> searchJson(tree, query.text.toString()) }.setNegativeButton("Abbrechen", null).show()
            }
            104 -> {
                val spoken = data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull().orEmpty()
                val key = saved.all.keys.singleOrNull { LocalWorkflow.normalize(it) == LocalWorkflow.normalize(spoken) }
                if (PhoneTaskPlanParser.isStop(spoken)) { WorkflowService.stop(); refresh() }
                else if (key != null && loadSaved(key)) launch(false, false)
                else status.text = "Kein eindeutiger gespeicherter Auftragsname erkannt; nichts gestartet"
            }
            103 -> data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull()?.let {
                if (it.length <= 500) commands.append((if (commands.text.isBlank()) "" else "\n") + it)
                status.text = "Diktat übernommen. Vor dem Start prüfen; Anführungszeichen und erwartetes Ergebnis gegebenenfalls ergänzen."
            }
        }
    }
    private fun readImage(uri: Uri) {
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
        }.getOrElse { reader.close(); status.text = "Bild konnte nicht geöffnet werden"; return }
        val image = InputImage.fromBitmap(bitmap, 0)
        reader.process(image).addOnSuccessListener {
            if (token == imageGeneration && !isDestroyed) {
                output.text = "Screenshot-Text (OCR, ungeprüft):\n${it.text.take(20_000)}"
                val labels = it.textBlocks.flatMap { block -> block.lines }.map { line -> line.text.trim() }
                    .filter { label -> WorkflowComposer.validText(label) }.distinct().take(80)
                status.text = "Screenshot lokal gelesen · Ziel auswählen, noch keine Ausführung"
                if (labels.isEmpty()) status.text = "Keine lesbare Beschriftung gefunden. Ziel über Schritt hinzufügen beschreiben."
                else AlertDialog.Builder(this).setTitle("Welche Beschriftung aus dem Screenshot?")
                    .setItems(labels.toTypedArray()) { _, i -> composeStep(labels[i]) }
                    .setNegativeButton("Abbrechen", null).show()
            }
        }.addOnFailureListener { if (token == imageGeneration) status.text = "Texterkennung fehlgeschlagen" }.addOnCompleteListener { reader.close(); bitmap.recycle() }
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
    override fun onDestroy() { aiGeneration++; imageGeneration++; cancelFiles(); super.onDestroy() }
}
