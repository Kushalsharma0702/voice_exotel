from fastapi import FastAPI, WebSocket, Request, UploadFile, File, Body
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

import utils. connect_agent as agent
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

CHUNK_SIZE = 800  # bytes for 20ms at 8000 Hz, 16-bit mono

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
sarvam = SarvamHandler(SARVAM_API_KEY)

BUFFER_DURATION_SECONDS = 1.0
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_DURATION = 5

GREETING_TEMPLATE_001 = {
    "en-IN": "Hello... this is Priya, calling on behalf of South India Finvest Bank. Am I speaking with Mr. {name}?",
    "hi-IN": "नमस्ते... मैं प्रिय हूं, और ज़्रोसिस बैंक की ओर से बात कर रही हूं। क्या मैं श्री/सुश्री {name} से बात कर रही हूं?",
    "ta-IN": "வணக்கம்... நான் பிரியா, இது South India Finvest Bank அழைப்பு. திரு/திருமதி {name} பேசுகிறீர்களா?",
    "te-IN": "హలో... నేను ప్రియ మాట్లాడుతున్నాను, South India Finvest Bank కాల్. మిస్టర్/మిసెస్ {name} మాట్లాడుతున్నారా?",
    "ml-IN": "നമസ്കാരം... ഞാൻ പ്രിയയാണ്, സൗത്ത് ഇന്ത്യ ഫിൻവെസ്റ്റ് ബാങ്കിന്റെ ഭാഗമായാണ് വിളിച്ചത്. {name} ആണോ സംസാരിക്കുന്നത്?",
    "gu-IN": "નમસ્તે... હું પ્રિયા છું, સાઉથ ઇન્ડિયા ફિનવેસ્ટ બેંક તરફથી બોલી રહી છું. શું હું શ્રી {name} સાથે વાત કરી રહી છું?",
    "mr-IN": "नमस्कार... मी प्रिया बोलत आहे, साउथ इंडिया फिनवेस्ट बँकेकडून. मी श्री {name} शी बोलत आहे का?",
    "bn-IN": "নমস্কার... আমি প্রিয়া, সাউথ ইন্ডিয়া ফিনভেস্ট ব্যাংকের পক্ষ থেকে ফোন করছি। আমি কি {name} এর সাথে কথা বলছি?",
    "kn-IN": "ನಮಸ್ಕಾರ... ನಾನು ಪ್ರಿಯಾ, ಸೌತ್ ಇಂಡಿಯಾ ಫಿನ್‌ವೆಸ್ಟ್ ಬ್ಯಾಂಕ್‌ನಿಂದ ಕರೆ ಮಾಡುತ್ತಿದ್ದೇನೆ. ನಾನು ಶ್ರೀ {name} ಅವರೊಂದಿಗೆ ಮಾತನಾಡುತ್ತಿದ್ದೇನೆವಾ?",
    "pa-IN": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ... ਮੈਂ ਪ੍ਰਿਆ ਹਾਂ, ਸਾਊਥ ਇੰਡੀਆ ਫਿਨਵੈਸਟ ਬੈਂਕ ਵੱਲੋਂ ਗੱਲ ਕਰ ਰਹੀ ਹਾਂ। ਕੀ ਮੈਂ ਸ੍ਰੀ {name} ਨਾਲ ਗੱਲ ਕਰ ਰਹੀ ਹਾਂ?",
    "or-IN": "ନମସ୍କାର... ମୁଁ ପ୍ରିୟା, ସାଉଥ୍ ଇଣ୍ଡିଆ ଫିନଭେଷ୍ଟ ବ୍ୟାଙ୍କରୁ କଥାହୁଁଛି। ମୁଁ {name} ସହିତ କଥାହୁଁଛି କି?"
}

