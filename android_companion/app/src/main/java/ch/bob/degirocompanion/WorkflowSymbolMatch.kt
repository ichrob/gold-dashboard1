package ch.bob.degirocompanion

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

internal data class SymbolBox(val left: Int, val top: Int, val right: Int, val bottom: Int) {
    val width get() = right - left
    val height get() = bottom - top
}
internal data class SymbolPattern(val pixels: IntArray, val widthRatio: Double, val heightRatio: Double, val aspect: Double)

/** Bounded visual matching inside actual clickable nodes, never blind coordinate replay. */
internal object WorkflowSymbolMatch {
    const val SIDE = 16
    fun sample(pixels: IntArray, width: Int, box: SymbolBox): IntArray = IntArray(SIDE * SIDE) { i ->
        val x = box.left + ((i % SIDE + .5) * box.width / SIDE).toInt().coerceIn(0, box.width - 1)
        val y = box.top + ((i / SIDE + .5) * box.height / SIDE).toInt().coerceIn(0, box.height - 1)
        pixels[y * width + x]
    }
    fun distinctive(values: IntArray): Boolean {
        if (values.size != SIDE * SIDE || values.any { it !in 0..255 }) return false
        val mean = values.average()
        return values.count { abs(it - mean) > 30 } >= 24
    }
    fun pattern(pixels: IntArray, width: Int, height: Int, box: SymbolBox): SymbolPattern? {
        if (width <= 0 || height <= 0 || pixels.size != width * height || box.left < 0 || box.top < 0 ||
            box.right > width || box.bottom > height || box.width < 12 || box.height < 12 ||
            box.width > width / 2 || box.height > height / 2) return null
        val sample = sample(pixels, width, box)
        if (!distinctive(sample)) return null
        return SymbolPattern(sample, box.width.toDouble() / width, box.height.toDouble() / height, width.toDouble() / height)
    }
    fun match(pattern: SymbolPattern, pixels: IntArray, width: Int, height: Int, boxes: List<SymbolBox>): Int? {
        if (width <= 0 || height <= 0 || pixels.size != width * height || !distinctive(pattern.pixels) ||
            abs(width.toDouble() / height / pattern.aspect - 1) > .05 || boxes.size > 80) return null
        var attempts = 0
        val scores = boxes.map { box ->
            var best = 1.0
            if (box.left >= 0 && box.top >= 0 && box.right <= width && box.bottom <= height && box.width > 0 && box.height > 0) {
                for (scale in listOf(1.0, .9, 1.1)) {
                    val w = (width * pattern.widthRatio * scale).toInt().coerceAtLeast(12)
                    val h = (height * pattern.heightRatio * scale).toInt().coerceAtLeast(12)
                    if (w > box.width || h > box.height) continue
                    val stride = max(1, min(w, h) / 16)
                    for (y in box.top..box.bottom - h step stride) for (x in box.left..box.right - w step stride) {
                        if (++attempts > 30_000) return null
                        var error = 0
                        for (i in pattern.pixels.indices) {
                            val px = x + ((i % SIDE + .5) * w / SIDE).toInt().coerceAtMost(w - 1)
                            val py = y + ((i / SIDE + .5) * h / SIDE).toInt().coerceAtMost(h - 1)
                            error += abs(pixels[py * width + px] - pattern.pixels[i])
                            if (error > 11750) break // Keep plausible secondary matches for ambiguity rejection.
                        }
                        best = min(best, error / 65280.0)
                    }
                }
            }
            best
        }
        val ranked = scores.indices.sortedBy { scores[it] }
        val best = ranked.firstOrNull() ?: return null
        return best.takeIf { scores[it] <= .08 && (ranked.size == 1 || scores[ranked[1]] > .16) }
    }
}
