from fastapi import FastAPI, WebSocket, Request, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates # <-- NEW IMPORT
import xml.etree.ElementTree as ET
import json
import base64
import os
import asyncio
import httpx
import requests
from requests.auth import HTTPBasicAuth
from pydantic import BaseModel

import utils.agent_transfer as agent
import pandas as pd

app = FastAPI()

# Mount the static directory to serve static files (like CSS, JS, images, and your index.html)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Configure Jinja2Templates to serve HTML files from the 'static' directory
# This assumes your index.html is directly inside the 'static' folder
templates = Jinja2Templates(directory="static")

# --- NEW: Dashboard HTML Endpoint ---
@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    """
    Serves the dashboard HTML file at the root URL.
    """
    return templates.TemplateResponse("index.html", {"request": request})

class ExotelWebhookPayload(BaseModel):
    CallSid: str
    From: str
    To: str
    Direction: str

CHUNK_SIZE = 320  # bytes for 20ms at 8000 Hz, 16-bit mono

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

sarvam = SarvamHandler(SARVAM_API_KEY)

BUFFER_DURATION_SECONDS = 1.0
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_DURATION = 3.5

GREETING_TEMPLATE = {
    "en-IN": "Hello, this is Priya calling on behalf of South India Finvest Bank. Am I speaking with Mr. {name}?",
    "hi-IN": "नमस्ते, मैं प्रिय हूं और ज़्रोसिस बैंक की ओर से बात कर रही हूं। क्या मैं श्री/सुश्री {name} से बात कर रही हूं?",
    "ta-IN": "வணக்கம், நான் பிரியா. இது ஸ்ரோசிஸ் வங்கியிலிருந்து அழைப்பு. திரு/திருமதி {name} பேசுகிறீர்களா?",
    "te-IN": "హలో, నేను ప్రియ మాట్లాడుతున్నాను, ఇది జ్రోసిస్ బ్యాంక్ నుండి కాల్. మిస్టర్/మిసెస్ {name} మాట్లాడుతున్నారా?"
}

# Customer details - these would ideally come from a database or CRM based on the incoming call 'From' number
customer = {
        "name": "Ravi",
        "loan_id": "7824", # Maps to loan_last4
        "amount": "4,500", # Maps to emi_amount
        "due_date": "25 July", # Maps to due_date
}

# --- New TTS Helper Functions for the specified flow ---

async def play_initial_greeting(websocket, customer_name: str):
    """Plays the very first greeting in English."""
    prompt_text = f"Hello, this is South India Finvest Bank AI Assistant calling. Am I speaking with {customer_name}?"
    print(f"[Sarvam TTS] 🔁 Converting initial greeting: {prompt_text}")
    audio_bytes = await sarvam.synthesize_tts_end(prompt_text, "en-IN")
    await stream_audio_to_websocket(websocket, audio_bytes)

async def play_did_not_hear_response(websocket):
    """Plays a prompt when the initial response is not heard."""
    prompt_text = (
        "I'm sorry, I didn't hear your response. This call is regarding your loan account. "
        "If this is a convenient time to talk, please say 'yes'. Otherwise, we'll try to reach you later."
    )
    print(f"[Sarvam TTS] 🔁 Converting 'didn't hear' prompt: {prompt_text}")
    audio_bytes = await sarvam.synthesize_tts_end(prompt_text, "en-IN") # Keep English for this retry
    await stream_audio_to_websocket(websocket, audio_bytes)

async def greeting_template_play(websocket, customer_info, lang: str):
    """Plays the personalized greeting in the detected language."""
    print("greeting_template_play")
    greeting = GREETING_TEMPLATE.get(lang, GREETING_TEMPLATE["en-IN"]).format(name=customer_info['name'])
    print(f"[Sarvam TTS] 🔁 Converting personalized greeting: {greeting}")
    audio_bytes = await sarvam.synthesize_tts_end(greeting, lang)
    await stream_audio_to_websocket(websocket, audio_bytes)

