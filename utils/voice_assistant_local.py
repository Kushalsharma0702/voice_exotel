import os
import io
import time
import queue
import json
import base64
import sounddevice as sd
import soundfile as sf
from playsound import playsound
from dotenv import load_dotenv
from utils.bedrock_client import invoke_claude_model
from sarvamai import SarvamAI

load_dotenv()

API_KEY = os.getenv("SARVAM_API_KEY")
if not API_KEY:
    raise ValueError("SARVAM_API_KEY not found in environment.")

client = SarvamAI(api_subscription_key=API_KEY)
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_DURATION = 3.5  # seconds

q = queue.Queue()

GREETING_TEMPLATE = {
    "en": "Hello, this is Priya calling on behalf of Zrosis Bank. Am I speaking with Mr. {name}?",
    "hi": "नमस्ते, मैं प्रिय हूं और ज़्रोसिस बैंक की ओर से बात कर रही हूं। क्या मैं श्री/सुश्री {name} से बात कर रही हूं?",
    "ta": "வணக்கம், நான் பிரியா. இது ஸ்ரோசிஸ் வங்கியிலிருந்து அழைப்பு. திரு/திருமதி {name} பேசுகிறீர்களா?",
    "te": "హలో, నేను ప్రియ మాట్లాడుతున్నాను, ఇది జ్రోసిస్ బ్యాంక్ నుండి కాల్. మిస్టర్/మిసెస్ {name} మాట్లాడుతున్నారా?"
}

EMI_TEMPLATE = {
    "en": "Thank you. I’m reaching out regarding your loan account ending in {loan_id}, which currently shows an outstanding EMI of ₹{amount} that was due on {due_date}. If unpaid, it may impact your credit score. We have options such as part payments, revised EMI plans, or deferrals. Would you like help with that or receive a payment link?",
    "hi": "धन्यवाद। मैं आपके लोन खाता जिसकी समाप्ति {loan_id} पर होती है, के बारे में संपर्क कर रही हूं, जिसमें ₹{amount} की बकाया ईएमआई है जो {due_date} को देय थी। यदि भुगतान नहीं किया गया, तो यह आपके क्रेडिट स्कोर को प्रभावित कर सकता है। हमारे पास आंशिक भुगतान, संशोधित ईएमआई योजनाएं या स्थगन जैसे विकल्प हैं। क्या आप सहायता चाहते हैं या भुगतान लिंक प्राप्त करना चाहेंगे?",
    "ta": "நன்றி. உங்கள் கடன் கணக்கு {loan_id} முடிவில் இருப்பதாக அறியப்படுகின்றது, ₹{amount} நிலுவையிலுள்ளது மற்றும் {due_date} அன்று செலுத்த வேண்டியது. செலுத்தாத நிலையில் உங்கள் கிரெடிட் ஸ்கோருக்கு பாதிப்பு ஏற்படலாம். பகுதி கட்டணங்கள், திருத்தப்பட்ட EMI திட்டங்கள் அல்லது ஒத்திவைப்பு ஆகிய விருப்பங்கள் எங்களிடம் உள்ளன. நீங்கள் உதவி விரும்புகிறீர்களா அல்லது ஒரு கட்டண இணைப்பு பெற விரும்புகிறீர்களா?",
    "te": "ధన్యవాదాలు. మీ లోన్ ఖాతా {loan_id} నుండి ముగియనుంది, ఇది ప్రస్తుతం ₹{amount} పెండింగ్ EMI చూపిస్తుంది, ఇది {due_date} న due అయింది. చెల్లించని పక్షంలో మీ క్రెడిట్ స్కోరుపై ప్రభావం చూపవచ్చు. మేము భాగ చెల్లింపులు, సవరిస్తున్న EMI ప్రణాళికలు లేదా మినహాయింపుల వంటి ఎంపికలను కలిగి ఉన్నాము. మీకు సహాయం కావాలా లేదా చెల్లింపు లింక్ కావాలా?"
}

# ---------------------- AUDIO UTILITIES ------------------------ #

def record_audio(seconds=CHUNK_DURATION):
    print("🎙️ Listening... Speak now")
    recording = sd.rec(int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=CHANNELS, dtype='int16')
    sd.wait()
    return recording

def save_wav(array):
    wav_io = io.BytesIO()
    sf.write(wav_io, array, SAMPLE_RATE, format='WAV', subtype='PCM_16')
    wav_io.seek(0)
    return wav_io

