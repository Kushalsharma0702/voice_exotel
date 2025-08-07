#!/usr/bin/env python3
"""
Test script to verify the updated pass-through handler with working TTS templates
"""
import requests
from urllib.parse import urlencode

import json

def test_updated_passthru_handler():
    """Test the updated pass-through handler with working templates"""
    
    base_url = "http://localhost:8000"
    
    # Load test cases from external JSON file
    try:
        with open("test_cases.json", "r", encoding="utf-8") as f:
            test_cases = json.load(f)
    except FileNotFoundError:
        print("❌ Error: test_cases.json not found. Please create it.")
        return
    except json.JSONDecodeError:
        print("❌ Error: Invalid JSON in test_cases.json.")
        return
    
    print("🧪 Testing Updated Pass-Through Handler with Working TTS Templates")
    print("=" * 70)
    
    for test_case in test_cases:
        print(f"\n📞 Testing: {test_case['name']}")
        print(f"   Customer: {test_case['data']['customer_name']}")
        print(f"   Language: {test_case['data']['language_code']}")
        print(f"   Loan: {test_case['data']['loan_id']} - ₹{test_case['data']['amount']}")
        
        try:
            # Test GET request with query parameters
            query_string = urlencode(test_case['data'])
            url = f"{base_url}/passthru-handler?{query_string}"
            
            response = requests.get(url, timeout=10)
            
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                print("   ✅ SUCCESS - ExoML Response Generated")
                
                # Check if response contains expected elements
                content = response.text
                if '<Say voice="female">' in content:
                    print("   ✅ Contains Say elements for TTS")
                if '<Gather' in content:
                    print("   ✅ Contains Gather for user interaction")
                if test_case['data']['customer_name'] in content:
                    print("   ✅ Contains personalized customer name")
                if test_case['data']['loan_id'] in content:
                    print("   ✅ Contains loan information")
                    
                # Show a sample of the response
                lines = content.split('\n')
                for line in lines[2:5]:  # Show first few Say elements
                    if '<Say' in line:
                        print(f"   📝 Sample: {line.strip()[:80]}...")
                        
            else:
                print(f"   ❌ FAILED - HTTP {response.status_code}")
                print(f"   Error: {response.text[:100]}...")
                
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
    
    print("\n" + "=" * 70)
    print("✅ Pass-Through Handler Tests Completed!")
    
    print("\n📋 Expected Improvements:")
    print("1. ✅ Multi-language templates from working file.py")
    print("2. ✅ Proper customer name personalization")
    print("3. ✅ Structured EMI information")
    print("4. ✅ Language-aware agent prompts")
    print("5. ✅ Better ExoML structure for TTS")

if __name__ == "__main__":
    test_updated_passthru_handler()