# --- Multilingual Prompt Templates ---
EMI_DETAILS_PART1_TEMPLATE = {
    "en-IN": "Thank you. I'm calling about your loan ending in {loan_id}, which has an outstanding EMI of ₹{amount} due on {due_date}. I understand payments can be delayed — I'm here to help you avoid any further impact.",
    "hi-IN": "धन्यवाद। मैं आपके लोन (अंतिम चार अंक {loan_id}) के बारे में कॉल कर रही हूँ, जिसकी बकाया ईएमआई ₹{amount} है, जो {due_date} को देय है। मैं समझती हूँ कि भुगतान में देरी हो सकती है — मैं आपकी मदद के लिए यहाँ हूँ ताकि आगे कोई समस्या न हो।",
    "ta-IN": "நன்றி. உங்கள் கடன் (கடைசி நான்கு இலக்கங்கள் {loan_id}) குறித்து அழைக்கிறேன், அதற்கான நிலுவை EMI ₹{amount} {due_date} அன்று செலுத்த வேண்டியது உள்ளது. தாமதம் ஏற்படலாம் என்பதை புரிந்துகொள்கிறேன் — மேலும் பாதிப்பு ஏற்படாமல் உதவ நான் இங்கே இருக்கிறேன்.",
    "te-IN": "ధన్యవాదాలు. మీ రుణం ({loan_id} తో ముగిసే) గురించి కాల్ చేస్తున్నాను, దీనికి ₹{amount} EMI {due_date} నాటికి బాకీగా ఉంది. చెల్లింపులు ఆలస్యం కావచ్చు — మరింత ప్రభావం లేకుండా మీకు సహాయం చేయడానికి నేను ఇక్కడ ఉన్నాను."
}

EMI_DETAILS_PART2_TEMPLATE = {
    "en-IN": "Please note: if this EMI remains unpaid, it may be reported to the credit bureau, which can affect your credit score. Continued delay may also classify your account as delinquent, leading to penalty charges or collection notices.",
    "hi-IN": "कृपया ध्यान दें: यदि यह ईएमआई बकाया रहती है, तो इसे क्रेडिट ब्यूरो को रिपोर्ट किया जा सकता है, जिससे आपका क्रेडिट स्कोर प्रभावित हो सकता है। लगातार देरी से आपका खाता डिफॉल्टर घोषित हो सकता है, जिससे पेनल्टी या कलेक्शन नोटिस आ सकते हैं।",
    "ta-IN": "தயவு செய்து கவனிக்கவும்: இந்த EMI செலுத்தப்படவில்லை என்றால், அது கிரெடிட் ப்யூரோவுக்கு தெரிவிக்கப்படலாம், இது உங்கள் கிரெடிட் ஸ்கோருக்கு பாதிப்பை ஏற்படுத்தும். தொடர்ந்த தாமதம் உங்கள் கணக்கை குற்றவாளியாக வகைப்படுத்தும், அபராதம் அல்லது வசூல் நோட்டீஸ் வரலாம்.",
    "te-IN": "దయచేసి గమనించండి: ఈ EMI చెల్లించకపోతే, అది క్రెడిట్ బ్యూరోకు నివేదించబడవచ్చు, ఇది మీ క్రెడిట్ స్కోర్‌ను ప్రభావితం చేయవచ్చు. కొనసాగుతున్న ఆలస్యం వల్ల మీ ఖాతా డిఫాల్ట్‌గా పరిగణించబడుతుంది, జరిమానాలు లేదా వసూలు నోటీసులు రావచ్చు."
}

AGENT_CONNECT_TEMPLATE = {
    "en-IN": "If you're facing difficulties, we have options like part payments or revised EMI plans. Would you like me to connect to one of our agents, to assist you better?",
    "hi-IN": "यदि आपको कठिनाई हो रही है, तो हमारे पास आंशिक भुगतान या संशोधित ईएमआई योजनाओं जैसे विकल्प हैं। क्या आप चाहेंगे कि मैं आपको हमारे एजेंट से जोड़ दूं, ताकि वे आपकी मदद कर सकें?",
    "ta-IN": "உங்களுக்கு சிரமம் இருந்தால், பகுதி கட்டணம் அல்லது திருத்தப்பட்ட EMI திட்டங்கள் போன்ற விருப்பங்கள் உள்ளன. உங்களுக்கு உதவ எங்கள் ஏஜெண்டுடன் இணைக்க விரும்புகிறீர்களா?",
    "te-IN": "మీకు ఇబ్బంది ఉంటే, భాగ చెల్లింపులు లేదా సవరించిన EMI ప్లాన్‌లు వంటి ఎంపికలు ఉన్నాయి. మీకు సహాయం చేయడానికి మా ఏజెంట్‌ను కలిపించాలా?"
}

