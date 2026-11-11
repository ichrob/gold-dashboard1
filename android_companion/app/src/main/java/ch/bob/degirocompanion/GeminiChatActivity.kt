package ch.bob.degirocompanion

import android.app.Activity
import android.app.AlertDialog
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.speech.RecognizerIntent
import android.os.Build
import android.view.WindowInsets
import android.widget.*
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.ServerSocket
import java.net.URL
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.Base64
import java.util.concurrent.Executors
import java.util.zip.GZIPOutputStream

/** App-local session only: no exported component, JS bridge, cloud relay or saved token. */
internal object GeminiLocalSession {
    private val executor = Executors.newSingleThreadExecutor()
    private val main = Handler(Looper.getMainLooper())
    @Volatile private var port = 0
    @Volatile private var token = ""
    @Volatile var startedAt = 0L
        private set
    fun active() = token.isNotEmpty()

    fun start(context: Context): String {
        if (active()) return "STARTED"
        if (context.packageManager.getLaunchIntentForPackage(TermuxBridge.PACKAGE) == null)
            return "Termux ist nicht installiert."
        val source = try { context.assets.open("bob_gemini_bridge.py").use { it.readBytes() } }
            catch (_: Exception) { return "Gemini-Komponente fehlt in dieser App-Version." }
        if (source.size !in 1..100000) return "Ungültige Gemini-Komponente."
        val random = SecureRandom()
        val localPort = (1..20).asSequence().map { 20000 + random.nextInt(40000) }
            .firstOrNull { candidate ->
                try { ServerSocket(candidate, 1, java.net.InetAddress.getByName("127.0.0.1")).use { }; true }
                catch (_: Exception) { false }
            } ?: return "Kein lokaler Anschluss verfügbar."
        val localToken = ByteArray(32).also { random.nextBytes(it) }.joinToString("") { "%02x".format(it.toInt() and 255) }
        val sha = MessageDigest.getInstance("SHA-256").digest(source).joinToString("") { "%02x".format(it.toInt() and 255) }
        val buffer = ByteArrayOutputStream()
        GZIPOutputStream(buffer).use { it.write(source) }
        // Source is bundled in the signed APK. User text is sent later as JSON,
        // never interpolated into Python/shell code or process arguments.
        val bootstrap = "import sys,base64,gzip,hashlib; s=gzip.decompress(base64.b64decode(sys.argv[1],validate=True)); assert len(s)<=100000 and hashlib.sha256(s).hexdigest()==sys.argv[2]; sys.argv=['bob_gemini_bridge.py']+sys.argv[3:]; exec(compile(s,'bob_gemini_bridge.py','exec'),{'__name__':'__main__'})"
        val request = Intent("com.termux.RUN_COMMAND").apply {
            setClassName(TermuxBridge.PACKAGE, TermuxBridge.SERVICE)
            putExtra("com.termux.RUN_COMMAND_PATH", TermuxBridge.PYTHON)
            putExtra("com.termux.RUN_COMMAND_ARGUMENTS", arrayOf("-c", bootstrap,
                Base64.getEncoder().encodeToString(buffer.toByteArray()), sha,
                "--port", localPort.toString(), "--token", localToken))
            putExtra("com.termux.RUN_COMMAND_WORKDIR", "/data/data/com.termux/files/home/bob-gemini-work")
            putExtra("com.termux.RUN_COMMAND_BACKGROUND", true)
        }
        return try {
            if (context.startService(request) == null) "Termux konnte nicht gestartet werden."
            else { port = localPort; token = localToken; startedAt = System.currentTimeMillis(); "STARTED" }
        } catch (_: SecurityException) {
            "Bitte in Android für Bob Handy die Berechtigung „Termux-Befehle“ erlauben."
        } catch (_: RuntimeException) { "Android hat den Termux-Start verhindert." }
    }

