import os
import asyncio
import base64
import json
import time
import traceback
import uuid
import xml.etree.ElementTree as ET
from contextlib import asynccontextmanager
from datetime import datetime
from urllib.parse import quote

import httpx
import pandas as pd
import requests
import uvicorn
from dotenv import load_dotenv
from fastapi import (Body, FastAPI, File, HTTPException, Request, UploadFile,
                     WebSocket)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (HTMLResponse, JSONResponse, PlainTextResponse)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from requests.auth import HTTPBasicAuth
from starlette.websockets import WebSocketDisconnect

# Load environment variables at the very beginning
load_dotenv()

# Import project-specific modules
from database.schemas import (CallStatus, Customer,
                              db_manager, init_database, update_call_status, get_call_session_by_sid)
from services.call_management import call_service
from utils import bedrock_client
from utils.agent_transfer import trigger_exotel_agent_transfer
from utils.handler_asr import SarvamHandler
from utils.redis_session import (init_redis, redis_manager,
                                 generate_websocket_session_id)


# --- Lifespan Management ---
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

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
sarvam_handler = SarvamHandler(SARVAM_API_KEY)

# --- Constants ---
BUFFER_DURATION_SECONDS = 1.0

# --- Multilingual Prompt Templates with SSML and Pauses ---
GREETING_TEMPLATE = {
    "en-IN": "Hello, this is Priya, calling on behalf of South India Finvest Bank. Am I speaking with Mr. {name}?",
    "hi-IN": "नमस्ते, मैं प्रिया हूं, और साउथ इंडिया फिनवेस्ट बैंक की ओर से बात कर रही हूं। क्या मैं श्री/सुश्री {name} से बात कर रही हूं?",
    "ta-IN": "வணக்கம், நான் பிரியா, இது சவுத் இந்தியா ஃபின்வெஸ்ட் வங்கியிலிருந்து அழைப்பு. திரு/திருமதி {name} பேசுகிறீர்களா?",
    "te-IN": "హలో, నేను ప్రియ మాట్లాడుతున్నాను, ఇది సౌత్ ఇండియా ఫిన్‌వెస్ట్ బ్యాంక్ నుండి కాల్. మిస్టర్/మిసెస్ {name} మాట్లాడుతున్నారా?",
    "ml-IN": "നമസ്കാരം, ഞാൻ പ്രിയയാണ്, സൗത്ത് ഇന്ത്യ ഫിൻവെസ്റ്റ് ബാങ്കിന്റെ ഭാഗമായാണ് വിളിച്ചത്. {name} ആണോ സംസാരിക്കുന്നത്?",
    "gu-IN": "નમસ્તે, હું પ્રિયા છું, સાઉથ ઇન્ડિયા ફિનવેસ્ટ બેંક તરફથી બોલી રહી છું. શું હું શ્રી {name} સાથે વાત કરી રહી છું?",
    "mr-IN": "नमस्कार, मी प्रिया बोलत आहे, साउथ इंडिया फिनवेस्ट बँकेकडून. मी श्री {name} शी बोलत आहे का?",
    "bn-IN": "নমস্কার, আমি প্রিয়া, সাউথ ইন্ডিয়া ফিনভেস্ট ব্যাংকের পক্ষ থেকে ফোন করছি। আমি কি {name} এর সাথে কথা বলছি?",
    "kn-IN": "ನಮಸ್ಕಾರ, ನಾನು ಪ್ರಿಯಾ, ಸೌತ್ ಇಂಡಿಯಾ ಫಿನ್‌ವೆಸ್ಟ್ ಬ್ಯಾಂಕ್‌ನಿಂದ ಕರೆ ಮಾಡುತ್ತಿದ್ದೇನೆ. ನಾನು ಶ್ರಿ {name} ಅವರೊಂದಿಗೆ ಮಾತನಾಡುತ್ತಿದ್ದೇನೆವಾ?",
    "pa-IN": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ, ਮੈਂ ਪ੍ਰਿਆ ਹਾਂ, ਸਾਊਥ ਇੰਡੀਆ ਫਿਨਵੈਸਟ ਬੈਂਕ ਵੱਲੋਂ ਗੱਲ ਕਰ ਰਹੀ ਹਾਂ। ਕੀ ਮੈਂ ਸ੍ਰੀ {name} ਨਾਲ ਗੱਲ ਕਰ ਰਹੀ ਹਾਂ?",
    "or-IN": "ନମସ୍କାର, ମୁଁ ପ୍ରିୟା, ସାଉଥ୍ ଇଣ୍ଡିଆ ଫିନଭେଷ୍ଟ ବ୍ୟାଙ୍କରୁ କଥାହୁଁଛି। ମୁଁ {name} ସହିତ କଥାହୁଁଛି କି?",
}

EMI_DETAILS_PART1_TEMPLATE = {
    "en-IN": "Thank you. I am calling about your loan ending in {loan_id}, which has an outstanding EMI of ₹{amount} due on {due_date}. I understand payments can be delayed. I am here to help you avoid any further impact.",
    "hi-IN": "धन्यवाद। मैं आपके लोन (अंतिम चार अंक {loan_id}) के बारे में कॉल कर रही हूँ, जिसकी बकाया ईएमआई ₹{amount} है, जो {due_date} को देय है। मैं समझती हूँ कि भुगतान में देरी हो सकती है। मैं आपकी मदद के लिए यहाँ हूँ ताकि आगे कोई समस्या न हो।",
    "ta-IN": "நன்றி. உங்கள் கடன் (கடைசி நான்கு இலக்கங்கள் {loan_id}) குறித்து அழைக்கிறேன், அதற்கான நிலுவை EMI ₹{amount} {due_date} அன்று செலுத்த வேண்டியது உள்ளது. தாமதம் ஏற்படலாம் என்பதை புரிந்துகொள்கிறேன். மேலும் பாதிப்பு ஏற்படாமல் உதவ நான் இங்கே இருக்கிறேன்.",
    "te-IN": "ధన్యవాదాలు. మీ రుణం ({loan_id} తో ముగిసే) గురించి కాల్ చేస్తున్నాను, దీనికి ₹{amount} EMI {due_date} నాటికి బాకీగా ఉంది. చెల్లింపులు ఆలస్యం కావచ్చు. మరింత ప్రభావం లేకుండా మీకు సహాయం చేయడానికి నేను ఇక్కడ ఉన్నాను.",
    "ml-IN": "നന്ദി. നിങ്ങളുടെ വായ്പ ({loan_id} അവസാനിക്കുന്ന) സംബന്ധിച്ച് വിളിക്കുന്നു, അതിന് ₹{amount} EMI {due_date} ന് ബാക്കി ഉണ്ട്. പണമടയ്ക്കുന്നതിൽ വൈകിപ്പോകാം. കൂടുതൽ പ്രശ്നങ്ങൾ ഒഴിവാക്കാൻ ഞാൻ സഹായിക്കാൻ ഇവിടെ ഉണ്ട്.",
    "gu-IN": "આભાર. હું તમારા લોન ({loan_id}) વિશે કોલ કરી રહી છું, જેમાં ₹{amount} EMI {due_date} સુધી બાકી છે. ચુકવણીમાં વિલંબ થઈ શકે છે. વધુ અસરથી બચવા માટે હું અહીં છું.",
    "mr-IN": "धन्यवाद. मी तुमच्या कर्ज ({loan_id}) विषयी कॉल करत आहे, ज्याची ₹{amount} EMI {due_date} रोजी बाकी आहे. पेमेंटमध्ये उशीर होऊ शकतो. पुढील परिणाम टाळण्यासाठी मी मदतीसाठी येथे आहे.",
    "bn-IN": "ধন্যবাদ. আমি আপনার ঋণ ({loan_id}) সম্পর্কে ফোন করছি, যার ₹{amount} EMI {due_date} তারিখে বাকি আছে। পেমেন্টে দেরি হতে পারে। আরও সমস্যা এড়াতে আমি সাহায্য করতে এখানে আছি।",
    "kn-IN": "ಧನ್ಯವಾದಗಳು. ನಿಮ್ಮ ಸಾಲ ({loan_id}) ಬಗ್ಗೆ ಕರೆ ಮಾಡುತ್ತಿದ್ದೇನೆ, ಇದಕ್ಕೆ ₹{amount} EMI {due_date} ರಂದು ಬಾಕಿ ಇದೆ. ಪಾವತಿಯಲ್ಲಿ ವಿಳಂಬವಾಗಬಹುದು. ಹೆಚ್ಚಿನ ಪರಿಣಾಮ ತಪ್ಪಿಸಲು ನಾನು ಸಹಾಯ ಮಾಡಲು ಇಲ್ಲಿದ್ದೇನೆ.",
    "pa-IN": "ਧੰਨਵਾਦ. ਮੈਂ ਤੁਹਾਡੇ ਲੋਨ ({loan_id}) ਬਾਰੇ ਕਾਲ ਕਰ ਰਹੀ ਹਾਂ, ਜਿਸ ਵਿੱਚ ₹{amount} EMI {due_date} ਤੱਕ ਬਕਾਇਆ ਹੈ। ਭੁਗਤਾਨ ਵਿੱਚ ਦੇਰੀ ਹੋ ਸਕਦੀ ਹੈ. ਹੋਰ ਪ੍ਰਭਾਵ ਤੋਂ ਬਚਣ ਲਈ ਮੈਂ ਇੱਥੇ ਹਾਂ।",
    "or-IN": "ଧନ୍ୟବାଦ. ମୁଁ ଆପଣଙ୍କର ଋଣ ({loan_id}) ବିଷୟରେ କଥାହୁଁଛି, ଯାହାର ₹{amount} EMI {due_date} ରେ ବକାୟା ଅଛି। ଦେୟ ଦେବାରେ ବିଳମ୍ବ ହେବା ସମ୍ଭବ. ଅଧିକ ସମସ୍ୟା ରୋକିବା ପାଇଁ ମୁଁ ଏଠାରେ ଅଛି।"
}

