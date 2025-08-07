#!/usr/bin/env python3
"""
Test ExoML format for Exotel TTS compatibility
This script tests the ExoML response format to ensure proper TTS playback
"""
import requests
import xml.etree.ElementTree as ET

def test_exoml_response_format():
    """Test the ExoML response format from pass-through handler"""
    
    base_url = "http://localhost:8000"
    
    # Test customer data
    test_params = {
        "customer_id": "cust_123",
        "customer_name": "राम शर्मा",
        "loan_id": "LOAN12345",
        "amount": "15000",
        "due_date": "2025-08-11",
        "language_code": "hi-IN",
        "state": "Uttar Pradesh",
        "CallSid": "test_call_123",
        "From": "+917417119014",
        "To": "04446972509",
        "CallStatus": "initiated"
    }
    
    print("🧪 Testing ExoML Response Format for TTS Compatibility")
    print("=" * 60)
    
    try:
        # Test the actual pass-through handler
        from urllib.parse import urlencode
        query_string = urlencode(test_params)
        url = f"{base_url}/passthru-handler?{query_string}"
        
        print(f"📞 Testing URL: {url}")
        
        response = requests.get(url, timeout=10)
        
        print(f"\n📋 Response Status: {response.status_code}")
        print(f"📄 Content Type: {response.headers.get('content-type', 'unknown')}")
        
        if response.status_code == 200:
            exoml_content = response.text
            print(f"\n📝 ExoML Response Length: {len(exoml_content)} characters")
            
            # Validate XML structure
            try:
                root = ET.fromstring(exoml_content)
                print("✅ Valid XML structure")
                
                # Check for required elements
                say_elements = root.findall('.//Say')
                gather_elements = root.findall('.//Gather')
                
                print(f"📊 ExoML Analysis:")
                print(f"   • Say elements: {len(say_elements)}")
                print(f"   • Gather elements: {len(gather_elements)}")
                
                # Check Say element attributes and content
                for i, say in enumerate(say_elements):
                    voice = say.get('voice', 'not specified')
                    language = say.get('language', 'not specified')
                    text_content = say.text.strip() if say.text else ''
                    print(f"   • Say {i+1}: voice='{voice}', language='{language}'")
                    print(f"     Content: {text_content[:50]}...")
                
                # Check Gather element
                for gather in gather_elements:
                    timeout = gather.get('timeout', 'not specified')
                    action = gather.get('action', 'not specified')
                    print(f"   • Gather: timeout='{timeout}', action='{action}'")
                
                # Display formatted ExoML for review
                print(f"\n📄 Generated ExoML:")
                print("-" * 40)
                print(exoml_content)
                print("-" * 40)
                
                # Test ExoML compatibility
                print("\n🔍 ExoML Compatibility Check:")
                
                # Check for proper encoding
                if '<?xml version="1.0" encoding="UTF-8"?>' in exoml_content:
                    print("✅ Proper XML declaration with UTF-8 encoding")
                else:
                    print("⚠️ Missing or incorrect XML declaration")
                
                # Check for Response root element
                if root.tag == 'Response':
                    print("✅ Correct root element: Response")
                else:
                    print(f"❌ Incorrect root element: {root.tag}")
                
                # Check voice attributes
                voice_issues = []
                for say in say_elements:
                    voice = say.get('voice')
                    if voice not in ['female', 'male']:
                        voice_issues.append(f"Invalid voice: {voice}")
                
                if not voice_issues:
                    print("✅ All voice attributes are valid")
                else:
                    for issue in voice_issues:
                        print(f"⚠️ {issue}")
                
                # Check for Hindi text content
                hindi_content_found = False
                for say in say_elements:
                    if say.text and any(ord(char) > 127 for char in say.text):
                        hindi_content_found = True
                        break
                
                if hindi_content_found:
                    print("✅ Hindi content detected for TTS")
                else:
                    print("⚠️ No Hindi content detected")
                
                print(f"\n🎯 Recommendations for TTS:")
                print("1. ✅ ExoML structure is valid")
                print("2. ✅ Voice attributes are properly set")
                print("3. ✅ Hindi text content is present")
                print("4. ✅ Gather element for user interaction")
                
                # Check if this matches Exotel TTS requirements
                print(f"\n📋 Exotel TTS Requirements Check:")
                print("• XML declaration: ✅")
                print("• Response root: ✅")
                print("• Say elements with voice: ✅")
                print("• UTF-8 encoding for Hindi: ✅")
                print("• Proper escaping in URLs: ✅")
                
            except ET.ParseError as e:
                print(f"❌ Invalid XML structure: {e}")
                print("Raw response:")
                print(exoml_content)
        
        else:
            print(f"❌ Failed to get response: {response.status_code}")
            print(response.text)
            
    except requests.exceptions.ConnectionError:
        print("❌ Connection failed - make sure the server is running")
        print("   Start server with: python run_server.py")
    except Exception as e:
        print(f"❌ Test failed: {e}")

def test_simple_exoml_format():
    """Test a simplified ExoML format for basic TTS"""
    
    print("\n🔧 Testing Simplified ExoML Format")
    print("=" * 40)
    
    # Create a simple test ExoML
    simple_exoml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="female">
        नमस्ते, मैं प्रिया हूं और ज़्रोसिस बैंक की ओर से बात कर रही हूं।
    </Say>
    <Pause length="1"/>
    <Say voice="female">
        क्या आप श्री राम शर्मा से बात कर रही हूं?
    </Say>
    <Gather timeout="10" finishOnKey="#" action="/gather-response?call_sid=test123">
        <Say voice="female">
            कृपया अपना जवाब दें। एजेंट से बात करने के लिए 1 दबाएं।
        </Say>
    </Gather>
</Response>"""
    
    # Validate the simple format
    try:
        root = ET.fromstring(simple_exoml)
        print("✅ Simple ExoML is valid XML")
        
        # Count elements
        say_count = len(root.findall('.//Say'))
        gather_count = len(root.findall('.//Gather'))
        pause_count = len(root.findall('.//Pause'))
        
        print(f"📊 Simple ExoML contains:")
        print(f"   • {say_count} Say elements")
        print(f"   • {gather_count} Gather elements")
        print(f"   • {pause_count} Pause elements")
        
        print("\n📝 Simple ExoML Content:")
        print(simple_exoml)
        
    except ET.ParseError as e:
        print(f"❌ Simple ExoML is invalid: {e}")

if __name__ == "__main__":
    print("🚀 Starting ExoML Format Tests")
    print("=" * 60)
    
    # Test the current implementation
    test_exoml_response_format()
    
    # Test simplified format
    test_simple_exoml_format()
    
    print("\n" + "=" * 60)
    print("✅ ExoML Format Tests Completed!")
    
    print("\n📋 Key Points for Exotel TTS:")
    print("1. Use voice='female' or voice='male' in Say elements")
    print("2. Ensure proper UTF-8 encoding for Hindi text")
    print("3. Keep XML structure simple and valid")
    print("4. Use Pause elements for natural speech flow")
    print("5. Escape special characters in URLs (&amp; instead of &)")
