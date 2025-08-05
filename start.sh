#!/bin/bash

# Voice Assistant Application Startup Script
# This script sets up and starts the enhanced voice assistant application

echo "🚀 Starting Voice Assistant Call Management System..."

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}$1${NC}"
}

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    print_header "Creating Python virtual environment..."
    python3 -m venv venv
    if [ $? -eq 0 ]; then
        print_status "Virtual environment created successfully"
    else
        print_error "Failed to create virtual environment"
        exit 1
    fi
fi

# Activate virtual environment
print_header "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
print_header "Upgrading pip..."
pip install --upgrade pip

# Install requirements
print_header "Installing Python dependencies..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    if [ $? -eq 0 ]; then
        print_status "Dependencies installed successfully"
    else
        print_error "Failed to install dependencies"
        exit 1
    fi
else
    print_error "requirements.txt not found"
    exit 1
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    print_warning ".env file not found. Please create one with necessary environment variables."
    print_status "Example .env variables needed:"
    echo "EXOTEL_SID=your_exotel_sid"
    echo "EXOTEL_TOKEN=your_exotel_token"
    echo "EXOTEL_API_KEY=your_exotel_api_key"
    echo "SARVAM_API_KEY=your_sarvam_api_key"
    echo "DATABASE_URL=postgresql://user:pass@localhost/dbname"
    echo "REDIS_HOST=localhost"
    echo "REDIS_PORT=6379"
    echo ""
fi

# Check if Redis is running
print_header "Checking Redis connection..."
python3 -c "
import redis
try:
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)
    r.ping()
    print('✅ Redis is running')
except:
    print('❌ Redis is not running. Please start Redis server.')
    print('   Ubuntu/Debian: sudo systemctl start redis-server')
    print('   macOS: brew services start redis')
    print('   Docker: docker run -d -p 6379:6379 redis:alpine')
"

# Check if PostgreSQL is running
print_header "Checking PostgreSQL connection..."
python3 -c "
import os
from dotenv import load_dotenv
load_dotenv()

database_url = os.getenv('DATABASE_URL')
if database_url:
    try:
        import psycopg2
        from urllib.parse import urlparse
        result = urlparse(database_url)
        conn = psycopg2.connect(
            database=result.path[1:],
            user=result.username,
            password=result.password,
            host=result.hostname,
            port=result.port
        )
        conn.close()
        print('✅ PostgreSQL connection successful')
    except Exception as e:
        print(f'❌ PostgreSQL connection failed: {e}')
        print('   Please ensure PostgreSQL is running and DATABASE_URL is correct')
else:
    print('❌ DATABASE_URL not found in .env file')
"

# Create database directory if it doesn't exist
if [ ! -d "database" ]; then
    print_header "Creating database directory..."
    mkdir -p database
    touch database/__init__.py
fi

# Create services directory if it doesn't exist
if [ ! -d "services" ]; then
    print_header "Creating services directory..."
    mkdir -p services
    touch services/__init__.py
fi

# Initialize database tables
print_header "Initializing database tables..."
python3 -c "
from database.schemas import init_database
if init_database():
    print('✅ Database tables initialized successfully')
else:
    print('❌ Failed to initialize database tables')
"

# Start the application
print_header "Starting the Voice Assistant application..."
print_status "Application will be available at: http://localhost:8000"
print_status "Enhanced dashboard available at: http://localhost:8000/static/enhanced_dashboard.html"
print_status "WebSocket endpoint: ws://localhost:8000/ws"
print_status ""
print_status "Press Ctrl+C to stop the application"
print_status ""

# Check if uvicorn is available
if command -v uvicorn &> /dev/null; then
    # Start with uvicorn
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload --log-level info
else
    # Fallback to python -m uvicorn
    python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload --log-level info
fi
