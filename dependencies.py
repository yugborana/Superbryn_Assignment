import logging
import os
import sys
from dotenv import load_dotenv

# Import our custom helper classes that handle the API logic
from gcal_manager import GoogleCalendarManager
from sms_manager import SMSManager

# 1. LOAD ENVIRONMENT VARIABLES
# This pulls API keys from .env (local) or Railway/Fly.io Secrets (cloud).
# This must happen before any service tries to use a key.
load_dotenv()

# 2. SETUP LOGGING
# Configures the console to show us what the agent is doing.
# level=logging.INFO hides useless debug noise but shows errors and main events.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voice-agent")

# --- 🛡️ CRITICAL PRE-FLIGHT CHECK ---
# Before we even try to start, check if the required API keys exist.
# If they are missing, the agent will fail silently later. We prefer to fail loud and early.
REQUIRED_KEYS = ["LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "GROQ_API_KEY"]
missing_keys = [key for key in REQUIRED_KEYS if not os.environ.get(key)]
if missing_keys:
    logger.critical(f"❌ CRITICAL ERROR: Missing API Keys: {', '.join(missing_keys)}")
    logger.critical("The agent cannot start. Please add them to Railway/Env.")
    sys.exit(1) # Stop the container immediately to alert the developer.

# 3. INITIALIZE SERVICES (Singleton Pattern)
# We wrap these in try-except blocks so that if one service fails (e.g., Twilio is down),
# the rest of the agent can still try to function.

try:
    # Initialize the connection to Google Calendar
    db = GoogleCalendarManager()
    logger.info("✅ Calendar Manager Loaded")
except Exception as e:
    logger.error(f"❌ Calendar Manager Failed to Init: {e}")
    # Set to None so we can check `if db:` later in the code to prevent crashes
    db = None 

try:
    # Initialize the connection to Twilio SMS
    sms = SMSManager()
    logger.info("✅ SMS Manager Loaded")
except Exception as e:
    logger.error(f"❌ SMS Manager Failed to Init: {e}")
    sms = None