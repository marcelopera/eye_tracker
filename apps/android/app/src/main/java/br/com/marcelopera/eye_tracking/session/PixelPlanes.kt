package br.com.marcelopera.eye_tracking.session

import java.nio.ByteBuffer

/** Handles planar/interleaved chroma and padded rows without changing source positions. */
internal fun copyPlane(source: ByteBuffer, sourceRow: Int, sourcePixel: Int,
                       target: ByteBuffer, targetRow: Int, targetPixel: Int, width: Int, height: Int) {
    val input = source.duplicate()
    val output = target.duplicate()
    val inputStart = input.position()
    val outputStart = output.position()
    for (y in 0 until height) for (x in 0 until width) {
        output.put(outputStart + y * targetRow + x * targetPixel,
            input.get(inputStart + y * sourceRow + x * sourcePixel))
    }
}
