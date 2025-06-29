import streamlit as st
import threading
import tempfile
import os
import webbrowser
from datetime import datetime
import sounddevice as sd
import vosk
import json
import queue
import pyttsx3
import numpy as np
import wave
import re

from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.prompts import PromptTemplate
from langchain_ollama import OllamaLLM
from langchain_community.callbacks import StreamlitCallbackHandler
# from googletrans import Translator ❌
from deep_translator import GoogleTranslator


# ========== CONFIG ==========
st.set_page_config(page_title="AIRA", page_icon="🎤", layout="wide")

st.sidebar.title("⚙️ Assistant Settings")

voice_rate = st.sidebar.slider("🗣️ TTS Speed", 100, 250, 160)
preferred_language = st.sidebar.selectbox("🌍 Preferred Language", ["en", "hi", "kn", "ml", "te", "ta"])
enable_translation = st.sidebar.checkbox("🌐 Auto-Translate to English", value=True)
wake_word = st.sidebar.text_input("🔊 Wake Word", value="hey aira")

llm = OllamaLLM(model="deepseek-r1:8b", streaming=True)

# === TTS Setup ===
tts_engine = pyttsx3.init()
tts_engine.setProperty("rate", voice_rate)

def speak(text):
    def _speak():
        tts_engine.say(text)
        tts_engine.runAndWait()
    threading.Thread(target=_speak).start()

# === Clean AI Output ===
def clean_ai_output(response):
    return re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()

# === Chat History ===
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = ChatMessageHistory()

# === Load Vosk Model ===
MODEL_PATH = "models/vosk-model-small-en-us-0.15"
if not os.path.exists(MODEL_PATH):
    st.error("Vosk model not found. Download from https://alphacephei.com/vosk/models and place it in 'models/'.")
    st.stop()
model = vosk.Model(MODEL_PATH)

def record_audio(duration=5):
    fs = 16000
    st.write("🎙️ Listening...")
    audio = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='int16')
    sd.wait()
    return audio

def listen_vosk():
    audio = record_audio()
    rec = vosk.KaldiRecognizer(model, 16000)
    audio_bytes = audio.tobytes()
    rec.AcceptWaveform(audio_bytes)
    result = json.loads(rec.Result())
    text = result.get("text", "").strip()

    if text:
        try:
            if enable_translation and preferred_language != "en":
                translated = GoogleTranslator(source='auto', target='en').translate(text)
                st.success(f"🗣️ You said: {text} → 🇬🇧 {translated}")
                return translated.lower()
            else:
                st.success(f"🗣️ You said: {text}")
                return text.lower()
        except Exception as e:
            st.warning(f"Translation failed: {e}")
            return text.lower()
    else:
        st.error("🤖 Didn't catch that.")
        return None


# === Prompt Template ===
prompt = PromptTemplate(
    input_variables=["chat_history", "question"],
    template="""
    You are Aira, a friendly and helpful voice assistant. Respond clearly and kindly.
    Previous Conversation:
    {chat_history}
    User: {question}
    AI:
    """
)

def clean_ai_output(response):
    return re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()


def run_chain(question):
    chat_history_str = "\n".join([
        f"{msg.type.capitalize()}: {msg.content}" for msg in st.session_state.chat_history.messages
    ])

    prompt_input = prompt.format(chat_history=chat_history_str, question=question)

    with st.spinner("🤖 Thinking..."):
        raw_response = llm.invoke(prompt_input)

    cleaned_response = clean_ai_output(str(raw_response))

    # Debugging print (optional)
    print("=== Prompt sent to LLM ===")
    print(prompt_input)
    print("=== Raw response ===")
    print(raw_response)

    st.session_state.chat_history.add_user_message(question)
    st.session_state.chat_history.add_ai_message(cleaned_response)

    speak(cleaned_response)  # 🔊 Speak the response
    return cleaned_response




