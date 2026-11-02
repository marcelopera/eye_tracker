package br.com.marcelopera.eye_tracking

import br.com.marcelopera.eye_tracking.session.RenderTimestamps
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class RenderTimestampsTest {
    @Test fun codecStreamOffsetIsRemovedOnlyWithRendererMetadataAndActualCallback() {
        val times = RenderTimestamps()
        times.output(1, 1_000_000_040_000L)
        times.metadata(40_000)
        times.release(1, true)
        assertEquals(40_000L, times.rendered(1_000_000_040_000L))
        assertNull(times.rendered(1_000_000_040_000L))
    }
    @Test fun droppedBuffersMissingMetadataAndFlushNeverInventRenderEvents() {
        val times = RenderTimestamps()
        times.output(1, 100)
        times.release(1, false)
        assertNull(times.rendered(100))
        times.output(2, 200)
        times.release(2, true)
        assertNull(times.rendered(200))
        times.output(3, 300)
        times.metadata(30)
        times.release(3, true)
        times.clear()
        assertNull(times.rendered(300))
    }
}
