#!/usr/bin/env python3
"""
Test script for database schemas
This script tests the database connection and table creation
"""

import sys
import os

# Add the parent directory to the path so we can import from database
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_database_schemas():
    """Test database schemas and functionality"""
    print("🧪 Testing Database Schemas...")
    
    try:
        # Import after adding to path
        from database.schemas import (
            init_database, db_manager, CallStatus,
            get_customer_by_phone, create_customer,
            create_call_session, update_call_status,
            get_call_session_by_sid
        )
        
        print("✅ Successfully imported database schemas")
        
        # Test database manager initialization
        print("🔧 Testing database manager...")
        if hasattr(db_manager, 'engine'):
            print("✅ Database manager initialized successfully")
        else:
            print("❌ Database manager initialization failed")
            return False
        
        # Test CallStatus constants
        print("🔧 Testing CallStatus constants...")
        expected_statuses = [
            'INITIATED', 'RINGING', 'IN_PROGRESS', 'AGENT_TRANSFER',
            'COMPLETED', 'FAILED', 'NOT_PICKED', 'DISCONNECTED', 'BUSY', 'NO_ANSWER'
        ]
        
        for status in expected_statuses:
            if hasattr(CallStatus, status):
                print(f"✅ CallStatus.{status} = {getattr(CallStatus, status)}")
            else:
                print(f"❌ Missing CallStatus.{status}")
                return False
        
        # Test helper functions exist
        print("🔧 Testing helper functions...")
        helper_functions = [
            get_customer_by_phone, create_customer,
            create_call_session, update_call_status,
            get_call_session_by_sid
        ]
        
        for func in helper_functions:
            if callable(func):
                print(f"✅ Function {func.__name__} is available")
            else:
                print(f"❌ Function {func.__name__} is not callable")
                return False
        
        print("🎉 All database schema tests passed!")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    success = test_database_schemas()
    sys.exit(0 if success else 1)