# === Actions ===
def handle_actions(query):
    query = query.lower()
    if "open youtube" in query:
        webbrowser.open("https://www.youtube.com")
        return "Opening YouTube."
    elif "open google" in query:
        webbrowser.open("https://www.google.com")
        return "Opening Google."
    elif "open whatsapp" in query:
        webbrowser.open("https://web.whatsapp.com")
        return "Opening WhatsApp Web."
    elif "open gmail" in query:
        webbrowser.open("https://mail.google.com")
        return "Opening Gmail."
    elif "open github" in query:
        webbrowser.open("https://github.com")
        return "Opening GitHub."
    elif "open stackoverflow" in query:
        webbrowser.open("https://stackoverflow.com")
        return "Opening Stack Overflow."
    elif "what time is it" in query or "current time" in query:
        return f"It's {datetime.now().strftime('%I:%M %p')}."
    elif "what is the date" in query or "today's date" in query:
        return f"Today's date is {datetime.now().strftime('%A, %B %d, %Y')}."
    elif "open notepad" in query:
        os.system("notepad")
        return "Opening Notepad."
    elif "open calculator" in query:
        os.system("calc")
        return "Opening Calculator."
    elif "shutdown" in query:
        os.system("shutdown /s /t 1")
        return "Shutting down the system."
    elif "restart" in query:
        os.system("shutdown /r /t 1")
        return "Restarting the system."
    elif "search for" in query:
        search_term = query.split("search for")[-1].strip()
        webbrowser.open(f"https://www.google.com/search?q={search_term}")
        return f"Searching Google for {search_term}."
    return None

# === Wake Word Detection ===
def wait_for_wake_word(trigger=None):
    if trigger is None:
        trigger = wake_word.lower()
    q = queue.Queue()
    def callback(indata, frames, time, status):
        q.put(bytes(indata))
    with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16', channels=1, callback=callback):
        rec = vosk.KaldiRecognizer(model, 16000)
        while True:
            data = q.get()
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                text = result.get("text", "")
                if trigger in text:
                    return True

# === UI ===
st.markdown("<h1 style='text-align: center;'>🤖 AIRA </h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center;'>🎙️ Say 'Hey Aira' to activate or press button</p>", unsafe_allow_html=True)
st.divider()

if st.button("🎤 Manual Start Listening"):
    query = listen_vosk()
    if query:
         st.session_state.transcribed_query = query  # Save to state



if st.button("🔊 Start Wake Word Listener"):
    st.warning(f"Listening for '{wake_word}'... speak now")
    if wait_for_wake_word():
        st.success("✅ Wake word detected! Listening now...")
        query = listen_vosk()
        if query:
            st.session_state.transcribed_query = query  # Save to state

st.markdown("### ✏️ Edit or Submit Your Query")

user_input = st.text_input("Your Query", value=st.session_state.get("transcribed_query", ""), key="editable_input")

if st.button("🚀 Submit Query"):
    if user_input:
        action_response = handle_actions(user_input)
        if action_response:
            st.success(f"**Action:** {action_response}")
            speak(action_response)
        else:
            ai_response = run_chain(user_input)
            st.success(f"**User:** {user_input}")
            st.info(f"**AI:** {ai_response}")
            speak(ai_response)
    else:
        st.warning("Please enter something before submitting.")


# === Chat History ===
st.markdown("<h3 style='color: yellow;'>📝 Chat History</h3>", unsafe_allow_html=True)
for msg in st.session_state.chat_history.messages:
    if msg.type == "user":
        st.write(f"🗣️ **You**: {msg.content}")
    else:
        st.write(f"🤖 **AI**: {msg.content}")

# === Export Chat ===
if st.button("💾 Export Chat History"):
    filename = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(filename, "w", encoding="utf-8") as f:
        for msg in st.session_state.chat_history.messages:
            f.write(f"{msg.type.upper()}: {msg.content}\n")
    st.success(f"Chat history saved as {filename}")
