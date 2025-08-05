# 🎙️ Voice Assistant Call Management System

An advanced voice assistant application with comprehensive call management, Redis-based session handling, real-time status tracking, and PostgreSQL database integration.

## 🚀 Features

### Core Features
- **Real-time Call Management**: Track calls from initiation to completion
- **Redis Session Management**: Robust session handling for parallel calls
- **Database Integration**: PostgreSQL for persistent data storage
- **Status Tracking**: Real-time call status updates (initiated, ringing, in-progress, agent transfer, completed, failed, not picked)
- **WebSocket Communication**: Real-time dashboard updates
- **File Upload**: CSV/Excel customer data upload with validation
- **Bulk Operations**: Trigger multiple calls simultaneously
- **Agent Transfer**: Seamless handoff to human agents

### Enhanced Features
- **Session Isolation**: Each call gets a unique SID preventing data merge
- **Parallel Call Support**: Handle multiple concurrent calls
- **Comprehensive Logging**: Detailed system and call logs
- **Dashboard Analytics**: Real-time statistics and monitoring
- **Error Handling**: Robust error management and recovery
- **Multi-language Support**: Support for Indian regional languages

## 📋 Prerequisites

### System Requirements
- Python 3.8+
- PostgreSQL 12+
- Redis 6+
- Node.js (optional, for additional tools)

### External Services
- **Exotel Account**: For call management
- **Sarvam AI Account**: For speech processing
- **AWS Account**: For Bedrock (optional)

## 🛠️ Installation & Setup

### 1. Clone and Setup Environment

```bash
git clone <your-repo-url>
cd voice_exotel
```

### 2. Create Environment Variables

Create a `.env` file in the root directory:

```bash
# Exotel Configuration
EXOTEL_SID="your_exotel_account_sid"
EXOTEL_TOKEN="your_exotel_api_token"
EXOTEL_API_KEY="your_exotel_api_key"
EXOTEL_VIRTUAL_NUMBER="your_exotel_virtual_number"
EXOTEL_FLOW_APP_ID="your_exotel_app_id"
AGENT_PHONE_NUMBER="your_agent_phone_number"

# Sarvam AI Configuration
SARVAM_API_KEY="your_sarvam_api_key"

# Database Configuration
DATABASE_URL="postgresql://username:password@localhost:5432/voice_assistant_db"

# Redis Configuration
REDIS_HOST="localhost"
REDIS_PORT="6379"
REDIS_PASSWORD=""  # Optional
REDIS_DB="0"

# AWS Configuration (Optional)
AWS_ACCESS_KEY_ID="your_aws_access_key"
AWS_SECRET_ACCESS_KEY="your_aws_secret_key"
AWS_REGION="your_aws_region"
CLAUDE_MODEL_ID="your_claude_model_arn"

# Gemini Configuration (Optional)
GEMINI_API_KEY="your_gemini_api_key"
```

### 3. Database Setup

#### PostgreSQL Installation

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

**macOS:**
```bash
brew install postgresql
brew services start postgresql
```

#### Create Database
```bash
sudo -u postgres psql
CREATE DATABASE voice_assistant_db;
CREATE USER voice_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE voice_assistant_db TO voice_user;
\q
```

### 4. Redis Setup

**Ubuntu/Debian:**
```bash
sudo apt install redis-server
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

**macOS:**
```bash
brew install redis
brew services start redis
```

**Docker:**
```bash
docker run -d -p 6379:6379 --name redis redis:alpine
```

### 5. Start the Application

```bash
# Make startup script executable
chmod +x start.sh

# Run the startup script
./start.sh
```

The script will:
- Create a virtual environment
- Install dependencies
- Check Redis and PostgreSQL connections
- Initialize database tables
- Start the application

## 🎛️ Dashboard Usage

### Access Points
- **Main Dashboard**: http://localhost:8000
- **Enhanced Dashboard**: http://localhost:8000/static/enhanced_dashboard.html
- **WebSocket Endpoint**: ws://localhost:8000/ws

### Dashboard Features

#### 1. File Upload
- Drag & drop CSV/Excel files
- Automatic validation and processing
- Real-time upload status
- Bulk customer data import

#### 2. Call Management
- Single call triggering
- Bulk call operations
- Selected customer calling
- Real-time status tracking

#### 3. Session Management
- WebSocket session tracking
- Redis-based session isolation
- Call SID association
- Parallel call support

#### 4. Status Monitoring
- Real-time call status updates
- System logs with timestamps
- Statistics dashboard
- Error tracking

## 🏗️ Architecture

### System Components

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │   FastAPI       │    │   PostgreSQL    │
│   Dashboard     │◄──►│   Backend       │◄──►│   Database      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │   Redis         │
                       │   Session Mgmt  │
                       └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │   Exotel API    │
                       │   Call Service  │
                       └─────────────────┘
```

### Database Schema

