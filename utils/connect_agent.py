import os
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

# Load .env environment variables
load_dotenv()

EXOTEL_SID = os.getenv("EXOTEL_SID")
EXOTEL_KEY = os.getenv("EXOTEL_API_KEY")
EXOTEL_TOKEN = os.getenv("EXOTEL_TOKEN")
EXOTEL_FROM_NO = os.getenv("EXOTEL_FROM_NO")
EXOTEL_TO_NO = os.getenv("AGENT_PHONE_NUMBER")
EXOTEL_CALLER_ID = os.getenv("EXOTEL_CALLER_ID")
EXOTEL_CALL_URL = os.getenv("callurl")  # Typically like: https://api.exotel.in/v1/Accounts/{EXOTEL_SID}/Calls/connect.json

def trigger_exotel_agent_transfer(customer_number: str, agent_number: str):
    print("[📞] Initiating call via Exotel...")

    payload = {
        'From': customer_number,
        'To': agent_number,
        'CallerId': EXOTEL_CALLER_ID,  # This should be your ExoPhone (virtual number)
        'CallType': 'trans'  # Optional: can be 'trans' (transactional) or 'promo'
    }

    try:
        response = requests.post(
            EXOTEL_CALL_URL,
            data=payload,
            auth=HTTPBasicAuth(EXOTEL_KEY, EXOTEL_TOKEN),
            timeout=10  # optional timeout
        )

        print(f"[🌐] Status Code: {response.status_code}")
        try:
            print("[📨] Response JSON:")
            print(response.json())
        except Exception:
            print("[📨] Raw Response:")
            print(response.text)

    except requests.exceptions.RequestException as e:
        print(f"[❌ ERROR] Request to Exotel failed: {e}")  