EMI_DETAILS_PART2_TEMPLATE = {
    "en-IN": "Please note. If this EMI remains unpaid, it may be reported to the credit bureau, which can affect your credit score. Continued delay may also classify your account as delinquent, leading to penalty charges or collection notices.",
    "hi-IN": "कृपया ध्यान दें। यदि यह ईएमआई बकाया रहती है, तो इसे क्रेडिट ब्यूरो को रिपोर्ट किया जा सकता है, जिससे आपका क्रेडिट स्कोर प्रभावित हो सकता है। लगातार देरी से आपका खाता डिफॉल्टर घोषित हो सकता है, जिससे पेनल्टी या कलेक्शन नोटिस आ सकते हैं।",
    "ta-IN": "தயவு செய்து கவனிக்கவும். இந்த EMI செலுத்தப்படவில்லை என்றால், அது கிரெடிட் ப்யூரோவுக்கு தெரிவிக்கப்படலாம், இது உங்கள் கிரெடிட் ஸ்கோருக்கு பாதிப்பை ஏற்படுத்தும். தொடர்ந்த தாமதம் உங்கள் கணக்கை குற்றவாளியாக வகைப்படுத்தும், அபராதம் அல்லது வசூல் நோட்டீஸ் வரலாம்.",
    "te-IN": "దయచేసి గమనించండి. ఈ EMI చెల్లించకపోతే, అది క్రెడిట్ బ్యూరోకు నివేదించబడవచ్చు, ఇది మీ క్రెడిట్ స్కోర్‌ను ప్రభావితం చేయవచ్చు. కొనసాగుతున్న ఆలస్యం వల్ల మీ ఖాతా డిఫాల్ట్‌గా పరిగణించబడుతుంది, జరిమానాలు లేదా వసూలు నోటీసులు రావచ్చు.",
    "ml-IN": "ദയവായി ശ്രദ്ധിക്കുക. ഈ EMI അടയ്ക്കപ്പെടാതെ പോയാൽ, അത് ക്രെഡിറ്റ് ബ്യൂറോയ്ക്ക് റിപ്പോർട്ട് ചെയ്യപ്പെടാം, ഇത് നിങ്ങളുടെ ക്രെഡിറ്റ് സ്കോറിനെ ബാധിക്കും. തുടർച്ചയായ വൈകിപ്പിക്കൽ നിങ്ങളുടെ അക്കൗണ്ടിനെ ഡിഫോൾട്ട് ആയി കണക്കാക്കും, പിഴയോ കലക്ഷൻ നോട്ടീസോ വരാം.",
    "gu-IN": "મહેરબાની કરીને નોંધો. જો આ EMI બાકી રહેશે, તો તે ક્રેડિટ બ્યુરોને રિપોર્ટ થઈ શકેછે, જે તમારા ક્રેડિટ સ્કોરને અસર કરી શકેછે. સતત વિલંબથી તમારું ખાતું ડિફોલ્ટ તરીકે ગણાય શકેછે, દંડ અથવા વસૂલાત નોટિસ આવી શકેછે.",
    "mr-IN": "कृपया लक्षात घ्या. ही EMI बकाया राहिल्यास, ती क्रेडिट ब्युरोला रिपोर्ट केली जाऊ शकते, ज्यामुळे तुमचा क्रेडिट स्कोर प्रभावित होऊ शकतो. सततच्या विलंबामुळे तुमचे खाते डिफॉल्टर म्हणून घोषित केले जाऊ शकते, दंड किंवा वसुली नोटीस येऊ शकते.",
    "bn-IN": "দয়া করে লক্ষ্য করুন. এই EMI বকেয়া থাকলে, এটি ক্রেডিট ব্যুরোতে রিপোর্ট করা হতে পারে, যা আপনার ক্রেডিট স্কোরকে প্রভাবিত করতে পারে। ক্রমাগত দেরিতে আপনার অ্যাকাউন্ট ডিফল্ট হিসাবে বিবেচিত হতে পারে, জরিমানা বা সংগ্রহের নোটিশ আসতে পারে।",
    "kn-IN": "ದಯವಿಟ್ಟು ಗಮನಿಸಿ. ಈ EMI ಪಾವತಿಯಾಗದೆ ಇದ್ದರೆ, ಅದು ಕ್ರೆಡಿಟ್ ಬ್ಯೂರೋಗೆ ವರದಿ ಮಾಡಬಹುದು, ಇದು ನಿಮ್ಮ ಕ್ರೆಡಿಟ್ ಸ್ಕೋರ್‌ಗೆ ಪರಿಣಾಮ ಬೀರುತ್ತದೆ. ನಿರಂತರ ವಿಳಂಬದಿಂದ ನಿಮ್ಮ ಖಾತೆಯನ್ನು ಡಿಫಾಲ್ಟ್ ಎಂದು ಪರಿಗಣಿಸಬಹುದು, ದಂಡ ಅಥವಾ ಸಂಗ್ರಹಣಾ ಸೂಚನೆಗಳು ಬರಬಹುದು.",
    "pa-IN": "ਕਿਰਪਾ ਕਰਕੇ ਧਿਆਨ ਦਿਓ. ਜੇ ਇਹ EMI ਬਕਾਇਆ ਰਹੰਦੀ ਹੈ, ਤਾਂ ਇਹਨੂੰ ਕਰੈਡਿਟ ਬਿਊਰੋ ਨੂੰ ਰਿਪੋਰਟ ਕੀਤਾ ਜਾ ਸਕਦਾ ਹੈ, ਜੁਰਮਾਨਾ ਨਾਲ ਤੁਹਾਡਾ ਕਰੈਡਿਟ ਸਕੋਰ ਪ੍ਰਭਾਵਿਤ ਹੋ ਸਕਦਾ ਹੈ। ਲਗਾਤਾਰ ਦੇਰੀ ਨਾਲ ਤੁਹਾਡਾ ਖਾਤਾ ਡਿਫੌਲਟਰ ਘੋਸ਼ਿਤ ਕੀਤਾ ਜਾ ਸਕਦਾ ਹੈ, ਜੁਰਮਾਨਾ ਜਾਂ ਕਲੈਕਸ਼ਨ ਨੋਟਿਸ ਆ ਸਕਦੇ ਹਨ।",
    "or-IN": "ଦୟାକରି ଧ୍ୟାନ ଦିଅନ୍ତୁ. ଏହି EMI ବକାୟା ରହିଲେ, ଏହା କ୍ରେଡିଟ୍ ବ୍ୟୁରୋକୁ ରିପୋର୍ଟ କରାଯାଇପାରେ, ଯାହା ଆପଣଙ୍କର କ୍ରେଡିଟ୍ ସ୍କୋରକୁ ପ୍ରଭାବିତ କରିପାରେ। ଲଗାତାର ବିଳମ୍ବ ଆପଣଙ୍କର ଖାତାକୁ ଡିଫଲ୍ଟ୍ ଭାବରେ ଘୋଷଣା କରିପାରେ, ଜରିମାନା କିମ୍ବା କଲେକ୍ସନ୍ ନୋଟିସ୍ ଆସିପାରେ।"
}