GOODBYE_TEMPLATE = {
    "en-IN": "I understand. If you change your mind, please call us back. Thank you. Goodbye.",
    "hi-IN": "मैं समझती हूँ। यदि आप अपना विचार बदलते हैं, तो कृपया हमें वापस कॉल करें। धन्यवाद। अलविदा।",
    "ta-IN": "நான் புரிந்துகொள்கிறேன். நீங்கள் உங்கள் மனதை மாற்றினால், தயவுசெய்து எங்களை மீண்டும் அழைக்கவும். நன்றி. விடைபெறுகிறேன்.",
    "te-IN": "నాకు అర్థమైంది. మీరు మీ అభిప్రాయాన్ని మార్చుకుంటే, దయచేసి మమ్మల్ని తిరిగి కాల్ చేయండి. ధన్యవాదాలు. వీడ్కోలు."
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
    audio_bytes = await sarvam.synthesize_tts_end(prompt_text, lang)
    await stream_audio_to_websocket(websocket, audio_bytes)

async def play_emi_details_part2(websocket, customer_info, lang: str):
    """Plays the second part of EMI details."""
    prompt_text = EMI_DETAILS_PART2_TEMPLATE.get(lang, EMI_DETAILS_PART2_TEMPLATE["en-IN"])
    print(f"[Sarvam TTS] 🔁 Converting EMI part 2: {prompt_text}")
    audio_bytes = await sarvam.synthesize_tts_end(prompt_text, lang)
    await stream_audio_to_websocket(websocket, audio_bytes)

async def play_agent_connect_question(websocket, lang: str):
    """Asks the user if they want to connect to a live agent."""
    prompt_text = AGENT_CONNECT_TEMPLATE.get(lang, AGENT_CONNECT_TEMPLATE["en-IN"])
    print(f"[Sarvam TTS] 🔁 Converting agent connect question: {prompt_text}")
    audio_bytes = await sarvam.synthesize_tts_end(prompt_text, lang)
    await stream_audio_to_websocket(websocket, audio_bytes)

async def play_goodbye_after_decline(websocket, lang: str):
    """Plays a goodbye message if the user declines agent connection."""
    prompt_text = GOODBYE_TEMPLATE.get(lang, GOODBYE_TEMPLATE["en-IN"])
    print(f"[Sarvam TTS] 🔁 Converting goodbye after decline: {prompt_text}")
    audio_bytes = await sarvam.synthesize_tts_end(prompt_text, lang)
    await stream_audio_to_websocket(websocket, audio_bytes)

# --- Main WebSocket Endpoint (Voicebot Flow) ---

@app.websocket("/stream")
async def exotel_voicebot(websocket: WebSocket):
    await websocket.accept()
    print("[WebSocket] ✅ Connected to Exotel Voicebot Applet")
    
    # State variable for the conversation stage
    conversation_stage = "INITIAL_GREETING" # States: INITIAL_GREETING, WAITING_FOR_LANG_DETECT, PLAYING_PERSONALIZED_GREETING, PLAYING_EMI_PART1, PLAYING_EMI_PART2, ASKING_AGENT_CONNECT, WAITING_AGENT_RESPONSE, TRANSFERRING_TO_AGENT, GOODBYE_DECLINE
    call_detected_lang = "en-IN" # Default language, will be updated after first user response
    audio_buffer = bytearray()
    last_transcription_time = time.time()
    interaction_complete = False # Flag to stop processing media after the main flow ends

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            if msg.get("event") == "start":
                print("[WebSocket] 🔁 Got start event")
                if conversation_stage == "INITIAL_GREETING":
                    print("[Voicebot] 1. Sending initial English greeting.")
                    await play_initial_greeting(websocket, customer['name'])
                    conversation_stage = "WAITING_FOR_LANG_DETECT"
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
                            await play_did_not_hear_response(websocket)
                        elif conversation_stage == "WAITING_AGENT_RESPONSE":
                            print("[Voicebot] No audio received during agent question stage. Repeating question.")
                            await play_agent_connect_question(websocket, call_detected_lang)
                        audio_buffer.clear()
                        last_transcription_time = now
                        continue

                    transcript = sarvam.transcribe_from_payload(audio_buffer)
                    print(f"[Sarvam ASR] 📝 Transcript: {transcript}")

                    if transcript:
                        if conversation_stage == "WAITING_FOR_LANG_DETECT":
                            call_detected_lang = detect_language(transcript)
                            print(f"[Voicebot] 2. Detected Language: {call_detected_lang}")
                            
                            await greeting_template_play(websocket, customer, lang=call_detected_lang)
                            await play_emi_details_part1(websocket, customer, call_detected_lang)
                            await play_emi_details_part2(websocket, customer, call_detected_lang)
                            await play_agent_connect_question(websocket, call_detected_lang)
                            conversation_stage = "WAITING_AGENT_RESPONSE"
                        
                        elif conversation_stage == "WAITING_AGENT_RESPONSE":
                            intent = detect_intent(transcript.lower())
                            if intent == "affirmative":
                                print("[Voicebot] User affirmed agent transfer. Initiating transfer.")
                                # Replace "08438019383" with the actual customer number from the call context
                                # This number would typically be available from the Exotel webhook payload at call start
                                await play_transfer_to_agent(websocket, customer_number="08438019383") 
                                conversation_stage = "TRANSFERRING_TO_AGENT"
                                interaction_complete = True
                            elif intent == "negative":
                                print("[Voicebot] User declined agent transfer. Saying goodbye.")
                                await play_goodbye_after_decline(websocket, call_detected_lang)
                                conversation_stage = "GOODBYE_DECLINE"
                                interaction_complete = True
                            else:
                                print("[Voicebot] Unclear response to agent connect. Repeating question.")
                                await play_agent_connect_question(websocket, call_detected_lang)
                        # Add more elif conditions here for additional conversation stages if your flow extends

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

    if any(word in text for word in ["नमस्ते", "हां", "नहीं", "कैसे", "आप"]) or _is_devanagari(text):
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

def detect_intent(text):
    # This intent detection is simplified for the flow provided by the user.
    # For a production system, consider a more robust NLU solution (e.g., fine-tuned LLM, Rasa, Dialogflow).
    if any(word in text for word in ["agent", "live agent", "speak to someone", "transfer", "help desk"]):
        return "agent_transfer"
    elif any(word in text for word in ["yes", "yeah", "sure", "okay", "haan", "ஆம்", "அவுனு", "हॉं", "ಹೌದು", "please"]):
        return "affirmative"
    elif any(word in text for word in ["no", "not now", "later", "nah", "nahi", "இல்லை", "காது", "ನಹಿ"]):
        return "negative"
    elif any(word in text for word in ["what", "who", "why", "repeat", "pardon"]):
        return "confused"
    return "unknown"

# --- Audio Streaming and Call Trigger Functions ---

async def play_account_info(websocket): # This function is no longer explicitly used in the new flow but kept for completeness.
    print("play_account_info")
    info_text = (
        "Our records show that your recent loan repayment is overdue."
        "Please note that continued delay in payment may negatively affect your credit score, which can impact your ability to get future loans or financial services."
        "To avoid these consequences, we strongly recommend making the payment at the earliest."
        "If you'd like to speak with an agent about a flexible repayment option or payment plan, please say 'Yes' now."
    )
    print("[Sarvam TTS] 🔁 Converting account info text")
    audio_bytes = await sarvam.synthesize_tts_end(info_text, "en-IN")
    print("[Sarvam TTS] 📢 Account info audio generated")
    await stream_audio_to_websocket(websocket, audio_bytes)

async def play_goodbye_message(websocket): # This function is no longer explicitly used in the new flow but kept for completeness.
    print("play_goodbye_message")
    goodbye_text = "Thank you for your time. We will call back later. Have a good day."
    print("[Sarvam TTS] 🔁 Converting goodbye message text")
    audio_bytes = await sarvam.synthesize_tts_end(goodbye_text, "en-IN")
    print("[Sarvam TTS] 📢 Goodbye audio generated")
    await stream_audio_to_websocket(websocket, audio_bytes)

async def play_repeat_question(websocket): # This function is no longer explicitly used in the new flow but kept for completeness.
    print("play_repeat_question")
    repeat_text = "Sorry, I didn’t catch that. Can you please repeat if this is a good time to talk?"
    print("[Sarvam TTS] 🔁 Converting repeat question text")
    audio_bytes = await sarvam.synthesize_tts_end(repeat_text, "en-IN")
    print("[Sarvam TTS] 📢 Repeat question audio generated")
    await stream_audio_to_websocket(websocket, audio_bytes)


async def play_transfer_to_agent(websocket, customer_number: str):
    print("play_transfer_to_agent")
    transfer_text = (
        "Please wait, we are transferring the call to an agent."
    )
    print("[Sarvam TTS] 🔁 Converting agent transfer prompt")
    # Using 'en-IN' for transfer prompt for consistency, but could be `call_detected_lang`
    audio_bytes = await sarvam.synthesize_tts_end(transfer_text, "en-IN") 
    print("[Sarvam TTS] 📢 Agent transfer audio generated")

    await stream_audio_to_websocket(websocket, audio_bytes)

    print("[Exotel] 📞 Initiating agent call transfer")
    # customer_number must be the `From` number of the original call to the voicebot
    await agent.trigger_exotel_agent_transfer(customer_number, AGENT_NUMBER)


async def stream_audio_to_websocket(websocket, audio_bytes):
    print("stream_audio_to_websocket")
    if not audio_bytes:
        print("[stream_audio_to_websocket] ❌ No audio bytes to stream.")
        return
    for i in range(0, len(audio_bytes), CHUNK_SIZE):
        chunk = audio_bytes[i:i + CHUNK_SIZE]
        if not chunk:
            continue
        b64_chunk = base64.b64encode(chunk).decode("utf-8")
        response_msg = {
            "event": "media",
            "media": {"payload": b64_chunk}
        }
        await websocket.send_json(response_msg)
        await asyncio.sleep(0.02) # Small delay to simulate real-time streaming

# --- Outbound Call Trigger Function (used by dashboard) ---

async def trigger_exotel_call_async(to_number: str, initial_lang: str = "en-IN"):
    """
    Triggers an outbound call via Exotel API using async httpx client.
    This function is now async to fit FastAPI's async nature better.
    Accepts initial_lang for future use.
    """
    url = f"https://api.exotel.com/v1/Accounts/{EXOTEL_SID}/Calls/connect.json"
    flow_url = f"http://my.exotel.com/{EXOTEL_SID}/exoml/start_voice/{EXOTEL_APP_ID}"
    payload = {
        'From': to_number,
        'CallerId': EXOPHONE,
        'Url': flow_url,
        'CallType': 'trans',
        'TimeLimit': '300',
        'TimeOut': '30',
        'CustomField': f'DashboardTriggeredCall|lang={initial_lang}'
    }
    try:
        auth = HTTPBasicAuth(EXOTEL_SID, EXOTEL_TOKEN)
        async with httpx.AsyncClient(auth=auth) as client:
            response = await client.post(url, data=payload)
        if response.status_code == 200:
            print("✅ Exotel call triggered successfully:", response.json())
        else:
            print(f"❌ Failed to trigger Exotel call. Status: {response.status_code}, Response: {response.text}")
            raise Exception(f"Exotel API error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Error triggering Exotel call: {e}")
        raise

async def trigger_exotel_customer_call(customer_info, status_callback_url=None):
    """
    Triggers an outbound call to a customer using Exotel API and connects to the voicebot flow.
    customer_info: dict with keys: phone, name, loan_id, amount, due_date, state
    """
    url = f"https://api.exotel.com/v1/Accounts/{EXOTEL_SID}/Calls/connect.json"
    flow_url = f"http://my.exotel.com/{EXOTEL_SID}/exoml/start_voice/{EXOTEL_APP_ID}"
    payload = {
        'From': customer_info.get('phone', '').strip(),
        'CallerId': EXOPHONE,
        'Url': flow_url,
        'CallType': 'trans',
        'TimeLimit': '300',
        'TimeOut': '30',
        'CustomField': f"BulkUpload|name={customer_info.get('name','')}|loan_id={customer_info.get('loan_id','')}|state={customer_info.get('state','')}"
    }
    if status_callback_url:
        payload['StatusCallback'] = status_callback_url
    # Debug print
    print(f"[Exotel] Payload for {customer_info.get('phone')}: {payload}")
    # Validation
    missing = [k for k in ['From', 'CallerId', 'Url'] if not payload.get(k)]
    if missing:
        return {"phone": customer_info.get('phone'), "status": f"error: missing fields: {missing}", "payload": payload}
    try:
        auth = HTTPBasicAuth(EXOTEL_SID, EXOTEL_TOKEN)
        async with httpx.AsyncClient(auth=auth) as client:
            response = await client.post(url, data=payload)
        if response.status_code == 200:
            return {"phone": customer_info.get('phone'), "status": "triggered", "response": response.json()}
        else:
            return {"phone": customer_info.get('phone'), "status": f"error: {response.status_code}", "response": response.text, "payload": payload}
    except Exception as e:
        return {"phone": customer_info.get('phone'), "status": f"exception: {e}", "payload": payload}

@app.post("/trigger-bulk-calls/")
async def trigger_bulk_calls(customers: list):
    """
    Triggers calls to a list of customers (as returned by /upload-customers/).
    Expects a JSON array: [ ... ]
    """
    results = []
    for customer in customers:
        # Validate required fields before calling
        if not customer.get('phone') or not EXOPHONE or not EXOTEL_APP_ID:
            results.append({"phone": customer.get('phone'), "status": "error: missing required fields", "customer": customer})
            continue
        result = await trigger_exotel_customer_call(customer)
        results.append(result)
    return {"results": results}

# --- WebSocket Endpoint for Dashboard Communication ---
@app.websocket("/ws")
async def websocket_trigger_call(websocket: WebSocket):
    """
    WebSocket endpoint for the dashboard to trigger outbound Exotel calls.
    Expects JSON messages like: `{"action": "trigger-call", "customer_number": "+91XXXXXXXXXX"}`
    """
    await websocket.accept()
    print("[WebSocket /ws] Dashboard client connected. Waiting for call trigger messages.")
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                action = message.get("action")
                customer_number = message.get("customer_number")

                if action == "trigger-call" and customer_number:
                    print(f"📞 Triggering Exotel call to {customer_number} from dashboard...")
                    try:
                        await trigger_exotel_call_async(customer_number)
                        await websocket.send_text(f"📞 Call triggered to {customer_number} successfully.")
                    except Exception as e:
                        await websocket.send_text(f"❌ Error triggering call: {e}")
                else:
                    await websocket.send_text(f"Received unknown or incomplete message: {data}. "
                                             "Expected: {'action': 'trigger-call', 'customer_number': '+91XXXXXXXXXX'}")
            except json.JSONDecodeError:
                await websocket.send_text(f"Received non-JSON message: {data}. Expected JSON for call trigger.")
                
    except WebSocketDisconnect:
        print("[WebSocket /ws] Dashboard client disconnected.")
    except Exception as e:
        print(f"[WebSocket /ws Error] ❌ {e}")

@app.post("/upload-customers/")
async def upload_customers(file: UploadFile = File(...)):
    """
    Accepts an Excel or CSV file, extracts customer details, and returns them for dashboard display.
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
        return {"customers": extracted}
    except Exception as e:
        return {"error": str(e)}