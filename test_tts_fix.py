#!/usr/bin/env python3
"""
Test script to verify TTS fixes and language logic
"""
import asyncio
import os
from utils.handler_asr import SarvamHandler

# Test the TTS fixes
async def test_tts_methods():
    api_key = os.getenv("SARVAM_API_KEY")
    if not api_key:
        print("❌ SARVAM_API_KEY not found in environment")
        return
    
    handler = SarvamHandler(api_key)
    
    # Test 1: Direct TTS with Hindi greeting (should work without translation)
    print("=== Test 1: Direct TTS (Hindi greeting) ===")
    hindi_greeting = "नमस्ते, मैं प्रिया हूं, और साउथ इंडिया फिनवेस्ट बैंक की ओर से बात कर रही हूं।"
    try:
        audio_bytes = await handler.synthesize_tts_direct(hindi_greeting, "hi-IN")
        if audio_bytes:
            print(f"✅ Direct TTS successful - Audio size: {len(audio_bytes)} bytes")
        else:
            print("❌ Direct TTS failed - No audio returned")
    except Exception as e:
        print(f"❌ Direct TTS error: {e}")
    
    # Test 2: Translation-based TTS with English text (should translate to Hindi)
    print("\n=== Test 2: Translation TTS (English to Hindi) ===")
    english_text = "Hello, this is Priya calling from South India Finvest Bank."
    try:
        audio_bytes = await handler.synthesize_tts(english_text, "hi-IN")
        if audio_bytes:
            print(f"✅ Translation TTS successful - Audio size: {len(audio_bytes)} bytes")
        else:
            print("❌ Translation TTS failed - No audio returned")
    except Exception as e:
        print(f"❌ Translation TTS error: {e}")
    
    # Test 3: Test language detection
    print("\n=== Test 3: Language Detection ===")
    from main import detect_language, get_initial_language_from_state
    
    test_cases = [
        ("नमस्ते, कैसे हैं आप?", "hi-IN"),
        ("வணக்கம், எப்படி இருக்கீங்க?", "ta-IN"),
        ("ನಮಸ್ಕಾರ, ಹೇಗಿದ್ದೀರಿ?", "kn-IN"),
        ("Hello, how are you?", "en-IN"),
    ]
    
    for text, expected in test_cases:
        detected = detect_language(text)
        status = "✅" if detected == expected else "❌"
        print(f"{status} Text: '{text}' -> Detected: {detected}, Expected: {expected}")
    
    # Test 4: State to language mapping
    print("\n=== Test 4: State to Language Mapping ===")
    state_tests = [
        ("kerala", "ml-IN"),
        ("tamil nadu", "ta-IN"),
        ("karnataka", "kn-IN"),
        ("maharashtra", "mr-IN"),
        ("unknown state", "en-IN"),
    ]
    
    for state, expected in state_tests:
        mapped = get_initial_language_from_state(state)
        status = "✅" if mapped == expected else "❌"
        print(f"{status} State: '{state}' -> Language: {mapped}, Expected: {expected}")

if __name__ == "__main__":
    print("🧪 Testing TTS fixes and language logic...\n")
    asyncio.run(test_tts_methods())
    print("\n🎉 Test completed!")
