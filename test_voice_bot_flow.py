#!/usr/bin/env python3
"""
Test actual call triggering with working TTS templates
This will test the complete call flow from CSV upload to call triggering
"""
import requests
import json
import io
import time

def test_voice_bot_call_flow():
    """Test the complete voice bot call flow"""
    
    base_url = "http://localhost:8000"
    
    print("🧪 Testing Complete Voice Bot Call Flow")
    print("=" * 50)
    
    # Step 1: Test CSV upload with customer data
    print("📤 Step 1: Testing CSV upload...")
    
    # Read CSV content from the test data file
    try:
        with open("test_data.csv", "r", encoding="utf-8") as f:
            csv_content = f.read()
    except FileNotFoundError:
        print("❌ Error: test_data.csv not found. Please create it.")
        return
    
    try:
        files = {
            'file': ('test_customers.csv', io.StringIO(csv_content), 'text/csv')
        }
        
        upload_response = requests.post(
            f"{base_url}/api/upload-customers",
            files=files,
            timeout=10
        )
        
        print(f"   Upload Status: {upload_response.status_code}")
        
        if upload_response.status_code == 200:
            upload_data = upload_response.json()
            print(f"   ✅ Upload successful: {upload_data.get('message', 'No message')}")
            print(f"   📊 Customers processed: {upload_data.get('customers_processed', 0)}")
            
            # Get customer ID from response
            customer_id = None
            if 'data' in upload_data and 'customers' in upload_data['data']:
                customers = upload_data['data']['customers']
                if customers:
                    customer_id = customers[0].get('id')
                    print(f"   🆔 Customer ID: {customer_id}")
            
            # Step 2: Trigger call for uploaded customer
            if customer_id:
                print(f"\n📞 Step 2: Triggering call for customer {customer_id}...")
                
                call_response = requests.post(
                    f"{base_url}/api/trigger-single-call",
                    json={"customer_id": customer_id},
                    timeout=15
                )
                
                print(f"   Call Status: {call_response.status_code}")
                
                if call_response.status_code == 200:
                    call_data = call_response.json()
                    print(f"   ✅ Call triggered successfully")
                    print(f"   📋 Response: {call_data.get('message', 'No message')}")
                    
                    # Extract call details
                    if 'data' in call_data:
                        call_info = call_data['data']
                        exotel_sid = call_info.get('exotel_call_sid')
                        customer_number = call_info.get('customer_number')
                        pass_url = call_info.get('passthru_url')
                        
                        print(f"   📱 Customer Number: {customer_number}")
                        print(f"   🆔 Exotel Call SID: {exotel_sid}")
                        print(f"   🔗 Pass-through URL: {pass_url}")
                        
                        # Step 3: Test the pass-through URL that will be called by Exotel
                        print(f"\n🎙️ Step 3: Testing Pass-through URL (Voice Bot Templates)...")
                        
                        if pass_url:
                            passthru_response = requests.get(pass_url, timeout=10)
                            print(f"   Pass-through Status: {passthru_response.status_code}")
                            
                            if passthru_response.status_code == 200:
                                exoml_content = passthru_response.text
                                print(f"   ✅ ExoML generated successfully")
                                print(f"   📝 ExoML Length: {len(exoml_content)} characters")
                                
                                # Check for Hindi content
                                if "नमस्ते" in exoml_content and "प्रिया" in exoml_content:
                                    print(f"   ✅ Hindi greeting template detected")
                                if "लोन खाता" in exoml_content and "LOAN12345" in exoml_content:
                                    print(f"   ✅ Loan information template detected")
                                if "Gather" in exoml_content:
                                    print(f"   ✅ Interactive gather element detected")
                                
                                print(f"\n📄 Generated ExoML Preview:")
                                print("-" * 30)
                                lines = exoml_content.split('\n')
                                for line in lines[:15]:  # Show first 15 lines
                                    if line.strip():
                                        print(f"   {line}")
                                if len(lines) > 15:
                                    print(f"   ... ({len(lines) - 15} more lines)")
                                print("-" * 30)
                                
                            else:
                                print(f"   ❌ Pass-through failed: {passthru_response.status_code}")
                                print(f"   Error: {passthru_response.text}")
                        
                        # Step 4: Check call status
                        print(f"\n📊 Step 4: Checking call status...")
                        time.sleep(2)  # Wait a moment
                        
                        status_response = requests.get(
                            f"{base_url}/api/call-status/{exotel_sid}",
                            timeout=10
                        )
                        
                        if status_response.status_code == 200:
                            status_data = status_response.json()
                            redis_data = status_data.get('redis_data', {})
                            db_data = status_data.get('database_data', {})
                            
                            print(f"   📋 Call Status Information:")
                            print(f"   • Redis Status: {redis_data.get('status', 'Unknown')}")
                            print(f"   • Database Status: {db_data.get('status', 'Unknown')}")
                            print(f"   • Customer: {db_data.get('customer_name', 'Unknown')}")
                        
                    else:
                        print(f"   ❌ No call data in response")
                
                else:
                    print(f"   ❌ Call trigger failed: {call_response.status_code}")
                    print(f"   Error: {call_response.text}")
            
            else:
                print(f"   ❌ No customer ID found in upload response")
        
        else:
            print(f"   ❌ Upload failed: {upload_response.status_code}")
            print(f"   Error: {upload_response.text}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Connection failed - make sure the server is running")
        print("   Start server with: python run_server.py")
    except Exception as e:
        print(f"❌ Test failed: {e}")

