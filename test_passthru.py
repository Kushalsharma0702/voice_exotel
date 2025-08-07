#!/usr/bin/env python3
"""
Test script for pass-through URL functionality
This script tests the Exotel pass-through handler with sample customer data
"""

import requests
import json
from urllib.parse import urlencode

def test_passthru_handler():
    """Test the pass-through handler with sample customer data"""
    
    base_url = "http://localhost:8000"
    
    # Sample customer data from a more realistic source (e.g., a dict)
    customer_data = {
        "customer_id": "cust_123",
        "customer_name": "Riddhi Mittal",
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
    
    print("🧪 Testing Pass-Through Handler...")
    print(f"📞 Customer: {customer_data['customer_name']}")
    print(f"💰 Loan: {customer_data['loan_id']} - ₹{customer_data['amount']}")
    
    try:
        # Test GET request with query parameters
        query_string = urlencode(customer_data)
        url = f"{base_url}/passthru-handler?{query_string}"
        
        print(f"\n🔗 Testing URL: {url}")
        
        response = requests.get(url, timeout=10)
        
        print(f"\n📋 Response Status: {response.status_code}")
        print(f"📄 Content Type: {response.headers.get('content-type', 'unknown')}")
        
        if response.status_code == 200:
            print("✅ Pass-through handler is working!")
            print("\n📄 ExoML Response Preview:")
            content = response.text
            # Show first 200 characters
            print(content[:200] + "..." if len(content) > 200 else content)
        else:
            print(f"❌ Failed with status {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Error testing pass-through handler: {e}")
        print("Make sure the server is running with: python main.py")

def test_gather_response():
    """Test the gather response handler"""
    
    base_url = "http://localhost:8000"
    
    test_data = {
        "call_sid": "test_call_123",
        "customer_id": "cust_123",
        "Digits": "1"  # Customer pressed 1 for agent transfer
    }
    
    print("\n🎯 Testing Gather Response Handler...")
    
    try:
        query_string = urlencode(test_data)
        url = f"{base_url}/gather-response?{query_string}"
        
        response = requests.get(url, timeout=10)
        
        print(f"📋 Response Status: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ Gather response handler is working!")
            print("\n📄 ExoML Response Preview:")
            content = response.text
            print(content[:200] + "..." if len(content) > 200 else content)
        else:
            print(f"❌ Failed with status {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error testing gather response: {e}")

if __name__ == "__main__":
    print("🚀 Starting Pass-Through URL Tests")
    print("=" * 50)
    
    test_passthru_handler()
    test_gather_response()
    
    print("\n" + "=" * 50)
    print("✅ Tests completed!")
    
    print("\n📋 Next Steps:")
    print("1. Update BASE_URL in .env with your public domain")
    print("2. Configure your Exotel flow to use the pass-through URL")
    print("3. Test with real Exotel calls")
