import logging
import os
import datetime
import asyncio 
from dotenv import load_dotenv

# --- LIVEKIT AGENT FRAMEWORK ---
# Core classes for building the voice agent worker
from livekit.agents import (
    Agent,
    AgentSession,
    AutoSubscribe,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
    llm,
    metrics,
    RoomInputOptions,
    function_tool,
    RunContext,
)

# --- AI PLUGINS ---
# Integrations for specific AI services:
# cartesia: Fast Text-to-Speech (TTS)
# openai: Used here as the client interface for Groq (LLM)
# deepgram: Fast Speech-to-Text (STT)
# noise_cancellation: LiveKit's audio cleaning
# silero: Voice Activity Detection (VAD) to know when user speaks
# bey: Beyond Presence (Avatar) integration
from livekit.plugins import (
    cartesia,
    openai,
    deepgram,
    noise_cancellation,
    silero,
    bey
)

# --- CUSTOM MANAGERS ---
# Helper classes for Calendar and SMS logic
from gcal_manager import GoogleCalendarManager
from sms_manager import SMSManager

# Load environment variables (API Keys, etc.) from .env file
load_dotenv()

# Initialize external services globally to reuse connections
db = GoogleCalendarManager()
sms = SMSManager()

# Setup logging to track agent behavior in the console
logger = logging.getLogger("voice-agent")

class ClinicAssistant(Agent):
    def __init__(self) -> None:
        # --- LLM CONFIGURATION (Groq) ---
        # Using Groq for ultra-low latency inference.
        # We use the 'openai' plugin but point it to Groq's base_url.
        groq_model = openai.LLM(
            base_url="https://api.groq.com/openai/v1",
            api_key=os.environ.get("GROQ_API_KEY"),
            model="meta-llama/llama-4-scout-17b-16e-instruct", # Specific Llama model optimized for instruction following
        )

        # dynamic variable for the system prompt so the AI knows "Today"
        today = datetime.datetime.now().strftime("%A, %B %d, %Y")

        super().__init__(
            # --- SYSTEM INSTRUCTIONS (The "Brain") ---
            # These rules strictly control the AI's behavior, personality, and flow.
            instructions=(
                f"Role: Professional clinic voice assistant.\n"
                f"CURRENT DATE: {today}\n"
                
                "Core Goals:\n"
                "1. Manage Appts: Book, Cancel, Reschedule.\n"
                "2. Info: Hours 9AM-5PM, Address 123 Health St.\n"
                
                "Strict Constraints & Flow:\n"
                "1. CHECK FIRST:\n"
                # CRITICAL: Prevents hallucinating availability. AI must use the tool first.
                "   - ALWAYS check availability for the requested date/time.\n"
                "   - If available, SAY: 'That slot is open. Shall I book it?'\n"
                "   - STOP and WAIT for the user to say 'Yes' or 'No'.\n"
                
                "2. NEW REQUEST OVERRIDE:\n"
                # Handles context switching if user changes mind mid-flow
                "   - If the user asks for a DIFFERENT time/date, FORGET the old slot.\n"
                "   - Check the NEW slot immediately.\n"
                
                "3. DATA COLLECTION (Only after User says 'Yes' to a slot): \n"
                # Enforces step-by-step data gathering to avoid overwhelming the STT/User
                "   - Step 1: Ask Name. Wait.\n"
                "   - Step 2: Ask Phone Number. Wait.\n"
                "   - Step 3: Confirm Service Type. \n"
                "   - Step 4: ONLY THEN call 'book_appointment'.\n"
                
                "4. SPEAKING STYLE:\n"
                # TTS Optimizations: 2025 -> October 25th sounds better naturally
                "   - DATES: Say 'October 25th', not '2025-10-25'.\n"
                "   - TIMES: Say '2 PM', not '14:00'.\n"
                "   - BREVITY: Keep answers < 15 words.\n"
            ),
            stt=deepgram.STT(), # Speech-to-Text
            llm=groq_model,     # Logic
            # --- TTS OPTIMIZATION (Cartesia) ---
            # Configured specifically for low latency and speed
            tts=cartesia.TTS(
                model="sonic-3",      # Fastest model available
                speed=1.1,            # Slightly faster playback clears buffer quicker
                encoding="pcm_s16le", # Raw PCM audio avoids MP3 decoding overhead
                sample_rate=24000,    # Balanced quality/bandwidth
            ),
        )

    async def on_enter(self):
        # Triggered when the agent joins the room.
        # Starts the conversation immediately so the user knows the agent is listening.
        logger.info("Agent session started, generating greeting.")
        await self.session.generate_reply(
            instructions="Hello! I can help you book, cancel, or reschedule appointments. What do you need?", 
            allow_interruptions=True
        )

    # --- TOOLS (Capabilities) ---
    # These functions allow the LLM to interact with the outside world (Calendar, SMS)

    @function_tool()
    async def check_availability(self, context: RunContext, date: str) -> str:
        """Check available slots for a date (YYYY-MM-DD)."""
        logger.info(f"Checking availability for {date}")
        
        # ⚡ ASYNC WRAPPER: CRITICAL FOR PERFORMANCE
        # The 'db.check_availability' method is blocking (synchronous).
        # We wrap it in 'asyncio.to_thread' so the Agent doesn't freeze while waiting for Google.
        slots = await asyncio.to_thread(db.check_availability, date)
        
        if not slots:
            return "No slots available for this date."
        
        # Limit the output to 3 slots to avoid the TTS reading a huge list
        if len(slots) > 4:
            shown_slots = slots[:3]
            remaining = len(slots) - 3
            return f"Available slots include {', '.join(shown_slots)}, and {remaining} other openings throughout the day."
        
        return f"Available slots: {', '.join(slots)}"

    @function_tool()
    async def book_appointment(
        self, 
        context: RunContext, 
        name: str,  
        contact: str, 
        date: str, 
        time: str, 
        service: str
    ) -> str:
        """
        Book a new appointment. 
        Args:
            name: Customer's full name.
            contact: Phone number.
            date: Date (YYYY-MM-DD).
            time: Time (e.g., "10:00 AM").
            service: Service type.
        """
        logger.info(f"Booking for {name}")
        
        # ⚡ ASYNC DB CALL: Prevents audio stuttering during booking
        booking_result = await asyncio.to_thread(db.book_appointment, name, contact, date, time, service)
        
        # ⚡ FIRE AND FORGET SMS
        # We use 'create_task' to send the SMS in the background.
        # The Agent can reply "Booked!" to the user immediately without waiting for Twilio.
        # NOTE: Passed 'contact' as the first arg for SMS (fixed typo in original logic)
        if "Success" in booking_result:
            asyncio.create_task(
                asyncio.to_thread(sms.send_confirmation, contact, name, date, time, service)
            )
            
        return f"{booking_result}"

    @function_tool()
    async def cancel_appointment(self, context: RunContext, name: str, date: str, time: str) -> str:
        """Cancel an existing appointment. Requires name and date/time."""
        logger.info(f"Cancelling for {name}")
        # Standard async wrapper for cancellation
        return await asyncio.to_thread(db.cancel_appointment, name, date, time)

    @function_tool()
    async def modify_appointment(self, context: RunContext, name: str, old_date: str, old_time: str, new_date: str, new_time: str) -> str:
        """Reschedule/Modify an appointment."""
        logger.info(f"Modifying for {name}")
        # Standard async wrapper for rescheduling
        return await asyncio.to_thread(db.modify_appointment, name, old_date, old_time, new_date, new_time)

    @function_tool()
    async def end_conversation(self, context: RunContext, should_end: bool = True) -> str:
        """Ends the conversation."""
        # A keyword 'TERMINATE' can be used by the framework to close the room
        return "TERMINATE"


