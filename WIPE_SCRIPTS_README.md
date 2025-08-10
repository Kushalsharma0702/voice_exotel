# 🧹 Database Wipe Scripts

This directory contains scripts to completely wipe all data from your Voice Assistant application. Use these scripts during development and testing.

## ⚠️ **CRITICAL WARNING**
**These scripts will PERMANENTLY DELETE ALL DATA!**
- All customer records
- All call sessions and history  
- All file uploads
- All status updates
- All Redis cache data

**NEVER run these scripts in production!**

## 📁 Available Scripts

### 1. `wipe_data.py` - Safe Wipe Script
**Recommended for most users**

```bash
python wipe_data.py
```

**Features:**
- ✅ Multiple confirmation prompts
- ✅ Shows what will be deleted
- ✅ Displays database connection info
- ✅ Detailed progress reporting
- ✅ Recreates clean database schema
- ✅ Error handling and rollback

**Usage:**
1. Run the script
2. Type `WIPE ALL DATA` when prompted
3. Type `YES` for final confirmation
4. Wait for completion

### 2. `quick_wipe.py` - Fast Wipe Script
**For rapid development cycles**

```bash
python quick_wipe.py
```

**Features:**
- ⚡ No confirmation prompts
- ⚡ Immediate data deletion
- ⚡ Minimal output
- ⚠️ **DANGEROUS** - Use only in development

### 3. `wipe_data.bat` - Windows Batch File
**For Windows users**

```cmd
wipe_data.bat
```

Double-click the file or run from Command Prompt.

## 🚀 Quick Start

### Most Common Usage (Development):
```bash
# Safe wipe with confirmations
python wipe_data.py

# Quick wipe for rapid testing
python quick_wipe.py
```

### Make Scripts Executable (Linux/Mac):
```bash
chmod +x wipe_data.py quick_wipe.py

# Then run directly
./wipe_data.py
./quick_wipe.py
```

## 🗂️ What Gets Wiped

### PostgreSQL Database:
- `customers` table - All customer records
- `call_sessions` table - All call history and session data  
- `call_status_updates` table - All call status tracking
- `file_uploads` table - All uploaded file records

### Redis Cache:
- All WebSocket session data
- All temporary call data
- All cached customer information
- All session keys and values

## 🔧 Configuration

The scripts automatically read from your `.env` file:

```env
DATABASE_URL=postgresql://user:pass@host:port/dbname
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
```

## 🛠️ Troubleshooting

### "Permission Denied" Error:
```bash
chmod +x wipe_data.py
```

### "Module Not Found" Error:
```bash
# Ensure you're in the project directory
cd /path/to/voice/project

# Ensure virtual environment is activated
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate     # Windows
```

### Database Connection Error:
- Check your `.env` file has correct `DATABASE_URL`
- Ensure PostgreSQL is running
- Verify database credentials

### Redis Connection Error:
- Redis wipe will be skipped if Redis is not available
- This is not critical - the script will continue

## 🔒 Safety Features

### `wipe_data.py` Safety Features:
- ✅ Requires exact text confirmation
- ✅ Shows target database before wiping
- ✅ Double confirmation required
- ✅ Graceful error handling
- ✅ Operation summary report

### What's NOT Protected:
- ❌ `quick_wipe.py` has NO safety features
- ❌ Scripts cannot be undone
- ❌ No automatic backups created

## 💡 Best Practices

1. **Always backup production data** before running any scripts
2. **Use `wipe_data.py`** for normal development 
3. **Use `quick_wipe.py`** only for rapid testing cycles
4. **Never run in production** environments
5. **Test scripts in development** environment first
6. **Keep scripts in version control** for team usage

## 🚨 Emergency Recovery

If you accidentally wipe production data:

1. **Stop the application immediately**
2. **Restore from your latest backup**
3. **Do NOT run the application** until data is restored
4. **Check data integrity** before resuming operations

## 📝 Example Usage

```bash
# Development workflow
git pull origin main
python wipe_data.py          # Clean slate
python main.py               # Start fresh app
# ... do testing ...
python quick_wipe.py         # Quick clean between tests
```

---

**Remember: With great power comes great responsibility! 🕷️**
