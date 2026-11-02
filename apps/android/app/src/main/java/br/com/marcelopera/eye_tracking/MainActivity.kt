package br.com.marcelopera.eye_tracking

import android.Manifest
import android.app.AlertDialog
import android.widget.EditText
import android.widget.Toast
import br.com.marcelopera.eye_tracking.data.ApiClient
import org.json.JSONObject
import java.io.File
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Bundle
import android.view.Choreographer
import android.view.Gravity
import android.view.View
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import android.os.Build
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.common.PlaybackException
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import br.com.marcelopera.eye_tracking.data.SessionEvent
import br.com.marcelopera.eye_tracking.session.RenderedFrames
import androidx.activity.OnBackPressedCallback
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.net.toUri
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.createSavedStateHandle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import br.com.marcelopera.eye_tracking.data.SessionRepository
import br.com.marcelopera.eye_tracking.session.CameraRecordingEngine
import br.com.marcelopera.eye_tracking.session.RecordingEngineFactory
import br.com.marcelopera.eye_tracking.session.SessionController
import br.com.marcelopera.eye_tracking.session.SessionHost
import br.com.marcelopera.eye_tracking.session.SessionPhase
import br.com.marcelopera.eye_tracking.session.SessionResult
import br.com.marcelopera.eye_tracking.session.TargetDisplay
import br.com.marcelopera.eye_tracking.session.VideoPlayback
import br.com.marcelopera.eye_tracking.session.readClockSample
import br.com.marcelopera.eye_tracking.ui.CompletionScreen
import br.com.marcelopera.eye_tracking.ui.Destination
import br.com.marcelopera.eye_tracking.ui.IdentificationScreen
import br.com.marcelopera.eye_tracking.ui.PreparationScreen
import br.com.marcelopera.eye_tracking.ui.SessionEffect
import br.com.marcelopera.eye_tracking.ui.SessionUiState
import br.com.marcelopera.eye_tracking.ui.SessionViewModel
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlin.coroutines.resume

@androidx.annotation.OptIn(UnstableApi::class)
class MainActivity : AppCompatActivity(), SessionHost {

    private val viewModel: SessionViewModel by viewModels {
        viewModelFactory {
            initializer { SessionViewModel(createSavedStateHandle()) }
        }
    }

    private lateinit var root: FrameLayout
    private lateinit var controller: SessionController

    private var currentDestination: Destination? = null
    private var identificationScreen: IdentificationScreen? = null
    private var preparationScreen: PreparationScreen? = null
    private var completionScreen: CompletionScreen? = null
    private var sessionContent: FrameLayout? = null
    private val measurements = mutableListOf<SessionEvent>()
    override fun telemetry(): List<SessionEvent> = measurements.toList()

    private fun measured(name: String, time: Long, data: JSONObject) {
        measurements += SessionEvent(name, time, "frameTimeNanos", data.toString())
    }

