#!/usr/bin/env python3
"""
Quick Database Wipe Script (No Confirmations)
WARNING: This script will immediately wipe ALL data!
Use only for rapid development cycles.
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

def quick_wipe():
    """Quickly wipe all data without confirmations"""
    print("🧹 Quick Database Wipe - Starting...")
    
    # Wipe PostgreSQL
    try:
        DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:Kushal07@localhost/voice_assistant_db')
        engine = create_engine(DATABASE_URL, echo=False)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # Quick delete all data
        session.execute(text("TRUNCATE call_status_updates, call_sessions, file_uploads, customers RESTART IDENTITY CASCADE;"))
        session.commit()
        session.close()
        print("✅ PostgreSQL data wiped")
        
    except Exception as e:
        print(f"❌ PostgreSQL wipe failed: {e}")
    
    # Wipe Redis
    try:
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.flushdb()
        print("✅ Redis cache wiped")
    except:
        print("⚠️  Redis not available - skipped")
    
    print("🎉 Quick wipe completed!")

if __name__ == "__main__":
    quick_wipe()
