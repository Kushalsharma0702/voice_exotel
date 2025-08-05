#!/usr/bin/env python3
"""
Quick database test script
"""
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("🚀 Starting database test...")

try:
    print("1. Testing basic imports...")
    import sqlalchemy
    print(f"   SQLAlchemy version: {sqlalchemy.__version__}")
    
    import psycopg2
    print(f"   psycopg2 imported successfully")
    
    print("2. Testing database schema imports...")
    from database.schemas import DATABASE_URL
    print(f"   DATABASE_URL: {DATABASE_URL}")
    
    from database.schemas import DatabaseManager
    print("   DatabaseManager imported")
    
    from database.schemas import init_database, get_database_info
    print("   Functions imported")
    
    print("3. Testing database initialization...")
    init_database()
    print("   ✅ Database initialization completed!")
    
    print("4. Getting database info...")
    get_database_info()
    
    print("\n🎉 All tests passed!")
    
except Exception as e:
    print(f"❌ Test failed: {e}")
    import traceback
    traceback.print_exc()