AGENT_CONNECT_TEMPLATE = {
    "en-IN": "If you are facing difficulties, we have options like part payments or revised EMI plans. Would you like me to connect you to one of our agents to assist you better?",
    "hi-IN": "यदि आपको कठिनाई हो रही है, तो हमारे पास आंशिक भुगतान या संशोधित ईएमआई योजनाओं जैसे विकल्प हैं। क्या आप चाहेंगे कि मैं आपको हमारे एजेंट से जोड़ दूं, ताकि वे आपकी मदद कर सकें?",
    "ta-IN": "உங்களுக்கு சிரமம் இருந்தால், பகுதி கட்டணம் அல்லது திருத்தப்பட்ட EMI திட்டங்கள் போன்ற விருப்பங்கள் உள்ளன. உங்களுக்கு உதவ எங்கள் ஏஜெண்டுடன் இணைக்க விரும்புகிறீர்களா?",
    "te-IN": "మీకు ఇబ్బంది ఉంటే, భాగ చెల్లింపులు లేదా సవరించిన EMI ప్లాన్‌లు వంటి ఎంపికలు ఉన్నాయి. మీకు సహాయం చేయడానికి మా ఏజెంట్‌ను కలిపించాలా?",
    "ml-IN": "നിങ്ങൾക്ക് ബുദ്ധിമുട്ട് ഉണ്ടെങ്കിൽ, ഭാഗിക പണമടയ്ക്കൽ അല്ലെങ്കിൽ പുതുക്കിയ EMI പദ്ധതികൾ പോലുള്ള ഓപ്ഷനുകൾ ഞങ്ങൾക്കുണ്ട്. നിങ്ങളെ സഹായിക്കാൻ ഞങ്ങളുടെ ഏജന്റുമായി ബന്ധിപ്പിക്കണോ?",
    "gu-IN": "જો તમને મુશ્કેલી હોય, તો અમારી પાસે ભાગ ચુકવણી અથવા સુધારેલી EMI યોજનાઓ જેવા વિકલ્પો છે. શું હું તમને અમારા એજન્ટ સાથે જોડું?",
    "mr-IN": "तुम्हाला अडचण असल्यास, आमच्याकडे भाग पेमेन्ट किंवा सुधारित EMI योजना आहेत. मी तुम्हाला आमच्या एजंटशी जोडू का?",
    "bn-IN": "আপনার অসুবিধা হলে, আমাদের কাছে আংশিক পেমেন্ট বা সংশোধিত EMI প্ল্যানের মতো বিকল্প রয়েছে। আপনাকে সাহায্য করতে আমাদের এজেন্টের সাথে সংযোগ করব?",
    "kn-IN": "ನಿಮಗೆ ತೊಂದರೆ ಇದ್ದರೆ, ಭಾಗ ಪಾವತಿ ಅಥವಾ ಪರಿಷ್ಕೃತ EMI ಯೋಜನೆಗಳೂ ನಮ್ಮ ಬಳಿ ಇವೆ. ನಿಮಗೆ ಸಹಾಯ ಮಾಡಲು ನಮ್ಮ ಏಜೆಂಟ್‌ಗೆ ಸಂಪರ್ಕ ಮಾಡಬೇಕೆ?",
    "pa-IN": "ਜੇ ਤੁਹਾਨੂੰ ਮੁਸ਼ਕਲ ਆ ਰਹੀ ਹੈ, ਤਾਂ ਸਾਡੇ ਕੋਲ ਹਿੱਸਾ ਭੁਗਤਾਨ ਜਾਂ ਸੋਧੀ EMI ਯੋਜਨਾਵਾਂ ਵਰਗੇ ਵਿਕਲਪ ਹਨ। ਕੀ ਮੈਂ ਤੁਹਾਨੂੰ ਸਾਡੇ ਏਜੰਟ ਨਾਲ ਜੋੜਾਂ?",
    "or-IN": "ଯଦି ଆପଣଙ୍କୁ ସମସ୍ୟା ହେଉଛି, ଆମ ପାଖରେ ଅଂଶିକ ପେମେଣ୍ଟ କିମ୍ବା ସଂଶୋଧିତ EMI ଯୋଜନା ଅଛି। ଆପଣଙ୍କୁ ସହଯୋଗ କରିବା ପାଇଁ ଆମ ଏଜେଣ୍ଟ ସହିତ ଯୋଗାଯୋଗ କରିବି?"
}