#### Tables
- **customers**: Customer information and contact details
- **call_sessions**: Individual call session data
- **call_status_updates**: Real-time status tracking
- **file_uploads**: Upload history and processing logs

#### Redis Structure
- **WebSocket Sessions**: `ws_session:{id}`
- **Call Sessions**: `call_session:{call_sid}`
- **Notifications**: `ws_notification:{id}`
- **Temporary Data**: `temp:{key}`

## 🔌 API Endpoints

### File Management
- `POST /api/upload-customers` - Upload customer data
- `GET /api/customers` - Get customer list

### Call Management
- `POST /api/trigger-call` - Trigger single call
- `POST /api/trigger-bulk-calls` - Trigger multiple calls
- `POST /api/transfer-to-agent` - Transfer call to agent
- `GET /api/call-status/{call_sid}` - Get call status

### Dashboard
- `GET /api/dashboard-data` - Get dashboard statistics
- `POST /api/exotel-webhook` - Exotel webhook handler

### WebSocket Events
- `connection_established` - Session created
- `file_processed` - File upload completed
- `call_triggered` - Call initiated
- `status_update` - Call status changed
- `agent_transfer_result` - Agent transfer completed

## 🔄 Call Flow

### Standard Call Flow
1. **File Upload**: Customer data uploaded and stored
2. **Call Trigger**: Call initiated with unique SID
3. **Session Creation**: Redis session created with call SID
4. **Database Storage**: Call record created in PostgreSQL
5. **Status Tracking**: Real-time status updates via WebSocket
6. **Agent Transfer**: Optional transfer to human agent
7. **Call Completion**: Final status update and session cleanup

### Session Management Flow
```
Upload File → Database Storage → Call Trigger → Exotel SID Assignment
     ↓
Redis Session Creation → Status Updates → WebSocket Notifications
     ↓
Agent Transfer (Optional) → Call Completion → Session Cleanup
```

## 🛡️ Error Handling

### Automatic Recovery
- WebSocket reconnection with exponential backoff
- Database connection pooling
- Redis connection retry logic
- Call failure notifications

### Monitoring
- Real-time error logging
- Status update tracking
- System health monitoring
- Performance metrics

## 🔧 Configuration

### Environment Variables
All configuration is handled through environment variables in the `.env` file.

### Database Configuration
- Connection pooling enabled
- Automatic table creation
- Migration support via Alembic

### Redis Configuration
- Connection pooling
- Automatic failover
- Session TTL management

## 🚀 Deployment

### Development
```bash
./start.sh
```

### Production
```bash
# Using Gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

# Using Docker (create Dockerfile)
docker build -t voice-assistant .
docker run -p 8000:8000 voice-assistant
```

### Environment Setup
- Set production environment variables
- Configure Redis cluster (if needed)
- Set up PostgreSQL with replication
- Configure load balancer
- Set up monitoring and logging

## 📊 Monitoring & Analytics

### Dashboard Metrics
- Total calls processed
- Active call count
- Success/failure rates
- Average call duration
- Agent transfer frequency

### System Monitoring
- WebSocket connection count
- Redis memory usage
- Database connection pool status
- API response times

## 🔒 Security

### Best Practices
- Environment variable management
- Database connection security
- API rate limiting
- Input validation
- Error message sanitization

### Authentication
- WebSocket session management
- API key validation
- Customer data encryption
- Audit logging

## 🧪 Testing

### Unit Tests
```bash
python -m pytest tests/
```

### Integration Tests
```bash
python -m pytest tests/integration/
```

### Load Testing
```bash
# Using locust or similar tools
locust -f tests/load_test.py
```

## 📚 Troubleshooting

### Common Issues

#### Redis Connection Failed
```bash
# Check Redis status
redis-cli ping

# Restart Redis
sudo systemctl restart redis-server
```

#### Database Connection Error
```bash
# Check PostgreSQL status
sudo systemctl status postgresql

# Verify connection
psql -h localhost -U voice_user -d voice_assistant_db
```

#### WebSocket Disconnections
- Check network connectivity
- Verify WebSocket URL
- Review browser console for errors

#### Call Failures
- Verify Exotel credentials
- Check account balance
- Review Exotel logs

### Logs Location
- Application logs: Console output
- WebSocket logs: Browser developer tools
- Database logs: PostgreSQL log files
- Redis logs: Redis server logs

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 📞 Support

For support and questions:
- Create an issue in the repository
- Check the troubleshooting section
- Review the API documentation
- Contact the development team

## 🔄 Updates & Changelog

### Version 2.0.0 (Current)
- ✅ Redis session management
- ✅ Enhanced database schema
- ✅ Real-time status tracking
- ✅ Parallel call support
- ✅ Comprehensive dashboard
- ✅ Agent transfer functionality
- ✅ WebSocket improvements
- ✅ Error handling enhancements

### Version 1.0.0 (Previous)
- Basic call triggering
- Simple file upload
- Basic WebSocket support
- Limited status tracking
