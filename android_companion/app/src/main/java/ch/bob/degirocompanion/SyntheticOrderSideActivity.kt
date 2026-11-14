package ch.bob.degirocompanion

import android.app.Activity
import android.os.Bundle
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

/**
 * Isolated demonstration of the KAUF / VERKAUF -> order-form transition.
 *
 * This activity never reads or controls the DEGIRO app. It has no broker
 * integration, no quote input, no remote action handler and no submit action.
 * It is intentionally NOT an AccessibilityService.
 */
class SyntheticOrderSideActivity : Activity() {
    private lateinit var form: LinearLayout

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(28, 32, 28, 32)
        }
        val scroll = ScrollView(this).apply { addView(container) }
        setContentView(scroll)

        fun text(value: String, parent: LinearLayout = container): TextView =
            TextView(this).apply {
                this.text = value
                textSize = 18f
                setPadding(0, 12, 0, 12)
                parent.addView(this)
            }

        text("BOB TESTLABOR – NUR KÜNSTLICHE ORDERMASKE")
        text("Die Schaltflächen öffnen eine lokale Demo. Keine Verbindung zu DEGIRO, keine Eingaben in DEGIRO und keine Echtgeldorders.")
        text("DEMO-PRODUKT · ISIN TEST-ONLY · KEIN ECHTER HANDEL")

        val choices = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            container.addView(this)
        }
        fun choice(title: String, side: String) {
            Button(this).apply {
                this.text = title
                isAllCaps = false
                setOnClickListener { showDemoForm(side) }
                choices.addView(this, LinearLayout.LayoutParams(0,
                    LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            }
        }
        choice("DEMO: KAUF", "KAUF")
        choice("DEMO: VERKAUF", "VERKAUF")

        form = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            container.addView(this)
        }
        text("Zum Testen KAUF oder VERKAUF antippen. Kein Versand möglich.", form)
        Button(this).apply {
            text = "DEMO schließen"
            isAllCaps = false
            setOnClickListener { finish() }
            container.addView(this)
        }
    }

    private fun showDemoForm(side: String) {
        form.removeAllViews()
        fun row(label: String) {
            form.addView(TextView(this).apply {
                text = label
                textSize = 18f
                setPadding(0, 12, 0, 12)
            })
        }
        row("DEMO: $side-ORDERMASKE – KEIN ECHTER HANDEL")
        row("Ordertyp: Limit / Stop Loss / Stop Limit (nur Darstellung)")
        row("Limit (€): — (keine echten Eingabefelder)")
        row("Anzahl: —")
        row("Betrag (CHF): —")
        row("KEIN ORDER-VERSAND: Diese Demo besitzt keinen Knopf 'Order platzieren'.")
    }
}
