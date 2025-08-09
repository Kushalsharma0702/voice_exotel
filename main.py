from fastapi import FastAPI, WebSocket, Request, UploadFile, File, Body, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import xml.etree.ElementTree as ET
import json
import base64
import os
import asyncio
import httpx
import requests
from requests.auth import HTTPBasicAuth
from pydantic import BaseModel
import traceback
import uuid
import redis
from utils.handler_asr import SarvamHandler
import pandas as pd
import string
import uuid
from datetime import datetime
from starlette.websockets import WebSocketDisconnect
from dotenv import load_dotenv
from urllib.parse import quote

# Load environment variables
load_dotenv()

# Import our new services and utilities
from database.schemas import init_database, db_manager, CallStatus
from utils.redis_session import init_redis, redis_manager, generate_websocket_session_id
from services.call_management import call_service
from utils.handler_asr import SarvamHandler
import utils.connect_agent as agent

# Initialize Sarvam TTS handler for voice synthesis
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
sarvam_handler = SarvamHandler(SARVAM_API_KEY) if SARVAM_API_KEY else None

# Audio streaming constants (Exotel WebSocket expects raw 8k PCM chunks)
# Default to 800 (historically used in working prototype) but allow override.
# 8kHz * 2 bytes = 16000 bytes / second. Common frame sizes:
# 320 bytes  = 20ms, 640 bytes = 40ms, 800 bytes ≈ 50ms.
CHUNK_SIZE = int(os.getenv("AUDIO_CHUNK_SIZE", "800"))
print(f"🔧 Audio CHUNK_SIZE set to {CHUNK_SIZE} bytes")

# Working greeting templates from file.py
GREETING_TEMPLATE = {
    "en-IN": "Hello, this is Priya calling on behalf of South India Finvest Bank. Am I speaking with Mr. {name}?",
    "hi-IN": "नमस्ते, मैं प्रिया हूं और साउथ इंडिया फिनवेस्ट बैंक की ओर से बात कर रही हूं। क्या मैं श्री/सुश्री {name} से बात कर रही हूं?",
    "ta-IN": "வணக்கம், நான் பிரியா. இது சவுத் இந்தியா ஃபின்வெஸ்ட் வங்கியிலிருந்து அழைப்பு. திரு/திருமதி {name} பேசுகிறீர்களா?",
    "te-IN": "హలో, నేను ప్రియ మాట్లాడుతున్నాను, ఇది సౌత్ ఇండియా ఫిన్‌వెస్ట్ బ్యాంక్ నుండి కాల్. మిస్టర్/మిసెస్ {name} మాట్లాడుతున్నారా?",
    "mr-IN": "नमस्कार, मी प्रिया बोलत आहे, साउथ इंडिया फिनवेस्ट बँकेकडून. मी श्री {name} शी बोलत आहे का?",
    "kn-IN": "ನಮಸ್ಕಾರ, ನಾನು ಪ್ರಿಯಾ, ಸೌತ್ ಇಂಡಿಯಾ ಫಿನ್‌ವೆಸ್ಟ್ ಬ್ಯಾಂಕ್‌ನಿಂದ ಕರೆ ಮಾಡುತ್ತಿದ್ದೇನೆ. ನಾನು ಶ್ರೀ {name} ಅವರೊಂದಿಗೆ ಮಾತನಾಡುತ್ತಿದ್ದೇನೆವಾ?",
}

# --- TTS Helper Functions for Template Playback ---

async def stream_audio_to_websocket(websocket, audio_bytes):
    """Stream raw 8kHz 16-bit mono PCM audio bytes to WebSocket in chunks expected by Exotel."""
    if not audio_bytes:
        print("[stream_audio_to_websocket] ❌ No audio bytes to stream.")
        return
    total = len(audio_bytes)
    riff_header = audio_bytes[:4] == b'RIFF'
    print(f"[stream_audio_to_websocket] ▶️ Streaming {total} bytes (header_is_riff={riff_header}) in chunks of {CHUNK_SIZE}")
    # If WAV header detected, strip the first 44 bytes (standard PCM WAV header)
    if riff_header and total > 44:
        print("[stream_audio_to_websocket] ⚠️ WAV header detected – stripping 44 bytes")
        audio_bytes = audio_bytes[44:]
        total = len(audio_bytes)
        print(f"[stream_audio_to_websocket] ✅ Stripped size now {total} bytes")
    chunk_count = 0
    for i in range(0, total, CHUNK_SIZE):
        chunk = audio_bytes[i:i + CHUNK_SIZE]
        if not chunk:
            continue
        b64_chunk = base64.b64encode(chunk).decode("utf-8")
        response_msg = {"event": "media", "media": {"payload": b64_chunk}}
        try:
            await websocket.send_json(response_msg)
        except Exception as e:
            print(f"[stream_audio_to_websocket] ❌ Send failed at chunk {chunk_count}: {e}")
            break
        chunk_count += 1
        # Sleep approximating 50ms (based on chosen chunk size) to not overflow Exotel buffer
        await asyncio.sleep(0.05 if CHUNK_SIZE >= 800 else 0.02)
    print(f"[stream_audio_to_websocket] ✅ Completed streaming {chunk_count} chunks")

async def play_initial_greeting(websocket, customer_name: str):
    """Plays the very first greeting in English."""
    prompt_text = f"Hello, this is South India Finvest Bank AI Assistant calling. Am I speaking with {customer_name}?"
    print(f"[Sarvam TTS] 🔁 Converting initial greeting: {prompt_text}")
    audio_bytes = await sarvam_handler.synthesize_tts_end(prompt_text, "en-IN")
    await stream_audio_to_websocket(websocket, audio_bytes)

async def greeting_template_play(websocket, customer_info, lang: str):
    """Plays the personalized greeting in the detected language."""
    print("greeting_template_play")
    greeting = GREETING_TEMPLATE.get(lang, GREETING_TEMPLATE["en-IN"]).format(name=customer_info['name'])
    print(f"[Sarvam TTS] 🔁 Converting personalized greeting: {greeting}")
    if not sarvam_handler:
        print("[Sarvam TTS] ❌ sarvam_handler not initialized (missing API key)")
        return
    audio_bytes = await sarvam_handler.synthesize_tts_end(greeting, lang)
    if not audio_bytes or len(audio_bytes) < 200:
        print(f"[Sarvam TTS] ❌ Generated audio is empty or too small (size={0 if not audio_bytes else len(audio_bytes)})")
        return
    print(f"[Sarvam TTS] 📦 Greeting audio size: {len(audio_bytes)} bytes, first10={audio_bytes[:10].hex()}")
    await stream_audio_to_websocket(websocket, audio_bytes)


# EMI details template for loan information
EMI_DETAILS_TEMPLATE = {
    "en-IN": "Thank you. I'm calling about your loan account {loan_id}, which has an outstanding EMI of ₹{amount} due on {due_date}. If this remains unpaid, it may affect your credit score.",
    "hi-IN": "धन्यवाद। मैं आपके लोन खाता {loan_id} के बारे में कॉल कर रही हूँ, जिसकी बकाया ईएमआई ₹{amount} है, जो {due_date} को देय है। यदि यह भुगतान नहीं हुआ तो आपके क्रेडिट स्कोर पर प्रभाव पड़ सकता है।",
    "ta-IN": "நன்றி. உங்கள் கடன் கணக்கு {loan_id} குறித்து அழைக்கிறேன், நिलुவை EMI ₹{amount} {due_date} அன்று செலুத்த வேண்டும். இது செலுத்தாவிட்டால் உங்கள் கிரெடிட் ஸ்கோருக்கு பாதிப்பு ஏற்படலாம்।",
    "te-IN": "ధన్యవాదాలు. మీ లోన్ ఖాతా {loan_id} గురించి కాల్ చేస్తున్నాను, ₹{amount} EMI {due_date} నాటికి బాకీగా ఉంది। ఇది చెల్లించకపోతే మీ క్రెడిట్ స్కోర్‌పై ప్రభావం ఉంటుంది।",
    "mr-IN": "धन्यवाद. मी तुमच्या कर्ज खाता {loan_id} विषयी कॉल करत आहे, ₹{amount} EMI {due_date} रोजी बाकी आहे। हे भरले नाही तर तुमच्या क्रेडिट स्कोरवर परिणाम होईल।",
    "kn-IN": "ಧನ್ಯವಾದಗಳು. ನಿಮ್ಮ ಸಾಲ ಖಾತೆ {loan_id} ಬಗ್ಗೆ ಕರೆ ಮಾಡುತ್ತಿದ್ದೇನೆ, ₹{amount} EMI {due_date} ರಂದು ಬಾಕಿ ಇದೆ। ಇದನ್ನು ಪಾವತಿಸದಿದ್ದರೆ ನಿಮ್ಮ ಕ್ರೆಡಿಟ್ ಸ್ಕೋರ್‌ ಮೇಲೆ ಪರಿಣಾಮ ಬೀರುತ್ತದೆ।",
}

# Agent connect prompt
AGENT_CONNECT_TEMPLATE = {
    "en-IN": "Would you like to speak with a live agent for payment options? Please say yes or no.",
    "hi-IN": "क्या आप भुगतान विकल्पों के लिए एजेंट से बात करना चाहेंगे? कृपया हां या नहीं कहें।",
    "ta-IN": "கட்டண விருப்பங்களுக்கு நீங்கள் ஒரு முகவருடன் பேச விரும்புகிறீர்களா? தயவுसेய்து ஆம் அல்லது இல்লை என்று சொல்लுங்கள்।",
    "te-IN": "చెల్లింపు ఎంపికల కోసం మీరు ఒక ఏజెంట్‌తో మాట్లాడాలనుకుంటున్నారా? దయచేసి అవును లేదా కాదు అని చెప్పండి।",
    "mr-IN": "पेमेंट पर्यायांसाठी तुम्ही एजेंटशी बोलू इच्छिता का? कृपया होय किंवा नाही म्हणा।",
    "kn-IN": "ಪಾವತಿ ಆಯ್ಕೆಗಳಿಗಾಗಿ ನೀವು ಏಜೆಂಟ್‌ನೊಂದಿಗೆ ಮಾತನಾಡಲು ಬಯಸುತ್ತೀರಾ? ದಯವಿಟ್ಟು ಹೌದು ಅಥವಾ ಇಲ್ಲ ಎಂದು ಹೇಳಿ।",
}
import utils.bedrock_client as bedrock_client
from utils.handler_asr import SarvamHandler
import utils.voice_assistant_local

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 Starting Voice Assistant Application...")
    
    # Initialize database
    if init_database():
        print("✅ Database initialized successfully")
    else:
        print("❌ Database initialization failed")
    
    # Initialize Redis
    if init_redis():
        print("✅ Redis initialized successfully")
    else:
        print("❌ Redis initialization failed - running without session management")
    
    print("🎉 Application startup complete!")
    
    yield
    
    # Shutdown
    print("🛑 Shutting down Voice Assistant Application...")

