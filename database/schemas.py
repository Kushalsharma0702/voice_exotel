"""
Database schemas for Voice Assistant Application
Handles call sessions, customer data, and call status tracking
"""

from sqlalchemy import create_engine, Column, String, DateTime, Text, JSON, Boolean, Integer, ForeignKey, text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
import uuid
from datetime import datetime, timedelta
import os
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

Base = declarative_base()

class Customer(Base):
    __tablename__ = 'customers'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    phone_number = Column(String(20), nullable=False, unique=True)
    state = Column(String(100))
    loan_id = Column(String(50))
    amount = Column(String(20))
    due_date = Column(String(50))
    language_code = Column(String(10), default='hi-IN')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow) # Corrected syntax
    
    # Relationships
    call_sessions = relationship("CallSession", back_populates="customer")

class CallSession(Base):
    __tablename__ = 'call_sessions'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    call_sid = Column(String(100), unique=True, nullable=False)  # Exotel Call SID
    customer_id = Column(UUID(as_uuid=True), ForeignKey('customers.id'), nullable=False)
    websocket_session_id = Column(String(100))  # WebSocket session ID
    
    # Call details
    status = Column(String(50), default='initiated')  # initiated, in_progress, agent_transfer, completed, failed, not_picked
    call_direction = Column(String(20), default='outbound')  # outbound, inbound
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime)
    duration = Column(Integer)  # in seconds
    
    # Exotel specific data
    exotel_data = Column(JSON)  # Store raw Exotel response
    agent_transfer_time = Column(DateTime)
    agent_number = Column(String(20))
    
    # AI Conversation data
    conversation_transcript = Column(JSON)  # Store conversation history
    intent_detected = Column(String(100))
    language_detected = Column(String(10))
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    customer = relationship("Customer", back_populates="call_sessions")
    status_updates = relationship("CallStatusUpdate", back_populates="call_session", cascade="all, delete-orphan")

class CallStatusUpdate(Base):
    __tablename__ = 'call_status_updates'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    call_session_id = Column(UUID(as_uuid=True), ForeignKey('call_sessions.id'), nullable=False)
    
    status = Column(String(50), nullable=False)
    message = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)
    extra_data = Column(JSON)  # Changed from 'metadata' to 'extra_data' to avoid conflict
    
    # Relationships
    call_session = relationship("CallSession", back_populates="status_updates")

class FileUpload(Base):
    __tablename__ = 'file_uploads'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500))
    total_records = Column(Integer)
    processed_records = Column(Integer, default=0)
    failed_records = Column(Integer, default=0)
    upload_status = Column(String(50), default='processing')  # processing, completed, failed
    upload_time = Column(DateTime, default=datetime.utcnow)
    processing_errors = Column(JSON)  # Store any processing errors

# Database connection and session management
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:Kushal07@localhost/voice_assistant_db')

class DatabaseManager:
    def __init__(self):
        try:
            print(f"🔧 Initializing database connection to: {DATABASE_URL}")
            self.engine = create_engine(
                DATABASE_URL, 
                echo=True,  # Enable SQL logging for debugging
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                pool_recycle=3600
            )
            self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
            print("✅ Database engine initialized successfully")
        except Exception as e:
            print(f"❌ Failed to initialize database engine: {e}")
            print(f"   Database URL: {DATABASE_URL}")
            raise
        
    def create_tables(self):
        """Create all tables if they don't exist"""
        try:
            print("🔧 Creating database tables...")
            
            # Get all table names that will be created
            table_names = [table.name for table in Base.metadata.tables.values()]
            print(f"📋 Tables to create: {', '.join(table_names)}")
            
            Base.metadata.create_all(bind=self.engine)
            
            # Confirm each table was created
            print("✅ Database schema creation completed!")
            for table_name in table_names:
                print(f"   ✓ Table '{table_name}' created successfully")
            
            print(f"🎉 Total {len(table_names)} tables created in database")
            return True
        except Exception as e:
            print(f"❌ Failed to create tables: {e}")
            return False
        
    def get_session(self):
        """Get a database session with error handling"""
        try:
            session = self.SessionLocal()
            return session
        except Exception as e:
            print(f"❌ Failed to create database session: {e}")
            raise
            
    def close_session(self, session):
        """Close database session safely"""
        try:
            session.close()
        except Exception as e:
            print(f"❌ Error closing database session: {e}")
    
    def test_connection(self):
        """Test database connection"""
        try:
            print("🔌 Testing database connection...")
            session = self.get_session()
            session.execute(text("SELECT 1"))
            self.close_session(session)
            print("✅ Database connection test passed")
            return True
        except Exception as e:
            print(f"❌ Database connection test failed: {e}")
            return False

