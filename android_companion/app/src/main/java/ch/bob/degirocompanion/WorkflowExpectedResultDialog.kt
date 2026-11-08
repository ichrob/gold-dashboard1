package ch.bob.degirocompanion

import android.app.Activity
import android.app.AlertDialog
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.widget.*
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions

/** A result image contributes one owner-confirmed text marker, never executable instructions. */
internal class WorkflowExpectedResultDialog(
    private val activity: Activity,
    private val target: String,
    private val before: List<String>,
    private val current: () -> Boolean,
    private val pickImage: () -> Unit,
    private val submit: (String) -> Unit
) {
    private val expected = EditText(activity).apply { hint = "Welcher Text soll danach erscheinen?" }
    private val info = TextView(activity)
    private val preview = ImageView(activity).apply { adjustViewBounds = true; maxHeight = 320 }
    private val choose = Button(activity).apply { text = "Screenshot als Ergebnis auswählen"; setOnClickListener { pickImage() } }
    private var bitmap: Bitmap? = null
    private var busy = false
    private var closed = false
    internal val resultText get() = expected.text.toString()
    private val dialog = AlertDialog.Builder(activity).setTitle("Ergebnis nach dem Tippen auf $target")
        .setView(LinearLayout(activity).apply {
            orientation = LinearLayout.VERTICAL; setPadding(24, 8, 24, 8)
            addView(expected); addView(choose); addView(preview); addView(info)
        }).setPositiveButton("Senden", null).setNegativeButton("Abbrechen", null).create()
    fun show() {
        dialog.setOnDismissListener {
            closed = true; preview.setImageDrawable(null)
            if (!busy) { bitmap?.recycle(); bitmap = null }
        }
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                if (!current()) { dismiss(); return@setOnClickListener }
                if (busy) { info.text = "Screenshot wird noch gelesen …"; return@setOnClickListener }
                val command = WorkflowComposer.command(WorkflowAction.CLICK, target, expected = resultText)
                if (command == null) expected.error = "Bitte Ergebnistext eingeben oder im Screenshot auswählen"
                else { dismiss(); submit(command) }
            }
        }
        dialog.show()
    }
    fun dismiss() = dialog.dismiss()
    fun readImage(uri: Uri) {
        if (closed || busy || !current()) return
        val image = runCatching {
            val options = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            activity.contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, options) }
            require(options.outWidth in 1..30000 && options.outHeight in 1..30000)
            var sample = 1
            while (options.outWidth / sample > 2048 || options.outHeight / sample > 2048) sample *= 2
            options.inJustDecodeBounds = false; options.inSampleSize = sample
            activity.contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, options) } ?: error("image")
        }.getOrElse { info.text = "Bild nicht lesbar. Bitte ein anderes Bild wählen."; return }
        preview.setImageDrawable(null); bitmap?.recycle(); bitmap = image
        preview.setImageBitmap(image)
        busy = true; choose.isEnabled = false; info.text = "Ergebnisbild wird lokal gelesen …"
        val reader = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
        reader.process(InputImage.fromBitmap(image, 0)).addOnSuccessListener { recognized ->
            if (!closed && current()) {
                val all = recognized.textBlocks.flatMap { it.lines }.map { it.text.trim() }
                    .filter(WorkflowComposer::validText).distinct().take(80)
                val fresh = all.filter { label -> before.none { LocalWorkflow.normalize(it) == LocalWorkflow.normalize(label) } }
                val labels = fresh.ifEmpty { all }
                when (labels.size) {
                    0 -> info.text = "Kein lesbarer Ergebnistext gefunden. Bitte Text eingeben oder anderes Bild wählen."
                    1 -> { expected.setText(labels.single()); info.text = "Ergebnis aus Screenshot übernommen · mit Senden starten" }
                    else -> {
                        info.text = "Wähle einen kennzeichnenden Text der Zielansicht."
                        AlertDialog.Builder(activity).setTitle("Woran soll Bob das Ergebnis erkennen?")
                            .setItems(labels.toTypedArray()) { _, index ->
                                if (!closed && current()) { expected.setText(labels[index]); info.text = "Ergebnis aus Screenshot übernommen · mit Senden starten" }
                            }.setNegativeButton("Zurück", null).show()
                    }
                }
            }
        }.addOnFailureListener { if (!closed) info.text = "Texterkennung fehlgeschlagen. Bitte erneut wählen oder Text eingeben." }
            .addOnCompleteListener {
                busy = false; choose.isEnabled = true; reader.close()
                if (closed) { bitmap?.recycle(); bitmap = null }
            }
    }
}