def test_direct_passthru_call():
    """Test direct pass-through URL call"""
    
    base_url = "http://localhost:8000"
    
    print(f"\n🎯 Testing Direct Pass-Through Call")
    print("=" * 40)
    
    # Direct pass-through URL with customer data
    passthru_url = f"{base_url}/passthru-handler"
    params = {
        "customer_id": "direct_test_123",
        "customer_name": "राम शर्मा",
        "loan_id": "LOAN12345",
        "amount": "15000",
        "due_date": "2025-08-11",
        "language_code": "hi-IN",
        "state": "Uttar Pradesh",
        "CallSid": "direct_test_call_123",
        "From": "+917417119014",
        "To": "04446972509",
        "CallStatus": "initiated"
    }
    
    try:
        response = requests.get(passthru_url, params=params, timeout=10)
        
        print(f"📋 Response Status: {response.status_code}")
        print(f"📄 Content Type: {response.headers.get('content-type')}")
        
        if response.status_code == 200:
            content = response.text
            print(f"✅ Direct pass-through successful")
            print(f"📝 Response length: {len(content)} characters")
            
            # Check template content
            checks = [
                ("Hindi greeting", "नमस्ते" in content and "प्रिया" in content),
                ("Bank name", "ज़्रोसिस बैंक" in content),
                ("Customer name", "राम शर्मा" in content),
                ("Loan ID", "LOAN12345" in content),
                ("Amount", "15000" in content),
                ("Gather element", "<Gather" in content),
                ("Voice attribute", 'voice="female"' in content)
            ]
            
            print(f"\n🔍 Template Verification:")
            for check_name, check_result in checks:
                status = "✅" if check_result else "❌"
                print(f"   {status} {check_name}")
            
            # Show sample content
            print(f"\n📄 Sample ExoML Content:")
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if line.strip() and i < 10:
                    print(f"   {line}")
            
        else:
            print(f"❌ Direct pass-through failed: {response.status_code}")
            print(response.text)
            
    except Exception as e:
        print(f"❌ Direct test failed: {e}")

if __name__ == "__main__":
    print("🚀 Starting Voice Bot Call Flow Tests")
    print("=" * 50)
    
    # Test complete flow
    test_voice_bot_call_flow()
    
    # Test direct pass-through
    test_direct_passthru_call()
    
    print("\n" + "=" * 50)
    print("✅ Voice Bot Call Flow Tests Completed!")
    
    print(f"\n📋 Expected Results:")
    print("1. ✅ CSV upload should work")
    print("2. ✅ Call trigger should work")  
    print("3. ✅ Pass-through URL should generate proper ExoML")
    print("4. ✅ Hindi templates should be present")
    print("5. ✅ Voice bot should speak instead of transferring directly")
    
    print(f"\n🎯 Next Steps:")
    print("• If tests pass, the voice bot templates are working")
    print("• Check Exotel logs for actual call execution")
    print("• Verify TTS audio quality in real calls")
    print("• Test with actual phone numbers when ready")
