package ch.bob.degirocompanion

import android.app.Activity
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView

/** Fixed offline surface. No intent arguments, external app or AI calls. */
class WorkflowSelfTestActivity : Activity() {
    companion object { internal var active = false; private set }
    private val handler = Handler(Looper.getMainLooper())
    private lateinit var surface: LinearLayout
    private lateinit var status: TextView
    private var started = false
    private var phase = 0
    private var deadline = 0L
    private val marker = "Bob Test " + java.util.UUID.randomUUID().toString().filter { it.isDigit() }.take(6).padEnd(6,'7')
    private val check = object : Runnable {
        override fun run() {
            if (!active || phase == 2) return
            if (SystemClock.elapsedRealtime() > deadline) { complete(false,"Zeitlimit: Selbsttest nicht vollständig bestätigt"); return }
            if (phase == 0) {
                val run = WorkflowService.run
                if (run?.finished == true) {
                    if (!WorkflowAiPolicy.verified(run)) { complete(false,WorkflowService.message); return }
                    // The actual edit field was verified by the service; now test OCR separately.
                    phase = 1
                    surface.removeAllViews()
                    surface.addView(TextView(this@WorkflowSelfTestActivity).apply { text=marker; textSize=30f })
                    addStatus("Klicken und Eingabe bestätigt. Bildtext wird geprüft.")
                    addStop()
                    if (WorkflowService.instance?.beginSelfTest(true) != true) { complete(false,"Lesedienst nicht verfügbar"); return }
                }
            } else if (WorkflowService.screenshotText.contains(marker)) {
                complete(true,"Selbsttest bestanden: Klicken, Texteingabe, Ergebnisprüfung und Screenshot-Lesen bestätigt."); return
            }
            handler.postDelayed(this,250)
        }
    }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        surface=LinearLayout(this).apply { orientation=LinearLayout.VERTICAL; setPadding(32,120,32,40) }
        setContentView(surface)
        addStatus("Lokaler Selbsttest · nur Testdaten")
        surface.addView(Button(this).apply {
            text="Suche"
            setOnClickListener {
                surface.removeView(this)
                surface.addView(EditText(this@WorkflowSelfTestActivity).apply {
                    id=R.id.selftest_search; hint="Suchfeld"; showSoftInputOnFocus=false
                })
            }
        })
        addStop()
    }
    private fun addStatus(text: String) {
        status=TextView(this).apply { this.text=text; textSize=20f }
        surface.addView(status)
    }
    private fun addStop() {
        surface.addView(Button(this).apply { text="STOPP"; setOnClickListener { if (phase == 2) finish() else complete(false,"Selbsttest gestoppt") } })
    }
    override fun onResume() {
        super.onResume(); active=true
        if (!started) {
            started=true; deadline=SystemClock.elapsedRealtime()+45_000
            if (WorkflowService.instance?.beginSelfTest(false) != true) {
                complete(false,"Bitte zuerst die Auftrags-Bedienungshilfe einschalten."); return
            }
            handler.post(check)
        }
    }
    private fun complete(success: Boolean, detail: String) {
        val confirmed = if (success) 3 else if (phase == 1) 2 else WorkflowService.run?.index ?: 0
        phase=2; handler.removeCallbacks(check); WorkflowService.stop()
        WorkflowHealth.record(this,if(success) "SUCCEEDED" else "STOPPED","LOCAL",
            confirmed.coerceIn(0,3),3,if(success) "NONE" else WorkflowFailure.code(detail))
        status.text=detail
        getSharedPreferences("workflow_selftest",0).edit()
            .putBoolean("success",success).putString("at",java.time.Instant.now().toString()).putString("detail",detail).apply()
    }
    override fun onPause() {
        active=false; handler.removeCallbacks(check)
        if (phase != 2) complete(false,"Selbsttest unterbrochen; erneut starten")
        super.onPause()
    }
}