    private fun call(localPort: Int, localToken: String, path: String, body: JSONObject?): JSONObject {
        require(path in setOf("/status", "/prompt", "/permission", "/stop"))
        val c = URL("http://127.0.0.1:$localPort$path").openConnection() as HttpURLConnection
        c.connectTimeout = 2000; c.readTimeout = 4000; c.instanceFollowRedirects = false
        c.setRequestProperty("Authorization", "Bearer $localToken")
        try {
            if (body != null) {
                c.requestMethod = "POST"; c.doOutput = true
                c.setRequestProperty("Content-Type", "application/json")
                c.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            }
            if (c.responseCode != 200) throw IllegalStateException("REQUEST_REJECTED")
            val bytes = c.inputStream.use { stream ->
                val output = ByteArrayOutputStream()
                val chunk = ByteArray(8192)
                while (true) {
                    val n = stream.read(chunk)
                    if (n < 0) break
                    require(output.size() + n <= 3000000)
                    output.write(chunk, 0, n)
                }
                output.toByteArray()
            }
            return JSONObject(String(bytes, Charsets.UTF_8))
        } finally { c.disconnect() }
    }

    fun request(path: String, body: JSONObject? = null, result: (JSONObject?) -> Unit) {
        val p = port; val t = token
        if (t.isEmpty()) { result(null); return }
        executor.execute {
            val reply = runCatching { call(p, t, path, body) }.getOrNull()
            main.post { result(if (token == t) reply else null) }
        }
    }

    fun stop() {
        val p = port; val t = token
        token = ""; port = 0; startedAt = 0L
        if (t.isNotEmpty()) executor.execute { runCatching { call(p, t, "/stop", JSONObject()) } }
        // If Android/Termux killed either process, the runner's heartbeat lease
        // also ends the agent within 120 seconds. Completed changes are not undone.
    }
}