app = FastAPI(
    title="Voice Assistant Call Management System",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the static directory to serve static files (like CSS, JS, images, and your index.html)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Configure Jinja2Templates to serve HTML files from the 'static' directory
templates = Jinja2Templates(directory="static")

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict = {}  # websocket_id -> websocket
        self.connection_info: dict = {}     # websocket_id -> connection info
    
    async def connect(self, websocket: WebSocket, client_ip: str = None):
        await websocket.accept()
        websocket_id = generate_websocket_session_id()
        
        self.active_connections[websocket_id] = websocket
        
        # Create Redis session
        client_info = {
            'ip': client_ip,
            'user_agent': websocket.headers.get('user-agent', ''),
            'connected_at': datetime.utcnow().isoformat()
        }
        
        redis_manager.create_websocket_session(websocket_id, client_info)
        
        self.connection_info[websocket_id] = {
            'websocket_id': websocket_id,
            'client_info': client_info
        }
        
        return websocket_id
    
    def disconnect(self, websocket_id: str):
        if websocket_id in self.active_connections:
            del self.active_connections[websocket_id]
        
        if websocket_id in self.connection_info:
            del self.connection_info[websocket_id]
        
        # Clean up Redis session
        redis_manager.remove_websocket_session(websocket_id)
    
    async def send_message(self, websocket_id: str, message: dict):
        if websocket_id in self.active_connections:
            websocket = self.active_connections[websocket_id]
            try:
                await websocket.send_text(json.dumps(message))
                return True
            except Exception as e:
                print(f"❌ Error sending message to {websocket_id}: {e}")
                self.disconnect(websocket_id)
                return False
        return False
    
    async def broadcast_to_all(self, message: dict):
        for websocket_id in list(self.active_connections.keys()):
            await self.send_message(websocket_id, message)
    
    def get_websocket_id_by_connection(self, websocket: WebSocket) -> str:
        for ws_id, ws in self.active_connections.items():
            if ws == websocket:
                return ws_id
        return None

manager = ConnectionManager()

# Global variable to store customer data (keeping for backward compatibility)
customer_data = []

# State to Language Mapping (moved up before it's used)
STATE_TO_LANGUAGE = {
    'andhra pradesh': 'te-IN',
    'arunachal pradesh': 'hi-IN',
    'assam': 'hi-IN',
    'bihar': 'hi-IN',
    'chhattisgarh': 'hi-IN',
    'goa': 'hi-IN',
    'gujarat': 'gu-IN',
    'haryana': 'hi-IN',
    'himachal pradesh': 'hi-IN',
    'jharkhand': 'hi-IN',
    'karnataka': 'kn-IN',
    'kerala': 'ml-IN',
    'madhya pradesh': 'hi-IN',
    'maharashtra': 'mr-IN',
    'manipur': 'hi-IN',
    'meghalaya': 'hi-IN',
    'mizoram': 'hi-IN',
    'nagaland': 'hi-IN',
    'odisha': 'or-IN',
    'punjab': 'pa-IN',
    'rajasthan': 'hi-IN',
    'sikkim': 'hi-IN',
    'tamil nadu': 'ta-IN',
    'telangana': 'te-IN',
    'tripura': 'hi-IN',
    'uttar pradesh': 'hi-IN',
    'uttarakhand': 'hi-IN',
    'west bengal': 'bn-IN',
    'delhi': 'hi-IN',
    'puducherry': 'ta-IN',
    'chandigarh': 'hi-IN',
    'andaman and nicobar islands': 'hi-IN',
    'dadra and nagar haveli and daman and diu': 'hi-IN',
    'jammu and kashmir': 'hi-IN',
    'ladakh': 'hi-IN',
    'lakshadweep': 'ml-IN',
}

def get_initial_language_from_state(state: str) -> str:
    """Get initial language from state"""
    if not state:
        return 'en-IN'
    return STATE_TO_LANGUAGE.get(state.strip().lower(), 'en-IN')

def process_uploaded_customers(customers_list):
    """Process uploaded customer data and add language mapping"""
    global customer_data
    try:
        customer_data = []
        for customer in customers_list:
            customer_info = {
                "name": customer["name"],
                "phone": str(customer["phone"]),
                "loan_id": str(customer["loan_id"]),
                "amount": str(customer["amount"]),
                "due_date": str(customer["due_date"]),
                "state": customer["state"],
                "lang": get_initial_language_from_state(customer["state"])
            }
            customer_data.append(customer_info)
        print(f"✅ Processed {len(customer_data)} customers from uploaded data")
        return customer_data
    except Exception as e:
        print(f"❌ Error processing uploaded customer data: {e}")
        return []

# --- NEW: Dashboard HTML Endpoint ---
@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    """
    Serves the enhanced dashboard HTML file at the root URL.
    """
    return templates.TemplateResponse("enhanced_dashboard.html", {"request": request})

@app.get("/original", response_class=HTMLResponse)
async def get_original_dashboard(request: Request):
    """
    Serves the original dashboard HTML file for backward compatibility.
    """
    return templates.TemplateResponse("index.html", {"request": request})

# --- NEW: Enhanced API Endpoints ---

@app.post("/api/upload-customers")
async def upload_customers_enhanced(file: UploadFile = File(...), websocket_id: str = None):
    """Enhanced customer file upload with database storage and session management"""
    try:
        # Validate file type
        if not file.filename.endswith(('.csv', '.xlsx', '.xls')):
            raise HTTPException(status_code=400, detail="Only CSV and Excel files are supported")
        
        # Read file content
        file_content = await file.read()
        
        # Process file using call management service
        result = await call_service.upload_and_process_customers(
            file_content, 
            file.filename, 
            websocket_id
        )
        
        if result['success']:
            return JSONResponse(content={
                "success": True,
                "message": f"Successfully processed {result['processed_records']} customers",
                "upload_id": result['upload_id'],
                "total_records": result['total_records'],
                "processed_records": result['processed_records'],
                "failed_records": result['failed_records'],
                "customers": result['customers']
            })
        else:
            raise HTTPException(status_code=400, detail=result['error'])
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/trigger-call")
async def trigger_single_call_enhanced(
    customer_id: str = Body(..., embed=True),
    websocket_id: str = Body(None, embed=True)
):
    """Enhanced single call trigger with session management"""
    try:
        result = await call_service.trigger_single_call(customer_id, websocket_id)
        
        if result['success']:
            return JSONResponse(content={
                "success": True,
                "message": "Call triggered successfully",
                "call_sid": result['call_sid'],
                "customer": result['customer'],
                "status": result['status']
            })
        else:
            raise HTTPException(status_code=400, detail=result['error'])
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/trigger-bulk-calls")
async def trigger_bulk_calls_enhanced(
    request_data: dict = Body(...)
):
    """Enhanced bulk call trigger with parallel processing"""
    try:
        websocket_id = request_data.get('websocket_id')
        customer_ids = request_data.get('customer_ids', [])
        customer_data_list = request_data.get('customer_data', [])
        
        print(f"🔄 Bulk call request received:")
        print(f"   WebSocket ID: {websocket_id}")
        print(f"   Customer IDs: {len(customer_ids)} provided")
        print(f"   Customer Data: {len(customer_data_list)} provided")
        
        # If no customer_ids provided, try to get all customers from database
        if not customer_ids and not customer_data_list:
            session = db_manager.get_session()
            try:
                from database.schemas import Customer
                customers = session.query(Customer).all()
                customer_ids = [str(customer.id) for customer in customers]
                print(f"📊 Found {len(customer_ids)} customers in database")
            finally:
                db_manager.close_session(session)
        
        # Use the call service to trigger bulk calls
        if customer_ids:
            print(f"🔄 Triggering calls for {len(customer_ids)} existing customers")
            result = await call_service.trigger_bulk_calls(customer_ids, websocket_id)
        elif customer_data_list:
            print(f"🔄 Triggering calls for {len(customer_data_list)} customers from data")
            result = await call_service.trigger_bulk_calls_from_data(customer_data_list, websocket_id)
        else:
            return JSONResponse(
                status_code=422,
                content={"success": False, "error": "No customer IDs or customer data provided"}
            )
        
        return JSONResponse(content={
            "success": True,
            "message": f"Bulk calls initiated: {result['successful_calls']} successful, {result['failed_calls']} failed",
            "total_calls": result['total_calls'],
            "successful_calls": result['successful_calls'],
            "failed_calls": result['failed_calls'],
            "results": result['results']
        })
        
    except Exception as e:
        print(f"❌ Bulk calls error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/transfer-to-agent")
async def transfer_to_agent_enhanced(call_sid: str = Body(..., embed=True)):
    """Enhanced agent transfer with session tracking"""
    try:
        result = await call_service.transfer_to_agent(call_sid)
        
        if result['success']:
            return JSONResponse(content={
                "success": True,
                "message": result['message']
            })
        else:
            raise HTTPException(status_code=400, detail=result['error'])
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/call-status/{call_sid}")
async def get_call_status(call_sid: str):
    """Get detailed call status and history"""
    try:
        # Get from Redis (real-time data)
        redis_data = redis_manager.get_call_session(call_sid)
        
        # Get from Database (persistent data)
        session = db_manager.get_session()
        try:
            from database.schemas import get_call_session_by_sid
            db_data = get_call_session_by_sid(session, call_sid)
            
            response = {
                "call_sid": call_sid,
                "redis_data": redis_data,
                "database_data": {
                    "status": db_data.status if db_data else None,
                    "start_time": db_data.start_time.isoformat() if db_data and db_data.start_time else None,
                    "end_time": db_data.end_time.isoformat() if db_data and db_data.end_time else None,
                    "duration": db_data.duration if db_data else None,
                    "customer_name": db_data.customer.name if db_data and db_data.customer else None
                } if db_data else None
            }
            
            return JSONResponse(content=response)
            
        finally:
            db_manager.close_session(session)
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/dashboard-data")
async def get_dashboard_data(websocket_id: str = None):
    """Get comprehensive dashboard data"""
    try:
        dashboard_data = call_service.get_call_status_dashboard(websocket_id)
        
        # Add Redis statistics
        redis_stats = redis_manager.get_active_sessions_count()
        dashboard_data['redis_statistics'] = redis_stats
        
        return JSONResponse(content=dashboard_data)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Test endpoint for Exotel configuration
@app.get("/test-exotel-config")
async def test_exotel_config():
    """Test endpoint to verify Exotel configuration"""
    return {
        "exotel_sid": os.getenv("EXOTEL_SID"),
        "exotel_virtual_number": os.getenv("EXOTEL_VIRTUAL_NUMBER"),
        "base_url": os.getenv("BASE_URL"),
        "passthru_endpoint": f"{os.getenv('BASE_URL', 'http://localhost:8000')}/passthru-handler",
        "webhook_endpoint": f"{os.getenv('BASE_URL', 'http://localhost:8000')}/api/exotel-webhook"
    }

# Test endpoint for pass-through ExoML response
@app.get("/test-passthru-exoml")
async def test_passthru_exoml():
    """Test endpoint to verify ExoML response generation"""
    # Sample test data
    test_params = {
        "customer_name": "Test Customer",
        "loan_id": "LOAN123",
        "amount": "15000",
        "language_code": "hi-IN",
        "call_sid": "test_call_123",
        "customer_id": "test_customer"
    }
    
    # Generate sample ExoML
    greeting = f"नमस्ते {test_params['customer_name']}, मैं प्रिया हूं और ज़्रोसिस बैंक की ओर से बात कर रही हूं। आपके लोन खाता {test_params['loan_id']} के बारे में है जिसमें {test_params['amount']} रुपये की बकाया राशि है।"
    
    exoml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="female">
        {greeting}
    </Say>
    <Gather timeout="10" finishOnKey="#" action="/gather-response?call_sid={test_params['call_sid']}&amp;customer_id={test_params['customer_id']}">
        <Say voice="female">
            कृपया अपना जवाब दें। यदि आप एजेंट से बात करना चाहते हैं तो 1 दबाएं।
        </Say>
    </Gather>
    <Say voice="female">
        धन्यवाद। आपका कॉल समाप्त हो रहा है।
    </Say>
</Response>"""
    
    return HTMLResponse(content=exoml_response, media_type="application/xml")

# --- NEW: Exotel Pass-Through URL Endpoint ---
@app.get("/passthru-handler")
@app.post("/passthru-handler")
async def exotel_passthru_handler(request: Request):
    """
    Exotel Pass-Through URL Handler
    Receives customer information and redirects to WebSocket stream with proper session data
    This ensures customer data is available for TTS templates
    """
    try:
        # Get query parameters and form data
        query_params = dict(request.query_params)
        
        # Try to get form data if POST request
        form_data = {}
        if request.method == "POST":
            try:
                form_data = dict(await request.form())
            except:
                pass
        
        # Combine all parameters
        call_params = {**query_params, **form_data}
        
        # Extract Exotel call information
        call_sid = call_params.get('CallSid', call_params.get('call_sid'))
        from_number = call_params.get('From', call_params.get('from'))
        to_number = call_params.get('To', call_params.get('to'))
        call_status = call_params.get('CallStatus', call_params.get('status', 'initiated'))
        
        # Extract custom customer data from URL parameters
        customer_id = call_params.get('customer_id')
        customer_name = call_params.get('customer_name', 'Unknown')
        loan_id = call_params.get('loan_id')
        amount = call_params.get('amount')
        due_date = call_params.get('due_date')
        language_code = call_params.get('language_code', 'hi-IN')
        state = call_params.get('state')
        temp_call_id = call_params.get('temp_call_id')
        
        print(f"🔄 Pass-Through Handler: Call {call_sid} for customer {customer_name} ({from_number})")
        print(f"   Customer ID: {customer_id}, Loan: {loan_id}, Amount: ₹{amount}")
        print(f"   Language: {language_code}, State: {state}")
        
        # If no customer data in URL, try to lookup from database by phone
        if not customer_name or customer_name == 'Unknown':
            print(f"🔍 No customer data in URL, looking up by phone: {from_number}")
            try:
                from database.schemas import get_customer_by_phone
                session = db_manager.get_session()
                
                # Clean phone number for database lookup
                clean_phone = from_number.replace('+', '').replace('-', '').replace(' ', '') if from_number else ''
                possible_phones = [
                    from_number, clean_phone, f"+{clean_phone}", 
                    f"+91{clean_phone[-10:]}" if len(clean_phone) >= 10 else clean_phone,
                    f"91{clean_phone[-10:]}" if len(clean_phone) >= 10 else clean_phone,
                    clean_phone[-10:] if len(clean_phone) >= 10 else clean_phone
                ]
                
                db_customer = None
                for phone_variant in possible_phones:
                    if phone_variant:
                        db_customer = get_customer_by_phone(session, phone_variant)
                        if db_customer:
                            print(f"✅ Found customer in database with phone: {phone_variant}")
                            customer_id = str(db_customer.id)
                            customer_name = db_customer.name
                            loan_id = db_customer.loan_id
                            amount = db_customer.amount
                            due_date = db_customer.due_date
                            language_code = db_customer.language_code or 'hi-IN'
                            state = db_customer.state or ''
                            break
                
                session.close()
                
                if not db_customer:
                    print(f"❌ Customer not found in database for phone: {from_number}")
                    # Return error response
                    error_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="female" language="hi-IN">क्षमा करें, आपका डेटा नहीं मिला। कॉल समाप्त हो रहा है।</Say>
    <Hangup/>
</Response>"""
                    return HTMLResponse(content=error_response, media_type="application/xml")
                    
            except Exception as e:
                print(f"❌ Database lookup error: {e}")
                # Return error response
                error_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="female" language="hi-IN">क्षमा करें, तकनीकी समस्या है। कॉल समाप्त हो रहा है।</Say>
    <Hangup/>
</Response>"""
                return HTMLResponse(content=error_response, media_type="application/xml")
        
        # Create session data with customer information
        session_data = {
            'call_sid': call_sid,
            'from_number': from_number,
            'to_number': to_number,
            'call_status': call_status,
            'customer_id': customer_id,
            'name': customer_name,
            'phone_number': from_number,
            'loan_id': loan_id,
            'amount': amount,
            'due_date': due_date,
            'language_code': language_code,
            'state': state,
            'temp_call_id': temp_call_id,
            'call_start_time': datetime.utcnow().isoformat(),
            'session_created_at': datetime.utcnow().isoformat()
        }
        
        # Store session in Redis for WebSocket access
        print(f"📦 Storing customer data: name={customer_name}, loan_id={loan_id}, amount={amount}")
        
        if call_sid:
            redis_manager.create_call_session(call_sid, session_data)
            print(f"📦 Stored session data in Redis for call_sid: {call_sid}")
        
        if temp_call_id:
            redis_manager.create_call_session(temp_call_id, session_data)
            print(f"📦 Stored session data in Redis for temp_call_id: {temp_call_id}")
        
        # Store by phone number for WebSocket lookup
        if from_number:
            clean_phone = from_number.replace('+', '').replace('-', '').replace(' ', '')
            phone_key = f"customer_phone_{clean_phone}"
            redis_manager.store_temp_data(phone_key, session_data, ttl=3600)
            print(f"📦 Stored session data in Redis for phone_key: {phone_key}")
            print(f"   Customer data: {customer_name}, Loan: {loan_id}, Amount: ₹{amount}")
        
        # Update call status in database if exists
        try:
            session = db_manager.get_session()
            from database.schemas import update_call_status
            update_call_status(session, call_sid, call_status, 
                             f"Pass-through handler called with customer: {customer_name}", 
                             {'passthru_params': call_params})
            session.close()
        except Exception as db_error:
            print(f"Database update error: {db_error}")
        
        # Build WebSocket URL for immediate TTS greeting (working approach)
        base_url = os.getenv("BASE_URL", "http://localhost:8000")
        websocket_url = f"{base_url.replace('http', 'ws')}/stream"
        
        # Add query parameters for session identification
        ws_params = []
        if call_sid:
            ws_params.append(f"call_sid={call_sid}")
        if temp_call_id:
            ws_params.append(f"temp_call_id={temp_call_id}")
        if from_number:
            # URL encode the phone number to handle + and other special chars
            from urllib.parse import quote
            encoded_phone = quote(from_number)
            ws_params.append(f"phone={encoded_phone}")
        
        if ws_params:
            websocket_url += "?" + "&".join(ws_params)
        
        print(f"🔗 Redirecting Exotel to WebSocket: {websocket_url}")
        print(f"🎙️ WebSocket will immediately play greeting for: {customer_name} - Loan {loan_id}")
        
        # Return ExoML that immediately connects to WebSocket (working approach)
        # The WebSocket will handle the initial TTS greeting on "start" event
        # Properly escape XML characters including & in URLs
        import xml.sax.saxutils as saxutils
        escaped_url = saxutils.escape(websocket_url)
        
        exoml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{escaped_url}" />
    </Connect>
</Response>"""
        
        print(f"📤 Returning ExoML for immediate WebSocket connection (working approach)")
        return HTMLResponse(content=exoml_response, media_type="application/xml")
        
    except Exception as e:
        print(f"❌ Pass-through handler error: {e}")
        import traceback
        traceback.print_exc()
        
        # Return error ExoML
        error_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="female" language="hi-IN">क्षमा करें, तकनीकी समस्या है। कॉल समाप्त हो रहा है।</Say>
    <Hangup/>
</Response>"""
        
        return HTMLResponse(content=error_response, media_type="application/xml")

@app.get("/gather-response")
@app.post("/gather-response")
async def handle_gather_response(request: Request):
    """Handle customer response from Exotel Gather"""
    try:
        query_params = dict(request.query_params)
        form_data = {}
        if request.method == "POST":
            try:
                form_data = dict(await request.form())
            except:
                pass
        
        params = {**query_params, **form_data}
        
        call_sid = params.get('call_sid')
        customer_id = params.get('customer_id')
        digits = params.get('Digits', '')
        
        # Get customer session data
        session_data = redis_manager.get_call_session(call_sid) if call_sid else None
        customer_name = session_data.get('customer_info', {}).get('name', 'Unknown') if session_data else 'Unknown'
        language_code = params.get('language', 'hi-IN')  # Get language from URL params
        template_lang = language_code if language_code in GREETING_TEMPLATE else "hi-IN"
        
        print(f"🎯 Customer response: {digits} for call {call_sid} (Lang: {template_lang})")
        
        if digits == "1":
            # Transfer to agent using localized message
            agent_number = os.getenv("AGENT_PHONE_NUMBER", "07417119014")
            
            transfer_messages = {
                "en-IN": f"Please wait {customer_name}, you are being connected to our agent.",
                "hi-IN": f"कृपया प्रतीक्षा करें {customer_name}, आपको हमारे एजेंट से जोड़ा जा रहा है।",
                "ta-IN": f"தயவுसेய்து காத்திருங்கள் {customer_name}, உங்களை எங்கள் முகவருடன் இணைக்கிறோம்।",
                "te-IN": f"దయचేసి వేచి ఉండండి {customer_name}, మిమ్మల్ని మా ఏజెంట్‌తో కనెక్ట్ చేస్తున్నాము।",
                "mr-IN": f"कृपया प्रतीक्षा करा {customer_name}, तुम्हाला आमच्या एजेंटशी जोडत आहोत।",
                "kn-IN": f"ದಯವಿಟ್ಟು ಕಾಯಿರಿ {customer_name}, ನಿಮ್ಮನ್ನು ನಮ್ಮ ಏಜೆಂಟ್‌ಗೆ ಸಂಪರ್ಕಿಸುತ್ತಿದ್ದೇವೆ।"
            }
            
            transfer_msg = transfer_messages.get(template_lang, transfer_messages["hi-IN"])
            
            exoml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="female">
        {transfer_msg}
    </Say>
    <Dial timeout="30" callerId="{os.getenv('EXOTEL_VIRTUAL_NUMBER', '04446972509')}">
        <Number>{agent_number}</Number>
    </Dial>
    <Say voice="female">
        एजेंट उपलब्ध नहीं है। कृपया बाद में कॉल करें।
    </Say>
</Response>"""
        else:
            # Continue with automated flow
            exoml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="female" language="{language_code}">
        धन्यवाद {customer_name}। आपकी जानकारी नोट कर ली गई है। 
        भुगतान लिंक SMS से भेजा जाएगा।
    </Say>
    <Hangup/>
</Response>"""
        
        # Update session with response
        if call_sid:
            redis_manager.update_call_session(call_sid, {
                'customer_response': digits,
                'response_time': datetime.utcnow().isoformat()
            })
        
        return HTMLResponse(content=exoml_response, media_type="application/xml")
        
    except Exception as e:
        print(f"❌ Gather response error: {e}")
        
        error_response = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="female" language="hi-IN">क्षमा करें, कॉल समाप्त हो रहा है।</Say>
    <Hangup/>
</Response>"""
        
        return HTMLResponse(content=error_response, media_type="application/xml")

@app.post("/api/exotel-webhook")
async def exotel_webhook_enhanced(request: Request):
    """Enhanced Exotel webhook handler with comprehensive status tracking"""
    try:
        # Parse webhook data
        form_data = await request.form()
        webhook_data = dict(form_data)
        
        print(f"📞 Exotel Webhook Received: {webhook_data}")
        
        # Process webhook using call management service
        result = await call_service.handle_exotel_webhook(webhook_data)
        
        if result['success']:
            return JSONResponse(content={
                "success": True,
                "message": "Webhook processed successfully",
                "status": result['status']
            })
        else:
            print(f"❌ Webhook processing failed: {result['error']}")
            return JSONResponse(content={
                "success": False,
                "error": result['error']
            })
            
    except Exception as e:
        print(f"❌ Webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class ExotelWebhookPayload(BaseModel):
    CallSid: str
    From: str
    To: str
    Direction: str

# NOTE: CHUNK_SIZE already defined at top with instrumentation; removing duplicate here.

from starlette.websockets import WebSocketDisconnect
from utils.handler_asr import SarvamHandler
import time
import utils.voice_assistant_local

# Environment variables for Sarvam and Exotel (ensure these are loaded via python-dotenv)
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
EXOTEL_SID = os.getenv("EXOTEL_SID")
EXOTEL_TOKEN = os.getenv("EXOTEL_TOKEN")
EXOTEL_API_KEY = os.getenv("EXOTEL_API_KEY") # This is often the same as SID or a separate API Key
EXOPHONE = os.getenv("EXOPHONE") # Your ExoPhone for outbound calls
AGENT_NUMBER = os.getenv("AGENT_PHONE_NUMBER")
EXOTEL_APP_ID = os.getenv("EXOTEL_APP_ID") # New: The ID of the Exotel Applet you want to connect the call to
EXOTEL_API_KEY        = os.getenv("EXOTEL_API_KEY")
EXOTEL_API_TOKEN      = os.getenv("EXOTEL_TOKEN")
EXOTEL_VIRTUAL_NUMBER = os.getenv("EXOTEL_VIRTUAL_NUMBER")
EXOTEL_FLOW_APP_ID= os.getenv("EXOTEL_FLOW_APP_ID")

BUFFER_DURATION_SECONDS = 3.0  # Duration to buffer audio before processing (increased to give more time)
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_DURATION = 5

# Duplicate GREETING_TEMPLATE removed (already defined earlier).

def get_customer_by_phone(phone_number: str):
    """Get customer data by phone number from database"""
    try:
        from database.schemas import get_customer_by_phone as db_get_customer_by_phone
        session = db_manager.get_session()
        
        # Clean phone number for database lookup - more comprehensive approach
        clean_phone = phone_number.replace('+', '').replace('-', '').replace(' ', '')
        
        # Extract just the 10-digit number if it's an Indian number
        if len(clean_phone) >= 10:
            last_10_digits = clean_phone[-10:]
        else:
            last_10_digits = clean_phone
        
        # Try multiple phone number formats that might be in the database
        possible_phones = [
            phone_number,              # Original format
            clean_phone,              # Cleaned format
            f"+{clean_phone}",        # With + prefix
            f"+91{last_10_digits}",   # With +91 prefix
            f"91{last_10_digits}",    # With 91 prefix (no +)
            last_10_digits            # Just 10 digits
        ]
        
        # Remove duplicates and empty values
        possible_phones = list(set([p for p in possible_phones if p]))
        
        db_customer = None
        for phone_variant in possible_phones:
            db_customer = db_get_customer_by_phone(session, phone_variant)
            if db_customer:
                break
        
        session.close()
        
        if db_customer:
            return {
                'id': str(db_customer.id),
                'name': db_customer.name,
                'phone': db_customer.phone_number,
                'loan_id': db_customer.loan_id,
                'amount': db_customer.amount,
                'due_date': db_customer.due_date,
                'state': db_customer.state,
                'lang': db_customer.language_code or 'en-IN'
            }
        return None
    except Exception as e:
        print(f"❌ Error getting customer from database: {e}")
        return None

# --- New TTS Helper Functions for the specified flow ---

# The `play_initial_greeting` function has been removed as it was a duplicate.

async def play_did_not_hear_response(websocket, lang: str = "en-IN"):
    """Plays a prompt when the initial response is not heard."""
    prompt_text = DID_NOT_HEAR_TEMPLATE.get(lang, DID_NOT_HEAR_TEMPLATE["en-IN"])
    print(f"[Sarvam TTS] 🔁 Converting 'didn't hear' prompt in {lang}: {prompt_text}")
    audio_bytes = await sarvam_handler.synthesize_tts_end(prompt_text, lang)
    await stream_audio_to_websocket(websocket, audio_bytes)

# Duplicate greeting_template_play removed; using earlier instrumented version.

# --- Multilingual Prompt Templates ---
EMI_DETAILS_PART1_TEMPLATE = {
    "en-IN": "Thank you... I'm calling about your loan ending in {loan_id}, which has an outstanding EMI of ₹{amount} due on {due_date}. I understand payments can be delayed — I'm here to help you avoid any further impact.",
    "hi-IN": "धन्यवाद... मैं आपके लोन (अंतिम चार अंक {loan_id}) के बारे में कॉल कर रही हूँ, जिसकी बकाया ईएमआई ₹{amount} है, जो {due_date} को देय है। मैं समझती हूँ कि भुगतान में देरी हो सकती है — मैं आपकी मदद के लिए यहाँ हूँ ताकि आगे कोई समस्या न हो।",
    "ta-IN": "நன்றி... உங்கள் கடன் (கடைசி நான்கு இலக்கங்கள் {loan_id}) குறித்து அழைக்கிறேன், அதற்கான நிலுவை EMI ₹{amount} {due_date} அன்று செலுத்த வேண்டியது உள்ளது. தாமதம் ஏற்படலாம் என்பதை புரிந்துகொள்கிறேன் — மேலும் பாதிப்பு ஏற்படாமல் உதவ நான் இங்கே இருக்கிறேன்.",
    "te-IN": "ధన్యవాదాలు... మీ రుణం ({loan_id} తో ముగిసే) గురించి కాల్ చేస్తున్నాను, దీనికి ₹{amount} EMI {due_date} నాటికి బాకీగా ఉంది. చెల్లింపులు ఆలస్యం కావచ్చు — మరింత ప్రభావం లేకుండా మీకు సహాయం చేయడానికి నేను ఇక్కడ ఉన్నాను.",
    "ml-IN": "നന്ദി... നിങ്ങളുടെ വായ്പ ({loan_id} അവസാനിക്കുന്ന) സംബന്ധിച്ച് വിളിക്കുന്നു, അതിന് ₹{amount} EMI {due_date} ന് ബാക്കി ഉണ്ട്. പണമടയ്ക്കുന്നതിൽ വൈകിപ്പോകാം — കൂടുതൽ പ്രശ്നങ്ങൾ ഒഴിവാക്കാൻ ഞാൻ സഹായിക്കാൻ ഇവിടെ ഉണ്ട്.",
    "gu-IN": "આભાર... હું તમારા લોન ({loan_id}) વિશે કોલ કરી રહી છું, જેમાં ₹{amount} EMI {due_date} સુધી બાકી છે. ચુકવણીમાં વિલંબ થઈ શકે છે — વધુ અસરથી બચવા માટે હું અહીં છું.",
    "mr-IN": "धन्यवाद... मी तुमच्या कर्ज ({loan_id}) विषयी कॉल करत आहे, ज्याची ₹{amount} EMI {due_date} रोजी बाकी आहे. पेमेंटमध्ये उशीर होऊ शकतो — पुढील परिणाम टाळण्यासाठी मी मदतीसाठी येथे आहे.",
    "bn-IN": "ধন্যবাদ... আমি আপনার ঋণ ({loan_id}) সম্পর্কে ফোন করছি, যার ₹{amount} EMI {due_date} তারিখে বাকি আছে। পেমেন্টে দেরি হতে পারে — আরও সমস্যা এড়াতে আমি সাহায্য করতে এখানে আছি।",
    "kn-IN": "ಧನ್ಯವಾದಗಳು... ನಿಮ್ಮ ಸಾಲ ({loan_id}) ಬಗ್ಗೆ ಕರೆ ಮಾಡುತ್ತಿದ್ದೇನೆ, ಇದಕ್ಕೆ ₹{amount} EMI {due_date} ರಂದು ಬಾಕಿ ಇದೆ. ಪಾವತಿಯಲ್ಲಿ ವಿಳಂಬವಾಗಬಹುದು — ಹೆಚ್ಚಿನ ಪರಿಣಾಮ ತಪ್ಪಿಸಲು ನಾನು ಸಹಾಯ ಮಾಡಲು ಇಲ್ಲಿದ್ದೇನೆ.",
    "pa-IN": "ਧੰਨਵਾਦ... ਮੈਂ ਤੁਹਾਡੇ ਲੋਨ ({loan_id}) ਬਾਰੇ ਕਾਲ ਕਰ ਰਹੀ ਹਾਂ, ਜਿਸ ਵਿੱਚ ₹{amount} EMI {due_date} ਤੱਕ ਬਕਾਇਆ ਹੈ। ਭੁਗਤਾਨ ਵਿੱਚ ਦੇਰੀ ਹੋ ਸਕਦੀ ਹੈ — ਹੋਰ ਪ੍ਰਭਾਵ ਤੋਂ ਬਚਣ ਲਈ ਮੈਂ ਇੱਥੇ ਹਾਂ।",
    "or-IN": "ଧନ୍ୟବାଦ... ମୁଁ ଆପଣଙ୍କର ଋଣ ({loan_id}) ବିଷୟରେ କଥାହୁଁଛି, ଯାହାର ₹{amount} EMI {due_date} ରେ ବକାୟା ଅଛି। ଦେୟ ଦେବାରେ ବିଳମ୍ବ ହେବା ସମ୍ଭବ — ଅଧିକ ସମସ୍ୟା ରୋକିବା ପାଇଁ ମୁଁ ଏଠାରେ ଅଛି।"
}

EMI_DETAILS_PART2_TEMPLATE = {
    "en-IN": "Please note... if this EMI remains unpaid, it may be reported to the credit bureau, which can affect your credit score. Continued delay may also classify your account as delinquent, leading to penalty charges or collection notices.",
    "hi-IN": "कृपया ध्यान दें... यदि यह ईएमआई बकाया रहती है, तो इसे क्रेडिट ब्यूरो को रिपोर्ट किया जा सकता है, जिससे आपका क्रेडिट स्कोर प्रभावित हो सकता है। लगातार देरी से आपका खाता डिफॉल्टर घोषित हो सकता है, जिससे पेनल्टी या कलेक्शन नोटिस आ सकते हैं।",
    "ta-IN": "தயவு செய்து கவனிக்கவும்... இந்த EMI செலுத்தப்படவில்லை என்றால், அது கிரெடிட் ப்யூரோவுக்கு தெரிவிக்கப்படலாம், இது உங்கள் கிரெடிட் ஸ்கோருக்கு பாதிப்பை ஏற்படுத்தும். தொடர்ந்த தாமதம் உங்கள் கணக்கை குற்றவாளியாக வகைப்படுத்தும், அபராதம் அல்லது வசூல் நோட்டீஸ் வரலாம்.",
    "te-IN": "దయచేసి గమనించండి... ఈ EMI చెల్లించకపోతే, అది క్రెడిట్ బ్యూరోకు నివేదించబడవచ్చు, ఇది మీ క్రెడిట్ స్కోర్‌ను ప్రభావితం చేయవచ్చు. కొనసాగుతున్న ఆలస్యం వల్ల మీ ఖాతా డిఫాల్ట్‌గా పరిగణించబడుతుంది, జరిమానాలు లేదా వసూలు నోటీసులు రావచ్చు.",
    "ml-IN": "ദയവായി ശ്രദ്ധിക്കുക... ഈ EMI അടയ്ക്കപ്പെടാതെ പോയാൽ, അത് ക്രെഡിറ്റ് ബ്യൂറോയ്ക്ക് റിപ്പോർട്ട് ചെയ്യപ്പെടാം, ഇത് നിങ്ങളുടെ ക്രെഡിറ്റ് സ്കോറിനെ ബാധിക്കും. തുടർച്ചയായ വൈകിപ്പിക്കൽ നിങ്ങളുടെ അക്കൗണ്ടിനെ ഡിഫോൾട്ട് ആയി കണക്കാക്കും, പിഴയോ കലക്ഷൻ നോട്ടീസോ വരാം.",
    "gu-IN": "મહેરબાની કરીને નોંધો... જો આ EMI બાકી રહેશે, તો તે ક્રેડિટ બ્યુરોને રિપોર્ટ થઈ શકેછે, જે તમારા ક્રેડિટ સ્કોરને અસર કરી શકેછે. સતત વિલંબથી તમારું ખાતું ડિફોલ્ટ તરીકે ગણાય શકેછે, દંડ અથવા વસૂલાત નોટિસ આવી શકેછે.",
    "mr-IN": "कृपया लक्षात घ्या... ही EMI बकाया राहिल्यास, ती क्रेडिट ब्युरोला रिपोर्ट केली जाऊ शकते, ज्यामुळे तुमचा क्रेडिट स्कोर प्रभावित होऊ शकतो. सततच्या विलंबामुळे तुमचे खाते डिफॉल्टर म्हणून घोषित केले जाऊ शकते, दंड किंवा वसुली नोटीस येऊ शकते.",
    "bn-IN": "দয়া করে লক্ষ্য করুন... এই EMI বকেয়া থাকলে, এটি ক্রেডিট ব্যুরোতে রিপোর্ট করা হতে পারে, যা আপনার ক্রেডিট স্কোরকে প্রভাবিত করতে পারে। ক্রমাগত দেরিতে আপনার অ্যাকাউন্ট ডিফল্ট হিসাবে বিবেচিত হতে পারে, জরিমানা বা সংগ্রহের নোটিশ আসতে পারে।",
    "kn-IN": "ದಯವಿಟ್ಟು ಗಮನಿಸಿ... ಈ EMI ಪಾವತಿಯಾಗದೆ ಇದ್ದರೆ, ಅದು ಕ್ರೆಡಿಟ್ ಬ್ಯೂರೋಗೆ ವರದಿ ಮಾಡಬಹುದು, ಇದು ನಿಮ್ಮ ಕ್ರೆಡಿಟ್ ಸ್ಕೋರ್‌ಗೆ ಪರಿಣಾಮ ಬೀರುತ್ತದೆ. ನಿರಂತರ ವಿಳಂಬದಿಂದ ನಿಮ್ಮ ಖಾತೆಯನ್ನು ಡಿಫಾಲ್ಟ್ ಎಂದು ಪರಿಗಣಿಸಬಹುದು, ದಂಡ ಅಥವಾ ಸಂಗ್ರಹಣಾ ಸೂಚನೆಗಳು ಬರಬಹುದು.",
    "pa-IN": "ਕਿਰਪਾ ਕਰਕੇ ਧਿਆਨ ਦਿਓ... ਜੇ ਇਹ EMI ਬਕਾਇਆ ਰਹੰਦੀ ਹੈ, ਤਾਂ ਇਹਨੂੰ ਕਰੈਡਿਟ ਬਿਊਰੋ ਨੂੰ ਰਿਪੋਰਟ ਕੀਤਾ ਜਾ ਸਕਦਾ ਹੈ, ਜੁਰਮਾਨਾ ਨਾਲ ਤੁਹਾਡਾ ਕਰੈਡਿਟ ਸਕੋਰ ਪ੍ਰਭਾਵਿਤ ਹੋ ਸਕਦਾ ਹੈ। ਲਗਾਤਾਰ ਦੇਰੀ ਨਾਲ ਤੁਹਾਡਾ ਖਾਤਾ ਡਿਫੌਲਟਰ ਘੋਸ਼ਿਤ ਕੀਤਾ ਜਾ ਸਕਦਾ ਹੈ, ਜੁਰਮਾਨਾ ਜਾਂ ਕਲੈਕਸ਼ਨ ਨੋਟਿਸ ਆ ਸਕਦੇ ਹਨ।",
    "or-IN": "ଦୟାକରି ଧ୍ୟାନ ଦିଅନ୍ତୁ... ଏହି EMI ବକାୟା ରହିଲେ, ଏହା କ୍ରେଡିଟ୍ ବ୍ୟୁରୋକୁ ରିପୋର୍ଟ କରାଯାଇପାରେ, ଯାହା ଆପଣଙ୍କର କ୍ରେଡିଟ୍ ସ୍କୋରକୁ ପ୍ରଭାବିତ କରିପାରେ। ଲଗାତାର ବିଳମ୍ବ ଆପଣଙ୍କର ଖାତାକୁ ଡିଫଲ୍ଟ୍ ଭାବରେ ଘୋଷଣା କରିପାରେ, ଜରିମାନା କିମ୍ବା କଲେକ୍ସନ୍ ନୋଟିସ୍ ଆସିପାରେ।"
}

AGENT_CONNECT_TEMPLATE = {
    "en-IN": "If you're facing difficulties... we have options like part payments or revised EMI plans. Would you like me to connect to one of our agents, to assist you better?",
    "hi-IN": "यदि आपको कठिनाई हो रही है... तो हमारे पास आंशिक भुगतान या संशोधित ईएमआई योजनाओं जैसे विकल्प हैं। क्या आप चाहेंगे कि मैं आपको हमारे एजेंट से जोड़ दूं, ताकि वे आपकी मदद कर सकें?",
    "ta-IN": "உங்களுக்கு சிரமம் இருந்தால்... பகுதி கட்டணம் அல்லது திருத்தப்பட்ட EMI திட்டங்கள் போன்ற விருப்பங்கள் உள்ளன. உங்களுக்கு உதவ எங்கள் ஏஜெண்டுடன் இணைக்க விரும்புகிறீர்களா?",
    "te-IN": "మీకు ఇబ్బంది ఉంటే... భాగ చెల్లింపులు లేదా సవరించిన EMI ప్లాన్‌లు వంటి ఎంపికలు ఉన్నాయి. మీకు సహాయం చేయడానికి మా ఏజెంట్‌ను కలిపించాలా?",
    "ml-IN": "നിങ്ങൾക്ക് ബുദ്ധിമുട്ട് ഉണ്ടെങ്കിൽ... ഭാഗിക പണമടയ്ക്കൽ അല്ലെങ്കിൽ പുതുക്കിയ EMI പദ്ധതികൾ പോലുള്ള ഓപ്ഷനുകൾ ഞങ്ങൾക്കുണ്ട്. നിങ്ങളെ സഹായിക്കാൻ ഞങ്ങളുടെ ഏജന്റുമായി ബന്ധിപ്പിക്കണോ?",
    "gu-IN": "જો તમને મુશ્કેલી હોય... તો અમારી પાસે ભાગ ચુકવણી અથવા સુધારેલી EMI યોજનાઓ જેવા વિકલ્પો છે. શું હું તમને અમારા એજન્ટ સાથે જોડું?",
    "mr-IN": "तुम्हाला अडचण असल्यास... आमच्याकडे भाग पेमेन्ट किंवा सुधारित EMI योजना आहेत. मी तुम्हाला आमच्या एजंटशी जोडू का?",
    "bn-IN": "আপনার অসুবিধা হলে... আমাদের কাছে আংশিক পেমেন্ট বা সংশোধিত EMI প্ল্যানের মতো বিকল্প রয়েছে। আপনাকে সাহায্য করতে আমাদের এজেন্টের সাথে সংযোগ করব?",
    "kn-IN": "ನಿಮಗೆ ತೊಂದರೆ ಇದ್ದರೆ... ಭಾಗ ಪಾವತಿ ಅಥವಾ ಪರಿಷ್ಕೃತ EMI ಯೋಜನೆಗಳೂ ನಮ್ಮ ಬಳಿ ಇವೆ. ನಿಮಗೆ ಸಹಾಯ ಮಾಡಲು ನಮ್ಮ ಏಜೆಂಟ್‌ಗೆ ಸಂಪರ್ಕ ಮಾಡಬೇಕೆ?",
    "pa-IN": "ਜੇ ਤੁਹਾਨੂੰ ਮੁਸ਼ਕਲ ਆ ਰਹੀ ਹੈ... ਤਾਂ ਸਾਡੇ ਕੋਲ ਹਿੱਸਾ ਭੁਗਤਾਨ ਜਾਂ ਸੋਧੀ EMI ਯੋਜਨਾਵਾਂ ਵਰਗੇ ਵਿਕਲਪ ਹਨ। ਕੀ ਮੈਂ ਤੁਹਾਨੂੰ ਸਾਡੇ ਏਜੰਟ ਨਾਲ ਜੋੜਾਂ?",
    "or-IN": "ଯଦି ଆପଣଙ୍କୁ ସମସ୍ୟା ହେଉଛି... ଆମ ପାଖରେ ଅଂଶିକ ପେମେଣ୍ଟ କିମ୍ବା ସଂଶୋଧିତ EMI ଯୋଜନା ଅଛି। ଆପଣଙ୍କୁ ସହଯୋଗ କରିବା ପାଇଁ ଆମ ଏଜେଣ୍ଟ ସହିତ ଯୋଗାଯୋଗ କରିବି?"
}

GOODBYE_TEMPLATE = {
    "en-IN": "I understand... If you change your mind, please call us back. Thank you. Goodbye.",
    "hi-IN": "मैं समझती हूँ... यदि आप अपना विचार बदलते हैं, तो कृपया हमें वापस कॉल करें। धन्यवाद। अलविदा।",
    "ta-IN": "நான் புரிந்துகொள்கிறேன்... நீங்கள் உங்கள் மனதை மாற்றினால், தயவுசெய்து எங்களை மீண்டும் அழைக்கவும். நன்றி. விடைபெறுகிறேன்.",
    "te-IN": "నాకు అర్థమైంది... మీరు మీ అభిప్రాయాన్ని మార్చుకుంటే, దయచేసి మమ్మల్ని తిరిగి కాల్ చేయండి. ధన్యవాదాలు. వీడ్కోలు.",
    "ml-IN": "ഞാൻ മനസ്സിലാക്കുന്നു... നിങ്ങൾ അഭിപ്രായം മാറ്റിയാൽ, ദയവായി ഞങ്ങളെ വീണ്ടും വിളിക്കുക. നന്ദി. വിട.",
    "gu-IN": "હું સમજું છું... જો તમે તમારો મન બદલો, તો કૃપા કરીને અમને પાછા કોલ કરો. આભાર. અલવિદા.",
    "mr-IN": "मी समजते... तुम्ही तुमचा निर्णय बदलल्यास, कृपया आम्हाला पुन्हा कॉल करा. धन्यवाद. गुडબाय.",
    "bn-IN": "আমি বুঝতে পারছি... আপনি যদি মত পরিবর্তন করেন, দয়া করে আমাদের আবার কল করুন। ধন্যবাদ। বিদায়।",
    "kn-IN": "ನಾನು ಅರ್ಥಮಾಡಿಕೊಂಡೆ... ನೀವು ನಿಮ್ಮ ಅಭಿಪ್ರಾಯವನ್ನು ಬದಲಾಯಿಸಿದರೆ, ದಯವಿಟ್ಟು ನಮಗೆ ಮತ್ತೆ ಕರೆ ಮಾಡಿ. ಧನ್ಯವಾದಗಳು. ವಿದಾಯ.",
    "pa-IN": "ਮੈਂ ਸਮਝਦੀ ਹਾਂ... ਜੇ ਤੁਸੀਂ ਆਪਣਾ ਮਨ ਬਦਲੋ, ਤਾਂ ਕਿਰਪਾ ਕਰਕੇ ਸਾਨੂੰ ਮੁੜ ਕਾਲ ਕਰੋ। ਧੰਨਵਾਦ। ਅਲਵਿਦਾ।",
    "or-IN": "ମୁଁ ବୁଝିଥିଲେ... ଯଦି ଆପଣ ମନ ବଦଳାନ୍ତି, ଦୟାକରି ଆମକୁ ପୁଣି କଲ୍ କରନ୍ତୁ। ଧନ୍ୟବାଦ। ବିଦାୟ।"
}

DID_NOT_HEAR_TEMPLATE = {
    "en-IN": "I'm unable to hear your choice. Please repeat.",
    "hi-IN": "मैं आपकी पसंद सुन नहीं पा रही हूँ। कृपया दोहराएँ।",
    "ta-IN": "நான் உங்கள் தேர்வைக் கேட்க முடியவில்லை. தயவுசெய்து மீண்டும் சொல்லுங்கள்.",
    "te-IN": "నేను మీ ఎంపికను వినలేకపోతున్నాను. దయచేసి మళ్లీ చెప్పండి.",
    "ml-IN": "നിങ്ങളുടെ തിരഞ്ഞെടുപ്പ് കേൾക്കാൻ കഴിയുന്നില്ല. ദയവായി ആവർത്തിക്കുക.",
    "gu-IN": "હું તમારી પસંદગી સાંભળી શકતો નથી. કૃપા કરીને પુનરાવર્તન કરો.",
    "mr-IN": "मी तुमची निवड ऐकू शकत नाही. कृपया पुन्हा सांगा.",
    "bn-IN": "আমি আপনার পছন্দ শুনতে পারছি না। অনুগ্রহ করে আবার বলুন।",
    "kn-IN": "ನಾನು ನಿಮ್ಮ ಆಯ್ಕೆಯನ್ನು ಕೇಳಲು ಸಾಧ್ಯವಿಲ್ಲ. ದಯವಿಟ್ಟು ಮತ್ತೆ ಹೇಳಿ.",
    "pa-IN": "ਮੈਂ ਤੁਹਾਡੀ ਚੋਣ ਸੁਣ ਨਹੀਂ ਸਕਦੀ। ਕਿਰਪਾ ਕਰਕੇ ਦੁਹਰਾਓ।",
    "or-IN": "ମୁଁ ଆପଣଙ୍କ ପସନ୍ଦ ଶୁଣି ପାରୁ ନାହିଁ। ଦୟାକରି ପୁନଃ କହନ୍ତୁ।"
}

async def play_emi_details_part1(websocket, customer_info, lang: str):
    """Plays the first part of EMI details."""
    prompt_text = EMI_DETAILS_PART1_TEMPLATE.get(
        lang, EMI_DETAILS_PART1_TEMPLATE["en-IN"]
    ).format(
        loan_id=customer_info.get('loan_id', 'XXXX'),
        amount=customer_info.get('amount', 'a certain amount'),
        due_date=customer_info.get('due_date', 'a recent date')
    )
    print(f"[Sarvam TTS] 🔁 Converting EMI part 1: {prompt_text}")
    audio_bytes = await sarvam_handler.synthesize_tts_end(prompt_text, lang)
    await stream_audio_to_websocket(websocket, audio_bytes)

async def play_emi_details_part2(websocket, customer_info, lang: str):
    """Plays the second part of EMI details."""
    prompt_text = EMI_DETAILS_PART2_TEMPLATE.get(lang, EMI_DETAILS_PART2_TEMPLATE["en-IN"])
    print(f"[Sarvam TTS] 🔁 Converting EMI part 2: {prompt_text}")
    audio_bytes = await sarvam_handler.synthesize_tts_end(prompt_text, lang)
    await stream_audio_to_websocket(websocket, audio_bytes)

async def play_agent_connect_question(websocket, lang: str):
    """Asks the user if they want to connect to a live agent."""
    prompt_text = AGENT_CONNECT_TEMPLATE.get(lang, AGENT_CONNECT_TEMPLATE["en-IN"])
    print(f"[Sarvam TTS] 🔁 Converting agent connect question: {prompt_text}")
    audio_bytes = await sarvam_handler.synthesize_tts_end(prompt_text, lang)
    await stream_audio_to_websocket(websocket, audio_bytes)

async def play_goodbye_after_decline(websocket, lang: str):
    """Plays a goodbye message if the user declines agent connection."""
    try:
        prompt_text = GOODBYE_TEMPLATE.get(lang, GOODBYE_TEMPLATE["en-IN"])
        print(f"[Sarvam TTS] 🔁 Converting goodbye after decline: {prompt_text}")
        audio_bytes = await sarvam_handler.synthesize_tts_end(prompt_text, lang)
        print(f"[Sarvam TTS] ✅ Goodbye audio generated, size: {len(audio_bytes)} bytes")
        await stream_audio_to_websocket(websocket, audio_bytes)
        print(f"[Voicebot] ✅ Goodbye message sent successfully in {lang}")
    except Exception as e:
        print(f"[Voicebot] ❌ Error in play_goodbye_after_decline: {e}")
        # Fallback to English
        try:
            fallback_text = GOODBYE_TEMPLATE["en-IN"]
            audio_bytes = await sarvam_handler.synthesize_tts_end(fallback_text, "en-IN")
            await stream_audio_to_websocket(websocket, audio_bytes)
            print("[Voicebot] ✅ Fallback goodbye message sent in English")
        except Exception as fallback_e:
            print(f"[Voicebot] ❌ Error in fallback goodbye message: {fallback_e}")

# --- Main WebSocket Endpoint (Voicebot Flow) ---

@app.websocket("/stream")
async def exotel_voicebot(websocket: WebSocket, temp_call_id: str = None, call_sid: str = None, phone: str = None):
    await websocket.accept()
    print("[WebSocket] ✅ Connected to Exotel Voicebot Applet")
    
    # Try to get customer info from query parameters
    query_params = dict(websocket.query_params) if hasattr(websocket, 'query_params') else {}
    if not temp_call_id:
        temp_call_id = query_params.get('temp_call_id')
    if not call_sid:
        call_sid = query_params.get('call_sid')
    if not phone:
        phone = query_params.get('phone')
    
    print(f"[WebSocket] Query params: temp_call_id={temp_call_id}, call_sid={call_sid}, phone={phone}")
    
    # State variable for the conversation stage
    conversation_stage = "INITIAL_GREETING" # States: INITIAL_GREETING, WAITING_FOR_LANG_DETECT, PLAYING_PERSONALIZED_GREETING, PLAYING_EMI_PART1, PLAYING_EMI_PART2, ASKING_AGENT_CONNECT, WAITING_AGENT_RESPONSE, TRANSFERRING_TO_AGENT, GOODBYE_DECLINE
    call_detected_lang = "en-IN" # Default language, will be updated after first user response
    audio_buffer = bytearray()
    last_transcription_time = time.time()
    interaction_complete = False # Flag to stop processing media after the main flow ends
    customer_info = None # Will be set when we get customer data
    initial_greeting_played = False # Track if initial greeting was played
    agent_question_repeat_count = 0 # Track how many times agent question was repeated

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            print(f"[WebSocket] 📨 Received message: {msg.get('event', 'unknown')}")

            if msg.get("event") == "start":
                print("[WebSocket] 🔁 Got start event")
                
                # Try to get customer info from multiple sources
                if not customer_info:
                    # 1. Try to get from Redis using temp_call_id or call_sid
                    if temp_call_id:
                        print(f"[WebSocket] Looking up customer data by temp_call_id: {temp_call_id}")
                        redis_data = redis_manager.get_call_session(temp_call_id)
                        if redis_data:
                            customer_info = {
                                'name': redis_data.get('name'),
                                'loan_id': redis_data.get('loan_id'),
                                'amount': redis_data.get('amount'),
                                'due_date': redis_data.get('due_date'),
                                'lang': redis_data.get('language_code', 'en-IN'),
                                'phone': redis_data.get('phone_number', ''),
                                'state': redis_data.get('state', '')
                            }
                            print(f"[WebSocket] ✅ Found customer data in Redis: {customer_info['name']}")
                    
                    elif call_sid:
                        print(f"[WebSocket] Looking up customer data by call_sid: {call_sid}")
                        redis_data = redis_manager.get_call_session(call_sid)
                        if redis_data:
                            customer_info = {
                                'name': redis_data.get('name'),
                                'loan_id': redis_data.get('loan_id'),
                                'amount': redis_data.get('amount'),
                                'due_date': redis_data.get('due_date'),
                                'lang': redis_data.get('language_code', 'en-IN'),
                                'phone': redis_data.get('phone_number', ''),
                                'state': redis_data.get('state', '')
                            }
                            print(f"[WebSocket] ✅ Found customer data in Redis: {customer_info['name']}")
                    
                    elif phone:
                        print(f"[WebSocket] Looking up customer data by phone: {phone}")
                        # Clean phone number for lookup
                        clean_phone = phone.replace('+', '').replace('-', '').replace(' ', '')
                        phone_key = f"customer_phone_{clean_phone}"
                        redis_data = redis_manager.get_temp_data(phone_key)
                        if redis_data:
                            customer_info = {
                                'name': redis_data.get('name'),
                                'loan_id': redis_data.get('loan_id'),
                                'amount': redis_data.get('amount'),
                                'due_date': redis_data.get('due_date'),
                                'lang': redis_data.get('language_code', 'en-IN'),
                                'phone': redis_data.get('phone_number', ''),
                                'state': redis_data.get('state', '')
                            }
                            print(f"[WebSocket] ✅ Found customer data by phone in Redis: {customer_info['name']}")
                
                # 2. Try to parse CustomField data from Exotel start message (if available)
                if not customer_info and 'customField' in msg:
                    print("[WebSocket] Parsing CustomField from Exotel start message")
                    try:
                        custom_field = msg['customField']
                        # Parse the CustomField format: "customer_id=|customer_name=Name|loan_id=LOAN123|..."
                        parts = custom_field.split('|')
                        custom_data = {}
                        for part in parts:
                            if '=' in part:
                                key, value = part.split('=', 1)
                                custom_data[key] = value
                        
                        customer_info = {
                            'name': custom_data.get('customer_name'),
                            'loan_id': custom_data.get('loan_id'),
                            'amount': custom_data.get('amount'),
                            'due_date': custom_data.get('due_date'),
                            'lang': custom_data.get('language_code', 'en-IN'),
                            'phone': '',
                            'state': custom_data.get('state', '')
                        }
                        print(f"[WebSocket] ✅ Parsed customer data from CustomField: {customer_info['name']}")
                    except Exception as e:
                        print(f"[WebSocket] ❌ Error parsing CustomField: {e}")
                
                # 3. Try to get customer data from database by phone number (if available)
                if not customer_info and phone:
                    print(f"[WebSocket] Looking up customer in database by phone: {phone}")
                    try:
                        from database.schemas import get_customer_by_phone
                        session = db_manager.get_session()
                        
                        # Clean phone number for database lookup - more comprehensive approach
                        clean_phone = phone.replace('+', '').replace('-', '').replace(' ', '')
                        
                        # Extract just the 10-digit number if it's an Indian number
                        if len(clean_phone) >= 10:
                            last_10_digits = clean_phone[-10:]
                        else:
                            last_10_digits = clean_phone
                        
                        # Try multiple phone number formats that might be in the database
                        possible_phones = [
                            phone,                      # Original format
                            clean_phone,               # Cleaned format
                            f"+{clean_phone}",         # With + prefix
                            f"+91{last_10_digits}",    # With +91 prefix
                            f"91{last_10_digits}",     # With 91 prefix (no +)
                            last_10_digits             # Just 10 digits
                        ]
                        
                        # Remove duplicates and empty values
                        possible_phones = list(set([p for p in possible_phones if p]))
                        print(f"[WebSocket] Trying phone formats: {possible_phones}")
                        
                        db_customer = None
                        for phone_variant in possible_phones:
                            db_customer = get_customer_by_phone(session, phone_variant)
                            if db_customer:
                                print(f"[WebSocket] ✅ Found customer with phone variant: {phone_variant}")
                                break
                        
                        if db_customer:
                            customer_info = {
                                'name': db_customer.name,
                                'loan_id': db_customer.loan_id,
                                'amount': db_customer.amount,
                                'due_date': db_customer.due_date,
                                'lang': db_customer.language_code or 'en-IN',
                                'phone': db_customer.phone_number,
                                'state': db_customer.state or ''
                            }
                            print(f"[WebSocket] ✅ Found customer in database: {customer_info['name']} (Phone: {customer_info['phone']})")
                        else:
                            print(f"[WebSocket] ❌ Customer not found in database for phone: {phone}")
                        
                        session.close()
                    except Exception as e:
                        print(f"[WebSocket] ❌ Error looking up customer in database: {e}")
                
                # 4. If no customer found anywhere, throw an error instead of using fallback data
                if not customer_info:
                    print("[WebSocket] ❌ No customer data found - cannot proceed without real customer information")
                    await websocket.send_text(json.dumps({
                        "event": "error",
                        "message": "Customer data not found. Please ensure customer information is uploaded and call is triggered properly."
                    }))
                    return
                
                # 5. Validate customer data has required fields
                required_fields = ['name', 'loan_id', 'amount', 'due_date']
                missing_fields = [field for field in required_fields if not customer_info.get(field)]
                if missing_fields:
                    print(f"[WebSocket] ❌ Customer data missing required fields: {missing_fields}")
                    await websocket.send_text(json.dumps({
                        "event": "error",
                        "message": f"Customer data incomplete. Missing fields: {', '.join(missing_fields)}"
                    }))
                    return
                
                print(f"[WebSocket] ✅ Customer data validated: {customer_info['name']} - Loan: {customer_info['loan_id']}, Amount: ₹{customer_info['amount']}")
                
                # Play initial greeting immediately when WebSocket starts (working approach)
                if conversation_stage == "INITIAL_GREETING":
                    print(f"[WebSocket] 1. Playing initial greeting for {customer_info['name']} in {customer_info['lang']}")
                    try:
                        # Use the working template approach
                        await greeting_template_play(websocket, customer_info, lang=customer_info['lang'])
                        print(f"[WebSocket] ✅ Initial greeting played successfully in {customer_info['lang']}")
                        initial_greeting_played = True
                        conversation_stage = "WAITING_FOR_LANG_DETECT"
                    except Exception as e:
                        print(f"[WebSocket] ❌ Error playing initial greeting: {e}")
                        # Try fallback simple greeting
                        try:
                            simple_greeting = f"Hello, this is South India Finvest Bank calling. Am I speaking with {customer_info['name']}?"
                            audio_bytes = await sarvam_handler.synthesize_tts_end(simple_greeting, "en-IN")
                            await stream_audio_to_websocket(websocket, audio_bytes)
                            print("[WebSocket] ✅ Fallback greeting sent successfully")
                            initial_greeting_played = True
                            conversation_stage = "WAITING_FOR_LANG_DETECT"
                        except Exception as fallback_e:
                            print(f"[WebSocket] ❌ Error sending fallback greeting: {fallback_e}")
                continue

            if msg.get("event") == "media":
                payload_b64 = msg["media"]["payload"]
                raw_audio = base64.b64decode(payload_b64)

                if interaction_complete:
                    continue

                if raw_audio and any(b != 0 for b in raw_audio):
                    audio_buffer.extend(raw_audio)
                
                now = time.time()

                if now - last_transcription_time >= BUFFER_DURATION_SECONDS:
                    if len(audio_buffer) == 0:
                        if conversation_stage == "WAITING_FOR_LANG_DETECT":
                            print("[Voicebot] No audio received during language detection stage. Playing 'didn't hear' prompt.")
                            await play_did_not_hear_response(websocket, call_detected_lang)
                            # Reset the timer to wait for user response
                            last_transcription_time = time.time()
                        elif conversation_stage == "WAITING_AGENT_RESPONSE":
                            agent_question_repeat_count += 1
                            if agent_question_repeat_count <= 2:  # Limit to 2 repeats
                                print(f"[Voicebot] No audio received during agent question stage. Repeating question (attempt {agent_question_repeat_count}/2).")
                                await play_agent_connect_question(websocket, call_detected_lang)
                                # Reset the timer to wait for user response
                                last_transcription_time = time.time()
                            else:
                                print("[Voicebot] Too many no-audio responses. Assuming user wants agent transfer.")
                                customer_number = customer_info.get('phone', '08438019383') if customer_info else "08438019383"
                                await play_transfer_to_agent(websocket, customer_number=customer_number) 
                                conversation_stage = "TRANSFERRING_TO_AGENT"
                                interaction_complete = True
                                await websocket.close()
                                print("[WebSocket-TRANSFERRING_TO_AGENT] 🔒 Closed")
                                break
                        audio_buffer.clear()
                        last_transcription_time = now
                        continue

                    try:
                        transcript = sarvam_handler.transcribe_from_payload(audio_buffer)
                        print(f"[Sarvam ASR] 📝 Transcript: {transcript}")

                        if transcript:
                            if conversation_stage == "WAITING_FOR_LANG_DETECT":
                                call_detected_lang = detect_language(transcript)
                                print(f"[Voicebot] 2. Detected Language: {call_detected_lang}")
                                print(f"[Voicebot] Original language from CSV: {customer_info.get('lang', 'en-IN')}")
                                
                                # Check if detected language is different from CSV language
                                if call_detected_lang != customer_info.get('lang', 'en-IN') and initial_greeting_played:
                                    print(f"[Voicebot] Language mismatch detected. Replaying greeting in {call_detected_lang}")
                                    try:
                                        await greeting_template_play(websocket, customer_info, lang=call_detected_lang)
                                        print(f"[Voicebot] ✅ Replayed greeting in {call_detected_lang}")
                                    except Exception as e:
                                        print(f"[Voicebot] ❌ Error replaying greeting: {e}")
                                
                                # Play EMI details in detected language
                                try:
                                    await play_emi_details_part1(websocket, customer_info or {}, call_detected_lang)
                                    await play_emi_details_part2(websocket, customer_info or {}, call_detected_lang)
                                    await play_agent_connect_question(websocket, call_detected_lang)
                                    conversation_stage = "WAITING_AGENT_RESPONSE"
                                    print(f"[Voicebot] ✅ EMI details and agent question sent successfully in {call_detected_lang}")
                                except Exception as e:
                                    print(f"[Voicebot] ❌ Error playing EMI details: {e}")
                            
                            elif conversation_stage == "WAITING_AGENT_RESPONSE":
                                # Use Claude for intent detection
                                try:
                                    intent = detect_intent_with_claude(transcript, call_detected_lang)
                                    print(f"[Voicebot] Claude detected intent: {intent}")
                                except Exception as e:
                                    print(f"[Voicebot] ❌ Error in Claude intent detection: {e}")
                                    # Fallback to keyword-based detection
                                    intent = detect_intent_fur(transcript, call_detected_lang)
                                    print(f"[Voicebot] Fallback intent detection: {intent}")
                                
                                if intent == "affirmative" or intent == "agent_transfer":
                                    if conversation_stage != "TRANSFERRING_TO_AGENT":  # Prevent multiple transfers
                                        print("[Voicebot] User affirmed agent transfer. Initiating transfer.")
                                        customer_number = customer_info.get('phone', '08438019383') if customer_info else "08438019383"
                                        await play_transfer_to_agent(websocket, customer_number=customer_number) 
                                        conversation_stage = "TRANSFERRING_TO_AGENT"
                                        interaction_complete = True
                                        await websocket.close()
                                        print("[WebSocket-TRANSFERRING_TO_AGENT] 🔒 Closed")
                                        break
                                    else:
                                        print("[Voicebot] ⚠️ Agent transfer already in progress, ignoring duplicate request")
                                elif intent == "negative":
                                    if conversation_stage != "GOODBYE_DECLINE":  # Prevent multiple goodbyes
                                        print("[Voicebot] User declined agent transfer. Saying goodbye.")
                                        await play_goodbye_after_decline(websocket, call_detected_lang)
                                        conversation_stage = "GOODBYE_DECLINE"
                                        interaction_complete = True
                                    else:
                                        print("[Voicebot] ⚠️ Goodbye already sent, ignoring duplicate request")
                                else:
                                    agent_question_repeat_count += 1
                                    if agent_question_repeat_count <= 2:  # Limit to 2 repeats
                                        print(f"[Voicebot] Unclear response to agent connect. Repeating question (attempt {agent_question_repeat_count}/2).")
                                        await play_agent_connect_question(websocket, call_detected_lang)
                                        # Reset the timer to wait for user response
                                        last_transcription_time = time.time()
                                    else:
                                        print("[Voicebot] Too many unclear responses. Assuming user wants agent transfer.")
                                        customer_number = customer_info.get('phone', '08438019383') if customer_info else "08438019383"
                                        await play_transfer_to_agent(websocket, customer_number=customer_number) 
                                        conversation_stage = "TRANSFERRING_TO_AGENT"
                                        interaction_complete = True
                                        await websocket.close()
                                        print("[WebSocket-TRANSFERRING_TO_AGENT] 🔒 Closed")
                                        break
                            # Add more elif conditions here for additional conversation stages if your flow extends
                    except Exception as e:
                        print(f"[Voicebot] ❌ Error processing transcript: {e}")

                    audio_buffer.clear()
                    last_transcription_time = now

    except Exception as e:
        print(f"[WebSocket Error] ❌ {e}")
    finally:
        await websocket.close()
        print("[WebSocket] 🔒 Closed")


# --- Language Detection and Intent Detection ---

def detect_language(text):
    text = text.strip().lower()

    # Check for Punjabi first (Gurmukhi script)
    if any(word in text for word in ["ਹਾਂ", "ਜੀ", "ਬਿਲਕੁਲ", "ਜੋੜ", "ਕਨੈਕਟ"]) or _is_gurmukhi(text):
        return "pa-IN"
    # Check for Hindi/Devanagari
    if any(word in text for word in ["नमस्ते", "हां", "नहीं", "कैसे", "आप", "जी", "बिलकुल", "जोड़", "कनेक्ट"]) or _is_devanagari(text):
        return "hi-IN"
    if any(word in text for word in ["வணக்கம்", "ஆம்", "இல்லை", "எப்படி"]) or _is_tamil(text):
        return "ta-IN"
    if any(word in text for word in ["హాయ్", "అవును", "కాదు", "ఎలా"]) or _is_telugu(text):
        return "te-IN"
    if any(word in text for word in ["ಹೆಲೋ", "ಹೌದು", "ಇಲ್ಲ", "ಹೆಗಿದೆ"]) or _is_kannada(text):
        return "kn-IN"
    return "en-IN"

def _is_devanagari(text):
    return any('\u0900' <= ch <= '\u097F' for ch in text)

def _is_tamil(text):
    return any('\u0B80' <= ch <= '\u0BFF' for ch in text)

def _is_telugu(text):
    return any('\u0C00' <= ch <= '\u0C7F' for ch in text)

def _is_kannada(text):
    return any('\u0C80' <= ch <= '\u0CFF' for ch in text)

def _is_gurmukhi(text):
    return any('\u0A00' <= ch <= '\u0A7F' for ch in text)

def detect_intent_with_claude(text: str, lang_code: str = "en-IN") -> str:
    """Use Claude to detect intent from user input"""
    try:
        # Create a simple chat history format for Claude
        chat_history = [{"sender": "user", "message": text}]
        
        # Use Claude to classify intent
        intent = bedrock_client.get_intent_from_text(chat_history)
        print(f"[Claude Intent] Raw response: {intent}")
        
        # Map Claude's intent to our flow intents
        if intent in ["emi", "balance", "loan", "agent_transfer"]:
            return "agent_transfer"  # These intents should trigger agent transfer
        elif intent in ["yes", "affirmative", "positive", "okay", "sure", "fine", "alright"]:
            return "affirmative"  # Positive responses
        elif intent in ["no", "negative", "decline", "not", "don't", "won't"]:
            return "negative"  # Negative responses
        elif intent == "unclear":
            # Fall back to keyword-based detection for unclear cases
            return detect_intent_fur(text, lang_code)
        else:
            # Fall back to keyword-based detection
            return detect_intent_fur(text, lang_code)
            
    except Exception as e:
        print(f"[Claude Intent] ❌ Error: {e}")
        # Fall back to keyword-based detection
        return detect_intent_fur(text, lang_code)

def detect_intent(text):
    """Legacy intent detection - kept for fallback"""
    print(f"detect_intent: {text}")
    if any(word in text for word in ["agent", "live agent", "speak to someone", "transfer", "help desk"]):
        return "agent_transfer"
    elif any(word in text for word in ["yes", "yeah", "sure", "okay", "haan", "ஆம்", "அவுனு", "हॉं", "ಹೌದು", "please","yes", "okay", 
                                       "ok", "sure", "alright", "go ahead", "continue", "yeah", "yup", "of course", "please do", "you may", "proceed",
                                       "ஆம்", "ஆமாம்", "சரி", "தயார்", "பேசுங்கள்", "இயலும்", "தொடங்கு", "ஆம் சரி", "வாங்க", "நிச்சயம்",
                                       "ശരി", "അതെ", "തുടങ്ങി", "സരി", "നിശ്ചയം", "തയ്യാര്", "ആണേ", "ഓക്കേ",
                                       "అవును", "సరే", "చెప్పు", "తప్పకుండా", "అలాగే", "కనీసం", "తయారు", "ఓకే",
                                       "ಹೌದು", "ಸರಿ", "ಹೇಳಿ", "ತಯారು", "ನಿಶ್ಚಿತವಾಗಿ", "ಬನ್ನಿ", "ಓಕೆ", "ಶರುವಮಾಡಿ"
                                       ]):
        return "affirmative"
    elif any(word in text for word in ["no", "not now", "later", "nah", "nahi", "இல்லை", "காது", "ನಹಿ"]):
        return "negative"
    elif any(word in text for word in ["what", "who", "why", "repeat", "pardon"]):
        return "confused"
    return "unknown"


AFFIRMATIVE_KEYWORDS = {
    "en": ["yes", "okay", "ok", "sure", "alright", "go ahead", "continue", "yeah", "yup", "of course", "please do", "you may", "proceed"],
    "ta": ["ஆம்", "ஆமாம்", "சரி", "தயார்", "பேசுங்கள்", "இயலும்", "தொடங்கு", "ஆம் சரி", "வாங்க", "நிச்சயம்"],
    "ml": ["ശരി", "അതെ", "തുടങ്ങി", "സരി", "നിശ്ചയം", "തയ്യാര്", "ആണേ", "ഓക്കേ"],
    "te": ["అవును", "సరే", "చెప్పు", "తప్పకుండా", "అలాగే", "కనీసం", "తయారు", "ఓకే"],
    "kn": ["ಹೌದು", "ಸರಿ", "ಹೇಳಿ", "ತಯಾರು", "ನಿಶ್ಚಿತವಾಗಿ", "ಬನ್ನಿ", "ಓಕೆ", "ಶರುವಮಾಡಿ"],
    "hi": ["हां", "हाँ", "जी", "बिलकुल", "ठीक", "सही", "हाँ जी", "बिलकुल जी", "जोड़", "जोड़ जी", "कनेक्ट", "कनेक्ट करो", "जोड़ दो", "जोड़ दीजिए", "हाँ बिलकुल", "बिलकुल हाँ", "जी बिलकुल", "जी बिलकुल जोड़ जी"],
    "pa": ["ਹਾਂ", "ਜੀ", "ਬਿਲਕੁਲ", "ਠੀਕ", "ਸਹੀ", "ਹਾਂ ਜੀ", "ਬਿਲਕੁਲ ਜੀ", "ਜੋੜ", "ਜੋੜ ਜੀ", "ਕਨੈਕਟ", "ਕਨੈਕਟ ਕਰੋ", "ਜੋੜ ਦੋ", "ਜੋੜ ਦੀਜੀਏ", "ਹਾਂ ਬਿਲਕੁਲ", "ਬਿਲਕੁਲ ਹਾਂ", "ਜੀ ਬਿਲਕੁਲ", "ਜੀ ਬਿਲਕੁਲ ਜੋੜ ਜੀ"]
}

NEGATIVE_KEYWORDS = {
    "en": ["no", "not now", "later", "don't want", "maybe later", "not interested", "nope"],
    "ta": ["இல்லை", "வேண்டாம்", "இப்போது இல்லை", "பின்னர்", "இல்ல"] ,
    "ml": ["ഇല്ല", "വേണ്ട", "ഇപ്പോൾ ഇല്ല", "പിന്നീട്"],
    "te": ["కాదు", "వద్దు", "ఇప్పుడవసరం లేదు", "తరువాత"],
    "kn": ["ಇಲ್ಲ", "ಬೇಡ", "ಇಲ್ಲವೇ", "ನಂತರ", "ಇದೀಗ ಬೇಡ"],
    "hi": ["नहीं", "नही", "नहि", "मत", "नहीं जी", "नहीं करो", "नहीं चाहिए", "बाद में", "अभी नहीं"],
    "pa": ["ਨਹੀਂ", "ਨਹੀ", "ਨਹਿ", "ਮਤ", "ਨਹੀਂ ਜੀ", "ਨਹੀਂ ਕਰੋ", "ਨਹੀਂ ਚਾਹੀਦਾ", "ਬਾਅਦ ਵਿੱਚ", "ਹੁਣ ਨਹੀਂ"]
}
def detect_intent_fur(transcript: str, lang_code: str) -> str:
    cleaned = transcript.lower().translate(str.maketrans('', '', string.punctuation)).strip()
    lang_prefix = lang_code[:2]

    print(f"[Intent] 🧠 Checking intent for: '{cleaned}' in lang: {lang_prefix}")

    for phrase in AFFIRMATIVE_KEYWORDS.get(lang_prefix, []):
        if phrase in cleaned:
            print(f"[Intent] ✅ Affirmative intent matched: '{phrase}'")
            return "affirmative"

    for phrase in NEGATIVE_KEYWORDS.get(lang_prefix, []):
        if phrase in cleaned:
            print(f"[Intent] ❌ Negative intent matched: '{phrase}'")
            return "negative"

    print("[Intent] 🤔 No clear intent detected")
    return "unknown"
# --- Audio Streaming and Call Trigger Functions ---

# The `play_account_info`, `play_goodbye_message`, and `play_repeat_question` functions have been removed as they were duplicates.

async def play_transfer_to_agent(websocket, customer_number: str):
    print("play_transfer_to_agent")
    transfer_text = (
        "Please wait, we are transferring the call to an agent."
    )
    print("[Sarvam TTS] 🔁 Converting agent transfer prompt")
    # Using 'en-IN' for transfer prompt for consistency, but could be `call_detected_lang`
    audio_bytes = await sarvam_handler.synthesize_tts_end(transfer_text, "en-IN") 
    print("[Sarvam TTS] 📢 Agent transfer audio generated")

    await stream_audio_to_websocket(websocket, audio_bytes)

    print("[Exotel] 📞 Initiating agent call transfer")
    # customer_number must be the `From` number of the original call to the voicebot
    #await agent.trigger_exotel_agent_transfer(customer_number, AGENT_NUMBER)


# Duplicate stream_audio_to_websocket removed; using earlier instrumented version.

# --- Outbound Call Trigger Function (used by dashboard) ---

# The `trigger_exotel_call_async` and `trigger_exotel_customer_call` functions have been removed as they were duplicates.

# --- State to Language Mapping (already defined above) ---

# --- TEST MODE for Exotel API (set to True to mock calls) ---

# --- Enhanced WebSocket Endpoint for Real-time Session Management ---
@app.websocket("/ws")
async def websocket_enhanced_session_manager(websocket: WebSocket):
    """
    Enhanced WebSocket endpoint with Redis session management, call tracking, and real-time status updates
    """
    websocket_id = None
    
    try:
        # Connect and create session
        client_ip = websocket.client.host if websocket.client else "unknown"
        websocket_id = await manager.connect(websocket, client_ip)
        
        print(f"🔌 WebSocket connected: {websocket_id}")
        
        # Send initial connection confirmation
        await manager.send_message(websocket_id, {
            "type": "connection_established",
            "websocket_id": websocket_id,
            "message": "Connected to Voice Assistant Call Management System",
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Send current dashboard data
        try:
            dashboard_data = call_service.get_call_status_dashboard(websocket_id)
            await manager.send_message(websocket_id, {
                "type": "dashboard_data",
                "data": dashboard_data,
                "timestamp": datetime.utcnow().isoformat()
            })
        except Exception as e:
            print(f"❌ Error sending initial dashboard data: {e}")
        
        # Main message loop
        while True:
            try:
                # Check for pending notifications from Redis
                notifications = redis_manager.get_websocket_notifications(websocket_id)
                for notification in notifications:
                    await manager.send_message(websocket_id, notification)
                
                # Wait for message with timeout to periodically check notifications
                try:
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
                except asyncio.TimeoutError:
                    # Send heartbeat
                    await manager.send_message(websocket_id, {
                        "type": "heartbeat",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    continue
                except WebSocketDisconnect:
                    # Client disconnected, break the loop
                    print(f"🔌 WebSocket client disconnected: {websocket_id}")
                    break
                
                try:
                    message = json.loads(data)
                    await handle_websocket_message(websocket_id, message)
                    
                except json.JSONDecodeError:
                    await manager.send_message(websocket_id, {
                        "type": "error",
                        "message": "Invalid JSON format",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    
            except WebSocketDisconnect:
                # Client disconnected, break the loop
                print(f"🔌 WebSocket client disconnected: {websocket_id}")
                break
            except Exception as e:
                print(f"❌ Error in WebSocket message loop: {e}")
                try:
                    await manager.send_message(websocket_id, {
                        "type": "error",
                        "message": f"Server error: {str(e)}",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                except:
                    # If we can't send the error message, the connection is likely dead
                    print(f"❌ Failed to send error message, connection likely dead: {websocket_id}")
                    break
                
    except WebSocketDisconnect:
        print(f"🔌 WebSocket disconnected: {websocket_id}")
    except Exception as e:
        print(f"❌ WebSocket error: {e}")
    finally:
        if websocket_id:
            manager.disconnect(websocket_id)

async def handle_websocket_message(websocket_id: str, message: dict):
    """Handle incoming WebSocket messages"""
    action = message.get("action")
    
    try:
        if action == "trigger_single_call":
            customer_id = message.get("customer_id")
            if not customer_id:
                await manager.send_message(websocket_id, {
                    "type": "error",
                    "message": "customer_id is required for trigger_single_call",
                    "timestamp": datetime.utcnow().isoformat()
                })
                return
            
            # Trigger call using service
            result = await call_service.trigger_single_call(customer_id, websocket_id)
            
            await manager.send_message(websocket_id, {
                "type": "call_triggered",
                "success": result['success'],
                "data": result,
                "timestamp": datetime.utcnow().isoformat()
            })
            
        elif action == "trigger_bulk_calls":
            customer_ids = message.get("customer_ids", [])
            if not customer_ids:
                await manager.send_message(websocket_id, {
                    "type": "error",
                    "message": "customer_ids array is required for trigger_bulk_calls",
                    "timestamp": datetime.utcnow().isoformat()
                })
                return
            
            # Trigger bulk calls
            result = await call_service.trigger_bulk_calls(customer_ids, websocket_id)
            
            await manager.send_message(websocket_id, {
                "type": "bulk_calls_triggered",
                "success": True,
                "data": result,
                "timestamp": datetime.utcnow().isoformat()
            })
            
        elif action == "transfer_to_agent":
            call_sid = message.get("call_sid")
            if not call_sid:
                await manager.send_message(websocket_id, {
                    "type": "error",
                    "message": "call_sid is required for transfer_to_agent",
                    "timestamp": datetime.utcnow().isoformat()
                })
                return
            
            # Transfer to agent
            result = await call_service.transfer_to_agent(call_sid)
            
            await manager.send_message(websocket_id, {
                "type": "agent_transfer_result",
                "success": result['success'],
                "data": result,
                "timestamp": datetime.utcnow().isoformat()
            })
            
        elif action == "get_call_status":
            call_sid = message.get("call_sid")
            if not call_sid:
                await manager.send_message(websocket_id, {
                    "type": "error",
                    "message": "call_sid is required for get_call_status",
                    "timestamp": datetime.utcnow().isoformat()
                })
                return
            
            # Get call status from Redis and Database
            redis_data = redis_manager.get_call_session(call_sid)
            
            await manager.send_message(websocket_id, {
                "type": "call_status",
                "call_sid": call_sid,
                "data": redis_data,
                "timestamp": datetime.utcnow().isoformat()
            })
            
        elif action == "get_dashboard_data":
            # Get fresh dashboard data
            dashboard_data = call_service.get_call_status_dashboard(websocket_id)
            
            await manager.send_message(websocket_id, {
                "type": "dashboard_data",
                "data": dashboard_data,
                "timestamp": datetime.utcnow().isoformat()
            })
            
        elif action == "get_customer_data":
            # Send current customer data (backward compatibility)
            await manager.send_message(websocket_id, {
                "type": "customer_data",
                "data": customer_data,
                "count": len(customer_data),
                "timestamp": datetime.utcnow().isoformat()
            })
            
        elif action == "trigger-call":  # Backward compatibility
            customer_number = message.get("customer_number")
            if not customer_number:
                await manager.send_message(websocket_id, {
                    "type": "error",
                    "message": "customer_number is required for trigger-call",
                    "timestamp": datetime.utcnow().isoformat()
                })
                return
            
            # Find customer by phone and trigger call
            customer_info = get_customer_by_phone(customer_number)
            if customer_info and customer_info.get('id'):
                # This is a simplified version for backward compatibility
                result = await call_service.trigger_single_call(customer_info['id'], websocket_id)
                await manager.send_message(websocket_id, {
                    "type": "call_triggered_legacy",
                    "success": result['success'],
                    "message": f"📞 Call triggered to {customer_number}",
                    "data": result,
                    "timestamp": datetime.utcnow().isoformat()
                })
            else:
                await manager.send_message(websocket_id, {
                    "type": "error",
                    "message": f"Customer with phone number {customer_number} not found.",
                    "timestamp": datetime.utcnow().isoformat()
                })
                
        else:
            await manager.send_message(websocket_id, {
                "type": "error",
                "message": f"Unknown action: {action}",
                "available_actions": [
                    "trigger_single_call", "trigger_bulk_calls", "transfer_to_agent",
                    "get_call_status", "get_dashboard_data", "get_customer_data"
                ],
                "timestamp": datetime.utcnow().isoformat()
            })
            
    except Exception as e:
        await manager.send_message(websocket_id, {
            "type": "error",
            "message": f"Error processing action '{action}': {str(e)}",
            "timestamp": datetime.utcnow().isoformat()
        })

@app.post("/upload-customers/")
async def upload_customers(file: UploadFile = File(...)):
    """
    Accepts an Excel or CSV file, extracts customer details, processes them, and returns them for dashboard display.
    Expects columns: name, phone, loan_id, amount, due_date, state
    """
    if not file.filename.endswith((".xls", ".xlsx", ".csv")):
        return {"error": "Please upload a valid Excel or CSV file (.xls, .xlsx, .csv)"}
    try:
        if file.filename.endswith(".csv"):
            df = pd.read_csv(file.file)
        else:
            df = pd.read_excel(file.file)
        required_cols = {"name", "phone", "loan_id", "amount", "due_date", "state"}
        df.columns = [c.lower() for c in df.columns]
        if not required_cols.issubset(set(df.columns)):
            return {"error": f"File must contain columns: {required_cols}"}
        extracted = []
        for _, row in df.iterrows():
            customer_info = {
                "name": row["name"],
                "loan_id": str(row["loan_id"]),
                "amount": str(row["amount"]),
                "due_date": str(row["due_date"]),
                "state": row["state"],
                "phone": str(row["phone"])
            }
            extracted.append(customer_info)
        
        # Process the uploaded data and store it globally
        process_uploaded_customers(extracted)
        
        return {"customers": extracted, "message": f"Successfully uploaded and processed {len(extracted)} customers"}
    except Exception as e:
        return {"error": str(e)}

@app.post("/reload-customers/")
async def reload_customers():
    """
    Clear customer data (since we no longer load from CSV file)
    """
    try:
        global customer_data
        customer_data = []
        return {"message": "Customer data cleared. Please upload a new CSV file.", "count": 0}
    except Exception as e:
        return {"error": str(e)}

@app.get("/customers/")
async def get_customers():
    """
    Get all customer data
    """
    return {"customers": customer_data, "count": len(customer_data)}

@app.get("/test-voice/")
async def test_voice():
    """
    Test endpoint to verify voice templates are working
    """
    try:
        # Test with a sample customer
        test_customer = {
            "name": "Test Customer",
            "loan_id": "1234",
            "amount": "5000",
            "due_date": "2024-08-15",
            "lang": "en-IN"
        }
        
        # Test template generation
        greeting = GREETING_TEMPLATE.get("en-IN", "").format(name=test_customer['name'])
        emi_part1 = EMI_DETAILS_PART1_TEMPLATE.get("en-IN", "").format(
            loan_id=test_customer['loan_id'],
            amount=test_customer['amount'],
            due_date=test_customer['due_date']
        )
        
        return {
            "status": "success",
            "customer": test_customer,
            "greeting_template": greeting,
            "emi_part1_template": emi_part1,
            "customer_data_loaded": len(customer_data),
            "templates_available": {
                "greeting": len(GREETING_TEMPLATE),
                "emi_part1": len(EMI_DETAILS_PART1_TEMPLATE),
                "emi_part2": len(EMI_DETAILS_PART2_TEMPLATE),
                "agent_connect": len(AGENT_CONNECT_TEMPLATE),
                "goodbye": len(GOODBYE_TEMPLATE)
            }
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/test-voice-audio/")
async def test_voice_audio():
    """
    Test endpoint to verify TTS is working
    """
    try:
        test_text = "Hello, this is a test message from the voice assistant."
        audio_bytes = await sarvam_handler.synthesize_tts_end(test_text, "en-IN")
        
        return {
            "status": "success",
            "message": "TTS test completed",
            "audio_size": len(audio_bytes),
            "text": test_text
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/test-stream-websocket/")
async def test_stream_websocket():
    """
    Test endpoint to check if stream WebSocket is accessible
    """
    return {
        "status": "success",
        "message": "Stream WebSocket endpoint is available",
        "endpoint": "/stream",
        "customer_data_count": len(customer_data)
    }

# Server startup section
if __name__ == "__main__":
    import uvicorn
    
    print("🚀 Voice Assistant Call Management System")
    print("=" * 50)
    print("🌐 Starting server on http://localhost:8000")
    print("📊 Enhanced Dashboard (default): http://localhost:8000/")
    print("📋 Original Dashboard: http://localhost:8000/original")
    print("📁 Static Files: http://localhost:8000/static/")
    print("🔧 API Documentation: http://localhost:8000/docs")
    print("🔌 WebSocket endpoint: ws://localhost:8000/ws/{session_id}")
    print("=" * 50)
    
    uvicorn.run(
        "main:app",  # Use import string format to fix reload warning
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )