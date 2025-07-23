import httpx
import os
from utils.handler_asr import SarvamHandler

SARVAM_API_KEY = "sk_eripea2q_qPQFtS6uPiAFrhgDGZtKMLzx"

sarvam = SarvamHandler(SARVAM_API_KEY)
EXOTEL_SID = os.getenv("EXOTEL_SID")
EXOTEL_TOKEN = os.getenv("EXOTEL_TOKEN")
EXOPHONE = os.getenv("EXOTEL_VIRTUAL_NUMBER")
AGENT_NUMBER = os.getenv("AGENT_PHONE_NUMBER")
EXOTEL_API_KEY = os.getenv("EXOTEL_API_KEY")



async def trigger_exotel_agent_transfer(customer_number: str, agent_number: str):
    print("[Exotel] 📞 Initiating agent call transfer")

    url = f"https://api.exotel.com/v1/Accounts/{EXOTEL_SID}/Calls/connect.json"
    payload = {
        "From": customer_number,
        "To": agent_number,
        "CallerId": EXOPHONE,
    }

    try:
        async with httpx.AsyncClient(auth=(EXOTEL_SID, EXOTEL_TOKEN)) as client:
            response = await client.post(url, data=payload)

        if response.status_code == 200:
            print("[Exotel] ✅ Call transfer request successful")
        else:
            print(f"[Exotel] ❌ Failed to transfer call. Status {response.status_code} - {response.text}")

    except Exception as e:
        print(f"[Exotel] ❌ Exception occurred during call transfer: {e}")  