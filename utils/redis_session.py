"""
Redis Session Manager for Voice Assistant Application
Handles WebSocket sessions, call state, and temporary data storage
"""

import redis
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import os
from dotenv import load_dotenv

load_dotenv()

class RedisSessionManager:
    def __init__(self):
        self.redis_host = os.getenv('REDIS_HOST', 'localhost')
        self.redis_port = int(os.getenv('REDIS_PORT', 6379))
        self.redis_password = os.getenv('REDIS_PASSWORD', None)
        self.redis_db = int(os.getenv('REDIS_DB', 0))
        
        # Connection pool for better performance
        self.pool = redis.ConnectionPool(
            host=self.redis_host,
            port=self.redis_port,
            password=self.redis_password,
            db=self.redis_db,
            decode_responses=True,
            max_connections=20
        )
        self.redis_client = redis.Redis(connection_pool=self.pool)
        
        # Session expiration times
        self.websocket_session_ttl = 3600  # 1 hour
        self.call_session_ttl = 7200  # 2 hours
        self.temp_data_ttl = 1800  # 30 minutes
        
    def test_connection(self):
        """Test Redis connection"""
        try:
            self.redis_client.ping()
            print("✅ Redis connection successful")
            return True
        except Exception as e:
            print(f"❌ Redis connection failed: {e}")
            return False
    
    # WebSocket Session Management
    def create_websocket_session(self, websocket_id: str, client_info: Dict[str, Any]) -> str:
        """Create a new WebSocket session"""
        session_data = {
            'websocket_id': websocket_id,
            'client_info': client_info,
            'created_at': datetime.utcnow().isoformat(),
            'status': 'active',
            'call_sessions': []  # List of call SIDs associated with this WebSocket
        }
        
        key = f"ws_session:{websocket_id}"
        self.redis_client.setex(key, self.websocket_session_ttl, json.dumps(session_data))
        return websocket_id
    
    def get_websocket_session(self, websocket_id: str) -> Optional[Dict[str, Any]]:
        """Get WebSocket session data"""
        key = f"ws_session:{websocket_id}"
        data = self.redis_client.get(key)
        return json.loads(data) if data else None
    
    def update_websocket_session(self, websocket_id: str, updates: Dict[str, Any]):
        """Update WebSocket session data"""
        session_data = self.get_websocket_session(websocket_id)
        if session_data:
            session_data.update(updates)
            session_data['updated_at'] = datetime.utcnow().isoformat()
            key = f"ws_session:{websocket_id}"
            self.redis_client.setex(key, self.websocket_session_ttl, json.dumps(session_data))
            return True
        return False
    
    def remove_websocket_session(self, websocket_id: str):
        """Remove WebSocket session"""
        key = f"ws_session:{websocket_id}"
        self.redis_client.delete(key)
    
    # Call Session Management
    def create_call_session(self, call_sid: str, customer_data: Dict[str, Any], websocket_id: str = None) -> str:
        """Create a new call session with unique call SID"""
        session_data = {
            'call_sid': call_sid,
            'customer_data': customer_data,
            'websocket_id': websocket_id,
            'status': 'initiated',
            'created_at': datetime.utcnow().isoformat(),
            'conversation_history': [],
            'status_history': [
                {
                    'status': 'initiated',
                    'timestamp': datetime.utcnow().isoformat(),
                    'message': 'Call session created'
                }
            ]
        }
        
        key = f"call_session:{call_sid}"
        self.redis_client.setex(key, self.call_session_ttl, json.dumps(session_data))
        
        # Link call session to WebSocket session
        if websocket_id:
            self.link_call_to_websocket(websocket_id, call_sid)
        
        return call_sid
    
    def get_call_session(self, call_sid: str) -> Optional[Dict[str, Any]]:
        """Get call session data"""
        key = f"call_session:{call_sid}"
        data = self.redis_client.get(key)
        return json.loads(data) if data else None
    
    def update_call_session(self, call_sid: str, updates: Dict[str, Any]):
        """Update call session data"""
        session_data = self.get_call_session(call_sid)
        if session_data:
            session_data.update(updates)
            session_data['updated_at'] = datetime.utcnow().isoformat()
            key = f"call_session:{call_sid}"
            self.redis_client.setex(key, self.call_session_ttl, json.dumps(session_data))
            return True
        return False
    
    def update_call_status(self, call_sid: str, status: str, message: str = None, metadata: Dict[str, Any] = None):
        """Update call status and add to status history"""
        session_data = self.get_call_session(call_sid)
        if session_data:
            # Update current status
            session_data['status'] = status
            session_data['updated_at'] = datetime.utcnow().isoformat()
            
            # Add to status history
            status_update = {
                'status': status,
                'timestamp': datetime.utcnow().isoformat(),
                'message': message,
                'metadata': metadata or {}
            }
            session_data['status_history'].append(status_update)
            
            # Store updated session
            key = f"call_session:{call_sid}"
            self.redis_client.setex(key, self.call_session_ttl, json.dumps(session_data))
            
            # Notify WebSocket if connected
            if session_data.get('websocket_id'):
                self.notify_websocket(session_data['websocket_id'], {
                    'type': 'status_update',
                    'call_sid': call_sid,
                    'status': status,
                    'message': message,
                    'timestamp': status_update['timestamp']
                })
            
            return True
        return False
    
    def add_conversation_message(self, call_sid: str, role: str, content: str, metadata: Dict[str, Any] = None):
        """Add message to conversation history"""
        session_data = self.get_call_session(call_sid)
        if session_data:
            message = {
                'role': role,  # 'user', 'assistant', 'system'
                'content': content,
                'timestamp': datetime.utcnow().isoformat(),
                'metadata': metadata or {}
            }
            session_data['conversation_history'].append(message)
            
            key = f"call_session:{call_sid}"
            self.redis_client.setex(key, self.call_session_ttl, json.dumps(session_data))
            return True
        return False
    
    def link_call_to_websocket(self, websocket_id: str, call_sid: str):
        """Link a call session to a WebSocket session"""
        ws_session = self.get_websocket_session(websocket_id)
        if ws_session:
            if call_sid not in ws_session.get('call_sessions', []):
                ws_session.setdefault('call_sessions', []).append(call_sid)
                self.update_websocket_session(websocket_id, {'call_sessions': ws_session['call_sessions']})
    
    def get_calls_for_websocket(self, websocket_id: str) -> list:
        """Get all call sessions for a WebSocket"""
        ws_session = self.get_websocket_session(websocket_id)
        if ws_session:
            call_sids = ws_session.get('call_sessions', [])
            calls = []
            for call_sid in call_sids:
                call_data = self.get_call_session(call_sid)
                if call_data:
                    calls.append(call_data)
            return calls
        return []
    
    def link_session_to_sid(self, temp_call_id: str, official_call_sid: str):
        """Link a temporary call session to the official Exotel CallSid"""
        # Get the temporary call session data
        temp_data = self.get_temp_data(temp_call_id)
        if temp_data:
            # Create a new session with the official CallSid
            self.create_call_session(official_call_sid, temp_data.get('customer_data', {}), temp_data.get('websocket_id'))
            
            # Transfer any conversation history
            if 'conversation_history' in temp_data:
                session_data = self.get_call_session(official_call_sid)
                if session_data:
                    session_data['conversation_history'] = temp_data['conversation_history']
                    key = f"call_session:{official_call_sid}"
                    self.redis_client.setex(key, self.call_session_ttl, json.dumps(session_data))
            
            # Clean up temporary session
            self.remove_temp_data(temp_call_id)
            
            print(f"✅ [Redis] Linked temp session {temp_call_id} to CallSid {official_call_sid}")
            return True
        else:
            print(f"⚠️ [Redis] No temp session found for {temp_call_id}")
            return False
    
    # Notification System
    def notify_websocket(self, websocket_id: str, message: Dict[str, Any]):
        """Store notification for WebSocket (to be picked up by WebSocket handler)"""
        key = f"ws_notification:{websocket_id}"
        notifications = self.redis_client.lrange(key, 0, -1)
        
        # Add new notification
        self.redis_client.lpush(key, json.dumps(message))
        self.redis_client.expire(key, 300)  # 5 minutes TTL for notifications
        
        # Keep only last 50 notifications
        self.redis_client.ltrim(key, 0, 49)
    
    def get_websocket_notifications(self, websocket_id: str) -> list:
        """Get pending notifications for WebSocket"""
        key = f"ws_notification:{websocket_id}"
        notifications = self.redis_client.lrange(key, 0, -1)
        
        # Clear notifications after retrieval
        self.redis_client.delete(key)
        
        return [json.loads(notif) for notif in notifications]
    
    # Temporary Data Storage
    def store_temp_data(self, key: str, data: Any, ttl: int = None) -> str:
        """Store temporary data with TTL"""
        temp_key = f"temp:{key}"
        ttl = ttl or self.temp_data_ttl
        self.redis_client.setex(temp_key, ttl, json.dumps(data))
        return temp_key
    
    def get_temp_data(self, key: str) -> Any:
        """Get temporary data"""
        temp_key = f"temp:{key}"
        data = self.redis_client.get(temp_key)
        return json.loads(data) if data else None
    
    def remove_temp_data(self, key: str):
        """Remove temporary data"""
        temp_key = f"temp:{key}"
        self.redis_client.delete(temp_key)
    
    # Statistics and Monitoring
    def get_active_sessions_count(self) -> Dict[str, int]:
        """Get count of active sessions"""
        ws_sessions = len(self.redis_client.keys("ws_session:*"))
        call_sessions = len(self.redis_client.keys("call_session:*"))
        
        return {
            'websocket_sessions': ws_sessions,
            'call_sessions': call_sessions
        }
    
    def get_call_sessions_by_status(self, status: str) -> list:
        """Get all call sessions with specific status"""
        call_keys = self.redis_client.keys("call_session:*")
        matching_sessions = []
        
        for key in call_keys:
            data = self.redis_client.get(key)
            if data:
                session_data = json.loads(data)
                if session_data.get('status') == status:
                    matching_sessions.append(session_data)
        
        return matching_sessions
    
    def cleanup_expired_sessions(self):
        """Manual cleanup of expired sessions (Redis handles this automatically, but useful for monitoring)"""
        # This is mainly for logging/monitoring purposes
        # Redis automatically handles TTL expiration
        pass

# Global Redis session manager instance
redis_manager = RedisSessionManager()

def init_redis():
    """Initialize Redis connection"""
    return redis_manager.test_connection()

# Session ID generators
def generate_websocket_session_id() -> str:
    """Generate unique WebSocket session ID"""
    return f"ws_{uuid.uuid4().hex[:12]}"

def generate_call_session_id() -> str:
    """Generate unique call session ID (before Exotel assigns SID)"""
    return f"call_{uuid.uuid4().hex[:12]}"
