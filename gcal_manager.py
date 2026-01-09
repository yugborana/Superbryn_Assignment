import os.path
import datetime
import logging
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from googleapiclient.discovery import build
import pytz

# CONFIGURATION
SCOPES = ['https://www.googleapis.com/auth/calendar']
SERVICE_ACCOUNT_FILE = 'service_account.json'
CALENDAR_ID = 'yugborana000@gmail.com' 
TIMEZONE = 'Asia/Kolkata' 

logger = logging.getLogger("gcal-manager")

class GoogleCalendarManager:
    def __init__(self):
        self.creds = None
        if os.path.exists(SERVICE_ACCOUNT_FILE):
            self.creds = service_account.Credentials.from_service_account_file(
                SERVICE_ACCOUNT_FILE, scopes=SCOPES
            )
        else:
            logger.error("❌ service_account.json not found!")
            raise FileNotFoundError("service_account.json missing")

        self.service = build('calendar', 'v3', credentials=self.creds)
        self.tz = pytz.timezone(TIMEZONE)

    def _to_iso(self, date_str: str, time_str: str) -> str:
        """Converts '2025-10-25' and '10:00 AM' to ISO format."""
        dt_str = f"{date_str} {time_str}"
        dt = datetime.datetime.strptime(dt_str, "%Y-%m-%d %I:%M %p")
        dt_aware = self.tz.localize(dt)
        return dt_aware.isoformat()

    def check_availability(self, date: str) -> list[str]:
        # --- WEEKEND LOGIC ---
        try:
            dt_obj = datetime.datetime.strptime(date, "%Y-%m-%d")
            if dt_obj.weekday() >= 5: # 5=Sat, 6=Sun
                return [] 
        except ValueError:
            return [] 
            
        # Define Working Hours (9 AM - 5 PM)
        WORK_START = 9
        WORK_END = 17
        
        base_slots = []
        current_hour = WORK_START
        while current_hour < WORK_END:
            dummy_dt = datetime.datetime(2000, 1, 1, current_hour, 0)
            slot_str = dummy_dt.strftime("%I:%M %p")
            base_slots.append(slot_str)
            current_hour += 1

        events_result = self.service.events().list(
            calendarId=CALENDAR_ID, 
            timeMin=self._to_iso(date, "12:00 AM"),
            timeMax=self._to_iso(date, "11:59 PM"),
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])

        available_slots = []
        for slot in base_slots:
            slot_start_iso = self._to_iso(date, slot)
            is_taken = False
            for event in events:
                start = event['start'].get('dateTime')
                if not start: continue 
                if start == slot_start_iso: 
                    is_taken = True
                    break
            if not is_taken:
                available_slots.append(slot)

        return available_slots

    # --- 1. EXPANDED SERVICE LIST ---
    SERVICES = {
        "checkup": 30,
        "general checkup": 30,
        "cleaning": 60,
        "dental cleaning": 60,
        "root canal": 90,  # <--- This is the key one
        "surgery": 120,
        "extraction": 45,
        "consultation": 15,
        "consult": 15
    }

    # --- 2. SMART DURATION FINDER ---
    def _get_duration(self, service_text: str) -> int:
        """Helper to find duration with partial matching."""
        if not service_text: return 60
        
        s = service_text.lower().strip()
        
        # Debug print to see what the Agent is passing
        print(f"🔍 CHECKING DURATION FOR: '{s}'")

        # 1. Check if the key is inside the text (e.g. "root canal" is in "root canal therapy")
        for key, duration in self.SERVICES.items():
            if key in s:
                print(f"   ✅ MATCHED: '{key}' -> {duration} mins")
                return duration
        
        print("   ⚠️ NO MATCH FOUND. Defaulting to 60 mins.")
        return 60 

    def book_appointment(self, name: str, contact: str, date: str, time: str, service_type: str) -> str:
        try:
            # 3. GET DURATION
            duration_minutes = self._get_duration(service_type)

            available_slots = self.check_availability(date)
            if time not in available_slots:
                if not available_slots:
                    return f"Sorry, no slots on {date}."
                alternatives = available_slots[:2] 
                return f"Slot {time} unavailable. Try {', '.join(alternatives)}."

            start_iso = self._to_iso(date, time)
            dt_start = datetime.datetime.fromisoformat(start_iso)
            # 4. CALCULATE END TIME CORRECTLY
            dt_end = dt_start + datetime.timedelta(minutes=duration_minutes)
            end_iso = dt_end.isoformat()

            event = {
                'summary': f"{service_type.title()} - {name}",
                'location': 'Clinic Main Office',
                'description': f"Contact: {contact}\nService: {service_type}\nDuration: {duration_minutes} mins",
                'start': {'dateTime': start_iso, 'timeZone': TIMEZONE},
                'end': {'dateTime': end_iso, 'timeZone': TIMEZONE},
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'popup', 'minutes': 30},
                        {'method': 'popup', 'minutes': 24 * 60}, 
                    ],
                },
            }

            created_event = self.service.events().insert(
                calendarId=CALENDAR_ID, 
                body=event
            ).execute()
            
            spoken_date = dt_start.strftime("%B %d") 
            return f"Success. Booked {service_type} ({duration_minutes} mins) for {name} on {spoken_date} at {time}."

        except Exception as e:
            logger.error(f"Booking failed: {e}")
            return f"Error: {str(e)}"

    def cancel_appointment(self, name: str, date: str, time: str) -> str:
        try:
            start_iso = self._to_iso(date, time)
            events_result = self.service.events().list(
                calendarId=CALENDAR_ID,
                timeMin=start_iso,
                maxResults=10, 
                singleEvents=True
            ).execute()
            events = events_result.get('items', [])
            
            target_event_id = None
            for event in events:
                event_start = event['start'].get('dateTime')
                event_summary = event.get('summary', '').lower()
                
                # Loose Match
                if event_start == start_iso and name.lower() in event_summary:
                    target_event_id = event['id']
                    break
            
            if target_event_id:
                self.service.events().delete(calendarId=CALENDAR_ID, eventId=target_event_id).execute()
                return "Old appointment found and cancelled."
            else:
                return f"Could not find appointment for {name} at {time}."
        
        except Exception as e:
            return f"Error cancelling: {str(e)}"

    def modify_appointment(self, name: str, old_date: str, old_time: str, new_date: str, new_time: str) -> str:
        """
        Reschedules an appointment by:
        1. Finding the old event to extract details (Service, Email, Contact).
        2. Deleting the old event.
        3. Booking the new event with the ORIGINAL details.
        """
        try:
            # 1. FIND OLD EVENT
            start_iso = self._to_iso(old_date, old_time)
            events_result = self.service.events().list(
                calendarId=CALENDAR_ID,
                timeMin=start_iso,
                maxResults=10, 
                singleEvents=True
            ).execute()
            
            target_event = None
            for event in events_result.get('items', []):
                # Match Time AND Name
                if (event['start'].get('dateTime') == start_iso and 
                    name.lower() in event.get('summary', '').lower()):
                    target_event = event
                    break
            
            if not target_event:
                return f"I couldn't find your appointment on {old_date} at {old_time}, so I cannot reschedule it."

            # 2. EXTRACT ORIGINAL DETAILS
            # We parse the description field we created earlier
            description = target_event.get('description', '')
            
            # Default values in case parsing fails
            service_type = "General Checkup" 
            email = ""
            contact = ""

            # Parse line by line
            if description:
                for line in description.split('\n'):
                    if "Service:" in line:
                        service_type = line.split("Service:")[1].strip()
                    elif "Email:" in line:
                        email = line.split("Email:")[1].strip()
                    elif "Contact:" in line:
                        contact = line.split("Contact:")[1].strip()

            print(f"♻️ RESCHEDULING: Found '{service_type}' for {name}. Moving to {new_date} {new_time}.")

            # 3. DELETE OLD EVENT
            self.service.events().delete(calendarId=CALENDAR_ID, eventId=target_event['id']).execute()

            # 4. BOOK NEW EVENT (Using the extracted details!)
            return self.book_appointment(name, contact, email, new_date, new_time, service_type)

        except Exception as e:
            logger.error(f"Reschedule failed: {e}")
            return f"Error during rescheduling: {str(e)}"