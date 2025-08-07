#!/usr/bin/env python3
"""
Test script to verify customer data lookup from database
"""

import os
import sys
from dotenv import load_dotenv

# Add current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

from database.schemas import get_customer_by_phone, db_manager

def test_customer_lookup():
    """Test customer lookup functionality"""
    print("🔍 Testing Customer Database Lookup")
    print("=" * 50)
    
    # Get database session
    session = db_manager.get_session()
    
    try:
        # Test phones from our uploaded CSV data
        test_phones = [
            "+917417119014",  # Riddhi Mittal
            "7417119014",
            "+919812345678",  # Aman Verma
            "9812345678",
            "+918765432109",  # Sneha Kapoor
            "8765432109"
        ]
        
        print("Testing phone number lookups:")
        print("-" * 30)
        
        for phone in test_phones:
            # Use the updated function from main.py
            from main import get_customer_by_phone
            customer = get_customer_by_phone(phone)
            if customer:
                print(f"✅ Phone: {phone}")
                print(f"   Name: {customer['name']}")
                print(f"   Loan ID: {customer['loan_id']}")
                print(f"   Amount: ₹{customer['amount']}")
                print(f"   Due Date: {customer['due_date']}")
                print(f"   Language: {customer['lang']}")
                print()
            else:
                print(f"❌ Phone: {phone} - Not found")
        
        # Show all customers in database
        from database.schemas import Customer
        all_customers = session.query(Customer).all()
        print(f"\n📊 Total customers in database: {len(all_customers)}")
        print("-" * 30)
        
        for customer in all_customers:
            print(f"• {customer.name} ({customer.phone_number}) - Loan: {customer.loan_id}, Amount: ₹{customer.amount}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    test_customer_lookup()
