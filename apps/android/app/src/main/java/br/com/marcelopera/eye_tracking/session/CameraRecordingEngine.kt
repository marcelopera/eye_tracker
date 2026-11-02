package br.com.marcelopera.eye_tracking.session

import android.content.Context
import android.hardware.camera2.CameraCharacteristics
import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaFormat
import android.media.MediaMuxer
import android.media.MediaExtractor
import android.util.Size
import androidx.camera.camera2.interop.Camera2CameraInfo
import androidx.camera.camera2.interop.ExperimentalCamera2Interop
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import br.com.marcelopera.eye_tracking.data.SessionEvent
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.withTimeout
import org.json.JSONObject
import java.io.File
import java.util.Collections
import java.util.concurrent.Executors

/** Explicitly assigns each encoded PTS from the corresponding camera image timestamp. */
@androidx.annotation.OptIn(ExperimentalCamera2Interop::class)
class CameraRecordingEngine(private val context: Context, private val lifecycleOwner: LifecycleOwner) : RecordingEngine {
    override fun start(outputFile: File): Recording {
        val handle = CameraRecording(outputFile)
        val future = ProcessCameraProvider.getInstance(context)
        future.addListener({
            try {
                val provider = future.get()
                handle.provider = provider
                if (handle.stopped) return@addListener
                val analysis = ImageAnalysis.Builder()
                    .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                    .setResolutionSelector(ResolutionSelector.Builder().setResolutionStrategy(
                        ResolutionStrategy(Size(640, 480), ResolutionStrategy.FALLBACK_RULE_CLOSEST_LOWER_THEN_HIGHER),
                    ).build()).build()
                handle.analysis = analysis
                provider.unbindAll()
                val camera = provider.bindToLifecycle(lifecycleOwner, CameraSelector.DEFAULT_FRONT_CAMERA, analysis)
                handle.realtime = Camera2CameraInfo.from(camera.cameraInfo).getCameraCharacteristic(
                    CameraCharacteristics.SENSOR_INFO_TIMESTAMP_SOURCE,
                ) == CameraCharacteristics.SENSOR_INFO_TIMESTAMP_SOURCE_REALTIME
                analysis.setAnalyzer(handle.executor) { image ->
                    try {
                        if (!handle.stopped) handle.encode(image)
                    } catch (error: Exception) {
                        handle.fail(error)
                    } finally {
                        image.close()
                    }
                }
            } catch (error: Exception) {
                handle.fail(error)
            }
        }, ContextCompat.getMainExecutor(context))
        return handle
    }