GREETING_TEMPLATE = {
    "en-IN": "Hello... this is Priya, calling on behalf of South India Finvest Bank. Am I speaking with Mr. {name}?",
    "hi-IN": "नमस्ते... मैं प्रिय हूं, और South India Finvest Bank की ओर से बात कर रही हूं। क्या मैं श्री/सुश्री {name} से बात कर रही हूं?",
    "ta-IN": "வணக்கம்... நான் பிரியா, இது South India Finvest Bank அழைப்பு. திரு/திருமதி {name} பேசுகிறீர்களா?",
    "te-IN": "హలో... నేను ప్రియ మాట్లాడుతున్నాను, ఇది South India Finvest Bank నుండి కాల్. మిస్టర్/మిసెస్ {name} మాట్లాడుతున్నారా?",
    "ml-IN": "നമസ്കാരം... ഞാൻ പ്രിയയാണ്, South India Finvest Bank-ന്റെ ഭാഗമായാണ് വിളിച്ചത്. {name} ആണോ സംസാരിക്കുന്നത്?",
    "gu-IN": "નમસ્તે... હું પ્રિયા છું, South India Finvest Bank તરફથી બોલી રહી છું. શું હું શ્રી {name} સાથે વાત કરી રહી છું?",
    "mr-IN": "नमस्कार... मी प्रिया बोलत आहे, South India Finvest Bank कडून. मी श्री {name} शी बोलत आहे का?",
    "bn-IN": "নমস্কার... আমি প্রিয়া, South India Finvest Bank-এর পক্ষ থেকে ফোন করছি। আমি কি {name} এর সাথে কথা বলছি?",
    "kn-IN": "ನಮಸ್ಕಾರ... ನಾನು ಪ್ರಿಯಾ, South India Finvest Bank ನಿಂದ ಕರೆ ಮಾಡುತ್ತಿದ್ದೇನೆ. ನಾನು ಶ್ರೀ {name} ಅವರೊಂದಿಗೆ ಮಾತನಾಡುತ್ತಿದ್ದೇನೆವಾ?",
    "pa-IN": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ... ਮੈਂ ਪ੍ਰਿਆ ਹਾਂ, South India Finvest Bank ਵੱਲੋਂ ਗੱਲ ਕਰ ਰਹੀ ਹਾਂ। ਕੀ ਮੈਂ ਸ੍ਰੀ {name} ਨਾਲ ਗੱਲ ਕਰ ਰਹੀ ਹਾਂ?",
    "or-IN": "ନମସ୍କାର... ମୁଁ ପ୍ରିୟା, South India Finvest Bank ବ୍ୟାଙ୍କରୁ କଥାହୁଁଛି। ମୁଁ {name} ସହିତ କଥାହୁଁଛି କି?"
}

