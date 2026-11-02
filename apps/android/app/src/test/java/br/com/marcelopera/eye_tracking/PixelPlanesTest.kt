package br.com.marcelopera.eye_tracking

import br.com.marcelopera.eye_tracking.session.copyPlane
import java.nio.ByteBuffer
import org.junit.Assert.assertEquals
import org.junit.Test

class PixelPlanesTest {
    @Test fun paddedInterleavedChromaIsCopiedWithoutChangingBufferPositions() {
        val source = ByteBuffer.wrap(byteArrayOf(99,1,9,2,9,8,8,3,9,4,9))
        source.position(1)
        val target = ByteBuffer.allocate(12)
        target.position(2)
        copyPlane(source, 6, 2, target, 4, 1, 2, 2)
        assertEquals(1, target.get(2).toInt())
        assertEquals(2, target.get(3).toInt())
        assertEquals(3, target.get(6).toInt())
        assertEquals(4, target.get(7).toInt())
        assertEquals(1, source.position())
        assertEquals(2, target.position())
    }
}
