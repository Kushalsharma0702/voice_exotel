#!/usr/bin/env python3
"""
Test script for CSV upload and call triggering
This script tests the bulk call functionality with your CSV format
"""

import requests
import json
import io

def test_csv_upload_and_calls():
    """Test CSV upload and bulk call triggering"""
    
    base_url = "http://localhost:8000"
    
    # Read CSV content from the test data file
    try:
        with open("test_data.csv", "r", encoding="utf-8") as f:
            csv_content = f.read()
    except FileNotFoundError:
        print("❌ Error: test_data.csv not found. Please create it.")
        return
    
    print("🧪 Testing CSV Upload and Call Triggering...")
    print("=" * 60)
    
    try:
        # Step 1: Upload CSV file
        print("📤 Step 1: Uploading CSV file...")
        
        files = {
            'file': ('customers.csv', io.StringIO(csv_content), 'text/csv')
        }
        
        upload_response = requests.post(
            f"{base_url}/api/upload-customers",
            files=files,
            timeout=10
        )
        
        print(f"📋 Upload Status: {upload_response.status_code}")
        
        if upload_response.status_code == 200:
            upload_result = upload_response.json()
            print("✅ CSV upload successful!")
            print(f"   Processed: {upload_result.get('processed_records', 0)} customers")
            print(f"   Failed: {upload_result.get('failed_records', 0)} customers")
            
            customers = upload_result.get('customers', [])
            print(f"\n📋 Uploaded Customers:")
            for i, customer in enumerate(customers[:3], 1):  # Show first 3
                print(f"   {i}. {customer.get('name')} - {customer.get('phone_number')}")
                print(f"      Loan: {customer.get('loan_id')} - ₹{customer.get('amount')}")
            
            if len(customers) > 3:
                print(f"   ... and {len(customers) - 3} more")
            
            # Step 2: Trigger bulk calls from uploaded data
            print(f"\n🚀 Step 2: Triggering calls for {len(customers)} customers...")
            
            bulk_call_data = {
                "customer_data": customers,
                "websocket_id": "test_session_123"
            }
            
            call_response = requests.post(
                f"{base_url}/api/trigger-bulk-calls",
                headers={'Content-Type': 'application/json'},
                data=json.dumps(bulk_call_data),
                timeout=30
            )
            
            print(f"📋 Call Trigger Status: {call_response.status_code}")
            
            if call_response.status_code == 200:
                call_result = call_response.json()
                print("✅ Bulk calls triggered successfully!")
                print(f"   Total Calls: {call_result.get('total_calls', 0)}")
                print(f"   Successful: {call_result.get('successful_calls', 0)}")
                print(f"   Failed: {call_result.get('failed_calls', 0)}")
                
                # Show some call results
                results = call_result.get('results', [])
                print(f"\n📞 Call Results (first 3):")
                for i, result in enumerate(results[:3], 1):
                    customer_data = result.get('customer_data', {})
                    success = result.get('success', False)
                    print(f"   {i}. {customer_data.get('name', 'Unknown')} - {'✅' if success else '❌'}")
                    if not success:
                        print(f"      Error: {result.get('error', 'Unknown error')}")
                
            else:
                print(f"❌ Failed to trigger calls: {call_response.status_code}")
                try:
                    error_detail = call_response.json()
                    print(f"   Error: {error_detail}")
                except:
                    print(f"   Raw response: {call_response.text}")
        
        else:
            print(f"❌ Failed to upload CSV: {upload_response.status_code}")
            try:
                error_detail = upload_response.json()
                print(f"   Error: {error_detail}")
            except:
                print(f"   Raw response: {upload_response.text}")
                
    except requests.exceptions.ConnectionError:
        print("❌ Connection failed - make sure the server is running")
        print("   Start server with: python main.py")
    except Exception as e:
        print(f"❌ Test failed: {e}")

def test_existing_customers_call():
    """Test triggering calls for existing customers in database"""
    
    base_url = "http://localhost:8000"
    
    print("\n🧪 Testing Existing Customers Call...")
    print("=" * 60)
    
    try:
        # Trigger calls for all existing customers
        bulk_call_data = {
            "websocket_id": "test_session_456"
        }
        
        call_response = requests.post(
            f"{base_url}/api/trigger-bulk-calls",
            headers={'Content-Type': 'application/json'},
            data=json.dumps(bulk_call_data),
            timeout=30
        )
        
        print(f"📋 Call Trigger Status: {call_response.status_code}")
        
        if call_response.status_code == 200:
            call_result = call_response.json()
            print("✅ Bulk calls for existing customers triggered!")
            print(f"   Total Calls: {call_result.get('total_calls', 0)}")
            print(f"   Successful: {call_result.get('successful_calls', 0)}")
            print(f"   Failed: {call_result.get('failed_calls', 0)}")
        else:
            print(f"❌ Failed: {call_response.status_code}")
            try:
                error_detail = call_response.json()
                print(f"   Error: {error_detail}")
            except:
                print(f"   Raw response: {call_response.text}")
                
    except Exception as e:
        print(f"❌ Test failed: {e}")

if __name__ == "__main__":
    print("🚀 Starting Bulk Call Tests")
    print("=" * 60)
    
    # Test CSV upload and calls
    test_csv_upload_and_calls()
    
    # Test existing customers calls
    test_existing_customers_call()
    
    print("\n" + "=" * 60)
    print("✅ Tests completed!")
    
    print("\n📋 Next Steps:")
    print("1. Check server logs for detailed call information")
    print("2. Verify Exotel configuration and credentials")
    print("3. Test with real phone numbers when ready")
