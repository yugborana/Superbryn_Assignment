# db_manager.py
import json
import os
from datetime import datetime
from typing import List, Dict, Optional

DB_FILE = "appointments.json"

class AppointmentManager:
    """
    Manages reading/writing appointments to a local JSON file.
    Handles availability logic to prevent double-booking.
    """
    def __init__(self):
        # Initialize the DB file if it doesn't exist
        if not os.path.exists(DB_FILE):
            with open(DB_FILE, 'w') as f:
                json.dump([], f)

    def _load_db(self) -> List[Dict]:
        try:
            with open(DB_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []

    def _save_db(self, data: List[Dict]):
        with open(DB_FILE, 'w') as f:
            json.dump(data, f, indent=2)

    def check_availability(self, date: str) -> List[str]:
        """
        Returns available slots for a given date.
        Filters out slots that are already booked in the DB.
        """
        # Base slots as per requirements
        base_slots = ["10:00 AM", "02:00 PM", "04:00 PM"]
        
        appointments = self._load_db()
        # Find booked times for the specific date
        booked_times = [
            appt['time'] for appt in appointments 
            if appt['date'] == date and appt['status'] == 'confirmed'
        ]
        
        # Return only slots that aren't in the booked_times list
        return [slot for slot in base_slots if slot not in booked_times]

    def book_appointment(self, name: str, contact: str, date: str, time: str, service: str) -> str:
        """
        Attempts to book a slot. Returns a success or error message.
        """
        available_slots = self.check_availability(date)
        
        if time not in available_slots:
            return f"Error: The slot {time} on {date} is no longer available."

        new_appointment = {
            "customer_name": name,
            "contact": contact,
            "date": date,
            "time": time,
            "service": service,
            "status": "confirmed",
            "created_at": datetime.now().isoformat()
        }

        data = self._load_db()
        data.append(new_appointment)
        self._save_db(data)
        
        return "Success: Appointment confirmed."
    
    def book_appointment(self, name: str, contact: str, date: str, time: str, service: str) -> str:
        available_slots = self.check_availability(date)
        if time not in available_slots:
            return f"Error: The slot {time} on {date} is not available."

        new_appointment = {
            "customer_name": name,
            "contact": contact,
            "date": date,
            "time": time,
            "service": service,
            "status": "confirmed",
            "created_at": datetime.now().isoformat()
        }

        data = self._load_db()
        data.append(new_appointment)
        self._save_db(data)
        return "Success: Appointment confirmed."

    def cancel_appointment(self, name: str, date: str, time: str) -> str:
        """Cancel an appointment by setting status to 'cancelled'."""
        data = self._load_db()
        found = False
        
        for appt in data:
            # We match by name, date, and time to be safe
            if (appt.get("customer_name") == name and 
                appt.get("date") == date and 
                appt.get("time") == time and 
                appt.get("status") == "confirmed"):
                
                appt["status"] = "cancelled"
                found = True
                break
        
        if found:
            self._save_db(data)
            return "Success: Appointment has been cancelled."
        else:
            return "Error: Could not find a confirmed appointment with those details."

    def modify_appointment(self, name: str, old_date: str, old_time: str, new_date: str, new_time: str) -> str:
        """
        Modifies an appointment by checking if new slot is free, 
        then booking new and cancelling old.
        """
        # 1. Check if the NEW slot is available
        available_slots = self.check_availability(new_date)
        if new_time not in available_slots:
            return f"Error: The new slot {new_time} on {new_date} is not available."

        data = self._load_db()
        
        # 2. Find the OLD appointment
        target_appt = None
        for appt in data:
            if (appt.get("customer_name") == name and 
                appt.get("date") == old_date and 
                appt.get("time") == old_time and 
                appt.get("status") == "confirmed"):
                target_appt = appt
                break
        
        if not target_appt:
            return "Error: Could not find your existing appointment to modify."

        # 3. Perform the Swap
        # Cancel old
        target_appt["status"] = "cancelled"
        
        # Create new (using details from the old one, but updated time)
        new_appointment = {
            "customer_name": target_appt["customer_name"],
            "contact": target_appt["contact"],
            "date": new_date,
            "time": new_time,
            "service": target_appt["service"],
            "status": "confirmed",
            "created_at": datetime.now().isoformat()
        }
        data.append(new_appointment)
        
        self._save_db(data)
        return f"Success: Rescheduled from {old_date} {old_time} to {new_date} {new_time}."