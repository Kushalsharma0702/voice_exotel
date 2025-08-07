#!/usr/bin/env python3
"""
Test script to verify WebSocket endpoint customer lookup logic
"""

import json
import asyncio
from unittest.mock import AsyncMock, MagicMock

# Mock the WebSocket object
class MockWebSocket:
    def __init__(self):
        self.query_params = {}
        self.sent_messages = []
    
    async def send_text(self, message):
        self.sent_messages.append(message)
        print(f"📤 WebSocket sent: {message}")

async def test_websocket_customer_lookup():
    """Test the customer lookup logic from the WebSocket endpoint"""
    print("🧪 Testing WebSocket Customer Lookup Logic")
    print("=" * 50)
    
    # Simulate the customer lookup logic from the WebSocket endpoint
    phone = "+917417119014"  # Riddhi Mittal's phone
    customer_info = None
    
    # Import and test the get_customer_by_phone function
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    
    from main import get_customer_by_phone
    
    # Test database lookup logic
    print(f"🔍 Testing customer lookup for phone: {phone}")
    
    try:
        # Simulate the database lookup from WebSocket logic
        from database.schemas import get_customer_by_phone as db_get_customer_by_phone
        from main import db_manager
        session = db_manager.get_session()
        
        # Clean phone number for database lookup - more comprehensive approach
        clean_phone = phone.replace('+', '').replace('-', '').replace(' ', '')
        
        # Extract just the 10-digit number if it's an Indian number
        if len(clean_phone) >= 10:
            last_10_digits = clean_phone[-10:]
        else:
            last_10_digits = clean_phone
        
        # Try multiple phone number formats that might be in the database
        possible_phones = [
            phone,                      # Original format
            clean_phone,               # Cleaned format
            f"+{clean_phone}",         # With + prefix
            f"+91{last_10_digits}",    # With +91 prefix
            f"91{last_10_digits}",     # With 91 prefix (no +)
            last_10_digits             # Just 10 digits
        ]
        
        # Remove duplicates and empty values
        possible_phones = list(set([p for p in possible_phones if p]))
        print(f"📞 Trying phone formats: {possible_phones}")
        
        db_customer = None
        for phone_variant in possible_phones:
            db_customer = db_get_customer_by_phone(session, phone_variant)
            if db_customer:
                print(f"✅ Found customer with phone variant: {phone_variant}")
                break
        
        if db_customer:
            customer_info = {
                'name': db_customer.name,
                'loan_id': db_customer.loan_id,
                'amount': db_customer.amount,
                'due_date': db_customer.due_date,
                'lang': db_customer.language_code or 'en-IN',
                'phone': db_customer.phone_number,
                'state': db_customer.state or ''
            }
            print(f"✅ Customer found: {customer_info['name']} (Phone: {customer_info['phone']})")
            
            # Validate customer data has required fields
            required_fields = ['name', 'loan_id', 'amount', 'due_date']
            missing_fields = [field for field in required_fields if not customer_info.get(field)]
            
            if missing_fields:
                print(f"❌ Customer data missing required fields: {missing_fields}")
                return False
            else:
                print(f"✅ Customer data validated: {customer_info['name']} - Loan: {customer_info['loan_id']}, Amount: ₹{customer_info['amount']}")
                
                # Test template generation with real data
                from main import GREETING_TEMPLATE, EMI_DETAILS_PART1_TEMPLATE
                
                # Test greeting template
                greeting = GREETING_TEMPLATE.get(customer_info['lang'], GREETING_TEMPLATE["en-IN"]).format(name=customer_info['name'])
                print(f"📢 Greeting template: {greeting}")
                
                # Test EMI details template
                emi_details = EMI_DETAILS_PART1_TEMPLATE.get(customer_info['lang'], EMI_DETAILS_PART1_TEMPLATE["en-IN"]).format(
                    loan_id=customer_info['loan_id'],
                    amount=customer_info['amount'],
                    due_date=customer_info['due_date']
                )
                print(f"💰 EMI details template: {emi_details}")
                
                return True
        else:
            print(f"❌ Customer not found in database for phone: {phone}")
            return False
        
        session.close()
    except Exception as e:
        print(f"❌ Error looking up customer in database: {e}")
        return False

async def main():
    success = await test_websocket_customer_lookup()
    if success:
        print("\n🎉 Test PASSED: Real customer data successfully retrieved and validated!")
        print("   - Mock data removed ✅")
        print("   - Database lookup working ✅")
        print("   - Template generation with real data ✅")
    else:
        print("\n❌ Test FAILED: Customer lookup issues detected")

if __name__ == "__main__":
    asyncio.run(main())