def prewarm(proc: JobProcess):
    # Pre-loads the VAD model into memory when the worker starts.
    # Saves ~200-500ms when the first user connects.
    proc.userdata["vad"] = silero.VAD.load()

async def entrypoint(ctx: JobContext):
    # This is the main function that runs for EVERY new user connection.
    logger.info(f"connecting to room {ctx.room.name}")
    
    # Connect to the LiveKit Room (Audio Only for the agent itself)
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # Initialize the Agent Logic class
    my_agent = ClinicAssistant()

    # Wait until a human actually joins the room
    participant = await ctx.wait_for_participant()
    
    # --- METRICS COLLECTION ---
    # Tracks latency, token usage, etc.
    usage_collector = metrics.UsageCollector()
    def on_metrics_collected(agent_metrics: metrics.AgentMetrics):
        usage_collector.collect(agent_metrics)

    # --- AGENT SESSION ---
    # Manages the VAD loop and Turn-Taking
    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
        min_endpointing_delay=0.1, # Fast Turn-Taking: Agent replies 100ms after you stop talking
        max_endpointing_delay=5.0, # Max wait time
    )
    session.on("metrics_collected", on_metrics_collected)

    # --- BEYOND PRESENCE AVATAR INTEGRATION ---
    # Sets up the video avatar session separately from the audio agent
    avatar = bey.AvatarSession(
        api_key=os.environ.get("BEYOND_PRESENCE_API_KEY"),
        avatar_id=os.environ.get("BEYOND_PRESENCE_AVATAR_ID"), 
    )
    
    # Start the avatar and wait for it to join the room visually
    logger.info("Starting Beyond Presence Avatar...")
    await avatar.start(session, room=ctx.room)

    # --- DISCONNECT HANDLER ---
    # Runs when the user leaves the room.
    # Generates a JSON summary of what happened (bookings/cancellations).
    @ctx.room.on("disconnected")
    def on_disconnect():
        logger.info("Room disconnected, generating summary...")
        if my_agent.chat_ctx:
            history = my_agent.chat_ctx.messages
            conversation_text = "\n".join([f"{m.role}: {m.content}" for m in history])
            
            summary_prompt = (
                f"Summarize conversation in JSON: "
                f"summary, booked_appointments, cancelled_appointments, rescheduled_appointments. \n\n{conversation_text}"
            )
            logger.info(f"FINAL SUMMARY GENERATED:\n{summary_prompt}")

    # --- START THE AGENT ---
    # Begins the listening/thinking/speaking loop
    await session.start(
        room=ctx.room,
        agent=my_agent,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(), # Applies noise suppression to user audio
        ),
    )

if __name__ == "__main__":
    # Entry point for the Python script
    # Starts the worker which listens for LiveKit jobs
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        ),
    )