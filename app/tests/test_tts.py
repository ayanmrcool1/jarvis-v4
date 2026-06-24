from tts_engine import JarvisTTS


tts = JarvisTTS(
    voice="am_adam",
    speed=1.0
)

tts.speak("Voice test is working.")
