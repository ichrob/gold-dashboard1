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
    private lateinit var appLabel: TextView
    private lateinit var status: TextView
    private lateinit var output: TextView
    private var selectedApp = ""
    private var imageGeneration = 0
    private var fileBusy = false
    private val saved by lazy { getSharedPreferences("local_workflows_v1", MODE_PRIVATE) }
    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        val stack = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(24, 20, 24, 20) }
        fun label(s: String) = TextView(this).also { it.text = s; it.textSize = 17f; stack.addView(it) }
        fun button(s: String, block: () -> Unit) = Button(this).also { it.text = s; it.isAllCaps = false; it.setOnClickListener { block() }; stack.addView(it) }
        label("Meine Aufträge")
        status = label("Lokal auf deinem Handy · keine ChatGPT-Verbindung nötig")
        button("STOPP · Auftrag und Lesesitzung beenden") { WorkflowService.stop(); imageGeneration++; output.text = ""; refresh() }
        label("Du bestimmst App, Schritte und erwartetes Ergebnis. Screenshots werden lokal als Text gelesen. Bilder und Dateiinhalte erteilen niemals Befehle. Keine Orders, Anmeldung oder Zahlungen.")
        button("Einrichtung · Auftrags-Bedienungshilfe öffnen") { startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) }
        appLabel = label("Noch keine App gewählt")
        button("App auswählen") { chooseApp() }
        name = EditText(this).apply { hint = "Name, z. B. Gold suchen"; setSingleLine(); stack.addView(this) }
        commands = EditText(this).apply { hint = "Tippe auf \"Suche\" -> \"Suchbegriff\"\nSchreibe \"Gold\" in \"Suchbegriff\"\nWarte auf \"Gold\""; minLines = 4; gravity = android.view.Gravity.TOP; stack.addView(this) }
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
        setContentView(ScrollView(this).apply { addView(stack) })
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
            .filter { LocalWorkflow.allowedApp(it.activityInfo.packageName) }.distinctBy { it.activityInfo.packageName }
            .sortedBy { it.loadLabel(packageManager).toString() }
        AlertDialog.Builder(this).setTitle("App für diesen Auftrag")
            .setItems(entries.map { "${it.loadLabel(packageManager)} · ${it.activityInfo.packageName}" }.toTypedArray()) { _, i ->
                WorkflowService.stop(); selectedApp = entries[i].activityInfo.packageName; appLabel.text = selectedApp
            }.setNegativeButton("Abbrechen", null).show()
    }
    private fun valid(): List<WorkflowStep>? {
        if (!LocalWorkflow.allowedApp(selectedApp)) { status.text = "Zuerst eine unterstützte App auswählen. DEGIRO nutzt den vorhandenen Produktleser."; return null }
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
            else runCatching {
                val data = JSONObject(saved.getString(key, "")!!)
                require(data.getInt("version") == 1 && LocalWorkflow.allowedApp(data.getString("app")))
                require(LocalWorkflow.parse(data.getString("commands")) != null)
                selectedApp = data.getString("app"); appLabel.text = selectedApp
                commands.setText(data.getString("commands")); name.setText(key); status.text = "Geladen · noch nicht gestartet"
            }.onFailure { status.text = "Gespeicherter Auftrag ungültig; keine Ausführung" }
        }.setNegativeButton("Abbrechen", null).show()
    }
    private fun launch(observe: Boolean, screenshot: Boolean) {
        val plan = if (observe) null else valid() ?: return
        if (!LocalWorkflow.allowedApp(selectedApp)) { status.text = "Bitte zuerst eine App wählen"; return }
        val service = WorkflowService.instance ?: run { status.text = "Bitte zuerst Bobs Auftrags-Bedienungshilfe aktivieren"; return }
        val intent = packageManager.getLaunchIntentForPackage(selectedApp) ?: run { status.text = "App nicht startbar"; return }
        if (service.begin(selectedApp, plan, screenshot)) runCatching { startActivity(intent) }
            .onFailure { WorkflowService.stop(); status.text = "App konnte nicht geöffnet werden" }
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
            101 -> data?.data?.let { readImage(it) }
            102 -> data?.data?.let { tree ->
                val query = EditText(this).apply { hint = "Dateiname oder Teil davon; leer = alle JSON-Dateien" }
                AlertDialog.Builder(this).setTitle("JSON suchen").setView(query).setPositiveButton("Suchen") { _, _ -> searchJson(tree, query.text.toString()) }.setNegativeButton("Abbrechen", null).show()
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
        val image = runCatching { InputImage.fromFilePath(this, uri) }.getOrElse { reader.close(); status.text = "Bild konnte nicht geöffnet werden"; return }
        reader.process(image).addOnSuccessListener {
            if (token == imageGeneration && !isDestroyed) { output.text = "Screenshot-Text (OCR, ungeprüft):\n${it.text.take(20_000)}"; status.text = "Screenshot gelesen · keine Befehle ausgeführt" }
        }.addOnFailureListener { if (token == imageGeneration) status.text = "Texterkennung fehlgeschlagen" }.addOnCompleteListener { reader.close() }
    }
    private fun searchJson(tree: Uri, query: String) {
        if (fileBusy) return
        fileBusy = true; status.text = "Suche ausschließlich im gewählten Ordner …"
        Thread {
            val found = mutableListOf<Pair<String, Uri>>()
            var visited = 0; var truncated = false
            val deadline = android.os.SystemClock.elapsedRealtime() + 15_000
            val seen = mutableSetOf<String>()
            fun scan(id: String, depth: Int) {
                if (depth > 5 || visited >= 300 || found.size >= 50 || android.os.SystemClock.elapsedRealtime() > deadline) { truncated = true; return }
                if (!seen.add(id)) return
                val children = DocumentsContract.buildChildDocumentsUriUsingTree(tree, id)
                contentResolver.query(children, arrayOf(DocumentsContract.Document.COLUMN_DOCUMENT_ID, DocumentsContract.Document.COLUMN_DISPLAY_NAME, DocumentsContract.Document.COLUMN_MIME_TYPE), null, null, null)?.use { c ->
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
                if (!isDestroyed) {
                    status.text = if (outcome.isFailure) "Ordner nicht vollständig lesbar" else "${found.size} JSON-Dateien gefunden${if (truncated) " · Suchgrenze erreicht, ggf. Unterordner wählen" else ""}"
                    if (found.isNotEmpty()) AlertDialog.Builder(this).setTitle("JSON-Datei lesen (max. 1 MiB)").setItems(found.map { it.first }.toTypedArray()) { _, i -> readJson(found[i].second) }.setNegativeButton("Abbrechen", null).show()
                }
            }
        }.start()
    }
    private fun readJson(uri: Uri) {
        if (fileBusy) return
        fileBusy = true
        Thread {
            val result = runCatching {
                val bytes = contentResolver.openInputStream(uri)?.use { input ->
                    val out = java.io.ByteArrayOutputStream(); val buffer = ByteArray(8192)
                    while (true) { val n = input.read(buffer); if (n < 0) break; require(out.size() + n <= 1_048_576); out.write(buffer, 0, n) }
                    out.toByteArray()
                } ?: error("unreadable")
                val text = bytes.toString(Charsets.UTF_8)
                val parsed = org.json.JSONTokener(text)
                val value = parsed.nextValue()
                require(value is JSONObject || value is JSONArray)
                require(parsed.nextClean() == '\u0000')
                (if (value is JSONObject) value.toString(2) else (value as JSONArray).toString(2)).take(20_000)
            }
            runOnUiThread {
                fileBusy = false
                if (!isDestroyed) {
                    status.text = if (result.isSuccess) "JSON gelesen · Vorschau bis 20.000 Zeichen · keine Ausführung" else "JSON ungültig, nicht lesbar oder größer als 1 MiB"
                    output.text = result.getOrDefault("")
                }
            }
        }.start()
    }
    override fun onDestroy() { imageGeneration++; super.onDestroy() }
}
