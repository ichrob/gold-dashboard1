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
        fun icon(id: Int) {
            layout.addView(object : android.view.View(this) {
                private val paint = android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG)
                init {
                    this.id = id; isClickable = true; importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES
                    setOnClickListener { layout.removeAllViews(); field(R.id.search_src_text) }
                }
                override fun onDraw(canvas: android.graphics.Canvas) {
                    canvas.drawColor(android.graphics.Color.WHITE)
                    paint.color = android.graphics.Color.BLACK; paint.style = android.graphics.Paint.Style.STROKE; paint.strokeWidth = width * .09f
                    canvas.drawCircle(width * .42f, height * .42f, width * .25f, paint)
                    canvas.drawLine(width * .60f, height * .60f, width * .85f, height * .85f, paint)
                }
            }, LinearLayout.LayoutParams(144, 144))
        }
        when (intent.getStringExtra("mode")) {
            "large" -> {
                repeat(450) { index -> layout.addView(TextView(this).apply {
                    text = "Element $index"; textSize = 1f; importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES
                }, LinearLayout.LayoutParams(-1,1)) }
                layout.addView(Button(this).apply { text = "Suche"; setOnClickListener { layout.removeAllViews(); field(R.id.search_src_text) } })
            }
            "deep" -> {
                var parent: android.view.ViewGroup = layout
                repeat(45) { index ->
                    val nested = android.widget.FrameLayout(this).apply {
                        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES; contentDescription = "Ebene $index"
                    }
                    parent.addView(nested,android.view.ViewGroup.LayoutParams(-1,160)); parent = nested
                }
                parent.addView(Button(this).apply { text="Suche"; setOnClickListener { layout.removeAllViews(); field(R.id.search_src_text) } })
            }
            "symbol" -> icon(R.id.symbol_button)
            "symbol-moved" -> {
                layout.addView(TextView(this).apply { text = "Andere Position" }, LinearLayout.LayoutParams(-1, 200))
                icon(R.id.symbol_button)
            }
            "symbol-duplicate" -> { icon(R.id.symbol_button); icon(R.id.symbol_duplicate) }
            "ocr" -> layout.addView(TextView(this).apply { text = "Bob Screenshot Test 314159"; textSize = 26f })
            "open" -> field(R.id.search_src_text)
            "ambiguous" -> { field(R.id.search_src_text); field(R.id.search_input) }
            "protected" -> { layout.addView(TextView(this).apply { text = "Passwort" }); field(R.id.search_src_text) }
            "nested" -> layout.addView(Button(this).apply { text = "Menü"; setOnClickListener {
                layout.removeAllViews()
                layout.addView(Button(this@MainActivity).apply { text = "Suche"; setOnClickListener { layout.removeAllViews(); field(R.id.search_src_text) } })
            } })
            "closed" -> layout.addView(Button(this).apply { text = "Suche"; setOnClickListener { layout.removeAllViews(); field(R.id.search_src_text) } })
            else -> {
                layout.addView(Button(this).apply { text = "Suche"; setOnClickListener { layout.removeAllViews(); field(R.id.search_src_text) } })
                layout.addView(Button(this).apply { text = "Favoriten"; setOnClickListener { isSelected = true } })
            }
        }
    }
}
