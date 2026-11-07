package org.bob.workflowfixture
import android.app.Activity
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView

/** Synthetic offline app only. No broker, account, credentials or network. */
class MainActivity : Activity() {
    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        val layout = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(40,100,40,40) }
        setContentView(layout)
        fun field(id: Int) { layout.addView(EditText(this).apply { this.id = id; hint = "Suchfeld"; showSoftInputOnFocus = false }) }
        when (intent.getStringExtra("mode")) {
            "ocr" -> layout.addView(TextView(this).apply { text = "Bob Screenshot Test 314159"; textSize = 26f })
            "open" -> field(R.id.search_src_text)
            "ambiguous" -> { field(R.id.search_src_text); field(R.id.search_input) }
            "protected" -> { layout.addView(TextView(this).apply { text = "Passwort" }); field(R.id.search_src_text) }
            else -> layout.addView(Button(this).apply { text = "Suche"; setOnClickListener { layout.removeAllViews(); field(R.id.search_src_text) } })
        }
    }
}
