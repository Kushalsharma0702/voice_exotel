#!/usr/bin/env python3
"""
Comprehensive Exotel Call Diagnostics
This script checks all aspects of call functionality
"""

import os
import httpx
import json
import asyncio
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

async def check_account_balance():
    """Check Exotel account balance and credits"""
    print("\n💰 Checking Exotel Account Balance...")
    
    exotel_sid = os.getenv("EXOTEL_SID")
    exotel_api_key = os.getenv("EXOTEL_API_KEY")
    exotel_token = os.getenv("EXOTEL_TOKEN")
    
    url = f"https://api.exotel.com/v1/Accounts/{exotel_sid}/Balance.json"
    
    try:
        async with httpx.AsyncClient(auth=(exotel_api_key, exotel_token)) as client:
            response = await client.get(url)
        
        if response.status_code == 200:
            balance_data = response.json()
            balance = balance_data.get('Account', {}).get('Balance', 'N/A')
            print(f"✅ Account Balance: ₹{balance}")
            
            if float(balance) <= 0:
                print("⚠️  Warning: Account balance is 0 or negative. This might prevent calls.")
                return False
            return True
        else:
            print(f"❌ Failed to get balance: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error checking balance: {e}")
        return False

async def check_phone_numbers():
    """Check virtual number status"""
    print("\n📱 Checking Phone Numbers...")
    
    exotel_sid = os.getenv("EXOTEL_SID")
    exotel_api_key = os.getenv("EXOTEL_API_KEY")
    exotel_token = os.getenv("EXOTEL_TOKEN")
    virtual_number = os.getenv("EXOTEL_VIRTUAL_NUMBER")
    
    url = f"https://api.exotel.com/v1/Accounts/{exotel_sid}/IncomingPhoneNumbers.json"
    
    try:
        async with httpx.AsyncClient(auth=(exotel_api_key, exotel_token)) as client:
            response = await client.get(url)
        
        if response.status_code == 200:
            numbers_data = response.json()
            numbers = numbers_data.get('IncomingPhoneNumbers', [])
            
            print(f"📋 Available Numbers:")
            found_virtual_number = False
            
            for number in numbers:
                phone_number = number.get('PhoneNumber')
                friendly_name = number.get('FriendlyName', 'N/A')
                status = number.get('VoiceCallerId', 'Unknown')
                
                print(f"   • {phone_number} ({friendly_name}) - Status: {status}")
                
                # Check if our configured virtual number exists
                if phone_number == virtual_number or phone_number == virtual_number.replace('+91', '0'):
                    found_virtual_number = True
                    print(f"     ✅ This matches our configured virtual number")
            
            if not found_virtual_number:
                print(f"⚠️  Warning: Configured virtual number {virtual_number} not found in account")
                return False
                
            return True
        else:
            print(f"❌ Failed to get phone numbers: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error checking phone numbers: {e}")
        return False

async def check_recent_calls():
    """Check recent call history"""
    print("\n📞 Checking Recent Call History...")
    
    exotel_sid = os.getenv("EXOTEL_SID")
    exotel_api_key = os.getenv("EXOTEL_API_KEY")
    exotel_token = os.getenv("EXOTEL_TOKEN")
    
    url = f"https://api.exotel.com/v1/Accounts/{exotel_sid}/Calls.json"
    
    try:
        async with httpx.AsyncClient(auth=(exotel_api_key, exotel_token)) as client:
            response = await client.get(url, params={'PageSize': 10})
        
        if response.status_code == 200:
            calls_data = response.json()
            calls = calls_data.get('Calls', [])
            
            print(f"📋 Recent Calls (Last 10):")
            
            for call in calls[:10]:
                call_sid = call.get('Sid')
                to_number = call.get('To')
                from_number = call.get('From') 
                status = call.get('Status')
                duration = call.get('Duration', 'N/A')
                date_created = call.get('DateCreated')
                
                print(f"   • {call_sid[:8]}... → {to_number} (Status: {status}, Duration: {duration}s)")
                print(f"     From: {from_number}, Created: {date_created}")
                
                if status in ['failed', 'busy', 'no-answer']:
                    print(f"     ⚠️  This call was not successful")
                elif status == 'completed':
                    print(f"     ✅ This call was successful")
            
            return True
        else:
            print(f"❌ Failed to get call history: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error checking call history: {e}")
        return False

