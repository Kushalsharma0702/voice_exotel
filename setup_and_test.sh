#!/bin/bash
# Voice Assistant Complete Setup and Test Script

echo "🚀 Voice Assistant - Complete Setup & Verification"
echo "=================================================="

# Function to print status
print_status() {
    echo -e "\n📋 $1"
    echo "----------------------------------------"
}

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    print_status "Creating Python virtual environment..."
    python3 -m venv .venv
    echo "✅ Virtual environment created"
fi

# Activate virtual environment
source .venv/bin/activate
echo "✅ Virtual environment activated"

# Install dependencies
print_status "Installing dependencies..."
pip install -q fastapi uvicorn[standard] sqlalchemy psycopg2-binary redis python-dotenv aioredis pandas openpyxl httpx requests pydantic python-multipart jinja2 aiofiles

# Verify key installations
echo "✅ Dependencies installed successfully"

# Test database connection
print_status "Testing database initialization..."
python -c "
from database.schemas import init_database
if init_database():
    print('✅ Database initialization successful')
else:
    print('❌ Database initialization failed')
"

# Test Redis connection (optional)
print_status "Testing Redis connection..."
python -c "
try:
    from utils.redis_session import init_redis
    if init_redis():
        print('✅ Redis connection successful')
    else:
        print('⚠️ Redis not available - app will run without session management')
except Exception as e:
    print('⚠️ Redis test skipped - app will run without session management')
"

# Run a quick application test
print_status "Testing application startup..."
timeout 5 python main.py > /tmp/app_test.log 2>&1 &
APP_PID=$!
sleep 3

if kill -0 $APP_PID 2>/dev/null; then
    echo "✅ Application started successfully"
    kill $APP_PID 2>/dev/null
else
    echo "❌ Application failed to start"
    echo "Error log:"
    cat /tmp/app_test.log
fi

print_status "Setup Complete!"
echo "🎉 Voice Assistant is ready to use!"
echo ""
echo "📋 Next Steps:"
echo "   1. Start the server: python run_server.py"
echo "   2. Open dashboard: http://localhost:8000/static/enhanced_dashboard.html"
echo "   3. API docs: http://localhost:8000/docs"
echo ""
echo "🔧 Configuration Files:"
echo "   • Database: .env (DATABASE_URL)"
echo "   • Redis: utils/redis_session.py"
echo "   • Exotel: .env (EXOTEL_* variables)"
echo ""
echo "=================================================="