    private inner class CameraRecording(val output: File) : Recording {
        val executor = Executors.newSingleThreadExecutor()
        var provider: ProcessCameraProvider? = null
        var analysis: ImageAnalysis? = null
        @Volatile var stopped = false
        var realtime = false
        private val started = CompletableDeferred<Boolean>()
        private val finalized = CompletableDeferred<FinalizeInfo>()
        private val events = Collections.synchronizedList(mutableListOf<SessionEvent>())
        private val pending = mutableMapOf<Long, SessionEvent>()
        private var codec: MediaCodec? = null
        private var muxer: MediaMuxer? = null
        private var track = -1
        private var origin = 0L
        private var lastPts = -1L
        private var written = 0
        private var failed = false

        fun encode(image: ImageProxy) {
            if (codec == null) {
                origin = image.imageInfo.timestamp
                val format = MediaFormat.createVideoFormat("video/avc", image.width, image.height).apply {
                    setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatYUV420Flexible)
                    setInteger(MediaFormat.KEY_BIT_RATE, 2_000_000)
                    setInteger(MediaFormat.KEY_FRAME_RATE, 30)
                    setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, 1)
                    setInteger(MediaFormat.KEY_PROFILE, MediaCodecInfo.CodecProfileLevel.AVCProfileBaseline)
                }
                codec = MediaCodec.createEncoderByType("video/avc")
                requireNotNull(codec).configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
                requireNotNull(codec).start()
                muxer = MediaMuxer(output.absolutePath, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4)
                events += SessionEvent("camera_info_v1", System.nanoTime(), "frameTimeNanos",
                    JSONObject().put("rotation_degrees", image.imageInfo.rotationDegrees).put("mirrored", false)
                        .put("width", image.width).put("height", image.height).put("timestamp_source_realtime", realtime)
                        .put("pts_origin_sensor_ns", origin).toString())
            }
            val encoder = requireNotNull(codec)
            drain(false)
            val index = encoder.dequeueInputBuffer(0)
            if (index < 0) return // A dropped input has no encoded PTS and no fabricated correspondence.
            val pts = (image.imageInfo.timestamp - origin) / 1000
            check(pts > lastPts) { "Timestamp da câmera não crescente" }
            val target = requireNotNull(encoder.getInputImage(index)) { "Encoder sem entrada YUV" }
            for (plane in 0..2) {
                val width = if (plane == 0) image.width else image.width / 2
                val height = if (plane == 0) image.height else image.height / 2
                val source = image.planes[plane]
                val destination = target.planes[plane]
                copyPlane(source.buffer, source.rowStride, source.pixelStride,
                    destination.buffer, destination.rowStride, destination.pixelStride, width, height)
            }
            val clock = readClockSample()
            val eventNs = image.imageInfo.timestamp + clock.monotonicNanos -
                (clock.elapsedBeforeNanos + (clock.elapsedAfterNanos - clock.elapsedBeforeNanos) / 2)
            pending[pts] = SessionEvent("camera_frame_v1", eventNs, "frameTimeNanos",
                JSONObject().put("pts_us", pts).put("sensor_ns", image.imageInfo.timestamp)
                    .put("clock_error_ns", (clock.elapsedAfterNanos - clock.elapsedBeforeNanos) / 2 + 1000)
                    .toString())
            encoder.queueInputBuffer(index, 0, image.width * image.height * 3 / 2, pts, 0)
            lastPts = pts
            drain(false)
        }

        private fun drain(ending: Boolean) {
            val encoder = requireNotNull(codec)
            val info = MediaCodec.BufferInfo()
            val deadline = System.nanoTime() + 10_000_000_000L
            while (true) {
                val index = encoder.dequeueOutputBuffer(info, if (ending) 10_000 else 0)
                if (index == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                    check(track == -1)
                    track = requireNotNull(muxer).addTrack(encoder.outputFormat)
                    requireNotNull(muxer).start()
                } else if (index >= 0) {
                    if (info.size > 0 && info.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG == 0) {
                        check(track >= 0)
                        val event = requireNotNull(pending.remove(info.presentationTimeUs)) { "PTS sem imagem de origem" }
                        requireNotNull(muxer).writeSampleData(track, requireNotNull(encoder.getOutputBuffer(index)), info)
                        events += event
                        written++
                        started.complete(true)
                    }
                    val eos = info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0
                    encoder.releaseOutputBuffer(index, false)
                    if (eos) return
                } else if (!ending) return
                if (System.nanoTime() > deadline) error("Encoder não finalizou em dez segundos")
            }
        }

        fun fail(error: Exception) {
            failed = true
            stopped = true
            events += SessionEvent("camera_error_v1", System.nanoTime(), "frameTimeNanos", error.javaClass.simpleName)
            started.complete(false)
            // Cleanup is serialized with encoding, including failures during camera setup.
            if (!executor.isShutdown) executor.execute { finish() }
        }

        private fun finish() {
            if (finalized.isCompleted) return
            try {
                codec?.let { encoder ->
                    val index = encoder.dequeueInputBuffer(1_000_000)
                    check(index >= 0) { "Encoder não aceitou fim da gravação" }
                    encoder.queueInputBuffer(index, 0, 0, lastPts + 1, MediaCodec.BUFFER_FLAG_END_OF_STREAM)
                    drain(true)
                }
            } catch (_: Exception) { failed = true }
            try { codec?.stop() } catch (_: Exception) { failed = true }
            runCatching { codec?.release() }
            try { if (track >= 0) muxer?.stop() } catch (_: Exception) { failed = true }
            runCatching { muxer?.release() }
            if (!failed && written > 0) {
                try { verifyStoredTimestamps() } catch (_: Exception) { failed = true }
            }
            codec = null
            muxer = null
            started.complete(false)
            finalized.complete(FinalizeInfo(failed || written == 0, if (failed || written == 0) -1 else 0))
        }

        private fun verifyStoredTimestamps() {
            val extractor = MediaExtractor()
            try {
                extractor.setDataSource(output.absolutePath)
                extractor.selectTrack(0)
                synchronized(events) {
                    for (index in events.indices) {
                        val event = events[index]
                        if (event.name != "camera_frame_v1") continue
                        check(extractor.sampleTime >= 0) { "MP4 perdeu quadros codificados" }
                        val data = JSONObject(requireNotNull(event.data))
                        data.put("assigned_pts_us", data.getLong("pts_us"))
                        data.put("pts_us", extractor.sampleTime)
                        events[index] = event.copy(data = data.toString())
                        extractor.advance()
                    }
                    check(extractor.sampleTime == -1L) { "MP4 contém quadros sem correspondência" }
                }
            } finally { extractor.release() }
        }

        override suspend fun awaitStart(): Boolean = try {
            withTimeout(15_000) { started.await() }
        } catch (_: kotlinx.coroutines.TimeoutCancellationException) {
            fail(IllegalStateException("Câmera não produziu quadros")); false
        }

        override suspend fun stopAndAwaitFinalize(): FinalizeInfo {
            stopped = true
            analysis?.clearAnalyzer()
            if (!executor.isShutdown) executor.execute { finish() }
            return try { withTimeout(20_000) { finalized.await() } }
            catch (_: kotlinx.coroutines.TimeoutCancellationException) { FinalizeInfo(true, -1) }
        }

        override fun unbind() {
            stopped = true
            analysis?.clearAnalyzer()
            provider?.unbindAll()
            provider = null
            executor.shutdown()
        }
        override fun telemetry(): List<SessionEvent> = synchronized(events) { events.toList() }
    }
}