def speak(text: str, language_code: str = "unknown", speaker: str = "anushka"):
    print(f"🔊 Speaking ({language_code}): {text}")
    resp = client.text_to_speech.convert(
        text=text,
        target_language_code=language_code,
        model="bulbul:v2",
        speaker=speaker
    )
    audio_b64 = resp.audios[0]
    audio_bytes = base64.b64decode(audio_b64)
    out_path = f"tts_{int(time.time())}.wav"
    with open(out_path, "wb") as f:
        f.write(audio_bytes)
    playsound(out_path)
    os.remove(out_path)

def lang_to_prefix(code):
    if code.startswith("hi"): return "hi"
    if code.startswith("ta"): return "ta"
    if code.startswith("te"): return "te"
    return "en"

# ---------------------- INTERACTION LOOP ------------------------ #

if __name__ == "__main__":
    customer = {
        "name": "Ravi",
        "loan_id": "7824",
        "amount": "4,500",
        "due_date": "25 July"
    }

    # 1. Initial generic English greeting
    speak("Hello. Please respond to continue.", language_code="en-IN")

    # 2. Wait for their response (to detect language)
    user_audio = record_audio()
    wav_io = save_wav(user_audio)

    # 3. Transcribe and detect language
    resp = client.speech_to_text.transcribe(
        file=("input.wav", wav_io, "audio/wav"),
        model="saarika:v2.5",
        language_code="unknown"
    )
    user_text = resp.transcript
    lang_code = resp.language_code or "en-IN"
    lang_key = lang_to_prefix(lang_code)
    print(f"🧠 Transcript: {user_text} ({lang_code})")

    # 4. Greet in detected language
    greeting = GREETING_TEMPLATE.get(lang_key, GREETING_TEMPLATE["en"]).format(name=customer['name'])
    speak(greeting, language_code=lang_code)

    # 5. Wait for confirmation response
    user_audio = record_audio()
    wav_io = save_wav(user_audio)
    resp = client.speech_to_text.transcribe(
        file=("input.wav", wav_io, "audio/wav"),
        model="saarika:v2.5",
        language_code=lang_code
    )
    user_text = resp.transcript

    # 6. Send to Bedrock
    prompt = [
        {"sender": "user", "content": user_text},
        {"sender": "assistant", "content": EMI_TEMPLATE.get(lang_key, EMI_TEMPLATE["en"]).format(**customer)}
    ]
    messages = []
    for m in prompt:
        messages.append({
            "role": "user" if m['sender'] == "user" else "assistant",
            "content": [{"type": "text", "text": m['content']}]
        })

    reply = invoke_claude_model(messages)
    if not reply.strip():
        reply = EMI_TEMPLATE.get(lang_key, EMI_TEMPLATE["en"]).format(**customer)

    # 7. Speak reply in detected language
    speak(reply, language_code=lang_code)
    print("✅ Interaction complete.")
import os
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket

# Load secrets from .env
load_dotenv()

EXOTEL_SID = os.getenv("EXOTEL_SID")
EXOTEL_API_TOKEN = os.getenv("EXOTEL_API_TOKEN")
EXOPHONE = os.getenv("EXOPHONE")
EXOTEL_APP_ID = os.getenv("EXOTEL_APP_ID")

app = FastAPI()

def trigger_exotel_call(to_number: str):
    url = f"https://{EXOTEL_API_Key}:{EXOTEL_API_TOKEN}@api.exotel.com/v1/Accounts/{EXOTEL_SID}/Calls/connect.json"
    # https://<your_api_key>:<your_api_token><subdomain>/v1/Accounts/<your_sid>/Calls/connect

    payload = {
        'From': to_number,
        'CallerId': EXOPHONE,
        'Url': f"http://my.exotel.com/{EXOTEL_SID}/exoml/start_voice/{EXOTEL_APP_ID}",
        'CallType': 'trans',
        'TimeLimit': '300',
        'TimeOut': '30',
        'CustomField': 'Zrosis_Call_01'
    }

    response = requests.post(url, data=payload)
    if response.status_code == 200:
        print("✅ Exotel call triggered:", response.json())
    else:
        print("❌ Failed to trigger Exotel call:", response.status_code, response.text)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        data = await websocket.receive_text()
        if data == "trigger-call":
            print("📞 Triggering Exotel call...")
            trigger_exotel_call("7417119104")  # Target number
            await websocket.send_text("📞 Call triggered successfully")
