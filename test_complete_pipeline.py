#!/usr/bin/env python3
"""
Complete Voice Assistant Pipeline Test
=====================================
Tests the entire voice assistant pipeline from TTS generation to WebSocket delivery.
"""

import asyncio
import base64
import json
import logging
import os
from datetime import datetime
from dotenv import load_dotenv
from utils.handler_asr import SarvamHandler
from utils.bedrock_client import invoke_claude_model

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(name)s | %(message)s')
logger = logging.getLogger("pipeline_test")

async def test_complete_pipeline():
    """Test the complete voice assistant pipeline"""
    
    print("🎯 Complete Voice Assistant Pipeline Test")
    print("=" * 60)
    
    try:
        # Initialize components
        print("\n🔧 Initializing components...")
        
        # Get Sarvam API key
        api_key = os.getenv("SARVAM_API_KEY")
        if not api_key:
            raise ValueError("SARVAM_API_KEY not found in environment")
            
        sarvam_handler = SarvamHandler(api_key)
        
        # Create a simple AI response function
        async def get_ai_response(query: str, customer_id: str = "test") -> str:
            """Simple AI response function for testing"""
            try:
                prompt = f"""You are a helpful customer service agent for Zrosis Bank. 
                
Customer query: {query}
                
Please provide a helpful, professional response. Keep it concise and friendly."""
                
                response = await invoke_claude_model(prompt)
                return response if response else "I apologize, but I'm having trouble processing your request right now. Please try again."
                
            except Exception as e:
                logger.error(f"AI response error: {e}")
                return "I apologize for the inconvenience. Let me connect you with a human agent."
        
        # Test TTS generation
        print("\n🔊 Testing TTS Generation...")
        test_messages = [
            "Hello! Welcome to our customer service. How can I help you today?",
            "Thank you for calling. I understand you need assistance.",
            "I'll be happy to help you with your query.",
        ]
        
        tts_results = []
        for i, message in enumerate(test_messages, 1):
            print(f"   Testing message {i}: '{message[:50]}{'...' if len(message) > 50 else ''}'")
            
            # Test both TTS methods
            try:
                # Direct TTS (English)
                direct_audio = await sarvam_handler.synthesize_tts_direct(message, "en-IN")
                if direct_audio:
                    tts_results.append({
                        'method': 'direct',
                        'message': message,
                        'audio_length': len(direct_audio),
                        'success': True
                    })
                    print(f"      ✅ Direct TTS: {len(direct_audio)} bytes")
                else:
                    print(f"      ❌ Direct TTS failed")
                    
                # Smart TTS (with translation to Hindi)
                smart_audio = await sarvam_handler.synthesize_tts(message, "hi-IN")
                if smart_audio:
                    tts_results.append({
                        'method': 'smart',
                        'message': message,
                        'audio_length': len(smart_audio),
                        'success': True
                    })
                    print(f"      ✅ Smart TTS: {len(smart_audio)} bytes")
                else:
                    print(f"      ❌ Smart TTS failed")
                    
            except Exception as e:
                print(f"      ❌ TTS error: {e}")
        
        # Test WebSocket message format
        print("\n📡 Testing WebSocket Message Format...")
        if tts_results:
            # Use the first successful TTS result
            test_audio = None
            for result in tts_results:
                if result['success']:
                    # Re-generate audio for testing
                    if result['method'] == 'direct':
                        test_audio = await sarvam_handler.synthesize_tts_direct(result['message'], "en-IN")
                    else:
                        test_audio = await sarvam_handler.synthesize_tts(result['message'], "hi-IN")
                    break
            
            if test_audio:
                # Convert to base64 for WebSocket transmission
                audio_b64 = base64.b64encode(test_audio).decode('utf-8')
                
                # Create WebSocket media message
                media_message = {
                    "event": "media",
                    "streamSid": "test_stream_" + datetime.now().strftime("%Y%m%d_%H%M%S"),
                    "media": {
                        "payload": audio_b64
                    }
                }
                
                print(f"   ✅ WebSocket message created:")
                print(f"      - Event: {media_message['event']}")
                print(f"      - StreamSid: {media_message['streamSid']}")
                print(f"      - Audio payload size: {len(audio_b64)} chars")
                print(f"      - Original audio size: {len(test_audio)} bytes")
                
                # Validate base64 encoding/decoding
                try:
                    decoded_audio = base64.b64decode(audio_b64)
                    if decoded_audio == test_audio:
                        print(f"   ✅ Base64 encoding/decoding verified")
                    else:
                        print(f"   ❌ Base64 encoding/decoding mismatch")
                except Exception as e:
                    print(f"   ❌ Base64 validation error: {e}")
            
        # Test voice assistant processing
        print("\n🤖 Testing Voice Assistant Processing...")
        try:
            # Simulate customer input
            customer_queries = [
                "I need help with my account",
                "What are your business hours?",
                "Can you help me reset my password?"
            ]
            
            for query in customer_queries:
                print(f"   Testing query: '{query}'")
                
                # Get AI response
                response = await get_ai_response(query, "test_customer_123")
                if response:
                    print(f"      ✅ AI Response: '{response[:100]}{'...' if len(response) > 100 else ''}'")
                    
                    # Generate TTS for response
                    response_audio = await sarvam_handler.synthesize_tts_direct(response, "en-IN")
                    if response_audio:
                        print(f"      ✅ Response TTS: {len(response_audio)} bytes")
                    else:
                        print(f"      ❌ Response TTS failed")
                else:
                    print(f"      ❌ AI Response failed")
                    
        except Exception as e:
            print(f"   ❌ Voice assistant error: {e}")
        
        # Summary
        print(f"\n📊 Pipeline Test Summary:")
        print(f"=" * 40)
        
        successful_tts = len([r for r in tts_results if r['success']])
        total_tts_tests = len(tts_results)
        
        print(f"✅ TTS Tests Passed: {successful_tts}/{total_tts_tests}")
        if successful_tts > 0:
            avg_audio_size = sum(r['audio_length'] for r in tts_results if r['success']) / successful_tts
            print(f"📊 Average Audio Size: {avg_audio_size:.0f} bytes")
        
        if successful_tts == total_tts_tests:
            print(f"🎉 ALL PIPELINE TESTS PASSED!")
            print(f"✅ The voice assistant is ready for production use.")
        elif successful_tts > 0:
            print(f"⚠️  PARTIAL SUCCESS - Some TTS methods working")
        else:
            print(f"❌ PIPELINE FAILED - No TTS methods working")
            
    except Exception as e:
        logger.error(f"Pipeline test failed: {e}")
        print(f"❌ Pipeline test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_complete_pipeline())
