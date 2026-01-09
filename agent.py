import logging
import os
import datetime
import asyncio 
from dotenv import load_dotenv

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
from livekit.plugins import (
    cartesia,
    openai,
    deepgram,
    noise_cancellation,
    silero,
    bey
)

from gcal_manager import GoogleCalendarManager
from email_manager import EmailManager

load_dotenv()
db = GoogleCalendarManager()
emailer = EmailManager()

logger = logging.getLogger("voice-agent")

class ClinicAssistant(Agent):
    def __init__(self) -> None:
        groq_model = openai.LLM(
            base_url="https://api.groq.com/openai/v1",
            api_key=os.environ.get("GROQ_API_KEY"),
            model="llama-3.3-70b-versatile",
        )

        today = datetime.datetime.now().strftime("%A, %B %d, %Y")

        super().__init__(
            instructions=(
                f"Role: Professional clinic voice assistant.\n"
                f"CURRENT DATE: {today}\n"
                
                "Core Goals:\n"
                "1. Manage Appts: Book, Cancel, Reschedule.\n"
                "2. Info: Hours 9AM-5PM, Address 123 Health St.\n"
                
                "Strict Constraints & Flow:\n"
                "1. DATA COLLECTION (One by One): \n"
                "   - Do NOT ask for Name, Email, and Contact all at once.\n"
                "   - Step 1: Ask Name. Wait for reply.\n"
                "   - Step 2: Ask Email. Wait for reply.\n"
                "   - Step 3: Ask Phone. Wait for reply.\n"
                "   - Step 4: Confirm Service Type. \n"
                "   - Step 5: ONLY THEN call 'book_appointment'.\n"
                
                "2. SPEAKING STYLE:\n"
                "   - DATES: Never say 'two zero two five'. Say 'October 25th'.\n"
                "   - TIMES: Say '2 PM' or '2 o'clock', not 'fourteen hundred'.\n"
                "   - BREVITY: Responses < 15 words.\n"
                
                "3. RESCHEDULING:\n"
                "   - Ask: 'What was the date and time of the OLD appointment?'\n"
                "   - Then ask: 'What is the NEW date and time?'\n"
                "   - Then call 'modify_appointment'.\n"
                
                "4. PROCEDURE:\n"
                "   - CHECK AVAILABILITY FIRST before promising a slot.\n"
                "   - LATENCY HACK: Start response with 2 words (e.g. 'Checking now.')."
            ),
            stt=deepgram.STT(),
            llm=groq_model,
            tts=cartesia.TTS(
                model="sonic-3",      # Faster than sonic-2
                speed=1.1,            # 10% faster speech reduces audio buffer build-up
                encoding="pcm_s16le", # Raw PCM is faster to process than MP3
                sample_rate=24000,    # Standard efficient rate
            ),
        )

    async def on_enter(self):
        logger.info("Agent session started, generating greeting.")
        await self.session.generate_reply(
            instructions="Hello! I can help you book, cancel, or reschedule appointments. What do you need?", 
            allow_interruptions=True
        )

    # --- TOOLS WITH ASYNCIO ---

    @function_tool()
    async def check_availability(self, context: RunContext, date: str) -> str:
        """Check available slots for a date (YYYY-MM-DD)."""
        logger.info(f"Checking availability for {date}")
        
        # ⚡ ASYNC WRAPPER: Runs blocking DB call in a separate thread
        slots = await asyncio.to_thread(db.check_availability, date)
        
        if not slots:
            return "No slots available for this date."
        
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
        email: str, 
        contact: str, 
        date: str, 
        time: str, 
        service: str
    ) -> str:
        """
        Book a new appointment. 
        Args:
            name: Customer's full name.
            email: Customer's email.
            contact: Phone number.
            date: Date (YYYY-MM-DD).
            time: Time (e.g., "10:00 AM").
            service: Service type.
        """
        logger.info(f"Booking for {name}")
        
        # ⚡ ASYNC WRAPPER: Prevent freezing while Google API works
        booking_result = await asyncio.to_thread(db.book_appointment, name, contact, email, date, time, service)
        
        # ⚡ FIRE AND FORGET: Send email in background so user doesn't wait
        if "Success" in booking_result:
            asyncio.create_task(
                asyncio.to_thread(emailer.send_confirmation, email, name, date, time, service)
            )
            
        return f"{booking_result}"

    @function_tool()
    async def cancel_appointment(self, context: RunContext, name: str, date: str, time: str) -> str:
        """Cancel an existing appointment. Requires name and date/time."""
        logger.info(f"Cancelling for {name}")
        # ⚡ ASYNC WRAPPER
        return await asyncio.to_thread(db.cancel_appointment, name, date, time)

    @function_tool()
    async def modify_appointment(self, context: RunContext, name: str, old_date: str, old_time: str, new_date: str, new_time: str) -> str:
        """Reschedule/Modify an appointment."""
        logger.info(f"Modifying for {name}")
        # ⚡ ASYNC WRAPPER
        return await asyncio.to_thread(db.modify_appointment, name, old_date, old_time, new_date, new_time)

    @function_tool()
    async def end_conversation(self, context: RunContext, should_end: bool = True) -> str:
        """Ends the conversation."""
        return "TERMINATE"


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

async def entrypoint(ctx: JobContext):
    logger.info(f"connecting to room {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    my_agent = ClinicAssistant()

    participant = await ctx.wait_for_participant()
    
    usage_collector = metrics.UsageCollector()
    def on_metrics_collected(agent_metrics: metrics.AgentMetrics):
        usage_collector.collect(agent_metrics)

    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
        min_endpointing_delay=0.1, # Keep this low for speed
        max_endpointing_delay=5.0,
    )
    session.on("metrics_collected", on_metrics_collected)

    avatar = bey.AvatarSession(
        api_key=os.environ.get("BEYOND_PRESENCE_API_KEY"),
        avatar_id=os.environ.get("BEYOND_PRESENCE_AVATAR_ID"), 
        options=bey.AvatarOptions(
            quality="medium",  # Change from 'high' to 'medium' or 'low'
            width=640,         # Lower resolution (default is often 1080p)
            height=360,
            fps=24             # Lower FPS (cinema standard, smooth enough)
        )
    )
    
    # Start the avatar and wait for it to join
    logger.info("Starting Beyond Presence Avatar...")
    await avatar.start(session, room=ctx.room)

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

    await session.start(
        room=ctx.room,
        agent=my_agent,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(), 
        ),
    )

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        ),
    )