GOODBYE_TEMPLATE = {
    "en-IN": "I understand. If you change your mind, please call us back. Thank you. Goodbye.",
    "hi-IN": "मैं समझती हूँ। यदि आप अपना विचार बदलते हैं, तो कृपया हमें वापस कॉल करें। धन्यवाद। अलविदा।",
    "ta-IN": "நான் புரிந்துகொள்கிறேன். நீங்கள் உங்கள் மனதை மாற்றினால், தயவுசெய்து எங்களை மீண்டும் அழைக்கவும். நன்றி. விடைபெறுகிறேன்.",
    "te-IN": "నాకు అర్థమైంది. మీరు మీ అభిప్రాయాన్ని మార్చుకుంటే, దయచేసి మమ్మల్ని తిరిగి కాల్ చేయండి. ధన్యవాదాలు. వీడ్కోలు.",
    "ml-IN": "ഞാൻ മനസ്സിലാക്കുന്നു. നിങ്ങൾ അഭിപ്രായം മാറ്റിയാൽ, ദയവായി ഞങ്ങളെ വീണ്ടും വിളിക്കുക. നന്ദി. വിട.",
    "gu-IN": "હું સમજું છું. જો તમે તમારો મન બદલો, તો કૃપા કરીને અમને પાછા કોલ કરો. આભાર. અલવિદા.",
    "mr-IN": "मी समजते. तुम्ही तुमचा निर्णय बदलल्यास, कृपया आम्हाला पुन्हा कॉल करा. धन्यवाद. गुडबाय.",
    "bn-IN": "আমি বুঝতে পারছি. আপনি যদি মত পরিবর্তন করেন, দয়া করে আমাদের আবার কল করুন। ধন্যবাদ। বিদায়।",
    "kn-IN": "ನಾನು ಅರ್ಥಮಾಡಿಕೊಂಡೆ. ನೀವು ನಿಮ್ಮ ಅಭಿಪ್ರಾಯವನ್ನು ಬದಲಾಯಿಸಿದರೆ, ದಯವಿಟ್ಟು ನಮಗೆ ಮತ್ತೆ ಕರೆ ಮಾಡಿ. ಧನ್ಯವಾದಗಳು. ವಿದಾಯ.",
    "pa-IN": "ਮੈਂ ਸਮਝਦੀ ਹਾਂ. ਜੇ ਤੁਸੀਂ ਆਪਣਾ ਮਨ ਬਦਲੋ, ਤਾਂ ਕਿਰਪਾ ਕਰਕੇ ਸਾਨੂੰ ਮੁੜ ਕਾਲ ਕਰੋ। ਧੰਨਵਾਦ। ਅਲਵਿਦਾ।",
    "or-IN": "ମୁଁ ବୁଝିଥିଲେ. ଯଦି ଆପଣ ମନ ବଦଳାନ୍ତି, ଦୟାକରି ଆମକୁ ପୁଣି କଲ୍ କରନ୍ତୁ। ଧନ୍ୟବାଦ। ବିଦାୟ।"
}

# --- TTS & Audio Helper Functions ---

async def play_transfer_to_agent(websocket, customer_number: str):
    print("play_transfer_to_agent")
    transfer_text = (
        "Please wait, we are transferring the call to an agent."
    )
    print("[Sarvam TTS] 🔁 Converting agent transfer prompt")
    # Using 'en-IN' for transfer prompt for consistency, but could be `call_detected_lang`
    audio_bytes = await sarvam_handler.synthesize_tts("Please wait, we are transferring the call to an agent.", "en-IN")
    print("[Sarvam TTS] 📢 Agent transfer audio generated")

    await stream_audio_to_websocket(websocket, audio_bytes)

    print("[Exotel] 📞 Initiating agent call transfer")
    # The AGENT_NUMBER should be loaded from environment variables
    agent_number = os.getenv("AGENT_PHONE_NUMBER")
    if customer_number and agent_number:
        await trigger_exotel_agent_transfer(customer_number, agent_number)
    else:
        print("[ERROR] Could not initiate agent transfer. Missing customer_number or agent_number.")


