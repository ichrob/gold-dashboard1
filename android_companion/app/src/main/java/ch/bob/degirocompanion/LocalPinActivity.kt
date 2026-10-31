package ch.bob.degirocompanion

import android.app.Activity
import android.os.Bundle
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import java.security.MessageDigest

/** Local-only keypad: no IME, clipboard, intent extras, saved-state input or displayed digits. */
class LocalPinActivity : Activity() {
    private val first = ByteArray(5)
    private val repeat = ByteArray(5)
    private var count = 0
    private var confirming = false
    private lateinit var status: TextView
    private lateinit var dots: TextView
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(null)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        if (!LocalPinVault.available(this) || !PhoneDiagnostics.keypadTestVerified(this) || PinReadinessProbe.running) { finish(); return }
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setPadding(24, 32, 24, 24)
            isSaveEnabled = false
            importantForAutofill = View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS
        }
        status = TextView(this).apply { textSize = 21f; text = "Bestehende DEGIRO-PIN eingeben" }
        dots = TextView(this).apply { textSize = 32f; isSaveEnabled = false; importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO }
        box.addView(status)
        box.addView(TextView(this).apply { text = "Die PIN bleibt verschlüsselt auf diesem Handy. Sie wird nicht an Bob oder ChatGPT übertragen. Danach zur Kontrolle nochmals eingeben. Eine Anmeldung startet erst über den separaten Knopf." })
        box.addView(dots)
        fun button(parent: LinearLayout, text: String, action: () -> Unit) {
            parent.addView(Button(this).apply {
                this.text = text; isAllCaps = false; filterTouchesWhenObscured = true; isSaveEnabled = false
                setOnTouchListener { _, event -> event.flags and (MotionEvent.FLAG_WINDOW_IS_OBSCURED or MotionEvent.FLAG_WINDOW_IS_PARTIALLY_OBSCURED) != 0 }
                setOnClickListener { if (LocalPinVault.available(this@LocalPinActivity)) action() else finish() }
            }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        }
        for (row in listOf(listOf(1,2,3), listOf(4,5,6), listOf(7,8,9), listOf(0))) {
            val line = LinearLayout(this)
            row.forEach { digit -> button(line, digit.toString()) {
                if (count < 5) { (if (confirming) repeat else first)[count++] = (48 + digit).toByte(); render() }
            } }
            box.addView(line)
        }
        val controls = LinearLayout(this)
        button(controls, "Ziffer löschen") { if (count > 0) { (if (confirming) repeat else first)[--count] = 0; render() } }
        button(controls, "Weiter / speichern") {
            if (count == 5) {
                if (!confirming) { confirming = true; count = 0; status.text = "Dieselbe PIN nochmals eingeben"; render() }
                else if (!MessageDigest.isEqual(first, repeat)) { clear(); status.text = "Eingaben verschieden. Bitte neu eingeben."; render() }
                else {
                    val saved = runCatching { LocalPinVault.save(this, first) }.isSuccess
                    clear(); render()
                    if (saved) { android.widget.Toast.makeText(this, "PIN nur auf diesem Handy gespeichert.", android.widget.Toast.LENGTH_LONG).show(); finish() }
                    else status.text = "Speichern nicht möglich. Keine Anmeldung gestartet."
                }
            }
        }
        box.addView(controls)
        val cancel = LinearLayout(this); button(cancel, "Abbrechen") { finish() }; box.addView(cancel)
        setContentView(ScrollView(this).apply { isSaveEnabled = false; addView(box) }); render()
    }
    private fun render() { dots.text = "● ".repeat(count) + "○ ".repeat(5 - count) }
    private fun clear() { first.fill(0); repeat.fill(0); count = 0; confirming = false }
    override fun onPause() { clear(); if (::dots.isInitialized) render(); super.onPause(); finish() }
    override fun onDestroy() { clear(); super.onDestroy() }
    override fun onSaveInstanceState(outState: Bundle) { /* Never persist entry state. */ }
}
