#!/usr/bin/env python3
"""
Exotel Call Testing Script
This script tests Exotel configuration and makes a test call
"""

import os
import httpx
import json
from dotenv import load_dotenv

load_dotenv()

def check_environment():
    """Check if all required environment variables are set"""
    required_vars = [
        'EXOTEL_SID',
        'EXOTEL_TOKEN', 
        'EXOTEL_API_KEY',
        'EXOTEL_VIRTUAL_NUMBER',
        'EXOTEL_FLOW_APP_ID',
        'BASE_URL'
    ]
    
    print("🔧 Checking Environment Variables...")
    missing_vars = []
    
    for var in required_vars:
        value = os.getenv(var)
        if value:
            if 'TOKEN' in var or 'KEY' in var:
                print(f"✅ {var}: {value[:10]}...{value[-10:]}")  # Hide sensitive data
            else:
                print(f"✅ {var}: {value}")
        else:
            print(f"❌ {var}: NOT SET")
            missing_vars.append(var)
    
    if missing_vars:
        print(f"\n❌ Missing required environment variables: {missing_vars}")
        return False
    
    print("\n✅ All environment variables are set!")
    return True

def test_exotel_connection():
    """Test Exotel API connection by fetching account details"""
    print("\n🔌 Testing Exotel API Connection...")
    
    exotel_sid = os.getenv("EXOTEL_SID")
    exotel_api_key = os.getenv("EXOTEL_API_KEY") 
    exotel_token = os.getenv("EXOTEL_TOKEN")
    
    url = f"https://api.exotel.com/v1/Accounts/{exotel_sid}.json"
    
    try:
        with httpx.Client(auth=(exotel_api_key, exotel_token)) as client:
            response = client.get(url)
        
        if response.status_code == 200:
            account_data = response.json()
            print("✅ Exotel API connection successful!")
            print(f"   Account Name: {account_data.get('Account', {}).get('FriendlyName', 'N/A')}")
            print(f"   Account Status: {account_data.get('Account', {}).get('Status', 'N/A')}")
            return True
        else:
            print(f"❌ Exotel API connection failed!")
            print(f"   Status Code: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error connecting to Exotel API: {e}")
        return False

def test_phone_number_format(phone_number):
    """Test and validate phone number format"""
    print(f"\n📱 Testing Phone Number Format: {phone_number}")
    
    # Check if starts with +91
    if not phone_number.startswith('+91'):
        print(f"⚠️  Phone number doesn't start with +91: {phone_number}")
        return False
    
    # Check length (should be +91 + 10 digits = 13 total)
    if len(phone_number) != 13:
        print(f"⚠️  Phone number length incorrect. Expected 13, got {len(phone_number)}: {phone_number}")
        return False
    
    # Check if rest are digits
    digits_part = phone_number[3:]  # Remove +91
    if not digits_part.isdigit():
        print(f"⚠️  Phone number contains non-digits after +91: {phone_number}")
        return False
    
    print("✅ Phone number format is correct!")
    return True

async def make_test_call(phone_number):
    """Make a test call through Exotel"""
    print(f"\n📞 Making Test Call to: {phone_number}")
    
    # Environment variables
    exotel_sid = os.getenv("EXOTEL_SID")
    exotel_api_key = os.getenv("EXOTEL_API_KEY")
    exotel_token = os.getenv("EXOTEL_TOKEN")
    exotel_virtual_number = os.getenv("EXOTEL_VIRTUAL_NUMBER")
    exotel_flow_app_id = os.getenv("EXOTEL_FLOW_APP_ID")
    base_url = os.getenv("BASE_URL")
    
    # API URL
    url = f"https://api.exotel.com/v1/Accounts/{exotel_sid}/Calls/connect.json"
    
    # Flow URL
    flow_url = f"http://my.exotel.com/{exotel_sid}/exoml/start_voice/{exotel_flow_app_id}"
    
    # Test payload
    payload = {
        'From': exotel_virtual_number,
        'To': phone_number,
        'CallerId': exotel_virtual_number,
        'Url': flow_url,
        'CallType': 'trans',
        'TimeLimit': '3600',
        'TimeOut': '30',
        'CustomField': f"test_call=true|phone={phone_number}|timestamp={os.time() if hasattr(os, 'time') else 'unknown'}",
        'StatusCallback': f"{base_url}/exotel-webhook"
    }
    
    print(f"📋 Call Details:")
    print(f"   API URL: {url}")
    print(f"   Flow URL: {flow_url}")
    print(f"   From: {payload['From']}")
    print(f"   To: {payload['To']}")
    print(f"   CallerId: {payload['CallerId']}")
    print(f"   StatusCallback: {payload['StatusCallback']}")
    print(f"   CustomField: {payload['CustomField']}")
    
    try:
        async with httpx.AsyncClient(auth=(exotel_api_key, exotel_token)) as client:
            response = await client.post(url, data=payload)
        
        print(f"\n📊 API Response:")
        print(f"   Status Code: {response.status_code}")
        
        if response.status_code == 200:
            response_data = response.json()
            call_sid = response_data.get('Call', {}).get('Sid')
            call_status = response_data.get('Call', {}).get('Status')
            
            print("✅ Call triggered successfully!")
            print(f"   Call SID: {call_sid}")
            print(f"   Call Status: {call_status}")
            print(f"   Full Response: {json.dumps(response_data, indent=2)}")
            return True
        else:
            print("❌ Call failed!")
            print(f"   Error Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error making call: {e}")
        return False

async def main():
    """Main test function"""
    print("🚀 Exotel Call Testing Script")
    print("=" * 50)
    
    # Step 1: Check environment
    if not check_environment():
        return
    
    # Step 2: Test API connection
    if not test_exotel_connection():
        return
    
    # Step 3: Test phone number format
    test_phone = "+917417119014"  # Your test number
    if not test_phone_number_format(test_phone):
        return
    
    # Step 4: Make test call
    print(f"\n⚠️  About to make a test call to {test_phone}")
    print("   This will trigger an actual call. Make sure this number can receive calls.")
    
    user_input = input("\nProceed with test call? (y/N): ").strip().lower()
    if user_input == 'y':
        await make_test_call(test_phone)
    else:
        print("Test call skipped.")
    
    print("\n✅ Test completed!")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
