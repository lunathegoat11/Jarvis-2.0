package com.lunathegoat11.jarvis

import android.content.Context
import android.speech.tts.TextToSpeech
import java.util.Locale

/** Reads replies aloud with Android's built-in voice, and tidies text first. */
class Speech(context: Context, private val settings: Settings) {
    private var tts: TextToSpeech? = null
    private var ready = false

    init {
        tts = TextToSpeech(context) { status ->
            if (status == TextToSpeech.SUCCESS) {
                tts?.language = Locale.getDefault()
                ready = true
            }
        }
    }

    fun say(text: String) {
        if (!settings.speakReplies) return
        val clean = cleanForSpeech(text)
        if (clean.isBlank()) return
        tts?.setSpeechRate(settings.voiceSpeed)
        tts?.speak(clean, TextToSpeech.QUEUE_FLUSH, null, "jarvis")
    }

    fun stop() {
        tts?.stop()
    }

    fun shutdown() {
        tts?.shutdown()
    }

    companion object {
        private val EMOJI = Regex("[\\x{1F000}-\\x{1FAFF}\\x{2600}-\\x{27BF}\\x{FE0F}\\x{200D}]")

        /** Removes think tags some models wrap their reasoning in. */
        fun stripThink(text: String): String =
            text.replace(Regex("(?s)<think>.*?</think>"), "").trim()

        /** Strips markdown symbols, code, emoji and raw links so they aren't read out. */
        fun cleanForSpeech(input: String): String {
            var t = input
            t = t.replace(Regex("(?s)```.*?```"), " I've left the code out. ")
            t = t.replace(Regex("`([^`]*)`"), "$1")
            t = t.replace(Regex("!?\\[([^\\]]*)]\\([^)]*\\)"), "$1")
            t = t.replace(Regex("https?://\\S+|www\\.\\S+"), "the link")
            t = t.replace(Regex("(?m)^\\s{0,3}#{1,6}\\s*"), "")
            t = t.replace(Regex("(?m)^\\s*(?:[-*+•]|\\d+[.)])\\s+"), "")
            t = t.replace(Regex("(\\*{1,3}|_{2,3}|~~)(\\S.*?\\S|\\S)\\1"), "$2")
            t = t.replace(Regex("[*#~^<>{}\\\\|]"), " ")
            t = EMOJI.replace(t, "")
            return t.replace(Regex("\\s{2,}"), " ").trim()
        }
    }
}
