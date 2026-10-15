package com.lunathegoat11.jarvis

import android.Manifest
import android.annotation.SuppressLint
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.RecognitionListener
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.app.Activity
import org.json.JSONArray
import org.json.JSONObject
import kotlin.concurrent.thread

/** The Jarvis phone app: the orb page, listening, the AI, and speaking back. */
class MainActivity : Activity() {

    private lateinit var web: WebView
    private lateinit var settings: Settings
    private lateinit var speech: Speech
    private var recognizer: SpeechRecognizer? = null
    private val brain by lazy { Brain(settings, JarvisAccessibilityService.actions()) }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        settings = Settings(this)
        speech = Speech(this, settings)

        web = WebView(this)
        web.settings.javaScriptEnabled = true
        web.settings.domStorageEnabled = true
        web.setBackgroundColor(0xFF04060A.toInt())
        web.addJavascriptInterface(Bridge(), "JarvisAndroid")
        web.loadUrl("file:///android_asset/app.html")
        setContentView(web)

        requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 1)
    }

    override fun onDestroy() {
        speech.shutdown()
        recognizer?.destroy()
        super.onDestroy()
    }

    private fun send(event: JSONObject) {
        runOnUiThread { web.evaluateJavascript("window.jarvis && window.jarvis.receive($event)", null) }
    }

    private fun state(name: String) = send(JSONObject().put("type", "state").put("state", name))

    // ---- messages from the page ----------------------------------------------

    inner class Bridge {
        @JavascriptInterface
        fun post(json: String) {
            val msg = JSONObject(json)
            when (msg.getString("type")) {
                "ready" -> sendInit()
                "talk" -> runOnUiThread { startListening() }
                "setup" -> saveSetup(msg)
                "set" -> saveSetting(msg)
                "open_accessibility" -> openSettings(android.provider.Settings.ACTION_ACCESSIBILITY_SETTINGS)
                "open_overlay" -> openOverlaySettings()
            }
        }
    }

    private fun sendInit() {
        val settingsJson = JSONObject()
            .put("voice", "")
            .put("voice_speed", settings.voiceSpeed)
            .put("speak_replies", settings.speakReplies)
            .put("clean_dictation", true)
            .put("vocabulary", "")
        val info = JSONObject()
            .put("provider", settings.provider)
            .put("model", settings.defaultModel())
            .put("vision_model", settings.defaultModel())
            .put("engine", "android")
            .put("hint", "Tap the orb and talk")
        if (!settings.configured) info.put("setup", "Choose the AI that powers Jarvis.")
        send(
            JSONObject().put("type", "init")
                .put("settings", settingsJson)
                .put("voices", JSONArray())
                .put("info", info)
        )
    }

    private fun saveSetup(msg: JSONObject) {
        val provider = msg.optString("provider")
        val key = msg.optString("key").trim()
        val model = msg.optString("model").trim()
        if (provider != "ollama" && key.isEmpty()) {
            send(JSONObject().put("type", "setup_error").put("text", "Paste your API key first."))
            return
        }
        if (provider == "ollama" && model.isEmpty()) {
            send(JSONObject().put("type", "setup_error").put("text", "Type the model name."))
            return
        }
        settings.provider = provider
        settings.apiKey = key
        settings.model = model
        send(JSONObject().put("type", "setup_done"))
        runOnUiThread { web.evaluateJavascript("document.getElementById('setup').hidden = true", null) }
    }

    private fun openSettings(action: String) {
        runOnUiThread {
            startActivity(Intent(action).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        }
    }

    private fun openOverlaySettings() {
        runOnUiThread {
            val intent = Intent(
                android.provider.Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                android.net.Uri.parse("package:$packageName"),
            ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            startActivity(intent)
            // Start the bubble; it appears once the permission is granted.
            startService(Intent(this, BubbleService::class.java))
        }
    }

    private fun saveSetting(msg: JSONObject) {
        when (msg.getString("key")) {
            "voice_speed" -> settings.voiceSpeed = msg.getDouble("value").toFloat()
            "speak_replies" -> settings.speakReplies = msg.getBoolean("value")
        }
    }

    // ---- listening and answering ---------------------------------------------

    private fun startListening() {
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO)
            != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 1)
            return
        }
        if (!settings.configured) {
            sendInit()
            return
        }
        speech.stop()
        recognizer?.destroy()
        recognizer = SpeechRecognizer.createSpeechRecognizer(this).apply {
            setRecognitionListener(Listener())
        }
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
        }
        state("listening")
        recognizer?.startListening(intent)
    }

    private inner class Listener : RecognitionListener {
        override fun onResults(results: Bundle?) {
            val text = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()
            if (text.isNullOrBlank()) {
                send(JSONObject().put("type", "step").put("title", "Jarvis").put("text", "Didn't catch that."))
                state("idle")
                return
            }
            send(JSONObject().put("type", "heard").put("text", text))
            state("thinking")
            answer(text)
        }

        override fun onError(error: Int) {
            state("idle")
        }

        override fun onReadyForSpeech(params: Bundle?) {}
        override fun onBeginningOfSpeech() {}
        override fun onRmsChanged(rmsdB: Float) {
            send(JSONObject().put("type", "level").put("value", ((rmsdB + 2) / 12f).coerceIn(0f, 1f)))
        }
        override fun onBufferReceived(buffer: ByteArray?) {}
        override fun onEndOfSpeech() {}
        override fun onPartialResults(partialResults: Bundle?) {}
        override fun onEvent(eventType: Int, params: Bundle?) {}
    }

    private fun answer(command: String) {
        thread {
            brain.run(command) { reply ->
                send(JSONObject().put("type", "reply").put("text", Speech.cleanForSpeech(reply)))
                runOnUiThread { speech.say(reply) }
                state("idle")
            }
        }
    }
}
