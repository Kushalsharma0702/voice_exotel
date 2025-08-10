#!/usr/bin/env python3
"""
Database Wipe Script for Voice Assistant Application
WARNING: This script will permanently delete ALL data from the database!
Use with extreme caution and only in development/testing environments.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import redis

# Add current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

# Load environment variables
load_dotenv()

# Import database schemas
from database.schemas import Base, DatabaseManager

def confirm_wipe():
    """Ask for user confirmation before wiping data"""
    print("🚨 WARNING: DATABASE WIPE OPERATION 🚨")
    print("=" * 50)
    print("This script will PERMANENTLY DELETE ALL DATA from:")
    print("• PostgreSQL database (all tables)")
    print("• Redis cache (all keys)")
    print("• Call sessions, customers, file uploads, status updates")
    print("=" * 50)
    print("⚠️  THIS ACTION CANNOT BE UNDONE! ⚠️")
    print()
    
    # Get current environment info
    db_url = os.getenv('DATABASE_URL', 'Not configured')
    redis_url = os.getenv('REDIS_URL', 'localhost:6379')
    
    print(f"Target Database: {db_url}")
    print(f"Target Redis: {redis_url}")
    print()
    
    confirmation = input("Type 'WIPE ALL DATA' to confirm (case sensitive): ")
    
    if confirmation != "WIPE ALL DATA":
        print("❌ Operation cancelled. Data is safe.")
        return False
    
    # Double confirmation
    final_confirm = input("Are you absolutely sure? Type 'YES' to proceed: ")
    if final_confirm.upper() != "YES":
        print("❌ Operation cancelled. Data is safe.")
        return False
    
    return True

def wipe_postgresql_data():
    """Wipe all data from PostgreSQL database"""
    print("\n🗑️  Wiping PostgreSQL Database...")
    print("-" * 40)
    
    try:
        # Initialize database connection
        DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:Kushal07@localhost/voice_assistant_db')
        engine = create_engine(DATABASE_URL, echo=False)
        
        # Create session
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # Get all table names
        table_names = [
            'call_status_updates',  # Delete child records first (foreign key constraints)
            'call_sessions',
            'file_uploads', 
            'customers'
        ]
        
        # Disable foreign key constraints temporarily (for PostgreSQL)
        session.execute(text("SET session_replication_role = replica;"))
        
        # Delete data from each table
        total_deleted = 0
        for table_name in table_names:
            try:
                result = session.execute(text(f"DELETE FROM {table_name}"))
                deleted_count = result.rowcount
                total_deleted += deleted_count
                print(f"   ✓ Deleted {deleted_count} records from '{table_name}'")
            except Exception as e:
                print(f"   ⚠️  Could not delete from '{table_name}': {e}")
        
        # Re-enable foreign key constraints
        session.execute(text("SET session_replication_role = DEFAULT;"))
        
        # Reset auto-increment sequences (if any)
        try:
            # Reset sequences for UUID primary keys (not typically needed, but good practice)
            session.execute(text("SELECT setval(pg_get_serial_sequence('customers', 'id'), 1, false);"))
            session.execute(text("SELECT setval(pg_get_serial_sequence('call_sessions', 'id'), 1, false);"))
            print("   ✓ Reset sequence counters")
        except Exception as e:
            # Sequences might not exist, that's okay
            pass
        
        # Commit all changes
        session.commit()
        session.close()
        
        print(f"✅ PostgreSQL wipe completed! Total records deleted: {total_deleted}")
        return True
        
    except Exception as e:
        print(f"❌ Error wiping PostgreSQL database: {e}")
        return False

def wipe_redis_data():
    """Wipe all data from Redis cache"""
    print("\n🗑️  Wiping Redis Cache...")
    print("-" * 40)
    
    try:
        # Connect to Redis
        redis_host = os.getenv('REDIS_HOST', 'localhost')
        redis_port = int(os.getenv('REDIS_PORT', 6379))
        redis_db = int(os.getenv('REDIS_DB', 0))
        
        r = redis.Redis(host=redis_host, port=redis_port, db=redis_db, decode_responses=True)
        
        # Test connection
        r.ping()
        
        # Get all keys
        all_keys = r.keys('*')
        
        if all_keys:
            # Delete all keys
            deleted_count = r.delete(*all_keys)
            print(f"   ✓ Deleted {deleted_count} Redis keys")
        else:
            print("   ✓ Redis cache was already empty")
        
        print("✅ Redis wipe completed!")
        return True
        
    except redis.ConnectionError:
        print("⚠️  Redis not available - skipping Redis wipe")
        return True  # Not critical if Redis is not running
    except Exception as e:
        print(f"❌ Error wiping Redis cache: {e}")
        return False

def recreate_database_schema():
    """Recreate all database tables (fresh schema)"""
    print("\n🔄 Recreating Database Schema...")
    print("-" * 40)
    
    try:
        # Initialize database manager
        db_manager = DatabaseManager()
        
        # Drop all tables first
        Base.metadata.drop_all(db_manager.engine)
        print("   ✓ Dropped all existing tables")
        
        # Recreate all tables
        Base.metadata.create_all(db_manager.engine)
        print("   ✓ Created fresh database schema")
        
        print("✅ Database schema recreation completed!")
        return True
        
    except Exception as e:
        print(f"❌ Error recreating database schema: {e}")
        return False

def main():
    """Main wipe function"""
    print("🧹 Voice Assistant Database Wipe Script")
    print("=" * 50)
    
    # Check if user confirmed the operation
    if not confirm_wipe():
        sys.exit(0)
    
    print("\n🚀 Starting data wipe operation...")
    
    # Track success of each operation
    operations = []
    
    # 1. Wipe PostgreSQL data
    postgres_success = wipe_postgresql_data()
    operations.append(("PostgreSQL Data Wipe", postgres_success))
    
    # 2. Wipe Redis data
    redis_success = wipe_redis_data()
    operations.append(("Redis Cache Wipe", redis_success))
    
    # 3. Recreate database schema (optional, ensures clean state)
    schema_success = recreate_database_schema()
    operations.append(("Database Schema Recreation", schema_success))
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 WIPE OPERATION SUMMARY")
    print("=" * 50)
    
    all_successful = True
    for operation, success in operations:
        status = "✅ SUCCESS" if success else "❌ FAILED"
        print(f"{operation}: {status}")
        if not success:
            all_successful = False
    
    print("=" * 50)
    
    if all_successful:
        print("🎉 ALL DATA SUCCESSFULLY WIPED!")
        print("The database is now clean and ready for fresh data.")
    else:
        print("⚠️  Some operations failed. Please check the errors above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