# Customer details - these would ideally come from a database or CRM based on the incoming call 'From' number
customer = {
        "name": "Jothika",
        "loan_id": "5 9 6 9 2 ", # Maps to loan_last4
        "amount": "2700", # Maps to emi_amount
        "due_date": "11 July", 
        "lang": "ta-IN"# Maps to due_date
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

async def record_audio_from_websocket(websocket) -> bytes:
    call_detected_lang = "en-IN" # Default language, will be updated after first user response
    audio_buffer = bytearray()
    last_transcription_time = time.time()
    interaction_complete = False # Flag to stop processing media after the main flow ends
    print("[Voicebot] record_audio_from_websocket.")
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            if msg.get("event") == "start":
                print("[WebSocket] 🔁 Got start event")


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
                            print("[Voicebot] No audio received during language detection stage. Playing 'didn't hear' prompt.")
                            await play_did_not_hear_response(websocket)
                            print("[Voicebot] No audio received during agent question stage. Repeating question.")
                    #await play_agent_connect_question(websocket, call_detected_lang)
    except Exception as e:
        print(f"[WebSocket Error] ❌ {e}")
    finally:
        await websocket.close()
        print("[WebSocket] 🔒 Closed")

    return bytes(audio_buffer)


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
                    #await play_initial_greeting(websocket, customer['name'])
                    await greeting_template_play(websocket, customer, lang=customer['lang'])
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
                            print(f"[Voicebot] 2. Detected Language: {call_detected_lang} , {customer['lang']}")
                            if customer['lang'] != call_detected_lang :
                                await greeting_template_play(websocket, customer, lang=call_detected_lang)
                            await play_emi_details_part1(websocket, customer, call_detected_lang)
                            await play_emi_details_part2(websocket, customer, call_detected_lang)
                            await play_agent_connect_question(websocket, call_detected_lang)
                            conversation_stage = "WAITING_AGENT_RESPONSE"
                        
                        elif conversation_stage == "WAITING_AGENT_RESPONSE":
                            intent = detect_intent(transcript.lower())
                            if intent == "affirmative" or "agent_transfer" :
                                print("[Voicebot] User affirmed agent transfer. Initiating transfer.")
                                # Replace "08438019383" with the actual customer number from the call context
                                # This number would typically be available from the Exotel webhook payload at call start
                                await play_transfer_to_agent(websocket, customer_number="08438019383") 
                                conversation_stage = "TRANSFERRING_TO_AGENT"
                                interaction_complete = True
                                await websocket.close()
                                print("[WebSocket-TRANSFERRING_TO_AGENT] 🔒 Closed")
                                break
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
    print(f"detect_intent: {text}")
    if any(word in text for word in ["agent", "live agent", "speak to someone", "transfer", "help desk"]):
        return "agent_transfer"
    elif any(word in text for word in ["yes", "yeah", "sure", "okay", "haan", "ஆம்", "அவுனு", "हॉं", "ಹೌದು", "please","yes", "okay", 
                                       "ok", "sure", "alright", "go ahead", "continue", "yeah", "yup", "of course", "please do", "you may", "proceed",
                                       "ஆம்", "ஆமாம்", "சரி", "தயார்", "பேசுங்கள்", "இயலும்", "தொடங்கு", "ஆம் சரி", "வாங்க", "நிச்சயம்",
                                       "ശരി", "അതെ", "തുടങ്ങി", "സരി", "നിശ്ചയം", "തയ്യാര്", "ആണേ", "ഓക്കേ",
                                       "అవును", "సరే", "చెప్పు", "తప్పకుండా", "అలాగే", "కనీసం", "తయారు", "ఓకే",
                                       "ಹೌದು", "ಸರಿ", "ಹೇಳಿ", "ತಯಾರು", "ನಿಶ್ಚಿತವಾಗಿ", "ಬನ್ನಿ", "ಓಕೆ", "ಶರುವಮಾಡಿ"
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
    "kn": ["ಹೌದು", "ಸರಿ", "ಹೇಳಿ", "ತಯಾರು", "ನಿಶ್ಚಿತವಾಗಿ", "ಬನ್ನಿ", "ಓಕೆ", "ಶರುವಮಾಡಿ"]
}

NEGATIVE_KEYWORDS = {
    "en": ["no", "not now", "later", "don't want", "maybe later", "not interested", "nope"],
    "ta": ["இல்லை", "வேண்டாம்", "இப்போது இல்லை", "பின்னர்", "இல்ல"] ,
    "ml": ["ഇല്ല", "വേണ്ട", "ഇപ്പോൾ ഇല്ല", "പിന്നീട്"],
    "te": ["కాదు", "వద్దు", "ఇప్పుడవసరం లేదు", "తరువాత"],
    "kn": ["ಇಲ್ಲ", "ಬೇಡ", "ಇಲ್ಲವೇ", "ನಂತರ", "ಇದೀಗ ಬೇಡ"]
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
    repeat_text = "Sorry, I didn't catch that. Can you please repeat if this is a good time to talk?"
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
    #await agent.trigger_exotel_agent_transfer(customer_number, AGENT_NUMBER)


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
    flow_url = f"http://my.exotel.com/{EXOTEL_SID}/exoml/start_voice/{EXOTEL_FLOW_APP_ID}"

    print(f"Call Details: {to_number} {EXOTEL_VIRTUAL_NUMBER} {flow_url}")
    payload = {
        'From': to_number,
        'CallerId': EXOTEL_VIRTUAL_NUMBER,
        'Url': flow_url,
        'CallType': 'trans',
        'TimeLimit': '300',
        'TimeOut': '30',
        'CustomField': f'DashboardTriggeredCall|lang={initial_lang}'
    }
    try:
        auth = HTTPBasicAuth(EXOTEL_API_KEY, EXOTEL_API_TOKEN)
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
    flow_url = f"http://my.exotel.com/{EXOTEL_SID}/exoml/start_voice/{EXOTEL_FLOW_APP_ID}"
    payload = {
        'From': customer_info.get('phone', '').strip(),
        'CallerId': EXOTEL_VIRTUAL_NUMBER,
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
        auth = auth = HTTPBasicAuth(EXOTEL_API_KEY, EXOTEL_API_TOKEN)
        async with httpx.AsyncClient(auth=auth) as client:
            response = await client.post(url, data=payload)
        if response.status_code == 200:
            return {"phone": customer_info.get('phone'), "status": "triggered", "response": response.json()}
        else:
            return {"phone": customer_info.get('phone'), "status": f"error: {response.status_code}", "response": response.text, "payload": payload}
    except Exception as e:
        return {"phone": customer_info.get('phone'), "status": f"exception: {e}", "payload": payload}

# --- State to Language Mapping ---
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
    if not state:
        return 'en-IN'
    return STATE_TO_LANGUAGE.get(state.strip().lower(), 'en-IN')

# --- TEST MODE for Exotel API (set to True to mock calls) ---


@app.post("/trigger-bulk-calls/")
async def trigger_bulk_calls(customers: list = Body(...)):
    """
    Triggers calls to a list of customers (as returned by /upload-customers/).
    Expects a JSON array: [ ... ]
    """
    TEST_MODE=False
    results = []
    for customer in customers:
        # Assign initial language from state
        initial_lang = get_initial_language_from_state(customer.get('state', ''))
        customer['initial_lang'] = initial_lang
        # Validate required fields before calling
        if not customer.get('phone') or not EXOTEL_VIRTUAL_NUMBER or not EXOTEL_FLOW_APP_ID:
            results.append({"phone": customer.get('phone'), "status": "error: missing required fields", "customer": customer})
            continue
        if TEST_MODE:
            print(f"[MOCK] Would trigger call to {customer['phone']} with initial_lang={initial_lang}")
            results.append({"phone": customer['phone'], "status": "mocked", "initial_lang": initial_lang})
        else:
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
    print("[WebSocket /ws] Dashboard client connected. Waiting for call trigger messages ---.")
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