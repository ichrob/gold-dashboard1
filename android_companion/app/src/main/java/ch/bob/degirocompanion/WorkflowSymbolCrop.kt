package ch.bob.degirocompanion

import android.content.Context
import android.graphics.*
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.View
import kotlin.math.*

/** Owner-controlled zoom and editable image-space selection; never inferred coordinates. */
internal class WorkflowSymbolCrop(context: Context, private val bitmap: Bitmap) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private var startX = 0f
    private var startY = 0f
    private var selection: RectF? = null
    private var initial: RectF? = null
    private var corner = -1
    private var moving = false
    private var pinching = false
    private var zoom = 1f
    private var centerX = bitmap.width / 2f
    private var centerY = bitmap.height / 2f
    private val scale get() = min(width.toFloat() / bitmap.width, height.toFloat() / bitmap.height) * zoom
    private val offsetX get() = width / 2f - centerX * scale
    private val offsetY get() = height / 2f - centerY * scale
    private val detector = ScaleGestureDetector(context, object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
        override fun onScaleBegin(detector: ScaleGestureDetector): Boolean { pinching = true; return true }
        override fun onScale(detector: ScaleGestureDetector): Boolean {
            if (scale <= 0) return false
            val x = (detector.focusX - offsetX) / scale
            val y = (detector.focusY - offsetY) / scale
            zoom = (zoom * detector.scaleFactor).coerceIn(1f, 8f)
            centerX = x - (detector.focusX - width / 2f) / scale
            centerY = y - (detector.focusY - height / 2f) / scale
            clampCenter(); invalidate(); return true
        }
    })
    init { contentDescription = "Symbol markieren; mit zwei Fingern vergrößern, Rahmen innen verschieben oder an den Ecken anpassen" }
    private fun clampCenter() {
        if (zoom == 1f) { centerX = bitmap.width / 2f; centerY = bitmap.height / 2f }
        else { centerX = centerX.coerceIn(0f, bitmap.width.toFloat()); centerY = centerY.coerceIn(0f, bitmap.height.toFloat()) }
    }
    fun zoomBy(factor: Float) {
        selection?.let { centerX = it.centerX(); centerY = it.centerY() }
        zoom = (zoom * factor).coerceIn(1f, 8f); clampCenter(); invalidate()
    }
    fun resetSelection() { selection = null; initial = null; invalidate() }
    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        if (scale <= 0) return
        paint.style = Paint.Style.FILL
        canvas.drawBitmap(bitmap, null, RectF(offsetX, offsetY, offsetX + bitmap.width * scale, offsetY + bitmap.height * scale), paint)
        selection?.let {
            paint.color = Color.rgb(0, 150, 136); paint.style = Paint.Style.STROKE; paint.strokeWidth = 3f * resources.displayMetrics.density
            canvas.drawRect(it.left * scale + offsetX, it.top * scale + offsetY, it.right * scale + offsetX, it.bottom * scale + offsetY, paint)
            paint.style = Paint.Style.FILL
            for ((x,y) in corners(it)) canvas.drawCircle(x * scale + offsetX, y * scale + offsetY, 6f * resources.displayMetrics.density, paint)
        }
    }
    private fun corners(r: RectF) = listOf(r.left to r.top, r.right to r.top, r.right to r.bottom, r.left to r.bottom)
    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (scale <= 0) return false
        detector.onTouchEvent(event)
        if (event.pointerCount > 1) { pinching = true; parent.requestDisallowInterceptTouchEvent(true); return true }
        if (pinching && event.actionMasked != MotionEvent.ACTION_DOWN) {
            if (event.actionMasked == MotionEvent.ACTION_UP || event.actionMasked == MotionEvent.ACTION_CANCEL) { pinching = false; parent.requestDisallowInterceptTouchEvent(false) }
            return true
        }
        val x = ((event.x - offsetX) / scale).coerceIn(0f, bitmap.width.toFloat())
        val y = ((event.y - offsetY) / scale).coerceIn(0f, bitmap.height.toFloat())
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                pinching = false; parent.requestDisallowInterceptTouchEvent(true); startX = x; startY = y
                initial = selection?.let { RectF(it) }; corner = -1; moving = false
                initial?.let { r ->
                    val tolerance = 24 * resources.displayMetrics.density / scale
                    corner = corners(r).indices.minByOrNull { i -> hypot(corners(r)[i].first - x, corners(r)[i].second - y) }?.takeIf {
                        hypot(corners(r)[it].first - x, corners(r)[it].second - y) <= tolerance
                    } ?: -1
                    moving = corner == -1 && r.contains(x, y)
                }
            }
            MotionEvent.ACTION_MOVE, MotionEvent.ACTION_UP -> {
                val r = initial
                selection = when {
                    r != null && corner >= 0 -> {
                        val opposite = corners(r)[(corner + 2) % 4]
                        RectF(min(x, opposite.first), min(y, opposite.second), max(x, opposite.first), max(y, opposite.second))
                    }
                    r != null && moving -> RectF(r).apply {
                        offset((x - startX).coerceIn(-r.left, bitmap.width - r.right), (y - startY).coerceIn(-r.top, bitmap.height - r.bottom))
                    }
                    else -> RectF(min(startX, x), min(startY, y), max(startX, x), max(startY, y))
                }
                if (event.actionMasked == MotionEvent.ACTION_UP) { parent.requestDisallowInterceptTouchEvent(false); performClick() }
            }
            MotionEvent.ACTION_CANCEL -> { selection = initial; parent.requestDisallowInterceptTouchEvent(false) }
        }
        invalidate(); return true
    }
    override fun performClick(): Boolean { super.performClick(); return true }
    fun box(): SymbolBox? = selection?.let { SymbolBox(it.left.toInt(), it.top.toInt(), it.right.toInt(), it.bottom.toInt()) }
}
