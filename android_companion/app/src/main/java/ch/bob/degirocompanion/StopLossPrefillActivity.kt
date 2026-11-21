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
    private lateinit var submissionConsent: CheckBox
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
        label("2. Öffne bei DEGIRO selbst die Detailseite deiner bestehenden Position oder deren VERKAUF-Ordermaske. Bob bereitet zunächst nur die Felder vor. Für das Absenden ist ein eigener, späterer Freigabeschritt erforderlich.")
        confirmation=CheckBox(this).apply {
            text="Ich bestätige: Diese ISIN und Stückzahl gehören zu meiner tatsächlich gehaltenen Position. Die Produktdetailseite oder VERKAUF-Maske ist in DEGIRO geöffnet. Den Geldkurs und den Stopp prüfe ich selbst."
            isChecked=false
        }
        content.addView(confirmation)
        status=label(StopLossPrefillSession.status)
        content.addView(Button(this).apply {
            isAllCaps=false
            text="SIMULATION starten · ohne DEGIRO und ohne Position"
            setOnClickListener {
                // This is a completely different, broker-free test path.
                // It never sets the actual-position checkbox or starts a broker.
                startActivity(Intent(this@StopLossPrefillActivity,
                    StopLossSimulationActivity::class.java))
            }
        })
        val start=Button(this).apply {
            isAllCaps=false; text="Stop-Loss-Felder automatisch vorbereiten"
            setOnClickListener { prepare() }
        }
        content.addView(start)
        label("3. Nach dem Eintragen: DEGIRO-Werte selbst kontrollieren, zu Bob Handy zurückkehren und ausschließlich diese eine Order freigeben.")
        submissionConsent=CheckBox(this).apply {
            text="Ich habe die konkrete Verkaufsorder selbst kontrolliert: ISIN, meine gehaltene Position, Stückzahl, Ordertyp Stop Loss und Stoppreis. Ich will diese eine ECHTE DEGIRO-Verkaufsorder jetzt verbindlich absenden. Eine Ausführung kann finanzielle Folgen haben."
            isChecked=false
        }
        content.addView(submissionConsent)
        content.addView(Button(this).apply {
            isAllCaps=false; text="Diese eine Verkaufsorder nach Bestätigung absenden"
            setOnClickListener { submitOrder() }
        })
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
        submissionConsent.isChecked=false
        if (!ProductReadDiagnostics.connected ||
            !getSharedPreferences("product_reader",MODE_PRIVATE).getBoolean("enabled",false)) {
            status.text="Bob-Lesedienst ist nicht eingeschaltet. Zuerst die Bedienungshilfe aktivieren."; return
        }
        if (PhoneRemote.active() || MorningReadRun.running || GoldSearchRun.running ||
            PinReadinessProbe.running || ProductReadRequest.active(SystemClock.elapsedRealtime()) ||
            MorningListDelivery.waiting || BobTradeDimMode.running ||
            DegiroReadOnlySession.active(SystemClock.elapsedRealtime())) {
            status.text="Andere DEGIRO-Lesesitzung läuft. Zuerst dort STOPP wählen."; return
        }
        val launch=packageManager.getLaunchIntentForPackage("nl.degiro.trader")
        if(launch==null) { status.text="DEGIRO-App nicht installiert.";return }
        AlertDialog.Builder(this)
            .setTitle("Stufe 1 · Stop-Loss-Felder vorbereiten")
            .setMessage("ISIN: ${draft.isin}\nVerkauf von: ${draft.quantity} Stück\nModell-Stopp: ${draft.stopText} EUR\n\nBob öffnet bei klar erkannter Produktdetailseite zunächst VERKAUF, überprüft die ISIN und die Verkaufsrichtung und darf dann nur „Ordertyp“ → „Stop Loss“ auswählen und diese beiden Zahlen eintragen. Bei unklaren Feldern stoppt er. In diesem Schritt wird „Order platzieren“ NICHT angetippt. Ein eventuelles Absenden erfolgt erst nach einer neuen ausdrücklichen Freigabe auf diesem Gerät.")
            .setNegativeButton("Abbrechen",null)
            .setPositiveButton("Eingabefelder vorbereiten") { _,_ ->
                StopLossPrefillSession.arm(draft,SystemClock.elapsedRealtime())
                runCatching { startActivity(launch) }.onFailure {
                    StopLossPrefillSession.finish("APP_NICHT_GESTARTET")
                    status.text=StopLossPrefillSession.status
                }
            }.show()
    }


    private fun submitOrder() {
        // Two independent local acknowledgements are required. The second one
        // is specific to this exact stop-loss draft, not a standing permission.
        val draft=StopLossDraftCodec.parse(payload.text.toString(),System.currentTimeMillis())
        if(draft==null) {
            status.text="Entwurf abgelaufen oder ungültig: Werte in Bob neu berechnen."
            return
        }
        if(!confirmation.isChecked || !submissionConsent.isChecked) {
            status.text="Bestehende Position und diese konkrete echte Order ausdrücklich freigeben."
            return
        }
        if(!StopLossPrefillSession.canAuthorize(draft,SystemClock.elapsedRealtime())) {
            status.text="Felder noch nicht erfolgreich geprüft oder Sitzung abgelaufen. Neue Vorbereitung erforderlich."
            return
        }
        if(!ProductReadDiagnostics.connected ||
            !getSharedPreferences("product_reader",MODE_PRIVATE).getBoolean("enabled",false)) {
            status.text="DEGIRO-Bediendienste nicht bereit."
            return
        }
        val launch=packageManager.getLaunchIntentForPackage("nl.degiro.trader")
        if(launch==null) { status.text="DEGIRO-App nicht installiert.";return }
        AlertDialog.Builder(this)
            .setTitle("ECHTE Verkaufsorder verbindlich senden?")
            .setMessage("Dies kann eine echte Verkaufsorder auslösen.\\n\\nISIN: ${draft.isin}\\nVERKAUF: ${draft.quantity} Stück\\nTyp: Stop Loss\\nStoppreis: ${draft.stopText} EUR\\n\\nNach deinem Klick darf Bob genau EINMAL „Order platzieren“ antippen, aber nur wenn DEGIRO noch exakt diese ISIN, Verkaufsrichtung, Orderart und beide Zahlen zeigt. Keine automatische Wiederholung. Falls DEGIRO danach eine weitere Bestätigungsseite öffnet, bestätigst du diese selbst. Kontrolliere anschließend den echten Orderstatus bei DEGIRO.")
            .setNegativeButton("Nicht absenden",null)
            .setPositiveButton("Ja, diese eine echte Order senden") { _,_ ->
                submissionConsent.isChecked=false
                if(!StopLossPrefillSession.authorizeSubmission(draft,SystemClock.elapsedRealtime())) {
                    status.text="Freigabe abgelaufen, keine Order gesendet."
                    return@setPositiveButton
                }
                runCatching { startActivity(launch) }.onFailure {
                    StopLossPrefillSession.finish("APP_NICHT_GESTARTET")
                    status.text=StopLossPrefillSession.status
                }
            }.show()
    }
}
