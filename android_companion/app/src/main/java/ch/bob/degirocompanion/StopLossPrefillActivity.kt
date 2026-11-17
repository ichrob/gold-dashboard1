package ch.bob.degirocompanion

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.os.Bundle
import android.os.SystemClock
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

/**
 * Local owner approval. Pasted Bob model values are untrusted proposals, not
 * broker/position evidence. No external exported entry point or network call.
 */
class StopLossPrefillActivity : Activity() {
    private lateinit var payload: EditText
    private lateinit var confirmation: CheckBox
    private lateinit var status: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val content=LinearLayout(this).apply {
            orientation=LinearLayout.VERTICAL
            setPadding(28,28,28,28)
        }
        fun label(s:String) = TextView(this).also { it.text=s; it.textSize=17f; content.addView(it) }
        label("Bob · Stop-Loss in DEGIRO vorbereiten")
        label("1. In Bob beim berechneten Produkt-Stopp „Entwurf kopieren“ wählen und hier einfügen. Nur EUR-Stopps; CHF-Finanzrahmen ist davon unabhängig.")
        payload=EditText(this).apply {
            hint="BOB-STOP/1|ISIN|EUR|Anzahl|Stopp|Zeit"
            minLines=2; maxLines=4
            setSingleLine(false)
            inputType=android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
        }
        content.addView(payload)
        content.addView(Button(this).apply {
            isAllCaps=false; text="Bob-Entwurf aus Zwischenablage übernehmen"
            setOnClickListener {
                // Only on an explicit local tap; never monitor the clipboard.
                val clipboard=getSystemService(CLIPBOARD_SERVICE) as android.content.ClipboardManager
                val clip=clipboard.primaryClip
                val raw=if(clip!=null && clip.itemCount==1 &&
                    clip.getItemAt(0).uri==null && clip.getItemAt(0).intent==null)
                    clip.getItemAt(0).text?.toString().orEmpty() else ""
                if(StopLossDraftCodec.parse(raw,System.currentTimeMillis())==null) {
                    status.text="Kein gültiger frischer Bob-Entwurf in der Zwischenablage."
                } else {
                    payload.setText(raw)
                    status.text="Bob-Entwurf übernommen. Position und Werte unbedingt prüfen."
                }
            }
        })
        label("2. Öffne bei DEGIRO selbst die Detailseite deiner bestehenden Position oder deren VERKAUF-Ordermaske. Bob darf nur die VERKAUF-Maske öffnen, keine Order senden.")
        confirmation=CheckBox(this).apply {
            text="Ich bestätige: Diese ISIN und Stückzahl gehören zu meiner tatsächlich gehaltenen Position. Die Produktdetailseite oder VERKAUF-Maske ist in DEGIRO geöffnet. Den Geldkurs und den Stopp prüfe ich selbst."
            isChecked=false
        }
        content.addView(confirmation)
        status=label(StopLossPrefillSession.status)
        val start=Button(this).apply {
            isAllCaps=false; text="Stop-Loss-Felder automatisch vorbereiten"
            setOnClickListener { prepare() }
        }
        content.addView(start)
        content.addView(Button(this).apply {
            isAllCaps=false; text="STOPP · Vorbereitung abbrechen"
            setOnClickListener { StopLossPrefillSession.finish("USER_STOP");status.text=StopLossPrefillSession.status }
        })
        val scroll=ScrollView(this).apply { addView(content) }
        setContentView(scroll)
    }
    override fun onResume() { super.onResume(); if(::status.isInitialized) status.text=StopLossPrefillSession.status }
    private fun prepare() {
        val draft=StopLossDraftCodec.parse(payload.text.toString(),System.currentTimeMillis())
        if (draft==null) { status.text="Ungültiger oder älter als 5 Minuten alter Bob-Entwurf. Neu berechnen und erneut kopieren."; return }
        if (!confirmation.isChecked) { status.text="Bestehende Position und Verkaufsmaske müssen lokal bestätigt werden."; return }
        if (!ProductReadDiagnostics.connected ||
            !getSharedPreferences("product_reader",MODE_PRIVATE).getBoolean("enabled",false)) {
            status.text="Bob-Lesedienst ist nicht eingeschaltet. Zuerst die Bedienungshilfe aktivieren."; return
        }
        if (PhoneRemote.active() || MorningReadRun.running || GoldSearchRun.running ||
            PinReadinessProbe.running || ProductReadRequest.active(SystemClock.elapsedRealtime())) {
            status.text="Andere DEGIRO-Lesesitzung läuft. Zuerst dort STOPP wählen."; return
        }
        val launch=packageManager.getLaunchIntentForPackage("nl.degiro.trader")
        if(launch==null) { status.text="DEGIRO-App nicht installiert.";return }
        AlertDialog.Builder(this)
            .setTitle("Nur Eingaben vorbereiten · KEINE Order")
            .setMessage("ISIN: ${draft.isin}\nVerkauf von: ${draft.quantity} Stück\nModell-Stopp: ${draft.stopText} EUR\n\nBob öffnet bei klar erkannter Produktdetailseite zunächst VERKAUF, überprüft die ISIN und die Verkaufsrichtung und darf dann nur „Ordertyp“ → „Stop Loss“ auswählen und diese beiden Zahlen eintragen. Bei unklaren Feldern stoppt er. „Order platzieren“ wird NIE angetippt. Die Ausführung bleibt allein bei dir.")
            .setNegativeButton("Abbrechen",null)
            .setPositiveButton("Eingabefelder vorbereiten") { _,_ ->
                StopLossPrefillSession.arm(draft,SystemClock.elapsedRealtime())
                runCatching { startActivity(launch) }.onFailure {
                    StopLossPrefillSession.finish("APP_NICHT_GESTARTET")
                    status.text=StopLossPrefillSession.status
                }
            }.show()
    }
}
