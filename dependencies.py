import logging
import os
import sys
from dotenv import load_dotenv

from gcal_manager import GoogleCalendarManager
from sms_manager import SMSManager

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voice-agent")

REQUIRED_KEYS = ["LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "GROQ_API_KEY"]
missing_keys = [key for key in REQUIRED_KEYS if not os.environ.get(key)]
if missing_keys:
    logger.critical(f"CRITICAL ERROR: Missing API Keys: {', '.join(missing_keys)}")
    logger.critical("The agent cannot start. Please add them to Railway/Env.")
    sys.exit(1) # Stop the container immediately to alert the developer.


try:
    # Initialize the connection to Google Calendar
    db = GoogleCalendarManager()
    logger.info("Calendar Manager Loaded")
except Exception as e:
    logger.error(f"Calendar Manager Failed to Init: {e}")
    # Set to None so we can check `if db:` later in the code to prevent crashes
    db = None 

try:
    sms = SMSManager()
    logger.info("SMS Manager Loaded")
except Exception as e:
    logger.error(f"SMS Manager Failed to Init: {e}")
    sms = None