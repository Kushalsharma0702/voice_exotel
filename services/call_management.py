"""
Call Management Service
Handles the complete call lifecycle with database and Redis integration
"""

import uuid
import json
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List
import httpx
import os
from urllib.parse import urlencode
from dotenv import load_dotenv

from database.schemas import (
    DatabaseManager, Customer, CallSession, CallStatusUpdate, FileUpload,
    CallStatus, get_customer_by_phone, create_customer, create_call_session,
    update_call_status, get_call_session_by_sid, db_manager
)
from utils.redis_session import redis_manager
from utils.handler_asr import SarvamHandler

load_dotenv()

class CallManagementService:
    def __init__(self):
        self.db_manager = db_manager
        self.redis_manager = redis_manager
        self.sarvam_handler = SarvamHandler(os.getenv("SARVAM_API_KEY"))
        
        # Exotel configuration
        self.exotel_sid = os.getenv("EXOTEL_SID")
        self.exotel_token = os.getenv("EXOTEL_TOKEN")
        self.exotel_api_key = os.getenv("EXOTEL_API_KEY")
        self.exotel_virtual_number = os.getenv("EXOTEL_VIRTUAL_NUMBER")
        self.exotel_flow_app_id = os.getenv("EXOTEL_FLOW_APP_ID")
        self.agent_phone_number = os.getenv("AGENT_PHONE_NUMBER")
        
    async def upload_and_process_customers(self, file_data: bytes, filename: str, websocket_id: str = None) -> Dict[str, Any]:
        """Process uploaded customer file and store in database"""
        session = self.db_manager.get_session()
        try:
            # Create file upload record
            file_upload = FileUpload(
                filename=filename,
                upload_status='processing'
            )
            session.add(file_upload)
            session.commit()
            session.refresh(file_upload)
            
            # Parse the file (assuming CSV/Excel)
            customers_data = await self._parse_customer_file(file_data, filename)
            file_upload.total_records = len(customers_data)
            
            processed_customers = []
            failed_records = 0
            processing_errors = []
            
            for customer_data in customers_data:
                try:
                    # Check if customer exists
                    existing_customer = get_customer_by_phone(session, customer_data['phone_number'])
                    
                    if existing_customer:
                        # Update existing customer
                        for key, value in customer_data.items():
                            if hasattr(existing_customer, key) and value:
                                setattr(existing_customer, key, value)
                        existing_customer.updated_at = datetime.utcnow()
                        customer = existing_customer
                    else:
                        # Create new customer
                        customer = create_customer(session, customer_data)
                    
                    processed_customers.append({
                        'id': str(customer.id),
                        'name': customer.name,
                        'phone_number': customer.phone_number,
                        'state': customer.state,
                        'loan_id': customer.loan_id,
                        'amount': customer.amount,
                        'due_date': customer.due_date,
                        'language_code': customer.language_code
                    })
                    
                except Exception as e:
                    failed_records += 1
                    processing_errors.append({
                        'customer_data': customer_data,
                        'error': str(e)
                    })
            
            # Update file upload record
            file_upload.processed_records = len(processed_customers)
            file_upload.failed_records = failed_records
            file_upload.processing_errors = processing_errors
            file_upload.upload_status = 'completed' if failed_records == 0 else 'partial_failure'
            session.commit()
            
            # Store in Redis for quick access
            temp_key = f"uploaded_customers_{file_upload.id}"
            self.redis_manager.store_temp_data(temp_key, processed_customers, ttl=3600)
            
            # Notify WebSocket if connected
            if websocket_id:
                self.redis_manager.notify_websocket(websocket_id, {
                    'type': 'file_processed',
                    'upload_id': str(file_upload.id),
                    'total_records': file_upload.total_records,
                    'processed_records': file_upload.processed_records,
                    'failed_records': failed_records,
                    'customers': processed_customers
                })
            
            return {
                'success': True,
                'upload_id': str(file_upload.id),
                'total_records': file_upload.total_records,
                'processed_records': file_upload.processed_records,
                'failed_records': failed_records,
                'customers': processed_customers,
                'temp_key': temp_key
            }
            
        except Exception as e:
            if 'file_upload' in locals():
                file_upload.upload_status = 'failed'
                file_upload.processing_errors = [{'error': str(e)}]
                session.commit()
            
            return {
                'success': False,
                'error': str(e)
            }
        finally:
            self.db_manager.close_session(session)
    
    async def trigger_single_call(self, customer_id: str, websocket_id: str = None) -> Dict[str, Any]:
        """Trigger a single outbound call"""
        session = self.db_manager.get_session()
        try:
            # Get customer data
            customer = session.query(Customer).filter(Customer.id == customer_id).first()
            if not customer:
                return {'success': False, 'error': f"Customer with ID {customer_id} not found"}
            
            print(f"✅ [CHECKPOINT] Found customer: {customer.name} ({customer.phone_number})")

            # Generate temporary call ID (before Exotel assigns SID)
            temp_call_id = f"temp_call_{uuid.uuid4().hex[:12]}"
            
            # Create Redis session with temp_call_id
            customer_data = {
                'id': str(customer.id),
                'name': customer.name,
                'phone_number': customer.phone_number,
                'state': customer.state,
                'loan_id': customer.loan_id,
                'amount': customer.amount,
                'due_date': customer.due_date,
                'language_code': customer.language_code,
                'temp_call_id': temp_call_id
            }
            
            # Store by temp_call_id
            self.redis_manager.create_call_session(temp_call_id, customer_data, websocket_id)
            
            # Also store by phone number for easy lookup by WebSocket
            phone_key = f"customer_phone_{customer.phone_number.replace('+', '').replace('-', '').replace(' ', '')}"
            self.redis_manager.store_temp_data(phone_key, customer_data, ttl=3600)
            print(f"[CallService] Stored customer data in Redis: temp_call_id={temp_call_id}, phone_key={phone_key}")
            
            # Store temp_call_id mapping by phone for reverse lookup
            temp_call_key = f"temp_call_phone_{customer.phone_number.replace('+', '').replace('-', '').replace(' ', '')}"
            self.redis_manager.store_temp_data(temp_call_key, temp_call_id, ttl=3600)
            
            print(f"📞 [CHECKPOINT] About to trigger Exotel call for temp_call_id: {temp_call_id}")
            # Trigger Exotel call with customer data
            exotel_response = await self._trigger_exotel_call(customer.phone_number, temp_call_id, customer_data)
            
            if exotel_response['success']:
                print(f"✅ [CHECKPOINT] Exotel call triggered successfully for temp_call_id: {temp_call_id}")
                call_sid = exotel_response['call_sid']
                
                # Create database call session with actual Exotel SID
                db_call_session = create_call_session(session, call_sid, customer.id, websocket_id)
                
                # Update Redis session with actual call SID
                self.redis_manager.update_call_session(temp_call_id, {'call_sid': call_sid})
                
                # Update status
                self.redis_manager.update_call_status(call_sid, CallStatus.RINGING, "Call initiated successfully")
                update_call_status(session, call_sid, CallStatus.RINGING, "Call initiated successfully", 
                                 {'exotel_response': exotel_response['response']})
                
                return {
                    'success': True,
                    'call_sid': call_sid,
                    'customer': customer_data,
                    'status': CallStatus.RINGING
                }
            else:
                print(f"❌ [CHECKPOINT] Exotel call failed for temp_call_id: {temp_call_id}. Error: {exotel_response.get('error')}")
                # Update Redis session with failure
                self.redis_manager.update_call_status(temp_call_id, CallStatus.FAILED, f"Failed to initiate call: {exotel_response['error']}")
                
                return {
                    'success': False,
                    'error': exotel_response['error'],
                    'temp_call_id': temp_call_id
                }
                
        except Exception as e:
            print(f"❌ [CRITICAL] Exception in trigger_single_call: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            self.db_manager.close_session(session)
    
    async def trigger_bulk_calls(self, customer_ids: List[str], websocket_id: str = None) -> Dict[str, Any]:
        """Trigger multiple calls in parallel"""
        results = []
        
        # Create tasks for parallel execution
        tasks = []
        for customer_id in customer_ids:
            task = asyncio.create_task(self.trigger_single_call(customer_id, websocket_id))
            tasks.append(task)
        
        # Execute all calls in parallel
        call_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        successful_calls = 0
        failed_calls = 0
        
        for i, result in enumerate(call_results):
            if isinstance(result, Exception):
                results.append({
                    'customer_id': customer_ids[i],
                    'success': False,
                    'error': str(result)
                })
                failed_calls += 1
            else:
                results.append(result)
                if result['success']:
                    successful_calls += 1
                else:
                    failed_calls += 1
        
        # Notify WebSocket
        if websocket_id:
            self.redis_manager.notify_websocket(websocket_id, {
                'type': 'bulk_calls_completed',
                'total_calls': len(customer_ids),
                'successful_calls': successful_calls,
                'failed_calls': failed_calls,
                'results': results
            })
        
        return {
            'success': True,
            'total_calls': len(customer_ids),
            'successful_calls': successful_calls,
            'failed_calls': failed_calls,
            'results': results
        }
    
    async def trigger_bulk_calls_from_data(self, customer_data_list: List[Dict[str, Any]], websocket_id: str = None) -> Dict[str, Any]:
        """Trigger calls from raw customer data (without storing in database first)"""
        results = []
        tasks = []
        
        # Create tasks for parallel execution
        for customer_data in customer_data_list:
            task = asyncio.create_task(self._trigger_call_from_data(customer_data, websocket_id))
            tasks.append(task)
        
        # Execute all calls in parallel
        call_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        successful_calls = 0
        failed_calls = 0
        
        for i, result in enumerate(call_results):
            if isinstance(result, Exception):
                results.append({
                    'customer_data': customer_data_list[i],
                    'success': False,
                    'error': str(result)
                })
                failed_calls += 1
            else:
                results.append(result)
                if result.get('success'):
                    successful_calls += 1
                else:
                    failed_calls += 1
        
        # Notify WebSocket
        if websocket_id:
            self.redis_manager.notify_websocket(websocket_id, {
                'type': 'bulk_calls_completed',
                'total_calls': len(customer_data_list),
                'successful_calls': successful_calls,
                'failed_calls': failed_calls,
                'results': results
            })
        
        return {
            'success': True,
            'total_calls': len(customer_data_list),
            'successful_calls': successful_calls,
            'failed_calls': failed_calls,
            'results': results
        }
    
    async def handle_exotel_webhook(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle Exotel webhook updates"""
        call_sid = webhook_data.get('CallSid')
        call_status = webhook_data.get('CallStatus', '').lower()
        
        if not call_sid:
            return {'success': False, 'error': 'No CallSid in webhook data'}
        
        session = self.db_manager.get_session()
        try:
            # Map Exotel status to our status
            status_mapping = {
                'ringing': CallStatus.RINGING,
                'in-progress': CallStatus.IN_PROGRESS,
                'completed': CallStatus.COMPLETED,
                'failed': CallStatus.FAILED,
                'busy': CallStatus.BUSY,
                'no-answer': CallStatus.NO_ANSWER,
                'canceled': CallStatus.DISCONNECTED
            }
            
            mapped_status = status_mapping.get(call_status, call_status)
            
            # Update Redis
            self.redis_manager.update_call_status(call_sid, mapped_status, 
                                                f"Exotel webhook: {call_status}", webhook_data)
            
            # Update Database
            update_call_status(session, call_sid, mapped_status, 
                             f"Exotel webhook: {call_status}", webhook_data)
            
            # If call ended, update end time and duration
            if mapped_status in [CallStatus.COMPLETED, CallStatus.FAILED, CallStatus.DISCONNECTED, CallStatus.NO_ANSWER]:
                call_session = get_call_session_by_sid(session, call_sid)
                if call_session:
                    call_session.end_time = datetime.utcnow()
                    if webhook_data.get('CallDuration'):
                        call_session.duration = int(webhook_data['CallDuration'])
                    session.commit()
            
            return {'success': True, 'status': mapped_status}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            self.db_manager.close_session(session)
    
    async def transfer_to_agent(self, call_sid: str) -> Dict[str, Any]:
        """Transfer call to human agent"""
        session = self.db_manager.get_session()
        try:
            # Update status
            self.redis_manager.update_call_status(call_sid, CallStatus.AGENT_TRANSFER, "Transferring to agent")
            update_call_status(session, call_sid, CallStatus.AGENT_TRANSFER, "Transferring to agent")
            
            # Get call session data
            redis_call_data = self.redis_manager.get_call_session(call_sid)
            if not redis_call_data:
                return {'success': False, 'error': 'Call session not found'}
            
            customer_data = redis_call_data['customer_data']
            
            # Trigger agent call using existing function
            agent_response = await self._trigger_agent_transfer(customer_data['phone_number'], self.agent_phone_number)
            
            if agent_response['success']:
                # Update database with agent transfer details
                db_call_session = get_call_session_by_sid(session, call_sid)
                if db_call_session:
                    db_call_session.agent_transfer_time = datetime.utcnow()
                    db_call_session.agent_number = self.agent_phone_number
                    session.commit()
                
                return {'success': True, 'message': 'Call transferred to agent successfully'}
            else:
                # Update status to failed transfer
                self.redis_manager.update_call_status(call_sid, CallStatus.FAILED, f"Agent transfer failed: {agent_response['error']}")
                update_call_status(session, call_sid, CallStatus.FAILED, f"Agent transfer failed: {agent_response['error']}")
                
                return {'success': False, 'error': agent_response['error']}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            self.db_manager.close_session(session)
    
    def get_call_status_dashboard(self, websocket_id: str = None) -> Dict[str, Any]:
        """Get dashboard data for call status monitoring"""
        session = self.db_manager.get_session()
        try:
            # Get active calls from Redis
            active_calls = []
            if websocket_id:
                active_calls = self.redis_manager.get_calls_for_websocket(websocket_id)
            
            # Get recent calls from database
            recent_calls = session.query(CallSession).order_by(CallSession.created_at.desc()).limit(20).all()
            
            # Get statistics
            total_calls = session.query(CallSession).count()
            completed_calls = session.query(CallSession).filter(CallSession.status == CallStatus.COMPLETED).count()
            failed_calls = session.query(CallSession).filter(CallStatus.FAILED).count()
            in_progress_calls = session.query(CallSession).filter(CallSession.status.in_([CallStatus.IN_PROGRESS, CallStatus.RINGING])).count()
            
            return {
                'active_calls': active_calls,
                'recent_calls': [
                    {
                        'call_sid': call.call_sid,
                        'customer_name': call.customer.name if call.customer else 'Unknown',
                        'phone_number': call.customer.phone_number if call.customer else 'Unknown',
                        'status': call.status,
                        'start_time': call.start_time.isoformat() if call.start_time else None,
                        'duration': call.duration
                    }
                    for call in recent_calls
                ],
                'statistics': {
                    'total_calls': total_calls,
                    'completed_calls': completed_calls,
                    'failed_calls': failed_calls,
                    'in_progress_calls': in_progress_calls
                }
            }
            
        except Exception as e:
            return {'error': str(e)}
        finally:
            self.db_manager.close_session(session)
    
    async def _trigger_call_from_data(self, customer_data: Dict[str, Any], websocket_id: str = None) -> Dict[str, Any]:
        """Trigger call from raw customer data and create database records"""
        session = self.db_manager.get_session()
        try:
            # Extract required fields
            phone_number = customer_data.get('phone', customer_data.get('phone_number', ''))
            name = customer_data.get('name', 'Unknown')
            
            if not phone_number:
                return {'success': False, 'error': 'Phone number is required', 'customer_data': customer_data}
            
            # Generate temporary call ID
            temp_call_id = f"temp_call_{uuid.uuid4().hex[:12]}"
            
            # First, check if customer exists in database, if not create one
            customer = get_customer_by_phone(session, phone_number)
            if not customer:
                # Create new customer record
                customer_dict = {
                    'name': name,
                    'phone_number': phone_number,
                    'loan_id': customer_data.get('loan_id', ''),
                    'amount': customer_data.get('amount', ''),
                    'due_date': customer_data.get('due_date', ''),
                    'state': customer_data.get('state', ''),
                    'language_code': customer_data.get('language_code', 'hi-IN')
                }
                customer = create_customer(session, customer_dict)
            
            # Create Redis session for this call
            self.redis_manager.create_call_session(temp_call_id, customer_data, websocket_id)
            
            # Also store by phone number for easy lookup by WebSocket
            clean_phone = phone_number.replace('+', '').replace('-', '').replace(' ', '')
            phone_key = f"customer_phone_{clean_phone}"
            self.redis_manager.store_temp_data(phone_key, customer_data, ttl=3600)
            
            # Store temp_call_id mapping by phone for reverse lookup
            temp_call_key = f"temp_call_phone_{clean_phone}"
            self.redis_manager.store_temp_data(temp_call_key, temp_call_id, ttl=3600)
            
            print(f"[CallService] Stored customer data for call: temp_call_id={temp_call_id}, phone_key={phone_key}, name={name}")
            
            # Trigger Exotel call with customer data
            exotel_response = await self._trigger_exotel_call(phone_number, temp_call_id, customer_data)
            
            if exotel_response.get('success'):
                call_sid = exotel_response['call_sid']
                
                # Create database call session record
                call_session = create_call_session(
                    session=session,
                    call_sid=call_sid,
                    customer_id=str(customer.id),
                    websocket_session_id=websocket_id
                )
                
                # Update Redis session with actual call SID and database ID
                self.redis_manager.update_call_session(temp_call_id, {
                    'call_sid': call_sid,
                    'customer_id': str(customer.id),
                    'call_session_id': str(call_session.id)
                })
                
                # Update status in both Redis and Database
                self.redis_manager.update_call_status(call_sid, CallStatus.RINGING, "Call initiated successfully")
                update_call_status(session, call_sid, CallStatus.RINGING, "Call initiated successfully")
                
                return {
                    'success': True,
                    'call_sid': call_sid,
                    'customer_data': customer_data,
                    'status': CallStatus.RINGING
                }
            else:
                # Update Redis session with failure
                self.redis_manager.update_call_status(temp_call_id, CallStatus.FAILED, f"Failed to initiate call: {exotel_response['error']}")
                
                return {
                    'success': False,
                    'error': exotel_response['error'],
                    'temp_call_id': temp_call_id,
                    'customer_data': customer_data
                }
                
        except Exception as e:
            return {'success': False, 'error': str(e), 'customer_data': customer_data}
        finally:
            self.db_manager.close_session(session)
    
    # Helper methods
    async def _parse_customer_file(self, file_data: bytes, filename: str) -> List[Dict[str, Any]]:
        """Parse uploaded customer file"""
        import pandas as pd
        import io
        
        try:
            if filename.endswith('.csv'):
                df = pd.read_csv(io.BytesIO(file_data))
            elif filename.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(io.BytesIO(file_data))
            else:
                raise ValueError("Unsupported file format")
            
            # Print column names for debugging
            print(f"📋 CSV Columns found: {list(df.columns)}")
            
            # Create a case-insensitive column mapping
            def normalize_column_name(col_name):
                """Normalize column names by removing spaces and converting to lowercase"""
                return str(col_name).lower().replace(' ', '_').replace('-', '_')
            
            # Create mapping from normalized names to actual column names
            actual_columns = {}
            for col in df.columns:
                normalized = normalize_column_name(col)
                actual_columns[normalized] = col
            
            print(f"📋 Normalized columns: {actual_columns}")
            
            # Expected columns mapping (normalized -> internal field name)
            column_mapping = {
                'name': 'name',
                'phone': 'phone_number',
                'phone_number': 'phone_number',
                'state': 'state',
                'loan_id': 'loan_id',
                'loan_ID': 'loan_id',  # Handle "Loan ID" case
                'amount': 'amount',
                'due_date': 'due_date',
                'due_DATE': 'due_date'  # Handle "Due Date" case
            }
            
            customers = []
            for _, row in df.iterrows():
                customer_data = {}
                
                # Map columns using normalized names
                for normalized_col, internal_field in column_mapping.items():
                    if normalized_col in actual_columns:
                        actual_col = actual_columns[normalized_col]
                        value = row[actual_col]
                        customer_data[internal_field] = str(value) if pd.notna(value) else ''
                
                # Ensure we have required fields
                if not customer_data.get('name'):
                    customer_data['name'] = 'Unknown'
                if not customer_data.get('phone_number'):
                    print(f"⚠️ Skipping row with missing phone number: {customer_data}")
                    continue
                
                # Clean phone number (remove spaces, hyphens, parentheses but keep + and digits)
                phone = customer_data['phone_number']
                if phone:
                    # Keep only digits and + sign
                    import re
                    phone = re.sub(r'[^\d+]', '', phone)
                    if not phone.startswith('+'):
                        # Keep the number as-is from CSV, just add +91 prefix (no leading zero removal)
                        phone = '+91' + phone
                    customer_data['phone_number'] = phone
                
                # Determine language code from state
                state = customer_data.get('state', '').lower()
                if state:
                    # Import state mapping
                    STATE_TO_LANGUAGE = {
                        'andhra pradesh': 'te-IN', 'arunachal pradesh': 'hi-IN', 'assam': 'hi-IN',
                        'bihar': 'hi-IN', 'chhattisgarh': 'hi-IN', 'goa': 'hi-IN', 'gujarat': 'gu-IN',
                        'haryana': 'hi-IN', 'himachal pradesh': 'hi-IN', 'jharkhand': 'hi-IN',
                        'karnataka': 'kn-IN', 'kerala': 'ml-IN', 'madhya pradesh': 'hi-IN',
                        'maharashtra': 'mr-IN', 'manipur': 'hi-IN', 'meghalaya': 'hi-IN',
                        'mizoram': 'hi-IN', 'nagaland': 'hi-IN', 'odisha': 'or-IN', 'punjab': 'pa-IN',
                        'rajasthan': 'hi-IN', 'sikkim': 'hi-IN', 'tamil nadu': 'ta-IN',
                        'telangana': 'te-IN', 'tripura': 'hi-IN', 'uttar pradesh': 'hi-IN',
                        'uttarakhand': 'hi-IN', 'west bengal': 'bn-IN', 'delhi': 'hi-IN',
                        'puducherry': 'ta-IN', 'chandigarh': 'hi-IN'
                    }
                    customer_data['language_code'] = STATE_TO_LANGUAGE.get(state, 'hi-IN')
                else:
                    customer_data['language_code'] = 'hi-IN'
                
                print(f"✅ Parsed customer: {customer_data['name']} - {customer_data['phone_number']}")
                customers.append(customer_data)
            
            return customers
            
        except Exception as e:
            raise Exception(f"Failed to parse file: {str(e)}")
    
    async def _trigger_exotel_call(self, to_number: str, temp_call_id: str, customer_data: Dict[str, Any]) -> Dict[str, Any]:
        """Internal method to trigger Exotel call and connect it to the ExoML flow."""
        
        # The base URL for API calls
        url = f"https://api.exotel.com/v1/Accounts/{self.exotel_sid}/Calls/connect.json"
        
        # The URL for the ExoML flow that Exotel will execute when the call connects.
        # This is NOT our server's URL, but Exotel's URL for our specific application flow.
        flow_url = f"http://my.exotel.com/{self.exotel_sid}/exoml/start_voice/{self.exotel_flow_app_id}"

        # We pass all customer data in the 'CustomField'. 
        # The Passthru applet within the ExoML flow will send this data back to our /passthru-handler.
        custom_field_data = {k: str(v) for k, v in customer_data.items()}
        custom_field_str = "|".join([f"{key}={value}" for key, value in custom_field_data.items()])

        payload = {
            'From': self.exotel_virtual_number,
            'To': to_number,
            'CallerId': self.exotel_virtual_number,
            'Url': flow_url,  # <-- This points to the Exotel Flow
            'CallType': 'trans',
            'TimeLimit': '3600',
            'TimeOut': '30',
            'CustomField': custom_field_str, # <-- All data is packed here
            'StatusCallback': f"{os.getenv('BASE_URL', 'http://localhost:8000')}/exotel-webhook"
        }
        
        print(f"📞 Triggering Exotel call to {to_number} with Flow URL: {flow_url}")
        print(f"📦 CustomField Payload: {custom_field_str}")
        print(f"🔧 Debug - API URL: {url}")
        print(f"🔧 Debug - Auth: {self.exotel_api_key[:10]}...{self.exotel_api_key[-10:]} / {self.exotel_token[:10]}...{self.exotel_token[-10:]}")
        print(f"🔧 Debug - Payload: {json.dumps(payload, indent=2)}")

        try:
            async with httpx.AsyncClient(auth=(self.exotel_api_key, self.exotel_token)) as client:
                response = await client.post(url, data=payload)
            
            if response.status_code == 200:
                response_data = response.json()
                call_sid = response_data.get('Call', {}).get('Sid')
                print(f"✅ Exotel call triggered successfully. CallSid: {call_sid}")
                return {'success': True, 'call_sid': call_sid, 'response': response_data}
            else:
                error_message = f"Exotel API Error: {response.status_code} - {response.text}"
                print(f"❌ Failed to trigger Exotel call. {error_message}")
                return {'success': False, 'error': error_message}
        except Exception as e:
            error_message = str(e)
            print(f"❌ Exception during Exotel call trigger: {error_message}")
            return {'success': False, 'error': error_message}

    async def _trigger_agent_transfer(self, customer_number: str, agent_number: str) -> Dict[str, Any]:
        """Trigger agent transfer call"""
        url = f"https://api.exotel.com/v1/Accounts/{self.exotel_sid}/Calls/connect.json"
        
        payload = {
            "From": customer_number,
            "To": agent_number,
            "CallerId": self.exotel_virtual_number,
        }
        
        try:
            async with httpx.AsyncClient(auth=(self.exotel_api_key, self.exotel_token)) as client:
                response = await client.post(url, data=payload, timeout=30.0)
                
                if response.status_code == 200:
                    return {'success': True, 'response': response.json()}
                else:
                    return {'success': False, 'error': f'HTTP {response.status_code}: {response.text}'}
                    
        except Exception as e:
            return {'success': False, 'error': str(e)}

# Global service instance
call_service = CallManagementService()
