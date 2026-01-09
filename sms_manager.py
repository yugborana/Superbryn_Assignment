import os
import logging
from twilio.rest import Client

logger = logging.getLogger("sms-manager")

class SMSManager:
    def __init__(self):
        # 1. Load Twilio Credentials from Railway Environment
        self.sid = os.environ.get("TWILIO_ACCOUNT_SID")
        self.token = os.environ.get("TWILIO_AUTH_TOKEN")
        self.from_number = os.environ.get("TWILIO_PHONE_NUMBER")
        self.client = None

        if self.sid and self.token and self.from_number:
            try:
                self.client = Client(self.sid, self.token)
                logger.info("✅ Twilio Client Initialized")
            except Exception as e:
                logger.error(f"❌ Twilio Init Failed: {e}")
        else:
            logger.warning("⚠️ Twilio Credentials missing! SMS will be simulated.")

    def _format_indian_number(self, number: str) -> str:
        """
        Cleans phone number and ensures it has +91 prefix.
        Input: "98765 43210" -> Output: "+919876543210"
        """
        # 1. Remove spaces, dashes, parentheses
        clean_num = number.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        
        # 2. Check if it already has '+'
        if clean_num.startswith("+"):
            return clean_num
        
        # 3. If it starts with '91' and is 12 digits (common error), just add '+'
        if clean_num.startswith("91") and len(clean_num) == 12:
             return f"+{clean_num}"

        # 4. Default: Add +91 to the 10-digit number
        return f"+91{clean_num}"

    def send_confirmation(self, to_number: str, name: str, date: str, time: str, service: str):
        # 1. Format the user's number first
        formatted_number = self._format_indian_number(to_number)
        
        message_body = (
            f"✅ Appointment Confirmed!\n"
            f"Hi {name}, you are booked for a {service}.\n"
            f"📅 {date} at {time}\n"
            f"📍 123 Health St, Clinic Main Office."
        )

        logger.info(f"📩 Preparing SMS for {formatted_number}")

        # 2. Simulation Mode (If keys are missing)
        if not self.client:
            logger.info(f"📝 [SIMULATION] Sending to {formatted_number}: {message_body}")
            return "SMS Simulated (Check Railway Variables)"

        # 3. Send Real SMS
        try:
            message = self.client.messages.create(
                body=message_body,
                from_=self.from_number,
                to=formatted_number
            )
            return f"SMS Sent! ID: {message.sid}"
        except Exception as e:
            logger.error(f"❌ Twilio Error: {e}")
            return f"Error sending SMS: {str(e)}"