# Global database manager instance
db_manager = DatabaseManager()

def init_database():
    """Initialize database and create tables"""
    try:
        print("🚀 Initializing Voice Assistant Database...")
        print("=" * 50)
        
        if db_manager.test_connection():
            print("✅ Database connection successful")
            print(f"🔗 Connected to: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else 'database'}")
            
            if db_manager.create_tables():
                print("=" * 50)
                print("🎉 Database initialization completed successfully!")
                print("📊 Database schema status:")
                print("   • Customer table: Ready for customer data")
                print("   • CallSession table: Ready for call tracking")
                print("   • CallStatusUpdate table: Ready for status updates")
                print("   • FileUpload table: Ready for file management")
                print("=" * 50)
                return True
            else:
                print("❌ Failed to create database tables")
                return False
        else:
            print("❌ Database connection failed")
            print("💡 Please check your DATABASE_URL in .env file")
            return False
    except Exception as e:
        print(f"❌ Failed to initialize database: {e}")
        return False

# Status constants
class CallStatus:
    INITIATED = "initiated"
    RINGING = "ringing"
    IN_PROGRESS = "in_progress"
    AGENT_TRANSFER = "agent_transfer"
    COMPLETED = "completed"
    FAILED = "failed"
    NOT_PICKED = "not_picked"
    DISCONNECTED = "disconnected"
    BUSY = "busy"
    NO_ANSWER = "no_answer"

# Helper functions for database operations
def get_customer_by_phone(session, phone_number: str) -> Optional['Customer']:
    """Get customer by phone number"""
    try:
        return session.query(Customer).filter(Customer.phone_number == phone_number).first()
    except Exception as e:
        print(f"❌ Error getting customer by phone: {e}")
        return None

def create_customer(session, customer_data: dict) -> Optional['Customer']:
    """Create a new customer record"""
    try:
        customer = Customer(**customer_data)
        session.add(customer)
        session.commit()
        session.refresh(customer)
        print(f"✅ Created customer: {customer.name} ({customer.phone_number})")
        return customer
    except Exception as e:
        session.rollback()
        print(f"❌ Error creating customer: {e}")
        return None

def create_call_session(session, call_sid: str, customer_id: str, websocket_session_id: str = None) -> Optional['CallSession']:
    """Create a new call session"""
    try:
        call_session = CallSession(
            call_sid=call_sid,
            customer_id=customer_id,
            websocket_session_id=websocket_session_id,
            status=CallStatus.INITIATED
        )
        session.add(call_session)
        session.commit()
        session.refresh(call_session)
        print(f"✅ Created call session: {call_sid} for customer {customer_id}")
        return call_session
    except Exception as e:
        session.rollback()
        print(f"❌ Error creating call session: {e}")
        return None

def update_call_status(session, call_sid: str, status: str, message: str = None, extra_data: dict = None) -> Optional['CallSession']:
    """Update call status and create status update record"""
    try:
        call_session = session.query(CallSession).filter(CallSession.call_sid == call_sid).first()
        if call_session:
            # Update main status
            call_session.status = status
            call_session.updated_at = datetime.utcnow()
            
            # Create status update record
            status_update = CallStatusUpdate(
                call_session_id=call_session.id,
                status=status,
                message=message,
                extra_data=extra_data
            )
            session.add(status_update)
            session.commit()
            print(f"✅ Updated call {call_sid} status to: {status}")
            return call_session
        else:
            print(f"⚠️ Call session not found: {call_sid}")
        return None
    except Exception as e:
        session.rollback()
        print(f"❌ Error updating call status: {e}")
        return None

