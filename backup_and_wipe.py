#!/usr/bin/env python3
"""
Database Backup Script for Voice Assistant Application
Creates a backup before wiping data
"""

import os
import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import subprocess
import json

# Load environment variables
load_dotenv()

def create_backup():
    """Create a backup of the database"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = Path("backups")
    backup_dir.mkdir(exist_ok=True)
    
    print(f"🗂️  Creating backup at {timestamp}...")
    
    # Parse database URL
    db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:Kushal07@localhost/voice_assistant_db')
    
    # Extract database info from URL
    # Format: postgresql://user:pass@host:port/dbname
    if db_url.startswith('postgresql://'):
        # Simple parsing (you might want to use urllib.parse for production)
        db_parts = db_url.replace('postgresql://', '').split('/')
        connection_part = db_parts[0]
        db_name = db_parts[1] if len(db_parts) > 1 else 'voice_assistant_db'
        
        if '@' in connection_part:
            auth_part, host_part = connection_part.split('@')
            user, password = auth_part.split(':')
            host = host_part.split(':')[0] if ':' in host_part else host_part
            port = host_part.split(':')[1] if ':' in host_part else '5432'
        else:
            user, password, host, port = 'postgres', '', 'localhost', '5432'
    
    backup_file = backup_dir / f"voice_assistant_backup_{timestamp}.sql"
    
    try:
        # Create PostgreSQL dump
        env = os.environ.copy()
        env['PGPASSWORD'] = password
        
        cmd = [
            'pg_dump',
            '-h', host,
            '-p', port,
            '-U', user,
            '-d', db_name,
            '--no-password',
            '--verbose',
            '--file', str(backup_file)
        ]
        
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"✅ Database backup created: {backup_file}")
            print(f"   Size: {backup_file.stat().st_size / 1024:.2f} KB")
            return str(backup_file)
        else:
            print(f"❌ Backup failed: {result.stderr}")
            return None
            
    except FileNotFoundError:
        print("❌ pg_dump not found. Please install PostgreSQL client tools.")
        print("   Ubuntu/Debian: sudo apt install postgresql-client")
        print("   macOS: brew install postgresql")
        return None
    except Exception as e:
        print(f"❌ Backup error: {e}")
        return None

def backup_and_wipe():
    """Create backup then wipe data"""
    print("🗂️  Backup and Wipe Operation")
    print("=" * 40)
    
    # Create backup first
    backup_file = create_backup()
    
    if backup_file:
        print(f"\n✅ Backup completed: {backup_file}")
        
        # Ask if user wants to proceed with wipe
        proceed = input("\nProceed with data wipe? (y/N): ").lower()
        
        if proceed == 'y':
            print("\n🧹 Starting wipe operation...")
            # Import and run the quick wipe
            from quick_wipe import quick_wipe
            quick_wipe()
        else:
            print("❌ Wipe cancelled. Backup is saved.")
    else:
        print("❌ Backup failed. Wipe operation cancelled for safety.")

if __name__ == "__main__":
    backup_and_wipe()