    private val cameraPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        viewModel.onCameraPermissionResult(granted)
    }

    private val backCallback = object : OnBackPressedCallback(false) {
        override fun handleOnBackPressed() {
            when (viewModel.uiState.value.destination) {
                Destination.Collecting -> {
                    if (viewModel.uiState.value.phase == SessionPhase.Finalizing) return
                    if (controller.isActive) controller.interrupt() else viewModel.cancelPendingStart()
                }

                Destination.Preparation -> viewModel.backToIdentification()
                Destination.Completed -> viewModel.resetToIdentification()
                Destination.Identification -> Unit
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        root = FrameLayout(this).apply {
            setBackgroundColor(color(R.color.surface))
        }
        setContentView(root)
        applySystemInsets()

        controller = SessionController(
            store = SessionRepository(applicationContext.filesDir),
            listener = object : SessionController.Listener {
                override fun onPhase(token: Long, phase: SessionPhase) {
                    viewModel.onPhase(token, phase)
                }

                override fun onFinished(token: Long, result: SessionResult) {
                    viewModel.onFinished(token, result)
                    if (result is SessionResult.Completed || result is SessionResult.Interrupted) {
                        val id = result.sessionId
                        val directory = id?.let { File(filesDir, "sessoes/$it") }
                        if (directory != null && File(directory, "face.mp4").isFile && File(directory, "sessao.json").isFile) {
                            val prefs = getSharedPreferences("connection", MODE_PRIVATE)
                            val data = JSONObject().put("base", prefs.getString("base", "")).put("participant", prefs.getString("participant", "")).put("experiment", viewModel.uiState.value.experimentId)
                            val saved = runCatching { File(directory, "upload.json").writeText(data.toString()) }.isSuccess
                            if (saved && result is SessionResult.Completed) uploadSession(id)
                            if (!saved) Toast.makeText(this@MainActivity, "Não foi possível registrar o envio; os arquivos permanecem no aparelho.", Toast.LENGTH_LONG).show()
                        }
                    }
                }
            },
            recordingEngines = RecordingEngineFactory {
                CameraRecordingEngine(this@MainActivity, this@MainActivity)
            },
            clockSampleSource = ::readClockSample,
        )
        controller.attachHost(this)
        onBackPressedDispatcher.addCallback(this, backCallback)

        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                viewModel.uiState.collect { state ->
                    render(state)
                    backCallback.isEnabled = state.destination != Destination.Identification
                }
            }
        }
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                viewModel.effects.collect { effect ->
                    when (effect) {
                        SessionEffect.CheckCameraPermission -> requestCameraPermission()
                        is SessionEffect.StartSession -> {
                            if (viewModel.acceptsStart(effect.token)) {
                                // The state and effect collectors can run in either order.
                                // Attach the session screen before the controller uses it.
                                render(viewModel.uiState.value)
                                controller.start(effect.config, effect.token)
                            }
                        }
                    }
                }
            }
        }

        render(viewModel.uiState.value)
    }

    override fun onStart() {
        super.onStart()
        revalidateVideoAccess()
    }

    override fun onStop() {
        if (viewModel.uiState.value.destination == Destination.Collecting) {
            if (controller.isActive) controller.interrupt() else viewModel.cancelPendingStart()
        }
        super.onStop()
    }

    override fun onDestroy() {
        controller.onHostDestroyed()
        super.onDestroy()
    }

    override suspend fun showPreparing() {
        measurements.clear()
        check(!isInMultiWindowMode) { "A coleta precisa da tela inteira do aparelho." }
        @Suppress("DEPRECATION")
        val bounds = android.util.DisplayMetrics().also { windowManager.defaultDisplay.getRealMetrics(it) }
        measured("display_v1", System.nanoTime(), JSONObject()
            .put("screen_width_px", bounds.widthPixels).put("screen_height_px", bounds.heightPixels)
            .put("manufacturer", Build.MANUFACTURER).put("model", Build.MODEL)
            .put("sdk", Build.VERSION.SDK_INT))
        val content = ensureSessionContent()
        content.removeAllViews()
        content.setBackgroundColor(color(R.color.surface))
        content.addView(
            sessionMessage(
                getString(R.string.preparing_camera_title),
                getString(R.string.preparing_camera_description),
            ),
            FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT),
        )
    }

    override suspend fun showMarker(flashOn: Boolean): Long {
        val content = ensureSessionContent()
        content.removeAllViews()
        content.setBackgroundColor(color(if (flashOn) R.color.marker_light else R.color.marker_dark))
        return awaitNextFrame()
    }

    override suspend fun showTarget(x: Double, y: Double): TargetDisplay {
        val content = ensureSessionContent()
        content.removeAllViews()
        content.setBackgroundColor(color(R.color.calibration_background))

        val size = dp(20)
        val dot = View(this).apply {
            background = GradientDrawable().apply {
                shape = GradientDrawable.OVAL
                setColor(color(R.color.target))
            }
        }
        content.addView(dot, FrameLayout.LayoutParams(size, size))

        awaitNonEmptyLayout(content)
        dot.x = (x * content.width - size / 2.0).toFloat()
        dot.y = (y * content.height - size / 2.0).toFloat()
        val committed = Build.VERSION.SDK_INT >= 29 && content.isHardwareAccelerated
        val time = if (committed) awaitFrameCommit(content) else awaitNextFrame()
        val location = IntArray(2)
        content.getLocationOnScreen(location)
        return TargetDisplay(time, content.width, content.height,
            location[0] + dot.x.toDouble() + size / 2.0,
            location[1] + dot.y.toDouble() + size / 2.0, committed)
    }

    override suspend fun showRest(): Long {
        val content = ensureSessionContent()
        content.removeAllViews()
        content.setBackgroundColor(color(R.color.calibration_background))
        return awaitNextFrame()
    }

    override suspend fun playVideo(uri: String, onStarted: (Long) -> Unit): VideoPlayback = coroutineScope {
        val content = ensureSessionContent()
        content.removeAllViews()
        content.setBackgroundColor(Color.BLACK)
        val sourceTimes = withContext(Dispatchers.IO) {
            val extractor = android.media.MediaExtractor()
            try {
                extractor.setDataSource(this@MainActivity, uri.toUri(), null)
                val track = (0 until extractor.trackCount).first {
                    extractor.getTrackFormat(it).getString(android.media.MediaFormat.KEY_MIME)?.startsWith("video/") == true
                }
                extractor.selectTrack(track)
                val times = mutableSetOf<Long>()
                while (extractor.sampleTime >= 0) {
                    check(times.size < 100000) { "Estímulo excede o limite de quadros" }
                    times += extractor.sampleTime
                    extractor.advance()
                }
                times.sorted()
            } finally { extractor.release() }
        }
        measured("stimulus_timing_v1", System.nanoTime(), JSONObject().put("media_pts_us", org.json.JSONArray(sourceTimes)))
        val end = CompletableDeferred<Boolean>()
        val view = PlayerView(this@MainActivity).apply { useController = false }
        content.addView(view, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))
        var first = true
        var observing = true
        val factory = RenderedFrames(this@MainActivity) { pts, time ->
            if (observing) {
                measured("presented_frame_v1", time, JSONObject().put("media_time_us", pts))
                if (first) {
                    first = false
                    onStarted(time)
                    val surface = view.videoSurfaceView
                    val location = IntArray(2)
                    surface?.getLocationOnScreen(location)
                    val size = view.player?.videoSize
                    if (surface != null && size != null && surface.width > 0 && surface.height > 0) {
                        measured("stimulus_geometry_v1", time, JSONObject()
                            .put("x_px", location[0]).put("y_px", location[1])
                            .put("width_px", surface.width).put("height_px", surface.height)
                            .put("video_width_px", size.width).put("video_height_px", size.height)
                            .put("rotation_degrees", size.unappliedRotationDegrees))
                    }
                }
            }
        }
        val player = ExoPlayer.Builder(this@MainActivity, factory).build()
        player.setVideoFrameMetadataListener { mediaTimeUs, _, _, _ -> factory.metadata(mediaTimeUs) }
        view.player = player
        player.addListener(object : Player.Listener {
            override fun onPlaybackStateChanged(playbackState: Int) {
                if (playbackState == Player.STATE_ENDED) end.complete(true)
            }
            override fun onPlayerError(error: PlaybackException) { end.complete(false) }
        })
        try {
            player.setMediaItem(MediaItem.fromUri(uri))
            player.prepare()
            player.play()
            if (end.await()) VideoPlayback.Finished(System.nanoTime()) else VideoPlayback.Failed(-1, -1)
        } finally {
            observing = false
            view.player = null
            player.release()
            content.removeView(view)
        }
    }

    override suspend fun showFinalizing() {
        val content = ensureSessionContent()
        content.removeAllViews()
        content.setBackgroundColor(color(R.color.surface))
        content.addView(
            sessionMessage(getString(R.string.finalizing), null),
            FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT),
        )
    }

    private fun render(state: SessionUiState) {
        if (currentDestination != state.destination) {
            currentDestination = state.destination
            identificationScreen = null
            preparationScreen = null
            completionScreen = null
            if (state.destination != Destination.Collecting) sessionContent = null

            when (state.destination) {
                Destination.Identification -> {
                    val screen = IdentificationScreen(
                        context = this,
                        initialState = state,
                        onInputChanged = viewModel::onExperimentInputChanged,
                        onContinue = ::prepareExperiment,
                        onPending = ::showPendingUploads,
                    )
                    identificationScreen = screen
                    replaceContent(screen.root)
                }

                Destination.Preparation -> {
                    val screen = PreparationScreen(
                        context = this,
                        initialState = state,
                        onStart = viewModel::onStartClicked,
                        onChangeId = viewModel::backToIdentification,
                    )
                    preparationScreen = screen
                    replaceContent(screen.root)
                }

                Destination.Collecting -> {
                    val alreadyCreated = sessionContent != null
                    val content = ensureSessionScreen()
                    if (!alreadyCreated) when (state.phase) {
                        SessionPhase.Finalizing -> {
                            content.addView(
                                sessionMessage(getString(R.string.finalizing), null),
                                FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT),
                            )
                        }

                        else -> {
                            content.addView(
                                sessionMessage(
                                    getString(R.string.preparing_camera_title),
                                    getString(R.string.preparing_camera_description),
                                ),
                                FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT),
                            )
                        }
                    }
                }

                Destination.Completed -> {
                    val screen = CompletionScreen(
                        context = this,
                        initialState = state,
                        onBackToStart = viewModel::resetToIdentification,
                        onUpload = { state.sessionId?.let(::uploadSession) },
                    )
                    completionScreen = screen
                    replaceContent(screen.root)
                }
            }
        }

        when (state.destination) {
            Destination.Identification -> identificationScreen?.render(state)
            Destination.Preparation -> preparationScreen?.render(state)
            Destination.Completed -> completionScreen?.render(state)
            Destination.Collecting -> Unit
        }
    }

    private fun ensureSessionScreen(): FrameLayout {
        sessionContent?.let { return it }
        val content = FrameLayout(this).apply {
            setBackgroundColor(color(R.color.surface))
        }
        sessionContent = content
        replaceContent(content)
        return content
    }

    private fun ensureSessionContent(): FrameLayout = ensureSessionScreen()

    private fun replaceContent(view: View) {
        root.removeAllViews()
        root.addView(view, FrameLayout.LayoutParams(MATCH_PARENT, MATCH_PARENT))
    }

    private fun applySystemInsets() {
        ViewCompat.setOnApplyWindowInsetsListener(root) { view, insets ->
            val bars = insets.getInsets(
                WindowInsetsCompat.Type.systemBars() or
                    WindowInsetsCompat.Type.displayCutout() or
                    WindowInsetsCompat.Type.ime(),
            )
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            WindowInsetsCompat.CONSUMED
        }
    }

    private fun sessionMessage(title: String, detail: String?): View {
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(dp(28), dp(28), dp(28), dp(28))
            setBackgroundColor(color(R.color.surface))
        }
        box.addView(
            TextView(this).apply {
                text = title
                setTextSize(android.util.TypedValue.COMPLEX_UNIT_SP, 24f)
                setTextColor(color(R.color.on_surface))
                gravity = Gravity.CENTER
            },
        )
        if (detail != null) {
            box.addView(
                TextView(this).apply {
                    text = detail
                    setTextSize(android.util.TypedValue.COMPLEX_UNIT_SP, 16f)
                    setTextColor(color(R.color.on_surface_variant))
                    gravity = Gravity.CENTER
                },
            )
        }
        return box
    }


    private fun prepareExperiment() {
        val code = viewModel.uiState.value.experimentInput.trim()
        if (code.isEmpty()) { viewModel.continueFromIdentification(); return }
        val prefs = getSharedPreferences("connection", MODE_PRIVATE)
        val layout = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(24), 0, dp(24), 0) }
        val address = EditText(this).apply { hint = "Endereço do servidor (ex.: http://192.168.1.10:8080)"; setText(prefs.getString("base", "")); setSingleLine() }
        val participant = EditText(this).apply { hint = "Código pseudônimo do participante"; setText(prefs.getString("participant", "")); setSingleLine() }
        layout.addView(address); layout.addView(participant)
        AlertDialog.Builder(this).setTitle("Conectar ao experimento").setView(layout)
            .setNegativeButton("Cancelar", null).setPositiveButton("Consultar") { _, _ ->
                val base = address.text.toString().trim().trimEnd('/')
                val person = participant.text.toString().trim()
                val parsed = runCatching { java.net.URI(base) }.getOrNull()
                if (parsed == null || parsed.scheme !in listOf("http", "https") || parsed.host == null || parsed.userInfo != null || parsed.path.orEmpty() !in listOf("", "/") || parsed.query != null || parsed.fragment != null || person.isEmpty() || person.length > 200) {
                    Toast.makeText(this, "Informe um endereço válido e o código do participante.", Toast.LENGTH_LONG).show()
                } else {
                    val progress = AlertDialog.Builder(this).setMessage("Consultando experimento e baixando vídeo…").setCancelable(false).create()
                    progress.show()
                    lifecycleScope.launch {
                        val result = withContext(Dispatchers.IO) { runCatching {
                            val protocol = JSONObject(assets.open("protocol.json").bufferedReader().use { it.readText() })
                            ApiClient(base).fetchExperiment(code, protocol, filesDir)
                        } }
                        progress.dismiss()
                        result.onSuccess { (id, uri) ->
                            prefs.edit().putString("base", base).putString("participant", person).apply()
                            viewModel.onExperimentInputChanged(id)
                            viewModel.continueFromIdentification()
                            viewModel.onVideoSelected(uri)
                        }.onFailure { Toast.makeText(this@MainActivity, it.message ?: "Falha de conexão.", Toast.LENGTH_LONG).show() }
                    }
                }
            }.show()
    }

    private fun showPendingUploads() {
        val sessions = File(filesDir, "sessoes").listFiles()?.filter {
            it.isDirectory && File(it, "upload.json").isFile && !File(it, "recebida.json").isFile
        }?.sortedBy { it.name }.orEmpty()
        if (sessions.isEmpty()) {
            Toast.makeText(this, "Nenhuma coleta pendente.", Toast.LENGTH_SHORT).show()
            return
        }
        AlertDialog.Builder(this).setTitle("Coletas pendentes")
            .setItems(sessions.map { it.name }.toTypedArray()) { _, index -> uploadSession(sessions[index].name) }
            .setNegativeButton("Cancelar", null).show()
    }

    private fun uploadSession(id: String) {
        val progress = AlertDialog.Builder(this).setMessage("Enviando coleta…").setCancelable(false).create()
        progress.show()
        lifecycleScope.launch {
            val result = withContext(Dispatchers.IO) { runCatching {
                val directory = File(filesDir, "sessoes/$id")
                val data = JSONObject(File(directory, "upload.json").readText())
                ApiClient(data.getString("base")).upload(data.getString("experiment"), data.getString("participant"), id, directory).also {
                    File(directory, "recebida.json").writeText(JSONObject().put("id", it).toString())
                }
            } }
            progress.dismiss()
            result.onSuccess { AlertDialog.Builder(this@MainActivity).setMessage("Coleta recebida pelo servidor. ID: $it. Os arquivos permanecem no aparelho.").setPositiveButton("OK", null).show() }
                .onFailure { AlertDialog.Builder(this@MainActivity).setMessage("Falha no envio: ${it.message}. Os arquivos permanecem no aparelho; tente novamente.").setPositiveButton("OK", null).show() }
        }
    }

    private fun requestCameraPermission() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) ==
            PackageManager.PERMISSION_GRANTED
        ) {
            viewModel.onCameraPermissionResult(true)
        } else {
            cameraPermission.launch(Manifest.permission.CAMERA)
        }
    }

    private fun revalidateVideoAccess() {
        val state = viewModel.uiState.value
        val uri = state.videoUri ?: return
        if (state.destination != Destination.Preparation) return
        lifecycleScope.launch {
            val accessible = withContext(Dispatchers.IO) { canRead(uri.toUri()) }
            viewModel.onVideoAccessChecked(uri, accessible)
        }
    }

    private fun canRead(uri: Uri): Boolean = try {
        contentResolver.openAssetFileDescriptor(uri, "r")?.use { true } ?: false
    } catch (_: Exception) {
        false
    }

    @androidx.annotation.RequiresApi(29)
    private suspend fun awaitFrameCommit(view: View): Long = suspendCancellableCoroutine { continuation ->
        val observer = view.viewTreeObserver
        val callback = Runnable { if (continuation.isActive) continuation.resume(System.nanoTime()) }
        observer.registerFrameCommitCallback(callback)
        continuation.invokeOnCancellation { if (observer.isAlive) observer.unregisterFrameCommitCallback(callback) }
        view.invalidate()
    }

    private suspend fun awaitNextFrame(): Long =
        suspendCancellableCoroutine { continuation ->
            val callback = Choreographer.FrameCallback { frameTimeNanos ->
                if (continuation.isActive) continuation.resume(frameTimeNanos)
            }
            Choreographer.getInstance().postFrameCallback(callback)
            continuation.invokeOnCancellation {
                Choreographer.getInstance().removeFrameCallback(callback)
            }
        }

    private suspend fun awaitNonEmptyLayout(view: View) {
        if (view.isLaidOut && !view.isLayoutRequested && view.width > 0 && view.height > 0) return
        suspendCancellableCoroutine<Unit> { continuation ->
            val listener = object : View.OnLayoutChangeListener {
                override fun onLayoutChange(
                    changed: View, left: Int, top: Int, right: Int, bottom: Int,
                    oldLeft: Int, oldTop: Int, oldRight: Int, oldBottom: Int,
                ) {
                    if (right <= left || bottom <= top) return
                    changed.removeOnLayoutChangeListener(this)
                    if (continuation.isActive) continuation.resume(Unit)
                }
            }
            view.addOnLayoutChangeListener(listener)
            continuation.invokeOnCancellation { view.removeOnLayoutChangeListener(listener) }
        }
    }

    private fun color(resource: Int): Int = ContextCompat.getColor(this, resource)

    private fun dp(value: Int): Int =
        (value * resources.displayMetrics.density + 0.5f).toInt()

    private sealed interface PlaybackEnd {
        data object Completed : PlaybackEnd
        data class Failed(val what: Int, val extra: Int) : PlaybackEnd
    }
}