async def check_exoml_flow():
    """Check ExoML flow configuration"""
    print("\n🔄 Checking ExoML Flow Configuration...")
    
    exotel_sid = os.getenv("EXOTEL_SID")
    exotel_api_key = os.getenv("EXOTEL_API_KEY")
    exotel_token = os.getenv("EXOTEL_TOKEN")
    flow_app_id = os.getenv("EXOTEL_FLOW_APP_ID")
    
    # Try to get flow information
    url = f"https://api.exotel.com/v1/Accounts/{exotel_sid}/Applications/{flow_app_id}.json"
    
    try:
        async with httpx.AsyncClient(auth=(exotel_api_key, exotel_token)) as client:
            response = await client.get(url)
        
        if response.status_code == 200:
            app_data = response.json()
            app_info = app_data.get('Application', {})
            
            print(f"✅ ExoML Flow Found:")
            print(f"   Flow ID: {flow_app_id}")
            print(f"   Name: {app_info.get('FriendlyName', 'N/A')}")
            print(f"   Voice URL: {app_info.get('VoiceUrl', 'N/A')}")
            print(f"   Voice Method: {app_info.get('VoiceMethod', 'N/A')}")
            
            # Check if the flow URL is accessible
            flow_url = f"http://my.exotel.com/{exotel_sid}/exoml/start_voice/{flow_app_id}"
            print(f"   Flow URL: {flow_url}")
            
            return True
        else:
            print(f"❌ Failed to get flow info: {response.status_code} - {response.text}")
            print(f"⚠️  This might indicate the Flow ID is incorrect")
            return False
            
    except Exception as e:
        print(f"❌ Error checking ExoML flow: {e}")
        return False

async def test_webhook_endpoint():
    """Test if webhook endpoint is accessible"""
    print("\n🌐 Testing Webhook Endpoint...")
    
    base_url = os.getenv("BASE_URL")
    webhook_url = f"{base_url}/exotel-webhook"
    
    try:
        async with httpx.AsyncClient() as client:
            # Test GET request to webhook (just to see if it's accessible)
            response = await client.get(webhook_url)
        
        print(f"✅ Webhook endpoint is accessible: {webhook_url}")
        print(f"   Response Status: {response.status_code}")
        return True
        
    except Exception as e:
        print(f"❌ Webhook endpoint not accessible: {webhook_url}")
        print(f"   Error: {e}")
        print(f"⚠️  This might prevent status updates from Exotel")
        return False

def generate_troubleshooting_report():
    """Generate troubleshooting suggestions"""
    print("\n📋 Troubleshooting Suggestions:")
    print("=" * 50)
    
    suggestions = [
        "1. **Check Exotel Dashboard**:",
        "   - Login to https://my.exotel.com/",
        "   - Check call logs and status",
        "   - Verify account balance and credits",
        "",
        "2. **Test with Different Numbers**:",
        "   - Try calling a different phone number",
        "   - Try calling your own number first",
        "   - Check if specific numbers are blocked",
        "",
        "3. **ExoML Flow Verification**:",
        "   - Check the flow configuration in Exotel dashboard",
        "   - Ensure the flow is properly published and active",
        "   - Test the flow manually from Exotel interface",
        "",
        "4. **Phone Number Issues**:",
        "   - Verify the customer's number is correct",
        "   - Check if the number is on DND (Do Not Disturb)",
        "   - Try removing and re-adding the +91 prefix",
        "",
        "5. **Network/Carrier Issues**:",
        "   - Check if the customer's network supports incoming calls",
        "   - Try calling at different times of day",
        "   - Check with the customer if they're receiving other calls",
        "",
        "6. **Account Configuration**:",
        "   - Verify Exotel account is active and verified",
        "   - Check if there are any restrictions on the account",
        "   - Ensure the virtual number is properly configured"
    ]
    
    for suggestion in suggestions:
        print(suggestion)

async def main():
    """Main diagnostic function"""
    print("🔍 Comprehensive Exotel Call Diagnostics")
    print("=" * 50)
    
    results = []
    
    # Run all diagnostic checks
    results.append(("Account Balance", await check_account_balance()))
    results.append(("Phone Numbers", await check_phone_numbers()))
    results.append(("Recent Calls", await check_recent_calls()))
    results.append(("ExoML Flow", await check_exoml_flow()))
    results.append(("Webhook Endpoint", await test_webhook_endpoint()))
    
    # Summary
    print("\n📊 Diagnostic Summary:")
    print("=" * 30)
    
    all_passed = True
    for check_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{check_name:20} {status}")
        if not passed:
            all_passed = False
    
    if all_passed:
        print("\n🎉 All checks passed! If calls are still not working, the issue might be:")
        print("   • ExoML flow configuration")
        print("   • Customer's phone network/settings")
        print("   • Carrier-specific blocking")
    else:
        print("\n⚠️  Some checks failed. Please address the issues above.")
    
    generate_troubleshooting_report()

if __name__ == "__main__":
    asyncio.run(main())
