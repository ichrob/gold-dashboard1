package ch.bob.degirocompanion

import android.content.Context
import android.graphics.*
import android.view.MotionEvent
import android.view.View
import kotlin.math.max
import kotlin.math.min

/** Owner draws a rectangle; the image itself cannot choose a target. */
internal class WorkflowSymbolCrop(context: Context, private val bitmap: Bitmap) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private var startX = 0f
    private var startY = 0f
    private var selection: RectF? = null
    private val scale get() = min(width.toFloat() / bitmap.width, height.toFloat() / bitmap.height)
    private val offsetX get() = (width - bitmap.width * scale) / 2
    private val offsetY get() = (height - bitmap.height * scale) / 2
    init { contentDescription = "Ziehe einen engen Rahmen um das zu lernende Symbol" }
    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        if (scale <= 0) return
        paint.style = Paint.Style.FILL
        canvas.drawBitmap(bitmap, null, RectF(offsetX, offsetY, offsetX + bitmap.width * scale, offsetY + bitmap.height * scale), paint)
        selection?.let {
            paint.color = Color.rgb(0, 150, 136); paint.style = Paint.Style.STROKE; paint.strokeWidth = 4f
            canvas.drawRect(it.left * scale + offsetX, it.top * scale + offsetY, it.right * scale + offsetX, it.bottom * scale + offsetY, paint)
        }
    }
    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (scale <= 0) return false
        val x = ((event.x - offsetX) / scale).coerceIn(0f, bitmap.width.toFloat())
        val y = ((event.y - offsetY) / scale).coerceIn(0f, bitmap.height.toFloat())
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> { parent.requestDisallowInterceptTouchEvent(true); startX = x; startY = y; selection = null }
            MotionEvent.ACTION_MOVE, MotionEvent.ACTION_UP -> {
                selection = RectF(min(startX, x), min(startY, y), max(startX, x), max(startY, y))
                if (event.actionMasked == MotionEvent.ACTION_UP) { parent.requestDisallowInterceptTouchEvent(false); performClick() }
            }
            MotionEvent.ACTION_CANCEL -> { selection = null; parent.requestDisallowInterceptTouchEvent(false) }
        }
        invalidate(); return true
    }
    override fun performClick(): Boolean { super.performClick(); return true }
    fun box(): SymbolBox? = selection?.let { SymbolBox(it.left.toInt(), it.top.toInt(), it.right.toInt(), it.bottom.toInt()) }
}