async def stream_audio_to_websocket(websocket, audio_bytes):
    CHUNK_SIZE = 8000  # Send 1 second of audio at a time
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
        await asyncio.sleep(float(CHUNK_SIZE) / 16000.0) # Sleep for the duration of the audio chunk

async def greeting_template_play(websocket, customer_info, lang: str):
    """Plays the personalized greeting in the detected language."""
    print("greeting_template_play")
    greeting = GREETING_TEMPLATE.get(lang, GREETING_TEMPLATE["en-IN"]).format(name=customer_info.get('name', 'there'))
    print(f"[Sarvam TTS] 🔁 Converting personalized greeting: {greeting}")
    audio_bytes = await sarvam_handler.synthesize_tts(greeting, lang)
    await stream_audio_to_websocket(websocket, audio_bytes)

async def play_did_not_hear_response(websocket, lang: str):
    """Plays a prompt when the initial response is not heard."""
    prompt_text = "I'm sorry, I didn't hear your response. This call is regarding your loan account. If this is a convenient time to talk, please say 'yes'."
    print(f"[Sarvam TTS] 🔁 Converting 'didn't hear' prompt: {prompt_text}")
    audio_bytes = await sarvam_handler.synthesize_tts(prompt_text, lang)
    await stream_audio_to_websocket(websocket, audio_bytes)

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
    audio_bytes = await sarvam_handler.synthesize_tts(prompt_text, lang)
    await stream_audio_to_websocket(websocket, audio_bytes)

async def play_emi_details_part2(websocket, customer_info, lang: str):
    """Plays the second part of EMI details."""
    prompt_text = EMI_DETAILS_PART2_TEMPLATE.get(lang, EMI_DETAILS_PART2_TEMPLATE["en-IN"])
    print(f"[Sarvam TTS] 🔁 Converting EMI part 2: {prompt_text}")
    audio_bytes = await sarvam_handler.synthesize_tts(prompt_text, lang)
    await stream_audio_to_websocket(websocket, audio_bytes)

async def play_agent_connect_question(websocket, lang: str):
    """Asks the user if they want to connect to a live agent."""
    prompt_text = AGENT_CONNECT_TEMPLATE.get(lang, AGENT_CONNECT_TEMPLATE["en-IN"])
    print(f"[Sarvam TTS] 🔁 Converting agent connect question: {prompt_text}")
    audio_bytes = await sarvam_handler.synthesize_tts(prompt_text, lang)
    await stream_audio_to_websocket(websocket, audio_bytes)

async def play_goodbye_after_decline(websocket, lang: str):
    """Plays a goodbye message if the user declines agent connection."""
    prompt_text = GOODBYE_TEMPLATE.get(lang, GOODBYE_TEMPLATE["en-IN"])
    print(f"[Sarvam TTS] 🔁 Converting goodbye after decline: {prompt_text}")
    audio_bytes = await sarvam_handler.synthesize_tts(prompt_text, lang)
    await stream_audio_to_websocket(websocket, audio_bytes)

# --- Language and Intent Detection ---
def _is_devanagari(text): return any('\u0900' <= ch <= '\u097F' for ch in text)
def _is_tamil(text): return any('\u0B80' <= ch <= '\u0BFF' for ch in text)
def _is_telugu(text): return any('\u0C00' <= ch <= '\u0C7F' for ch in text)
def _is_kannada(text): return any('\u0C80' <= ch <= '\u0CFF' for ch in text)
def _is_malayalam(text): return any('\u0D00' <= ch <= '\u0D7F' for ch in text)
def _is_gujarati(text): return any('\u0A80' <= ch <= '\u0AFF' for ch in text)
def _is_marathi(text): return any('\u0900' <= ch <= '\u097F' for ch in text)
def _is_bengali(text): return any('\u0980' <= ch <= '\u09FF' for ch in text)
def _is_punjabi(text): return any('\u0A00' <= ch <= '\u0A7F' for ch in text)
def _is_oriya(text): return any('\u0B00' <= ch <= '\u0B7F' for ch in text)

def _is_gurmukhi(text):
    """Checks if the text contains any Gurmukhi characters (for Punjabi)."""
    return any('\u0A00' <= char <= '\u0A7F' for char in text)

def detect_language(text):
    text = text.strip().lower()
    if any(word in text for word in ["नमस्ते", "हां", "नहीं"]) or _is_devanagari(text): return "hi-IN"
    if any(word in text for word in ["வணக்கம்", "ஆம்", "இல்லை"]) or _is_tamil(text): return "ta-IN"
    if any(word in text for word in ["హాయ్", "అవును", "కాదు"]) or _is_telugu(text): return "te-IN"
    if any(word in text for word in ["ಹೆಲೋ", "ಹೌದು", "ಇಲ್ಲ"]) or _is_kannada(text): return "kn-IN"
    if any(word in text for word in ["നമസ്കാരം", "അതെ", "ഇല്ല"]) or _is_malayalam(text): return "ml-IN"
    if any(word in text for word in ["નમસ્તે", "હા", "ના"]) or _is_gujarati(text): return "gu-IN"
    if any(word in text for word in ["नमस्कार", "होय", "नाही"]) or _is_marathi(text): return "mr-IN"
    if any(word in text for word in ["নমস্কার", "হ্যাঁ", "না"]) or _is_bengali(text): return "bn-IN"
    if any(word in text for word in ["ਸਤ ਸ੍ਰੀ ਅਕਾਲ", "ਹਾਂ", "ਨਹੀਂ"]) or _is_punjabi(text): return "pa-IN"
    if any(word in text for word in ["ନମସ୍କାର", "ହଁ", "ନା"]) or _is_oriya(text): return "or-IN"
    return "en-IN"

