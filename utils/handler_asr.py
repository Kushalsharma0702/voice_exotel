import base64
import tempfile
from pydub import AudioSegment
from sarvamai import SarvamAI
from sarvamai import AsyncSarvamAI, AudioOutput
from fastapi import Body


class SarvamHandler:
    def __init__(self, api_key):
        self.client = SarvamAI(api_subscription_key=api_key)

    def _slin_to_wav_file(self, slin_bytes) -> str:
        audio = AudioSegment(
            slin_bytes,
            sample_width=2,  # 16-bit PCM
            frame_rate=8000,
            channels=1
        )
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            audio.export(f.name, format="wav")
            return f.name

    def transcribe_from_payload(self, audio_buffer: bytes) -> str:
        print("[Sarvam REST] 🎙️ Converting SLIN base64 to WAV")

        # Convert SLIN (raw 8kHz PCM mono) to WAV
        audio = AudioSegment(
            data=audio_buffer,
            sample_width=2,  # 16-bit PCM
            frame_rate=8000,
            channels=1
        )
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            audio.export(f.name, format="wav")
            f.seek(0)
            print("[Sarvam REST] 🚀 Sending WAV to Sarvam API")

            # Call Sarvam REST API directly
            response = self.client.speech_to_text.transcribe(
                file=f,
                model="saarika:v2.5",
                language_code="unknown"  # Make sure this matches your subscription
            )
            print("[Sarvam REST] 📝 Transcript Arun:", response.transcript)
            return response.transcript
    
    async def synthesize_tts_end(self, text: str,lang: str) -> bytes:
        print(f"[Sarvam TTS] 🔁 Starting text-to-speech greetinggreeting: {text}")
        print(f"[Sarvam TTS] 🔁 Starting text-to-speech synthesis lang: {lang}")

        # Step 1: Translate text (e.g., English → Tamil)
       
        # Step 2: TTS generation
        try:
            response = self.client.text_to_speech.convert(
                text=text,
                target_language_code=lang,
                speaker="anushka",
                model="bulbul:v2"
            )
            audio_base64 = response.audios[0] if response.audios else None
            if not audio_base64:
                print("[Sarvam TTS] ❌ No audio returned from TTS.")
                return None
            audio_bytes = base64.b64decode(audio_base64)
        except Exception as e:
            print(f"[Sarvam TTS] ❌ TTS generation failed: {e}")
            return None
         # Step 3: Re-encode to SLIN WAV (8kHz mono, 16-bit)
        try:
            print("[Sarvam TTS] 🎧 Re-encoding to SLIN 8kHz mono")
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as mp3_file:
                mp3_file.write(audio_bytes)
                mp3_path = mp3_file.name

            audio = AudioSegment.from_file(mp3_path)
            wav_audio = audio.set_frame_rate(8000).set_channels(1).set_sample_width(2)  # SLIN: 8kHz mono 16-bit

            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
                wav_audio.export(f.name, format="wav")
                f.seek(0)
                final_bytes = f.read()

            if not final_bytes:
                print("[Sarvam TTS] ❌ Final WAV bytes are empty.")
                return None

            print(f"[Sarvam TTS] ✅ Audio ready (size: {len(final_bytes)} bytes)")
            return final_bytes

        except Exception as e:
            print(f"[Sarvam TTS] ❌ Error during WAV conversion: {e}")
            return None
   
    async def synthesize_tts(self, text: str,lang: str) -> bytes:
        print("[Sarvam TTS] 🔁 Starting text-to-speech synthesis")

        # Step 1: Translate text (e.g., English → Tamil)
        try:
            translate_speak = self.client.text.translate(
                input=text,
                language_code=lang,
                model="sarvam-translate:v1"
            )
            speak = translate_speak.translated_text
            print(f"[Sarvam TTS] 🔤 Translated text: {speak}")
        except Exception as e:
            print(f"[Sarvam TTS] ❌ Translation failed: {e}")
            return None

        # Step 2: TTS generation
        try:
            response = self.client.text_to_speech.convert(
                text=speak,
                language_code=lang_code,
                speaker="anushka",
                model="bulbul:v2"
            )
            audio_base64 = response.audios[0] if response.audios else None
            if not audio_base64:
                print("[Sarvam TTS] ❌ No audio returned from TTS.")
                return None
            audio_bytes = base64.b64decode(audio_base64)
        except Exception as e:
            print(f"[Sarvam TTS] ❌ TTS generation failed: {e}")
            return None
        

        # Step 3: Re-encode to SLIN WAV (8kHz mono, 16-bit)
        try:
            print("[Sarvam TTS] 🎧 Re-encoding to SLIN 8kHz mono")
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as mp3_file:
                mp3_file.write(audio_bytes)
                mp3_path = mp3_file.name

            audio = AudioSegment.from_file(mp3_path)
            wav_audio = audio.set_frame_rate(8000).set_channels(1).set_sample_width(2)  # SLIN: 8kHz mono 16-bit

            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
                wav_audio.export(f.name, format="wav")
                f.seek(0)
                final_bytes = f.read()

            if not final_bytes:
                print("[Sarvam TTS] ❌ Final WAV bytes are empty.")
                return None

            print(f"[Sarvam TTS] ✅ Audio ready (size: {len(final_bytes)} bytes)")
            return final_bytes

        except Exception as e:
            print(f"[Sarvam TTS] ❌ Error during WAV conversion: {e}")
            return None

    async def synthesize_tts_test_NOT_IN_USE(self, text: str) -> bytes:
        print("synthesize_tts")

        async with self.client.text_to_speech_streaming.connect(model="bulbul:v2") as ws:
            print("Inside")

            # Configure TTS stream
            await ws.configure(
                target_language_code="en-IN",
                speaker="anushka"
            )

            # Send text for conversion
            await ws.convert(text)
            print("convert")

            # Optional: finalize stream
            await ws.flush()
            print("bytearray")

            # Collect and decode audio chunks
            audio_data = bytearray()
            async for message in ws:
                if isinstance(message, AudioOutput):
                    audio_chunk = base64.b64decode(message.data.audio)
                    audio_data.extend(audio_chunk)

            print("[Sarvam TTS] 🎤 TTS generation complete")
            return bytes(audio_data)    