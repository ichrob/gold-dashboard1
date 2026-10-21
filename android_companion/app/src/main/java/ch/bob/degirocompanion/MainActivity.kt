package ch.bob.degirocompanion

import android.app.Activity
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
    private lateinit var status: TextView
    private lateinit var mockSearch: EditText
    private lateinit var demoResult: TextView
    private var evidenceDraft = ""

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val stack = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(28, 32, 28, 32)
        }
        fun label(text: String): TextView = TextView(this).also {
            it.text = text
            it.textSize = 17f
            it.setPadding(0, 10, 0, 12)
            stack.addView(it)
        }
        fun button(title: String, onClick: () -> Unit) = Button(this).also {
            it.text = title
            it.isAllCaps = false
            it.setOnClickListener { onClick() }
            stack.addView(it)
        }

        label("BOB ANDROID-LABOR – Keine DEGIRO-Verbindung, keine Orders.")
        button("Bild manuell auswählen und lokal lesen") {
            val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                addCategory(Intent.CATEGORY_OPENABLE)
                type = "image/*"
            }
            startActivityForResult(intent, selectImageRequest)
        }
        status = label("Noch kein Bild ausgewählt. OCR-Werte sind niemals automatisch ein Handelsnachweis.")
        button("OCR-Entwurf kopieren (zum Einfügen in Bob)") {
            if (evidenceDraft.isBlank()) {
                status.text = "Zuerst genau ein Produkt auf einem Bild auswählen."
            } else {
                val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                clipboard.setPrimaryClip(ClipData.newPlainText("Bob OCR ungeprüft", evidenceDraft))
                status.text = "Nur der unbestätigte Text wurde kopiert. In Bob unter Mehr → DEGIRO einfügen. Die Zwischenablage kann auch von anderen Apps gelesen werden."
            }
        }
        button("OCR-Entwurf über Android teilen") {
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

        label("Unabhängiger Bedienungstest: nur künstliche Produktdaten")
        mockSearch = EditText(this).apply {
            hint = "ISIN in Demo suchen"
            contentDescription = "Mock ISIN Eingabe"
            setSingleLine(true)
            setText("DE000FG14AV8")
            stack.addView(this)
        }
        button("DEMO: Produkt suchen") {
            val query = mockSearch.text.toString().trim().uppercase(Locale.ROOT)
            demoResult.text = if (query == "DE000FG14AV8") {
                "DEMO-TREFFER: DE000FG14AV8 | Handelsplatz TEST | KEIN ECHTER HANDEL"
            } else {
                "Kein Treffer in den künstlichen Testdaten. KEIN ECHTER HANDEL"
            }
        }
        demoResult = label("Demo bereit. Ein UIAutomator-Test kann Eingaben und Klicks simulieren.")
        setContentView(ScrollView(this).apply { addView(stack) })
        processUserShare(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        processUserShare(intent)
    }

    private fun processUserShare(incoming: Intent?) {
        if (incoming?.action != Intent.ACTION_SEND || !incoming.type.orEmpty().startsWith("image/")) return
        @Suppress("DEPRECATION")
        val uri = incoming.getParcelableExtra<Uri>(Intent.EXTRA_STREAM) ?: return
        readImage(uri)
    }

    @Deprecated("Android's activity-result API retained here to avoid framework dependencies in the lab.")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != selectImageRequest || resultCode != RESULT_OK) return
        val uri = data?.data ?: return
        readImage(uri)
    }

    private fun readImage(uri: Uri) {
        evidenceDraft = ""
        status.text = "Bild wird lokal gelesen. Es wird nichts automatisch versendet."
        try {
            val input = InputImage.fromFilePath(this, uri)
            val recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
            recognizer.process(input)
                .addOnSuccessListener { result ->
                    evidenceDraft = draftFromOcr(result.text)
                    status.text = if (evidenceDraft.isBlank()) {
                        "Bild nicht eindeutig: genau eine prüfziffergültige ISIN erforderlich. Keine Daten übernommen."
                    } else evidenceDraft
                }
                .addOnFailureListener {
                    evidenceDraft = ""
                    status.text = "Lokale Texterkennung fehlgeschlagen. Keine Nachweise übernommen."
                }
                .addOnCompleteListener { recognizer.close() }
        } catch (_: Exception) {
            evidenceDraft = ""
            status.text = "Bild nicht lesbar. Keine Nachweise übernommen."
        }
    }

    private fun draftFromOcr(raw: String): String {
        val rawUpper = raw.uppercase(Locale.ROOT)
        val isinPattern = Regex("(?<![A-Z0-9])[A-Z]{2}[A-Z0-9]{9}[0-9](?![A-Z0-9])")
        val isins = isinPattern.findAll(rawUpper)
            .map { it.value }.filter(::validIsin).distinct().take(12).toList()
        // Numeric OCR fields from a multi-product screenshot must not be assigned
        // to an arbitrary instrument. Never export an ambiguous interpretation.
        if (isins.size != 1) return ""

        fun observed(label: String, regex: Regex): String {
            val value = regex.find(raw)?.groupValues?.getOrNull(1)?.trim()
            return if (value.isNullOrEmpty()) "" else "\n$label (OCR ungeprüft): $value"
        }
        val numeric = "[0-9][0-9., ]{0,18}"
        val opts = setOf(RegexOption.IGNORE_CASE, RegexOption.MULTILINE)
        val bid = observed("Geld", Regex("^\\s*(?:Geld|Bid)\\s*[:：]\\s*($numeric)\\s*(?:EUR|CHF)?\\s*$", opts))
        val ask = observed("Brief", Regex("^\\s*(?:Brief|Ask)\\s*[:：]\\s*($numeric)\\s*(?:EUR|CHF)?\\s*$", opts))
        val lev = observed("Hebel", Regex("^\\s*(?:Hebel|Leverage)\\s*[:：]\\s*($numeric)\\s*(?:x|X)?\\s*$", opts))
        val ko = observed("KO-Schwelle", Regex("^\\s*(?:KO|KO-Schwelle|Knock-Out)\\s*[:：]\\s*($numeric)\\s*(?:USD|EUR|CHF)?\\s*$", opts))
        val venue = observed("Handelsplatz", Regex("^\\s*(?:Handelsplatz|Venue)\\s*[:：]\\s*([A-Za-z0-9 ._/-]{1,48})\\s*$", opts))
        val identity = if (isins.isEmpty()) "Keine prüfziffergültige ISIN gefunden" else "ISIN: " + isins.joinToString(", ")
        return "BOB OCR-ENTWURF – NICHT VERIFIZIERT\n$identity$bid$ask$lev$ko$venue\n" +
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
