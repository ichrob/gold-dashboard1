package ch.bob.degirocompanion

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.SystemClock
import android.provider.Settings
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

/** Explicit local controls; no exported intent, remote command or automatic upload. */
class ProductReadActivity : Activity() {
    private lateinit var result: TextView
    private val preferences by lazy { getSharedPreferences("product_reader", MODE_PRIVATE) }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val stack = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(24, 24, 24, 24) }
        fun button(title: String, action: () -> Unit) {
            stack.addView(Button(this).apply { text = title; isAllCaps = false; setOnClickListener { action() } })
        }
        stack.addView(TextView(this).apply { text = "DEGIRO-Produktseite lesen · einmalig und lokal"; textSize = 21f })
        button("STOPP · Lesen ausschalten und Entwurf löschen") {
            preferences.edit().putBoolean("enabled", false).apply()
            ProductReadSession.clear(); refresh()
        }
        button("Leseprüfung einschalten / Android-Einstellungen") {
            AlertDialog.Builder(this).setTitle("Sichtbare Produktfelder lesen")
                .setMessage("Bob erhält über die Android-Bedienungshilfe Zugriff auf sichtbare DEGIRO-Texte. Er liest nur nach deinem Tastendruck, speichert keinen Bildschirmtext und überträgt nichts automatisch. Login, Eingaben und Orderansichten werden ausgeschlossen. DEGIRO beschränkt automatisierte Werkzeuge; dieser Gerätetest ist keine Zustimmung von DEGIRO. Ohne Freigabe bleibt manuelles Screenshot-Teilen die Alternative.")
                .setNegativeButton("Abbrechen", null)
                .setPositiveButton("Leseprüfung aktivieren") { _, _ ->
                    preferences.edit().putBoolean("enabled", true).apply()
                    startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
                }.show()
        }
        button("DEGIRO öffnen") {
            val launch = packageManager.getLaunchIntentForPackage(ProductScreenEvidence.PACKAGE)
            if (launch == null) result.text = "DEGIRO-App nicht gefunden."
            else runCatching { startActivity(launch) }.onFailure { result.text = "DEGIRO konnte nicht geöffnet werden." }
        }
        button("Gelesene Werte in Bob prüfen") {
            val draft = ProductReadSession.get(SystemClock.elapsedRealtime()).draft
            if (draft.isBlank()) { refresh(); return@button }
            runCatching {
                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://bob-private-scanner.onrender.com/#bob-ocr=" + Uri.encode(draft))))
            }.onFailure { result.text = "Browser konnte nicht geöffnet werden. Entwurf bleibt lokal." }
        }
        stack.addView(TextView(this).apply {
            text = "1. In Android die Bedienungshilfe ‚Bob: Produktseite einmal lesen‘ und ihre Taste aktivieren.\n2. In DEGIRO selbst anmelden und eine Produktseite öffnen.\n3. Dort die Bedienungshilfe-Taste drücken.\n4. Zu Bob Handy zurückkehren und Werte prüfen.\n\nKeine automatische Produktsuche oder Orderbedienung. Ohne zugängliche Bildschirmtexte: Screenshot teilen. Entwurf verfällt nach fünf Minuten."
            textSize = 16f
        })
        result = TextView(this).apply { textSize = 16f; setTextIsSelectable(true) }
        stack.addView(result)
        setContentView(ScrollView(this).apply { addView(stack) })
    }
    override fun onResume() { super.onResume(); refresh() }
    private fun refresh() {
        val value = ProductReadSession.get(SystemClock.elapsedRealtime())
        result.text = (if (preferences.getBoolean("enabled", false)) "Leseprüfung lokal eingeschaltet. Android-Dienst separat aktivieren.\n" else "Leseprüfung ausgeschaltet.\n") + value.message +
            if (value.draft.isNotBlank()) "\n\n${value.draft}" else ""
    }
}
