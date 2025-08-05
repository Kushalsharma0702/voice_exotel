#!/usr/bin/env python3
"""
Voice Assistant Server Launcher
Starts the FastAPI application with proper configuration
"""
import uvicorn
import os
import sys
from pathlib import Path

# Add current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

def main():
    """Start the Voice Assistant server"""
    
    print("🚀 Starting Voice Assistant Server...")
    print("=" * 50)
    
    # Configuration
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    
    print(f"🌐 Server will start on: http://{host}:{port}")
    print(f"📊 Dashboard available at: http://{host}:{port}/static/enhanced_dashboard.html")
    print(f"🔧 Admin interface at: http://{host}:{port}/docs")
    print("=" * 50)
    
    try:
        # Start the server
        uvicorn.run(
            "main:app",
            host=host,
            port=port,
            reload=True,  # Enable auto-reload for development
            log_level="info",
            access_log=True
        )
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"❌ Server failed to start: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
