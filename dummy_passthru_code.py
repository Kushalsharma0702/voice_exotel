@app.get("/passthru-handler")
async def handle_passthru(request: Request):
    print("[INFO] /passthru-handler hit")
    
    # Access all query parameters safely
    params = request.query_params
    call_sid = params.get("CallSid")
    custom_field = params.get("CustomField")

    print(f"CallSid: {call_sid}")
    print(f"CustomField: {custom_field}")

    # Optional: parse CustomField if needed
    parsed_custom = {}
    if custom_field:
        for pair in custom_field.split("|"):
            if "=" in pair:
                key, value = pair.split("=", 1)
                parsed_custom[key.strip()] = value.strip()
        print(f"Parsed Custom Fields: {parsed_custom}")
    #redis cache with <call_id> as key and customer info {customer name, lang, amount, emi}
    #DB update <call_id>
    
    return PlainTextResponse("OK")



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
        'CustomField': f"lang={initial_lang}"
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