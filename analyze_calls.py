#!/usr/bin/env python3
"""
Simple Call Duration Analysis
"""

import os
import httpx
import json
import asyncio
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

async def analyze_specific_call(call_sid):
    """Get detailed information about a specific call"""
    print(f"\n🔍 Analyzing Call: {call_sid}")
    
    exotel_sid = os.getenv("EXOTEL_SID")
    exotel_api_key = os.getenv("EXOTEL_API_KEY")
    exotel_token = os.getenv("EXOTEL_TOKEN")
    
    url = f"https://api.exotel.com/v1/Accounts/{exotel_sid}/Calls/{call_sid}.json"
    
    try:
        async with httpx.AsyncClient(auth=(exotel_api_key, exotel_token)) as client:
            response = await client.get(url)
        
        if response.status_code == 200:
            call_data = response.json()
            call_info = call_data.get('Call', {})
            
            print(f"📋 Call Details:")
            print(f"   Call SID: {call_info.get('Sid')}")
            print(f"   Status: {call_info.get('Status')}")
            print(f"   To: {call_info.get('To')}")
            print(f"   From: {call_info.get('From')}")
            print(f"   Duration: {call_info.get('Duration')} seconds")
            print(f"   Start Time: {call_info.get('StartTime')}")
            print(f"   End Time: {call_info.get('EndTime')}")
            print(f"   Answered By: {call_info.get('AnsweredBy')}")
            print(f"   Direction: {call_info.get('Direction')}")
            
            # Analyze the duration
            duration = call_info.get('Duration')
            if duration:
                duration = int(duration)
                if duration <= 5:
                    print(f"⚠️  Short call duration ({duration}s) suggests:")
                    print(f"     • Customer answered but hung up quickly")
                    print(f"     • ExoML flow completed without proper interaction")
                    print(f"     • No audio/greeting played to customer")
                elif duration <= 15:
                    print(f"🔄 Moderate duration ({duration}s) suggests:")
                    print(f"     • Some interaction occurred")
                    print(f"     • Flow may be incomplete or customer ended call")
                else:
                    print(f"✅ Good duration ({duration}s) suggests:")
                    print(f"     • Successful interaction")
            
            return True
        else:
            print(f"❌ Failed to get call details: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error analyzing call: {e}")
        return False

async def get_recent_calls_analysis():
    """Analyze recent calls to your test number"""
    print("🔍 Analyzing Recent Calls to +917417119014")
    print("=" * 50)
    
    exotel_sid = os.getenv("EXOTEL_SID")
    exotel_api_key = os.getenv("EXOTEL_API_KEY")
    exotel_token = os.getenv("EXOTEL_TOKEN")
    
    url = f"https://api.exotel.com/v1/Accounts/{exotel_sid}/Calls.json"
    
    try:
        async with httpx.AsyncClient(auth=(exotel_api_key, exotel_token)) as client:
            response = await client.get(url, params={'PageSize': 20})
        
        if response.status_code == 200:
            calls_data = response.json()
            calls = calls_data.get('Calls', [])
            
            # Filter calls to the test number
            test_calls = [call for call in calls if call.get('To') == '+917417119014']
            
            print(f"Found {len(test_calls)} calls to +917417119014")
            
            for i, call in enumerate(test_calls[:5], 1):
                print(f"\n📞 Call #{i}:")
                await analyze_specific_call(call.get('Sid'))
            
            return True
        else:
            print(f"❌ Failed to get calls: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error getting calls: {e}")
        return False

def suggest_fixes():
    """Suggest fixes for the call duration issue"""
    print("\n🔧 Suggested Fixes:")
    print("=" * 30)
    
    fixes = [
        "1. **ExoML Flow Issues**:",
        "   - The flow might be ending immediately without playing audio",
        "   - Check if there's a proper greeting/TTS element in the flow",
        "   - Ensure the flow has a Passthru element to connect to your app",
        "",
        "2. **Missing Audio Content**:",
        "   - The flow might be connecting but not playing any greeting",
        "   - Customer answers, hears silence, and hangs up",
        "   - Add a TTS (Text-to-Speech) greeting in the ExoML flow",
        "",
        "3. **Flow Configuration**:",
        "   - Login to https://my.exotel.com/",
        "   - Go to Flows/ExoML section",
        "   - Check Flow ID: 1027293",
        "   - Ensure it has these elements:",
        "     • TTS greeting (\"Hello, this is a call from...\")",
        "     • Gather user input or wait",
        "     • Passthru to connect to your voice assistant",
        "",
        "4. **Test the Flow Manually**:",
        "   - Use Exotel's flow tester",
        "   - Make a test call from Exotel dashboard",
        "   - Verify audio plays correctly",
        "",
        "5. **Quick Fix - Add Debug TTS**:",
        "   - Add a simple TTS element that says:",
        "     \"Hello, you are connected to the voice assistant.\"",
        "   - This will help verify if audio is working"
    ]
    
    for fix in fixes:
        print(fix)

async def main():
    """Main analysis function"""
    await get_recent_calls_analysis()
    suggest_fixes()
    
    print("\n💡 Key Insight:")
    print("   Calls ARE working and connecting successfully!")
    print("   The issue is likely in the ExoML flow configuration.")
    print("   Customers are answering but hanging up after 4-5 seconds,")
    print("   probably because they hear silence or unexpected audio.")

if __name__ == "__main__":
    asyncio.run(main())