def detect_intent_with_claude(transcript: str, lang: str) -> str:
    """Detects intent using the Claude model via the bedrock_client."""
    print(f"[Claude Intent] Getting intent for: '{transcript}'")
    try:
        # The bedrock_client expects a chat history list of dicts
        chat_history = [{"role": "user", "content": transcript}]
        response = bedrock_client.get_intent_from_text(chat_history)
        
        # The response from the bedrock client is a dictionary, we need to extract the intent.
        # Based on the likely structure, it might be under a key like 'intent'.
        intent = response.get("intent", "unknown")
        print(f"[Claude Intent] Detected intent: {intent}")
        return intent
    except Exception as e:
        print(f"[Claude Intent] ❌ Error detecting intent with Claude: {e}")
        return "unknown"

def detect_intent_fur(text: str, lang: str) -> str:
    """A fallback intent detection function (a more descriptive name for the original detect_intent)."""
    return detect_intent(text)


def detect_intent(text):
    text = text.lower()
    if any(word in text for word in ["agent", "live agent", "speak to someone", "transfer", "help desk"]): return "agent_transfer"
    if any(word in text for word in ["yes", "yeah", "sure", "okay", "haan", "ஆம்", "அவுனு", "हॉं", "ಹೌದು", "please"]): return "affirmative"
    if any(word in text for word in ["no", "not now", "later", "nah", "nahi", "இல்லை", "காது", "ನಹಿ"]): return "negative"
    if any(word in text for word in ["what", "who", "why", "repeat", "pardon"]): return "confused"
    return "unknown"


# --- Static Files and Templates ---
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="static")

# --- HTML Endpoints ---
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

# --- Exotel Passthru Handler ---
@app.get("/passthru-handler", response_class=PlainTextResponse)
async def handle_passthru(request: Request):
    """
    Handles Exotel's Passthru applet request.
    This is a critical, lightweight endpoint that must respond quickly.
    It receives call data, caches it, and updates the DB.
    """
    print("✅ [CHECKPOINT] /passthru-handler hit")
    
    params = request.query_params
    call_sid = params.get("CallSid")
    custom_field = params.get("CustomField")

    if not call_sid:
        print("❌ [ERROR] Passthru handler called without a CallSid.")
        # Still return OK to Exotel to not break their flow, but log the error.
        return "OK"

    print(f"📞 [CHECKPOINT] Passthru: CallSid received: {call_sid}")
    print(f"📦 [CHECKPOINT] Passthru: CustomField received: {custom_field}")

    # Parse the pipe-separated CustomField
    customer_data = {}
    if custom_field:
        try:
            pairs = custom_field.split('|')
            for pair in pairs:
                if '=' in pair:
                    key, value = pair.split('=', 1)
                    customer_data[key.strip()] = value.strip()
            print(f"📊 [CHECKPOINT] Passthru: Parsed Custom Fields: {customer_data}")
        except Exception as e:
            print(f"❌ [ERROR] Passthru: Failed to parse CustomField: {e}")
            # Log error but continue, as we might have the CallSid
    
    # Get the temporary ID to link sessions
    temp_call_id = customer_data.get("temp_call_id")
    print(f"ℹ️ [CHECKPOINT] Passthru: temp_call_id from CustomField: {temp_call_id}")

    # --- Redis Caching ---
    # We now have the official CallSid, let's update/create the Redis session
    if temp_call_id:
        print(f"🔄 [CHECKPOINT] Passthru: Linking session from temp_call_id: {temp_call_id} to new CallSid: {call_sid}")
        redis_manager.link_session_to_sid(temp_call_id, call_sid)
    else:
        print(f"📦 [CHECKPOINT] Passthru: Creating new Redis session for CallSid: {call_sid}")
        redis_manager.create_call_session(call_sid, customer_data)

    # --- Database Update ---
    try:
        print(f"✍️ [CHECKPOINT] Passthru: Updating database for CallSid: {call_sid}")
        update_call_status(
            call_sid=call_sid,
            status=CallStatus.INITIATED,
            customer_id=customer_data.get("id"),
            temp_call_id=temp_call_id
        )
        print(f"✅ [CHECKPOINT] Passthru: Database updated successfully for CallSid: {call_sid}")
    except Exception as e:
        print(f"❌ [CRITICAL] Passthru: Database update failed for CallSid {call_sid}: {e}")

    # IMPORTANT: Always return "OK" for Exotel to proceed with the call flow.
    print("✅ [CHECKPOINT] Passthru: Responding 'OK' to Exotel.")
    return "OK"

