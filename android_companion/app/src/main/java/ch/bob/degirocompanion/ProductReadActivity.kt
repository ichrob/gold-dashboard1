package ch.bob.degirocompanion

import android.accessibilityservice.AccessibilityServiceInfo
import android.view.accessibility.AccessibilityManager
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
            ProductReadRequest.cancel(); ProductReadSession.clear(); refresh()
        }
        button("Leseprüfung einschalten / Android-Einstellungen") {
            AlertDialog.Builder(this).setTitle("Sichtbare Produktfelder lesen")
                .setMessage("Bob erhält über die Android-Bedienungshilfe Zugriff auf sichtbare DEGIRO-Texte. Nach „Prüfung starten“ wartet er höchstens eine Minute auf eine lesbare Produktseite; alternativ liest er nach deinem Tastendruck. Er speichert keinen Bildschirmtext und überträgt nichts automatisch. Login, Eingaben und Orderansichten werden ausgeschlossen. DEGIRO beschränkt automatisierte Werkzeuge; dieser Gerätetest ist keine Zustimmung von DEGIRO. Ohne Freigabe bleibt manuelles Screenshot-Teilen die Alternative.")
                .setNegativeButton("Abbrechen", null)
                .setPositiveButton("Leseprüfung aktivieren") { _, _ ->
                    preferences.edit().putBoolean("enabled", true).apply()
                    startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
                }.show()
        }
        button("Prüfung starten · DEGIRO öffnen und automatisch lesen") {
            if (!preferences.getBoolean("enabled", false) || !serviceEnabled()) {
                result.text = "Bitte zuerst die Leseprüfung und den Android-Dienst einschalten."
                return@button
            }
            ProductReadSession.clear()
            ProductReadRequest.start(SystemClock.elapsedRealtime())
            val launch = packageManager.getLaunchIntentForPackage(ProductScreenEvidence.PACKAGE)
            if (launch == null) { ProductReadRequest.cancel(); result.text = "DEGIRO-App nicht gefunden." }
            else runCatching { startActivity(launch) }.onFailure { ProductReadRequest.cancel(); result.text = "DEGIRO konnte nicht geöffnet werden." }
        }
        button("Gelesene Werte in Bob prüfen") {
            val draft = ProductReadSession.get(SystemClock.elapsedRealtime()).draft
            if (draft.isBlank()) { refresh(); return@button }
            runCatching {
                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://bob-private-scanner.onrender.com/#bob-ocr=" + Uri.encode(draft))))
            }.onFailure { result.text = "Browser konnte nicht geöffnet werden. Entwurf bleibt lokal." }
        }
        stack.addView(TextView(this).apply {
            text = "Einmalig: Leseprüfung und Android-Dienst aktivieren. Die Männchen-Taste ist optional.\n\n1. Prüfung starten.\n2. In DEGIRO eine Produktseite mit beschrifteten Kursen öffnen. Bob liest automatisch, höchstens 60 Sekunden lang.\n3. Zu Bob Handy zurückkehren: Das Ergebnis steht direkt hier. Mit ‚Gelesene Werte in Bob prüfen‘ öffnest du die Webprüfung.\n\nKeine automatische Produktsuche oder Orderbedienung. Anmeldung selbst durchführen. Bei Zeitablauf erneut starten. Ohne zugängliche Bildschirmtexte: Screenshot teilen. Entwurf verfällt nach fünf Minuten."
            textSize = 16f
        })
        result = TextView(this).apply { textSize = 16f; setTextIsSelectable(true) }
        stack.addView(result)
        setContentView(ScrollView(this).apply { addView(stack) })
    }
    override fun onResume() { super.onResume(); refresh() }
    private fun serviceEnabled(): Boolean {
        val manager = getSystemService(ACCESSIBILITY_SERVICE) as AccessibilityManager
        return manager.getEnabledAccessibilityServiceList(AccessibilityServiceInfo.FEEDBACK_ALL_MASK)
            .any { it.resolveInfo.serviceInfo.packageName == packageName &&
                it.resolveInfo.serviceInfo.name == ProductReadService::class.java.name }
    }
    private fun refresh() {
        val value = ProductReadSession.get(SystemClock.elapsedRealtime())
        result.text = (if (preferences.getBoolean("enabled", false)) (if (serviceEnabled()) "Android-Lesedienst bereit.\n" else "Android-Lesedienst noch ausgeschaltet.\n") else "Leseprüfung ausgeschaltet.\n") + (if (ProductReadRequest.active(SystemClock.elapsedRealtime())) "Prüfung wartet auf eine lesbare Produktseite (maximal 60 Sekunden).\n" else "Keine automatische Prüfung aktiv.\n") + value.message +
            if (value.draft.isNotBlank()) "\n\n${value.draft}" else ""
    }
}
