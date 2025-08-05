# Exotel Pass-Through URL Configuration

This document explains how to configure Exotel to use pass-through URLs for enhanced session management and customer data isolation.

## Overview

The pass-through URL system allows you to:
- Pass customer information directly to your voice bot
- Maintain session isolation for each call
- Enhance customer experience with personalized interactions
- Track call flow and customer responses

## Setup Instructions

### 1. Update Environment Variables

Ensure your `.env` file has the correct BASE_URL:

```env
# Replace with your public domain when deploying
BASE_URL="https://your-domain.com"  # For production
BASE_URL="http://localhost:8000"    # For local testing
```

### 2. Configure Exotel Flow

In your Exotel dashboard:

1. **Go to your Exotel Flow Configuration**
2. **Set the Pass-Through URL** in the "Information Pass Through" section:
   ```
   https://your-domain.com/passthru-handler
   ```

3. **Enable "Make Passthru Async"** if you want non-blocking calls

### 3. Pass-Through URL Parameters

The system automatically includes these customer parameters in the URL:

- `customer_id` - Unique customer identifier
- `customer_name` - Customer's name
- `loan_id` - Loan account number
- `amount` - Outstanding amount
- `due_date` - Payment due date
- `language_code` - Customer's preferred language
- `state` - Customer's state (for language detection)
- `temp_call_id` - Temporary call tracking ID

### 4. Example Pass-Through URL

When a call is triggered, the system generates a URL like:

```
https://your-domain.com/passthru-handler?customer_id=cust_123&customer_name=Riddhi+Mittal&loan_id=LOAN12345&amount=15000&due_date=2025-08-11&language_code=hi-IN&state=Uttar+Pradesh&temp_call_id=temp_call_abc123
```

## API Endpoints

### `/passthru-handler`
- **Method**: GET/POST
- **Purpose**: Receives call from Exotel with customer data
- **Returns**: ExoML response for call flow

### `/gather-response`
- **Method**: GET/POST  
- **Purpose**: Handles customer input (DTMF responses)
- **Returns**: ExoML response for next action

## ExoML Response Examples

### Initial Greeting
```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="female" language="hi-IN">
        नमस्ते Riddhi Mittal, मैं प्रिया हूं और ज़्रोसिस बैंक की ओर से बात कर रही हूं। 
        आपके लोन खाता LOAN12345 के बारे में है जिसमें 15000 रुपये की बकाया राशि है।
    </Say>
    <Gather timeout="10" finishOnKey="#" action="/gather-response?call_sid=ABC123&customer_id=cust_123">
        <Say voice="female" language="hi-IN">
            कृपया अपना जवाब दें। यदि आप एजेंट से बात करना चाहते हैं तो 1 दबाएं।
        </Say>
    </Gather>
</Response>
```

### Agent Transfer
```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="female" language="hi-IN">
        आपको एजेंट से जोड़ा जा रहा है। कृपया प्रतीक्षा करें।
    </Say>
    <Dial timeout="30" callerId="04446972509">
        <Number>07417119014</Number>
    </Dial>
</Response>
```

## Session Management

### Redis Session Storage
Each call creates a Redis session with:
- Customer information
- Call tracking data
- Response history
- Timestamps

### Database Integration
Call sessions are also stored in PostgreSQL for:
- Persistent call history
- Analytics and reporting
- Customer interaction tracking

## Testing

### Local Testing
1. Start the server: `python main.py`
2. Run tests: `python test_passthru.py`

### Production Testing
1. Deploy to your domain
2. Update BASE_URL in .env
3. Configure Exotel with your pass-through URL
4. Test with real calls

## Deployment Notes

### Requirements
- Public domain with HTTPS
- FastAPI server running
- Redis for session management
- PostgreSQL for data persistence

### Security
- Use HTTPS in production
- Validate incoming parameters
- Implement rate limiting if needed
- Log security events

### Monitoring
- Monitor pass-through URL response times
- Track call success rates
- Monitor Redis session storage
- Set up alerts for failures

## Troubleshooting

### Common Issues

1. **Pass-through URL not called**
   - Check Exotel flow configuration
   - Verify BASE_URL is accessible from internet
   - Check server logs for errors

2. **Customer data not passed**
   - Verify customer data in call trigger
   - Check URL parameter encoding
   - Review pass-through URL generation

3. **ExoML not working**
   - Validate XML syntax
   - Check language codes
   - Verify gather action URLs

### Debug Tools
- Check server logs: `tail -f server.log`
- Test endpoints: `python test_passthru.py`
- Monitor Redis: Use Redis CLI to check sessions
- Database queries: Check call_sessions table

## Support

For issues with this implementation:
1. Check server logs
2. Verify environment variables
3. Test endpoints locally
4. Review Exotel configuration
