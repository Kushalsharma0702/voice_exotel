import os
import requests
from requests.auth import HTTPBasicAuth
from pprint import pprint
from dotenv import load_dotenv

# Load .env environment variables
load_dotenv()

# Load credentials and config from env vars
EXOTEL_SID            = os.getenv("EXOTEL_SID")
EXOTEL_API_KEY        = os.getenv("EXOTEL_API_KEY")
EXOTEL_API_TOKEN      = os.getenv("EXOTEL_TOKEN")
EXOTEL_SUBDOMAIN      = os.getenv("EXOTEL_SUBDOMAIN", "api.exotel.com")
EXOTEL_FROM_NO        = os.getenv("to")
EXOTEL_CALLER_ID      = os.getenv("EXOTEL_CALLER_ID")           # Your ExoPhone
EXOTEL_FLOW_APP_ID    = os.getenv("EXOTEL_FLOW_APP_ID")         # Exotel App ID
EXOTEL_CUSTOMER_NO    = os.getenv("EXOTEL_CUSTOMER_NO")         # Optional override
EXOTEL_STATUS_CALLBACK= os.getenv("EXOTEL_STATUS_CALLBACK")     # Optional
EXOTEL_TIME_LIMIT     = os.getenv("EXOTEL_TIME_LIMIT", "60")    # Optional
EXOTEL_TIMEOUT        = os.getenv("EXOTEL_TIMEOUT", "30")       # Optional

def connect_customer_call():
    """
    Initiates a customer call via Exotel API.
    """
    call_url = f"https://{EXOTEL_SUBDOMAIN}/v1/Accounts/{EXOTEL_SID}/Calls/connect.json"
    flow_url = f"http://my.exotel.com/{EXOTEL_SID}/exoml/start_voice/{EXOTEL_FLOW_APP_ID}"

    print("[Exotel] 🔧 Initiating call with:")
    print(f"From:        {EXOTEL_FROM_NO}")
    print(f"CallerId:    {EXOTEL_CALLER_ID}")
    print(f"Flow URL:    {flow_url}")
    print(f"Call API:    {call_url}")

    payload = {
        "From": EXOTEL_FROM_NO,
        "CallerId": EXOTEL_CALLER_ID,
        "Url": flow_url,
        "CallType": "trans",
        "TimeLimit": EXOTEL_TIME_LIMIT,
        "TimeOut": EXOTEL_TIMEOUT,
    }

    # Optional: add status callback and custom fields if present
    if EXOTEL_STATUS_CALLBACK:
        payload["StatusCallback"] = EXOTEL_STATUS_CALLBACK
    payload["CustomField"] = "AgentTransfer"

    response = requests.post(
        call_url,
        auth=HTTPBasicAuth(EXOTEL_API_KEY, EXOTEL_API_TOKEN),
        data=payload
    )

    print(f"[Exotel] 📞 Status Code: {response.status_code}")
    try:
        pprint(response.json())
    except Exception as e:
        print("[Exotel] ❌ Failed to parse response:", e)
        print(response.text)

if __name__ == "__main__":
    connect_customer_call()