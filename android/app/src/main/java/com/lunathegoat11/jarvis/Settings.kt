package com.lunathegoat11.jarvis

import android.content.Context

/** Jarvis's settings on Android, saved to the app's private storage. */
class Settings(context: Context) {
    private val prefs = context.getSharedPreferences("jarvis", Context.MODE_PRIVATE)

    var provider: String
        get() = prefs.getString("provider", "") ?: ""
        set(v) = prefs.edit().putString("provider", v).apply()

    var apiKey: String
        get() = prefs.getString("api_key", "") ?: ""
        set(v) = prefs.edit().putString("api_key", v).apply()

    var model: String
        get() = prefs.getString("model", "") ?: ""
        set(v) = prefs.edit().putString("model", v).apply()

    var voiceSpeed: Float
        get() = prefs.getFloat("voice_speed", 1.0f)
        set(v) = prefs.edit().putFloat("voice_speed", v).apply()

    var speakReplies: Boolean
        get() = prefs.getBoolean("speak_replies", true)
        set(v) = prefs.edit().putBoolean("speak_replies", v).apply()

    val configured: Boolean
        get() = provider.isNotEmpty() && (provider == "ollama" || apiKey.isNotEmpty())

    /** Base URL and key for the chosen provider's OpenAI-compatible API. */
    fun baseUrl(): String = when (provider) {
        "nvidia" -> "https://integrate.api.nvidia.com/v1"
        "ollama" -> prefs.getString("base_url", "http://10.0.2.2:11434/v1") ?: ""
        "anthropic" -> "https://api.anthropic.com/v1"  // handled specially in Brain
        else -> prefs.getString("base_url", "") ?: ""
    }

    fun defaultModel(): String = when {
        model.isNotEmpty() -> model
        provider == "nvidia" -> "meta/llama-4-maverick-17b-128e-instruct"
        provider == "anthropic" -> "claude-opus-4-8"
        provider == "ollama" -> "llama3.2"
        else -> ""
    }
}
