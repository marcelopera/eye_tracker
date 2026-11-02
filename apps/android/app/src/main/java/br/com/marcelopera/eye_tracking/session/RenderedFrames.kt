package br.com.marcelopera.eye_tracking.session

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.media.MediaCodec
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.DefaultRenderersFactory
import androidx.media3.exoplayer.mediacodec.DefaultMediaCodecAdapterFactory
import androidx.media3.exoplayer.mediacodec.MediaCodecAdapter

/** Observes codec output-surface rendering, rather than player position or planned releases. */
@androidx.annotation.OptIn(UnstableApi::class)
class RenderedFrames(context: Context, private val onFrame: (Long, Long) -> Unit) : DefaultRenderersFactory(context) {
    private var activeAdapter: ObservedAdapter? = null
    fun metadata(mediaTimeUs: Long) { activeAdapter?.times?.metadata(mediaTimeUs) }
    private val delegate = DefaultMediaCodecAdapterFactory(context)
    override fun getCodecAdapterFactory(): MediaCodecAdapter.Factory = MediaCodecAdapter.Factory { configuration ->
        val adapter = delegate.createAdapter(configuration)
        if (configuration.format.sampleMimeType?.startsWith("video/") == true) ObservedAdapter(adapter).also { activeAdapter = it } else adapter
    }
    private inner class ObservedAdapter(private val adapter: MediaCodecAdapter) : MediaCodecAdapter by adapter {
        val times = RenderTimestamps()
        private var downstream: MediaCodecAdapter.OnFrameRenderedListener? = null
        private var downstreamHandler: Handler? = null
        private val handler = Handler(Looper.getMainLooper())
        init { install() }
        private fun install() {
            adapter.setOnFrameRenderedListener({ _, pts, nanoTime ->
                if (pts >= 0 && pts != Long.MAX_VALUE && nanoTime > 0) times.rendered(pts)?.let { onFrame(it, nanoTime) }
                downstream?.let { listener -> downstreamHandler?.post { listener.onFrameRendered(this, pts, nanoTime) } }
            }, handler)
        }
        override fun setOnFrameRenderedListener(listener: MediaCodecAdapter.OnFrameRenderedListener, handler: Handler) {
            downstream = listener
            downstreamHandler = handler
            install()
        }
        override fun dequeueOutputBufferIndex(info: MediaCodec.BufferInfo): Int {
            val index = adapter.dequeueOutputBufferIndex(info)
            if (index >= 0) times.output(index, info.presentationTimeUs)
            return index
        }
        override fun releaseOutputBuffer(index: Int, render: Boolean) {
            times.release(index, render)
            adapter.releaseOutputBuffer(index, render)
        }
        override fun releaseOutputBuffer(index: Int, renderTimeStampNs: Long) {
            times.release(index, true)
            adapter.releaseOutputBuffer(index, renderTimeStampNs)
        }
        override fun flush() { adapter.flush(); times.clear(); install() }
        override fun release() { adapter.release(); times.clear() }
    }
}