# --- WebSocket Endpoint for Voicebot ---
@app.websocket("/ws/voicebot/{session_id}")
async def websocket_voicebot_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    print(f"[WebSocket] ✅ Connected to Exotel Voicebot Applet for session: {session_id}")

    # Initialize variables from query parameters
    query_params = dict(websocket.query_params)
    temp_call_id = query_params.get('temp_call_id')
    call_sid = query_params.get('call_sid', session_id) # Use session_id as a fallback for call_sid
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
        # Ensure the websocket is closed gracefully
        if not websocket.client_state.name == 'DISCONNECTED':
            await websocket.close()
        print("[WebSocket] 🔒 Closed")


# --- API Endpoints for Dashboard ---

class CustomerData(BaseModel):
    name: str
    phone: str
    loan_id: str
    amount: str
    due_date: str
    state: str
    language_code: str

@app.post("/api/upload-customers")
async def upload_customers(file: UploadFile = File(...)):
    """
    Accepts a CSV or Excel file, processes it, and stores customer data in the database.
    """
    return await call_service.upload_and_process_customers(await file.read(), file.filename)

@app.post("/api/trigger-single-call")
async def trigger_single_call(customer_id: str = Body(..., embed=True)):
    """
    Triggers a single call to a customer by their ID.
    """
    return await call_service.trigger_single_call(customer_id)

@app.post("/api/trigger-bulk-calls")
async def trigger_bulk_calls(customer_ids: list[str] = Body(..., embed=True)):
    """
    Triggers calls to a list of customers by their IDs.
    """
    return await call_service.trigger_bulk_calls(customer_ids)

@app.get("/api/customers")
async def get_all_customers():
    """
    Retrieves all customers from the database.
    """
    session = db_manager.get_session()
    try:
        customers = session.query(Customer).all()
        return [
            {
                "id": str(c.id),
                "name": c.name,
                "phone_number": c.phone_number,
                "language_code": c.language_code,
                "loan_id": c.loan_id,
                "amount": c.amount,
                "due_date": c.due_date,
                "state": c.state,
                "created_at": c.created_at.isoformat()
            } for c in customers
        ]
    finally:
        session.close()

@app.post("/exotel-webhook")
async def exotel_webhook(request: Request):
    """
    Handles Exotel status webhooks for call status updates.
    """
    try:
        # Get the form data from Exotel webhook
        form_data = await request.form()
        call_sid = form_data.get("CallSid")
        call_status = form_data.get("CallStatus")
        call_duration = form_data.get("CallDuration") 
        
        print(f"📞 [WEBHOOK] Received Exotel webhook:")
        print(f"   CallSid: {call_sid}")
        print(f"   CallStatus: {call_status}")
        print(f"   CallDuration: {call_duration}")
        print(f"   All form data: {dict(form_data)}")
        
        if call_sid:
            # Update call status in database
            session = db_manager.get_session()
            try:
                call_session = get_call_session_by_sid(session, call_sid)
                if call_session:
                    # Map Exotel status to internal status
                    status_mapping = {
                        'ringing': 'ringing',
                        'in-progress': 'in_progress', 
                        'completed': 'completed',
                        'busy': 'busy',
                        'no-answer': 'no_answer',
                        'failed': 'failed',
                        'canceled': 'failed'
                    }
                    
                    internal_status = status_mapping.get(call_status.lower(), call_status)
                    
                    # Update call session
                    update_call_status(
                        session, 
                        call_sid, 
                        internal_status,
                        f"Exotel webhook: {call_status}",
                        extra_data={'webhook_data': dict(form_data)}
                    )
                    
                    print(f"✅ [WEBHOOK] Updated call {call_sid} status to: {internal_status}")
                else:
                    print(f"⚠️ [WEBHOOK] Call session not found for SID: {call_sid}")
                    
            finally:
                session.close()
        
        return {"status": "success", "message": "Webhook processed"}
        
    except Exception as e:
        print(f"❌ [WEBHOOK] Error processing webhook: {e}")
        return {"status": "error", "message": str(e)}

# This is a catch-all for the old websocket endpoint, redirecting or handling as needed.
@app.websocket("/stream")
async def old_websocket_endpoint(websocket: WebSocket):
    """
    Handles the old /stream endpoint.
    For now, it will just accept and close the connection with a message.
    """
    await websocket.accept()
    print("[Compatibility] Old /stream endpoint connected. This is deprecated.")
    await websocket.close(code=1008, reason="Endpoint /stream is deprecated. Use /ws/voicebot/{session_id}")

# --- WebSocket Endpoint for Dashboard ---
@app.websocket("/ws/dashboard/{session_id}")
async def websocket_dashboard_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    print(f"Dashboard connected: {session_id}")
    try:
        while True:
            # This loop will keep the connection alive.
            # We can add logic here later to handle messages from the dashboard.
            await websocket.receive_text()
    except WebSocketDisconnect:
        print(f"Dashboard disconnected: {session_id}")

if __name__ == "__main__":
    print("Starting server directly from main.py")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)