def get_call_session_by_sid(session, call_sid: str) -> Optional['CallSession']:
    """Get call session by Exotel SID"""
    try:
        return session.query(CallSession).filter(CallSession.call_sid == call_sid).first()
    except Exception as e:
        print(f"❌ Error getting call session by SID: {e}")
        return None

def get_customers_list(session, limit: int = 100, offset: int = 0) -> List['Customer']:
    """Get list of customers with pagination"""
    try:
        return session.query(Customer).offset(offset).limit(limit).all()
    except Exception as e:
        print(f"❌ Error getting customers list: {e}")
        return []

def get_call_sessions_by_status(session, status: str, limit: int = 50) -> List['CallSession']:
    """Get call sessions by status"""
    try:
        return session.query(CallSession).filter(CallSession.status == status).limit(limit).all()
    except Exception as e:
        print(f"❌ Error getting call sessions by status: {e}")
        return []

def get_customer_call_history(session, customer_id: str) -> List['CallSession']:
    """Get call history for a specific customer"""
    try:
        return session.query(CallSession).filter(CallSession.customer_id == customer_id).order_by(CallSession.created_at.desc()).all()
    except Exception as e:
        print(f"❌ Error getting customer call history: {e}")
        return []

def cleanup_old_sessions(session, days_old: int = 7) -> int:
    """Clean up old call sessions older than specified days"""
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        old_sessions = session.query(CallSession).filter(CallSession.created_at < cutoff_date).all()
        count = len(old_sessions)
        
        for session_obj in old_sessions:
            session.delete(session_obj)
        
        session.commit()
        if count > 0:
            print(f"✅ Cleaned up {count} old call sessions (older than {days_old} days)")
        return count
    except Exception as e:
        session.rollback()
        print(f"❌ Error cleaning up old sessions: {e}")
        return 0

def print_database_info():
    """Print detailed information about the database schema"""
    print("\n" + "=" * 60)
    print("📊 VOICE ASSISTANT DATABASE SCHEMA INFORMATION")
    print("=" * 60)
    
    print("\n🏢 DATABASE TABLES:")
    print("-" * 40)
    
    tables_info = [
        {
            "name": "customers",
            "description": "Stores customer information and contact details",
            "key_fields": ["id", "name", "phone_number", "state", "loan_id"]
        },
        {
            "name": "call_sessions", 
            "description": "Tracks individual call sessions with Exotel",
            "key_fields": ["id", "call_sid", "customer_id", "status", "start_time"]
        },
        {
            "name": "call_status_updates",
            "description": "Records real-time status changes for calls",
            "key_fields": ["id", "call_session_id", "status", "timestamp"]
        },
        {
            "name": "file_uploads",
            "description": "Manages uploaded customer data files",
            "key_fields": ["id", "filename", "total_records", "upload_status"]
        }
    ]
    
    for table in tables_info:
        print(f"📋 {table['name'].upper()}")
        print(f"   Purpose: {table['description']}")
        print(f"   Key Fields: {', '.join(table['key_fields'])}")
        print()
    
    print("🔄 CALL STATUS FLOW:")
    print("-" * 40)
    statuses = [
        CallStatus.INITIATED,
        CallStatus.RINGING, 
        CallStatus.IN_PROGRESS,
        CallStatus.AGENT_TRANSFER,
        CallStatus.COMPLETED
    ]
    print(" → ".join(statuses))
    
    print(f"\n🌐 DATABASE URL: {DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else 'Not configured'}")
    print("=" * 60)

def get_database_info():
    """Alias for print_database_info for backwards compatibility"""
    print_database_info()

# Initialize database info display
if __name__ == "__main__":
    print("🧪 Database Schema Module Loaded")
    print_database_info()
