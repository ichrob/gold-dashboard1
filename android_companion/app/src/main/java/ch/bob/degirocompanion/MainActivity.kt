package ch.bob.degirocompanion

import android.app.Activity
import android.app.TimePickerDialog
import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
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
 * No network permission, trade/order controls or credentials.
 * Only explicit local commands and an individually approved daily self-check.
 */
class MainActivity : Activity() {
    private val selectImageRequest = 42
    private lateinit var status: TextView
    private lateinit var mockSearch: EditText
    private lateinit var demoResult: TextView
    private var evidenceDraft = ""
    private var imageReadSequence = 0

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

        label("BOB SAMSUNG-STEUERUNG (LABOR): Freigegebene Aufgaben lokal ausführen. Keine Fernsteuerung, keine automatischen Handelsorders.")
        button("Auftrag: Bob öffnen") {
            if (BobRoutinePolicy.permits(
                    BobRoutinePolicy.Action.OPEN_BOB, BobRoutinePolicy.Origin.USER_TAP
                )) {
                try {
                    startActivity(Intent(Intent.ACTION_VIEW,
                        Uri.parse("https://bob-private-scanner.onrender.com/")))
                    status.text = "Bob im Browser geöffnet. Keine andere App wurde automatisch bedient."
                } catch (_: Exception) {
                    status.text = "Bob konnte nicht geöffnet werden."
                }
            }
        }
        label("Freigebbare Routine: Einmal täglich nur den lokalen Prüfstatus ermitteln und erinnern. Uhrzeit nach deiner Wahl. Kein Zugriff auf DEGIRO, keine Hintergrund-Screenshots.")
        val dailyStatus = label(DailyBobRoutine.summary(this))
        button("Täglichen lokalen Check freigeben · Uhrzeit wählen") {
            if (Build.VERSION.SDK_INT >= 33 &&
                checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) !=
                PackageManager.PERMISSION_GRANTED) {
                requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 7402)
                status.text = "Benachrichtigungen freigeben und danach erneut auf 'Täglichen lokalen Check freigeben' tippen."
            } else {
                TimePickerDialog(this, { _, hour, minute ->
                    DailyBobRoutine.enable(this, hour, minute)
                    dailyStatus.text = DailyBobRoutine.summary(this)
                    status.text = "Routine von dir freigegeben. Läuft lokal und kann jederzeit gestoppt werden."
                }, 8, 0, true).show()
            }
        }
        button("STOPP · Alle geplanten Bob-Routinen ausschalten") {
            DailyBobRoutine.stop(this)
            dailyStatus.text = DailyBobRoutine.summary(this)
            status.text = "Geplante Bob-Routinen abgeschaltet. Keine laufenden Handels- oder Fernsteuerungsaufträge."
        }
        button("Status der lokalen Routinen prüfen") {
            dailyStatus.text = DailyBobRoutine.summary(this)
            status.text = "Lokaler Status aktualisiert. Es wurden keine Brokerdaten abgerufen."
        }
        button("Auftrag: Produktbilder auswählen und lokal prüfen") {
            if (!BobRoutinePolicy.permits(
                    BobRoutinePolicy.Action.PICK_IMAGES, BobRoutinePolicy.Origin.USER_TAP
                )) return@button
            val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                addCategory(Intent.CATEGORY_OPENABLE)
                type = "image/*"
                putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
            }
            startActivityForResult(intent, selectImageRequest)
        }
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
        setContentView(ScrollView(this).apply { addView(stack) })
        processUserShare(intent)
        processUserCommand(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        processUserShare(intent)
        processUserCommand(intent)
    }

    private fun processUserCommand(incoming: Intent?) {
        // An ACTION_VIEW must be triggered on the device (for example by tapping
        // a link). No background ChatGPT control or unapproved action script.
        if (incoming?.action != Intent.ACTION_VIEW) return
        val action = BobRoutinePolicy.fromLink(incoming.dataString) ?: return
        if (!BobRoutinePolicy.permits(action, BobRoutinePolicy.Origin.USER_TAP)) return
        when (action) {
            BobRoutinePolicy.Action.OPEN_BOB -> {
                try {
                    startActivity(Intent(Intent.ACTION_VIEW,
                        Uri.parse("https://bob-private-scanner.onrender.com/")))
                    status.text = "Bob geöffnet. Der Link enthält keine Handelsanweisung."
                } catch (_: Exception) {
                    status.text = "Bob konnte nicht geöffnet werden."
                }
            }
            BobRoutinePolicy.Action.PICK_IMAGES -> {
                val picker = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    type = "image/*"
                    putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
                }
                startActivityForResult(picker, selectImageRequest)
            }
            BobRoutinePolicy.Action.LOCAL_HEALTH_CHECK -> {
                status.text = DailyBobRoutine.summary(this)
            }
        }
    }

    private fun processUserShare(incoming: Intent?) {
        if (incoming == null ||
            incoming.action !in listOf(Intent.ACTION_SEND, Intent.ACTION_SEND_MULTIPLE) ||
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
        if (requestCode != selectImageRequest || resultCode != RESULT_OK) return
        val clip = data?.clipData
        val viaClip = (0 until (clip?.itemCount ?: 0)).mapNotNull { clip?.getItemAt(it)?.uri }
        val all = (listOfNotNull(data?.data) + viaClip).distinct()
        readImages(all)
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
                if (evidenceDraft.isNotBlank()) DailyBobRoutine.recordOcr(this)
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
