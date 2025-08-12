import base64
import tempfile
import io
from pydub import AudioSegment
from sarvamai import SarvamAI
from sarvamai import AsyncSarvamAI, AudioOutput
from fastapi import Body
from .logger import logger


class SarvamHandler:
    def __init__(self, api_key):
        self.client = SarvamAI(api_subscription_key=api_key)
        
        # Language code mapping for proper BCP-47 format
        self.language_map = {
            'en': 'en-IN',
            'hi': 'hi-IN', 
            'bn': 'bn-IN',
            'ta': 'ta-IN',
            'te': 'te-IN',
            'gu': 'gu-IN',
            'kn': 'kn-IN',
            'ml': 'ml-IN',
            'mr': 'mr-IN',
            'pa': 'pa-IN',
            'od': 'od-IN',
            # Already correct formats
            'en-IN': 'en-IN',
            'hi-IN': 'hi-IN',
            'bn-IN': 'bn-IN',
            'ta-IN': 'ta-IN',
            'te-IN': 'te-IN',
            'gu-IN': 'gu-IN',
            'kn-IN': 'kn-IN',
            'ml-IN': 'ml-IN',
            'mr-IN': 'mr-IN',
            'pa-IN': 'pa-IN',
            'od-IN': 'od-IN'
        }

    def _normalize_language_code(self, lang: str) -> str:
        """Convert language code to proper BCP-47 format expected by Sarvam API"""
        normalized = self.language_map.get(lang.lower(), 'en-IN')
        logger.tts.info(f"🌍 Language mapping: {lang} → {normalized}")
        return normalized

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
        logger.tts.info("🎙️ Converting SLIN base64 to WAV")

        # Convert SLIN (raw 8kHz PCM mono) to WAV
        audio = AudioSegment(
            data=audio_buffer,
            sample_width=2,  # 16-bit PCM
            frame_rate=8000,
            channels=1
        )
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            audio.export(f.name, format="wav")
            wav_path = f.name
        logger.tts.info("🚀 Sending WAV to Sarvam API")
        # Call Sarvam REST API directly
        with open(wav_path, "rb") as wav_file:
            response = self.client.speech_to_text.transcribe(
                file=wav_file,
                model="saarika:v2.5",
                language_code="unknown"  # Make sure this matches your subscription
            )
        logger.tts.info(f"📝 Transcript received: {response.transcript}")
        return response.transcript
    
    async def synthesize_tts_end(self, text: str, lang: str) -> bytes:
        logger.tts.info(f"🔁 Starting text-to-speech for: {text} in {lang}")

        try:
            response = self.client.text_to_speech.convert(
                text=text,
                target_language_code=lang,
                speaker="anushka",
                model="bulbul:v2"
            )
            audio_base64 = response.audios[0] if response.audios else None
            if not audio_base64:
                logger.tts.error("❌ No audio data returned from API.")
                return None
            
            audio_bytes = base64.b64decode(audio_base64)
            
            # The audio is likely mp3, convert it to 8kHz mono 16-bit PCM (slin)
            try:
                audio_segment = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
            except Exception as dec_err:
                logger.tts.error(f"❌ Decode mp3 failed: {dec_err}")
                return None

            slin_audio = audio_segment.set_frame_rate(8000).set_channels(1).set_sample_width(2)
            raw_pcm = slin_audio.raw_data
            size = len(raw_pcm)
            if raw_pcm[:4] == b'RIFF' and size > 44:
                # Safety: if pydub ever returned WAV with header (shouldn't for raw_data) remove it
                logger.tts.warning("⚠️ Unexpected RIFF header in raw_data – stripping")
                raw_pcm = raw_pcm[44:]
                size = len(raw_pcm)
            logger.tts.info(f"✅ Audio ready PCM size={size} bytes, first10={raw_pcm[:10].hex()}")
            if size < 200:
                logger.tts.warning("⚠️ Very small audio payload – may be silence")
            return raw_pcm

        except Exception as e:
            logger.tts.error(f"❌ An error occurred: {e}")
            import traceback
            traceback.print_exc()
            return None
   
    async def synthesize_tts(self, text: str, lang: str) -> bytes:
        """Smart TTS synthesis with translation support"""
        logger.tts.info("🔁 Starting text-to-speech synthesis (with translation)")

        try:
            # Normalize language code to BCP-47 format
            lang_code = self._normalize_language_code(lang)
            
            # Check if translation is needed
            if not self._is_text_in_target_language(text, lang_code):
                logger.tts.info(f"� Text needs translation to {lang_code}")
                try:
                    response = self.client.translate.translate(
                        input=text,
                        source_language_code="en-IN",  # Assume English source
                        target_language_code=lang_code,
                        model="mayura:v1",
                        enable_preprocessing=True
                    )
                    
                    if response and hasattr(response, 'translated_text'):
                        translated_text = response.translated_text
                        logger.tts.info(f"🔤 Translated text: {translated_text}")
                    else:
                        logger.tts.warning("❌ Translation response is empty, using original text")
                        translated_text = text
                        
                except Exception as e:
                    logger.tts.error(f"❌ Translation failed: {e}")
                    logger.tts.info(f"🔤 Using original text: {text}")
                    translated_text = text
            else:
                logger.tts.info(f"✅ Text already in target language ({lang_code})")
                translated_text = text

            logger.tts.info("🎤 Generating TTS audio...")
            
            # Generate TTS with optimized parameters for bulbul:v2
            response = self.client.text_to_speech.convert(
                text=translated_text,
                target_language_code=lang_code,
                model="bulbul:v2",
                speaker="anushka",  # Compatible speaker for bulbul:v2
                pitch=1.0,        # Natural pitch
                pace=1.0,         # Natural speaking pace
                loudness=1.0,     # Natural volume
                speech_sample_rate=8000, # Optimized for telephony (correct parameter name)
                enable_preprocessing=True  # Better handling of mixed content
            )
            
            if not response or not hasattr(response, 'audios') or not response.audios:
                logger.tts.error("❌ No audio data returned from Sarvam TTS")
                return None
                
            audio_data = response.audios[0]
            logger.tts.info(f"✅ Received audio data from Sarvam API (length: {len(audio_data)})")
            
            # Handle base64 encoded audio
            if isinstance(audio_data, str):
                try:
                    audio_bytes = base64.b64decode(audio_data)
                    logger.tts.info(f"🔓 Decoded base64 audio ({len(audio_bytes)} bytes)")
                except Exception as e:
                    logger.tts.error(f"❌ Failed to decode base64 audio: {e}")
                    return None
            else:
                audio_bytes = audio_data
                
        except Exception as e:
            logger.tts.error(f"❌ TTS generation failed: {e}")
            return None

        # Step 3: Convert to SLIN format with better error handling
        try:
            logger.tts.info("🎧 Converting audio to SLIN format...")
            
            # Create temporary file to handle audio conversion
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_file.write(audio_bytes)
                temp_file.flush()
                
                # Load audio using pydub with explicit format
                try:
                    audio_segment = AudioSegment.from_file(temp_file.name)
                    logger.tts.info(f"📊 Original audio: {audio_segment.frame_rate}Hz, {audio_segment.channels}ch, {len(audio_segment)}ms")
                except:
                    # Try as WAV if MP3 fails
                    audio_segment = AudioSegment.from_wav(temp_file.name)
                    logger.tts.info(f"📊 WAV audio loaded: {audio_segment.frame_rate}Hz, {audio_segment.channels}ch, {len(audio_segment)}ms")
                
                # Convert to SLIN format (8kHz, mono, 16-bit)
                slin_audio = audio_segment.set_frame_rate(8000).set_channels(1).set_sample_width(2)
                final_bytes = slin_audio.raw_data
                
                # Clean up temp file
                import os
                os.unlink(temp_file.name)
                
            logger.tts.info(f"✅ SLIN audio ready: {len(final_bytes)} bytes, 8kHz mono")
            
            # Validate audio data
            if len(final_bytes) < 1000:  # Less than ~62ms of audio
                logger.tts.warning("⚠️ Very short audio generated, may be silence")
                
            return final_bytes
            
        except Exception as e:
            logger.tts.error(f"❌ Audio conversion failed: {e}")
            import traceback
            logger.tts.error(f"❌ Conversion traceback: {traceback.format_exc()}")
            return None

    async def synthesize_tts_direct(self, text: str, lang: str) -> bytes:
        """Direct TTS synthesis without translation - optimized for Sarvam API v2"""
        logger.tts.info("🔁 Starting direct text-to-speech synthesis (no translation)")

        try:
            # Normalize language code to BCP-47 format
            lang_code = self._normalize_language_code(lang)
            
            logger.tts.info("🎤 Generating direct TTS audio...")
            response = self.client.text_to_speech.convert(
                text=text,
                target_language_code=lang_code,
                speaker="anushka",  # Compatible speaker for bulbul:v2
                pitch=0.0,        # Natural pitch
                pace=1.0,         # Natural pace  
                loudness=1.0,     # Natural loudness
                speech_sample_rate=8000,  # 8kHz for telephony
                enable_preprocessing=True,  # Better mixed-language handling
                model="bulbul:v2"  # Latest stable model
            )
            
            if not response or not hasattr(response, 'audios') or not response.audios:
                logger.tts.error("❌ No audio data returned from Sarvam TTS")
                return None
                
            audio_data = response.audios[0]
            logger.tts.info(f"✅ Received direct audio data from Sarvam API (length: {len(audio_data)})")
            
            # Handle base64 encoded audio
            if isinstance(audio_data, str):
                try:
                    audio_bytes = base64.b64decode(audio_data)
                    logger.tts.info(f"🔓 Decoded base64 audio ({len(audio_bytes)} bytes)")
                except Exception as e:
                    logger.tts.error(f"❌ Failed to decode base64 audio: {e}")
                    return None
            else:
                audio_bytes = audio_data
            
            # Convert to SLIN format with better error handling
            logger.tts.info("🎧 Converting direct audio to SLIN format...")
            
            # Create temporary file to handle audio conversion
            import tempfile
            import os
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_file.write(audio_bytes)
                temp_file.flush()
                
                # Load audio using pydub with explicit format
                try:
                    audio_segment = AudioSegment.from_file(temp_file.name)
                    logger.tts.info(f"📊 Direct audio: {audio_segment.frame_rate}Hz, {audio_segment.channels}ch, {len(audio_segment)}ms")
                except:
                    # Try as WAV if MP3 fails
                    audio_segment = AudioSegment.from_wav(temp_file.name)
                    logger.tts.info(f"📊 Direct WAV audio: {audio_segment.frame_rate}Hz, {audio_segment.channels}ch, {len(audio_segment)}ms")
                
                # Convert to SLIN format (8kHz, mono, 16-bit)
                slin_audio = audio_segment.set_frame_rate(8000).set_channels(1).set_sample_width(2)
                final_bytes = slin_audio.raw_data
                
                # Clean up temp file
                os.unlink(temp_file.name)
                
            logger.tts.info(f"✅ Direct SLIN audio ready: {len(final_bytes)} bytes, 8kHz mono")
            
            # Validate audio data
            if len(final_bytes) < 1000:  # Less than ~62ms of audio
                logger.tts.warning("⚠️ Very short direct audio generated, may be silence")
                
            return final_bytes
            
        except Exception as e:
            logger.tts.error(f"❌ Direct TTS generation failed: {e}")
            import traceback
            logger.tts.error(f"❌ Direct TTS traceback: {traceback.format_exc()}")
            return None

    def _is_text_in_target_language(self, text: str, lang: str) -> bool:
        """Simple heuristic to check if text is already in target language"""
        # For Hindi/Devanagari languages
        if lang.startswith('hi'):
            return any('\u0900' <= char <= '\u097F' for char in text)
        # For Tamil
        elif lang.startswith('ta'):
            return any('\u0B80' <= char <= '\u0BFF' for char in text)
        # For Telugu
        elif lang.startswith('te'):
            return any('\u0C00' <= char <= '\u0C7F' for char in text)
        # For Kannada
        elif lang.startswith('kn'):
            return any('\u0C80' <= char <= '\u0CFF' for char in text)
        # For Malayalam
        elif lang.startswith('ml'):
            return any('\u0D00' <= char <= '\u0D7F' for char in text)
        # For Gujarati
        elif lang.startswith('gu'):
            return any('\u0A80' <= char <= '\u0AFF' for char in text)
        # For Marathi (uses Devanagari like Hindi)
        elif lang.startswith('mr'):
            return any('\u0900' <= char <= '\u097F' for char in text)
        # For Bengali
        elif lang.startswith('bn'):
            return any('\u0980' <= char <= '\u09FF' for char in text)
        # For Punjabi/Gurmukhi
        elif lang.startswith('pa'):
            return any('\u0A00' <= char <= '\u0A7F' for char in text)
        # For Oriya
        elif lang.startswith('or'):
            return any('\u0B00' <= char <= '\u0B7F' for char in text)
        # Default: assume English text needs translation to non-English languages
        return lang.startswith('en')
   
    async def synthesize_tts_test_NOT_IN_USE(self, text: str) -> bytes:
        logger.tts.debug("synthesize_tts_test_NOT_IN_USE called")

        async with self.client.text_to_speech_streaming.connect(model="bulbul:v2") as ws:
            logger.tts.debug("Inside streaming TTS connection")

            # Configure TTS stream
            await ws.configure(
                target_language_code="en-IN",
                speaker="anushka"
            )

            # Send text for conversion
            await ws.convert(text)
            logger.tts.debug("Text sent for conversion")

            # Optional: finalize stream
            await ws.flush()
            logger.tts.debug("Stream flushed")

            # Collect and decode audio chunks
            audio_data = bytearray()
            async for message in ws:
                if isinstance(message, AudioOutput):
                    audio_chunk = base64.b64decode(message.data.audio)
                    audio_data.extend(audio_chunk)

            logger.tts.info("🎤 TTS generation complete")
            return bytes(audio_data)