class GeminiChatActivity : Activity() {
    private lateinit var status: TextView
    private lateinit var transcript: TextView
    private lateinit var input: EditText
    private lateinit var permissions: LinearLayout
    private lateinit var send: Button
    private val handler = Handler(Looper.getMainLooper())
    private var visible = false
    private var polling = false
    private var permissionSignature = ""
    private var lastEvent = 0L
    private var pendingText = ""
    private var pendingRequest = ""
    private val history = StringBuilder()
    private val tick = Runnable { poll() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.setSoftInputMode(android.view.WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE)
        val padding = (12 * resources.displayMetrics.density).toInt()
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        if (Build.VERSION.SDK_INT >= 30) {
            window.setDecorFitsSystemWindows(false)
            root.setOnApplyWindowInsetsListener { view, insets ->
                val bars = insets.getInsets(WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout())
                val ime = insets.getInsets(WindowInsets.Type.ime())
                view.setPadding(padding + bars.left, padding + bars.top,
                    padding + bars.right, padding + maxOf(bars.bottom, ime.bottom))
                insets
            }
        } else {
            root.fitsSystemWindows = true
            root.setPadding(padding, padding, padding, padding)
        }
        // Controls and history can scroll even with a large font or a tall keyboard.
        val content = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val scroll = ScrollView(this).apply { addView(content); isFillViewport = true }
        root.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))
        fun label(text: String) = TextView(this).also { it.text = text; it.textSize = 16f; content.addView(it) }
        fun button(text: String, action: () -> Unit) = Button(this).also {
            it.text = text; it.isAllCaps = false; it.setOnClickListener { action() }; content.addView(it)
        }
        label("Mit Gemini an Bob arbeiten")
        status = label("Gemini noch nicht verbunden. Deine Google-Anmeldung bleibt in Termux.")
        button("Gemini verbinden") {
            if (GeminiLocalSession.active()) { poll(); return@button }
            AlertDialog.Builder(this).setTitle("Gemini für Bob starten")
                .setMessage("Deine Aufträge und die von Gemini gelesenen Inhalte werden über deine bestehende Google-Anmeldung verarbeitet. Gemini kann mit deinen Termux-Rechten Code bearbeiten und vorhandene Zugänge nutzen. Freigabefragen erscheinen hier; keine pauschale Freigabe aller Befehle. Keine kostenpflichtige API wird eingerichtet. Nutze deinen kostenlosen persönlichen Zugang. Die Sitzung läuft höchstens 2 Stunden und endet nach 2 Minuten ohne Verbindung zu dieser Ansicht. Android kann sie unterbrechen. Keine Passwörter oder Schlüssel in den Chat eingeben.")
                .setNegativeButton("Abbrechen", null)
                .setPositiveButton("Verbinden") { _, _ ->
                    lastEvent = 0L; history.clear(); permissionSignature = ""; transcript.text = ""
                    val r = GeminiLocalSession.start(this)
                    status.text = if (r == "STARTED") "Gemini startet …" else r
                    poll()
                }.show()
        }
        button("Meine Zugänge prüfen") {
            input.setText("Prüfe deine tatsächlich verfügbaren Bob-Entwicklungszugänge: GitHub, Bob-Diagnosen, Render, Cloudflare und Aiven. Prüfe GitHub-Rechte mit gh, bei anderen Verbindungen zunächst nur Werkzeugverfügbarkeit. Keine Schlüssel, privaten Logs oder Depotdaten ausgeben. Keine neuen Konten oder kostenpflichtigen Ressourcen anlegen. Nenne getrennt: eingerichtet, tatsächlich geprüft und Anmeldung fehlt. Kein ChatGPT erforderlich.")
        }
        button("STOPP · Gemini-Sitzung beenden") {
            GeminiLocalSession.stop(); permissions.removeAllViews(); send.isEnabled = false
            status.text = "STOPP angefordert. Bereits ausgeführte Änderungen bleiben bestehen."
        }
        transcript = TextView(this).apply { textSize = 16f; setTextIsSelectable(true) }
        content.addView(transcript)
        permissions = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        content.addView(permissions)
        input = EditText(this).apply {
            hint = "Dein Auftrag – schreiben oder mit der Tastatur diktieren"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
            minLines = 2; maxLines = 3
            setTextColor(android.graphics.Color.BLACK)
            setHintTextColor(android.graphics.Color.DKGRAY)
            setBackgroundColor(android.graphics.Color.WHITE)
            filters = arrayOf(android.text.InputFilter.LengthFilter(12000))
        }
        root.addView(input)
        val actions = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        root.addView(actions)
        val dictate = Button(this).apply {
            text = "Auftrag diktieren"; isAllCaps = false
            setOnClickListener { openSpeechInput() }
        }
        actions.addView(dictate, LinearLayout.LayoutParams(0, -2, 1f))
        send = button("Auftrag senden") {
            val text = input.text.toString().trim()
            if (text.isEmpty()) return@button
            send.isEnabled = false
            if (pendingText != text || pendingRequest.isEmpty()) {
                pendingText = text; pendingRequest = java.util.UUID.randomUUID().toString().replace("-", "")
            }
            GeminiLocalSession.request("/prompt", JSONObject().put("text", text).put("requestId", pendingRequest)) { r ->
                if (r?.optBoolean("accepted") == true) {
                    input.setText(""); pendingText = ""; pendingRequest = ""
                }
                else status.text = "Auftrag nicht bestätigt. Eingabe bleibt erhalten; erst Status prüfen."
                poll()
            }
        }
        content.removeView(send)
        actions.addView(send, LinearLayout.LayoutParams(0, -2, 1f))
        send.isEnabled = false
        setContentView(root)
        root.requestApplyInsets()
    }

    private fun openSpeechInput() {
        val request = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "de-DE")
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
            putExtra(RecognizerIntent.EXTRA_PROMPT, "Deinen Bob-Auftrag diktieren; anschließend prüfen und senden")
        }
        try {
            startActivityForResult(request, 4102)
        } catch (_: android.content.ActivityNotFoundException) {
            Toast.makeText(this, "Sprachdialog fehlt. Nutze das Mikrofon unten links in der Tastatur.", Toast.LENGTH_LONG).show()
            input.requestFocus()
            (getSystemService(Context.INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager)
                .showSoftInput(input, android.view.inputmethod.InputMethodManager.SHOW_IMPLICIT)
        }
    }

    @Deprecated("Platform activity result callback")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != 4102 || resultCode != RESULT_OK) return
        val spoken = data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)?.firstOrNull()?.trim()
        if (spoken.isNullOrEmpty()) return
        // Keep the draft; dictation inserts at the selection and never submits a prompt.
        val start = input.selectionStart.coerceAtLeast(0)
        val end = input.selectionEnd.coerceAtLeast(start)
        input.text.replace(start, end, spoken)
        input.requestFocus()
    }

    override fun onResume() { super.onResume(); visible = true; poll() }
    override fun onPause() { visible = false; handler.removeCallbacks(tick); super.onPause() }

    private fun poll() {
        if (!visible || polling || !GeminiLocalSession.active()) return
        handler.removeCallbacks(tick); polling = true
        GeminiLocalSession.request("/status") { r ->
            polling = false
            if (!visible) return@request
            if (r == null) {
                send.isEnabled = false
                val age = System.currentTimeMillis() - GeminiLocalSession.startedAt
                status.text = if (age < 90000) "Gemini wird verbunden …" else
                    "Keine Antwort von Termux. STOPP drücken und neu verbinden; ggf. Google-Anmeldung in Termux prüfen."
            } else {
                val state = r.optString("state")
                send.isEnabled = state == "ready"
                status.text = when (state) {
                    "ready" -> "Gemini bereit · unabhängig von ChatGPT"
                    "running" -> "Gemini arbeitet …"
                    "stopped" -> "Sitzung beendet. Neu verbinden erforderlich."
                    else -> "Gemini startet …"
                }
                val events = r.optJSONArray("events")
                for (i in 0 until (events?.length() ?: 0)) {
                    val e = events!!.getJSONObject(i); val id = e.optLong("id")
                    if (id <= lastEvent) continue
                    if (lastEvent != 0L && id > lastEvent + 1) history.append("\n[Ältere Anzeigeeinträge nicht mehr verfügbar]\n")
                    lastEvent = id
                    val kind = e.optString("kind")
                    if (kind == "answer") history.append(e.optString("text"))
                    else history.append("\n\n${if (kind == "user") "Du" else "Status"}: ${e.optString("text")}\n")
                }
                if (history.length > 120000) history.delete(0, history.length - 100000)
                transcript.text = history.toString()
                if (state == "stopped") GeminiLocalSession.stop()
                val pending = r.optJSONArray("permissions")
                val signature = pending?.toString() ?: "[]"
                if (signature != permissionSignature) {
                    permissionSignature = signature; permissions.removeAllViews()
                    for (i in 0 until (pending?.length() ?: 0)) {
                        val item = pending!!.getJSONObject(i)
                        val detail = TextView(this).apply { text = "Freigabe erforderlich:\n" + item.optString("details"); setTextIsSelectable(true) }
                        permissions.addView(detail)
                        val opts = item.getJSONArray("options")
                        for (j in 0 until opts.length()) {
                            val option = opts.getJSONObject(j)
                            permissions.addView(Button(this).apply {
                                text = if (option.optString("kind") == "allow_once") "Einmal erlauben" else "Ablehnen"
                                setOnClickListener {
                                    isEnabled = false
                                    GeminiLocalSession.request("/permission", JSONObject().put("id", item.getString("id")).put("option", option.getString("id"))) { reply ->
                                        if (reply == null) status.text = "Freigabe nicht bestätigt. Aktuellen Status prüfen."
                                        permissionSignature = ""; poll()
                                    }
                                }
                            })
                        }
                    }
                }
            }
            if (visible && GeminiLocalSession.active()) handler.postDelayed(tick, 1500)
        }
    }
}
