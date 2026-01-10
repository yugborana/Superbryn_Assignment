import asyncio
import os
from livekit.agents import Agent, function_tool, RunContext
from livekit.plugins import cartesia, openai, deepgram
from livekit import rtc

# Import the initialized singletons and the prompt generator
from dependencies import db, sms, logger
from prompts import get_instructions

class ClinicAssistant(Agent):
    def __init__(self, room: rtc.Room) -> None:
        self.confirmed_bookings = []
        # --- 🛡️ MODEL INITIALIZATION ---
        # We wrap model setup in try-except because invalid API keys here crash the whole app.
        try:
            self.room = room
            

            # GROQ LLM SETUP:
            # We use the 'openai' plugin structure but point the 'base_url' to Groq.
            # Why? Because Groq is the fastest inference engine (LPU), essential for voice.
            groq_model = openai.LLM(
                base_url="https://api.groq.com/openai/v1",
                api_key=os.environ.get("GROQ_API_KEY"),
                model="llama-3.3-70b-versatile",
            )
            
            # CARTESIA TTS SETUP:
            # Configured for maximum speed (Low Latency).
            tts_plugin = cartesia.TTS(
                model="sonic-3",      # The fastest model Cartesia offers.
                speed=1.1,            # 1.1x speed clears the audio buffer faster (latency hack).
                encoding="pcm_s16le", # RAW Audio. Avoids the time needed to decode MP3.
                sample_rate=24000,    # Good balance of quality vs bandwidth.
            )
        except Exception as e:
            logger.critical(f"❌ Failed to initialize AI Models: {e}")
            raise e # If models fail, the agent is useless, so we must crash.

        super().__init__(
            instructions=get_instructions(), # Load the text instructions
            stt=deepgram.STT(),              # Deepgram is the standard for fast Speech-to-Text
            llm=groq_model,
            tts=tts_plugin,
        )

    async def on_enter(self):
        """
        Triggered when the agent joins the room.
        We manually generate a greeting so the user knows the agent is ready.
        """
        try:
            logger.info("Agent session started.")
            await self.session.generate_reply(
                instructions="Hello! I can help you book, cancel, or reschedule appointments. What do you need?", 
                allow_interruptions=True
            )
        except Exception as e:
            logger.error(f"Failed to generate initial greeting: {e}")

    # --- TOOLS (The Agent's Capabilities) ---
    # Each function below is exposed to the LLM so it can "call" them.

    @function_tool()
    async def check_availability(self, context: RunContext, date: str) -> str:
        """Check available slots for a date (YYYY-MM-DD)."""
        logger.info(f"Checking availability for {date}")
        
        # 🛡️ GUARD CLAUSE: Check if DB loaded correctly
        if not db:
            return "I apologize, but I cannot access the calendar system right now."

        try:
            # ⚡ ASYNC WRAPPER (CRITICAL PERFORMANCE FIX):
            # The Google API call is "blocking" (synchronous). If we run it normally, 
            # the entire Voice Agent freezes while waiting for Google.
            # 'asyncio.to_thread' moves this wait to a background thread, keeping the agent alive.
            slots = await asyncio.to_thread(db.check_availability, date)
            
            if not slots:
                return "No slots available for this date."
            
            # OUTPUT LIMITING:
            # Reading 20 slots takes too long. We truncate the list to 3 to keep the conversation fast.
            if len(slots) > 4:
                shown_slots = slots[:3]
                remaining = len(slots) - 3
                return f"Available slots include {', '.join(shown_slots)}, and {remaining} other openings."
            
            return f"Available slots: {', '.join(slots)}"
            
        except Exception as e:
            logger.error(f"DB Error in check_availability: {e}")
            return "I encountered an error checking the schedule. Please try again."

    @function_tool()
    async def book_appointment(self, context: RunContext, name: str, contact: str, date: str, time: str, service: str) -> str:
        if not db: return "System unavailable."
        try:
            res = await asyncio.to_thread(db.book_appointment, name, contact, date, time, service)
            
            if "Success" in res:
                # 📝 TRACK BOOKING INSTANTLY
                self.confirmed_bookings.append(f"{service} on {date} at {time} for {name}")
                
                if sms:
                    asyncio.create_task(asyncio.to_thread(sms.send_confirmation, contact, name, date, time, service))
            
            return res
        except Exception as e:
            logger.error(f"Booking Error: {e}")
            return "Booking failed."

    @function_tool()
    async def cancel_appointment(self, context: RunContext, name: str, date: str, time: str) -> str:
        """Cancel an existing appointment."""
        if not db: return "Calendar system unavailable."
        try:
            return await asyncio.to_thread(db.cancel_appointment, name, date, time)
        except Exception as e:
            logger.error(f"Cancellation Error: {e}")
            return "Could not cancel the appointment."

    @function_tool()
    async def modify_appointment(self, context: RunContext, name: str, old_date: str, old_time: str, new_date: str, new_time: str) -> str:
        """Reschedule/Modify an appointment."""
        if not db: return "Calendar system unavailable."
        try:
            return await asyncio.to_thread(db.modify_appointment, name, old_date, old_time, new_date, new_time)
        except Exception as e:
            logger.error(f"Reschedule Error: {e}")
            return "Could not reschedule the appointment."

    @function_tool()
    async def end_conversation(self, context: RunContext, should_end: bool = True) -> str:
        """Ends the conversation and displays a smart summary."""
        logger.info("Generating Final Summary...")
        
        # 1. Get Timestamp
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 2. Format Bookings (Instant)
        if self.confirmed_bookings:
            booking_text = "\n".join([f"✅ {b}" for b in self.confirmed_bookings])
        else:
            booking_text = "❌ No appointments booked."

        # 3. Generate Discussion & Preferences (Fast LLM Call)
        discussion_summary = "No discussion details."
        preferences = "None detected."

        if self.chat_ctx:
            # We create a specific prompt for the LLM to extract ONLY what we need
            # Using 'llama-3.1-8b-instant' on Groq, this takes ~0.5 seconds.
            summary_prompt = (
                "Analyze the chat history. Output ONLY a valid JSON object with two keys: "
                "'summary' (1 sentence on what was discussed) and "
                "'preferences' (list user preferences like 'mornings only', 'hates mondays', etc. or 'None')."
            )
            
            summary_ctx = llm.ChatContext().append(
                role=llm.ChatRole.SYSTEM, 
                text=summary_prompt
            )
            # Add recent history (Limit to last 6 messages for speed if needed)
            summary_ctx.messages.extend(self.chat_ctx.messages)

            try:
                # Ask LLM
                stream = await self.llm.chat(chat_ctx=summary_ctx)
                raw_response = ""
                async for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        raw_response += chunk.choices[0].delta.content
                
                # Try to parse JSON (Simple parsing logic)
                import json
                # Find the first '{' and last '}' to handle potential extra text
                start = raw_response.find('{')
                end = raw_response.rfind('}') + 1
                if start != -1 and end != -1:
                    data = json.loads(raw_response[start:end])
                    discussion_summary = data.get("summary", discussion_summary)
                    prefs = data.get("preferences", [])
                    if isinstance(prefs, list) and prefs:
                        preferences = ", ".join(prefs)
                    elif isinstance(prefs, str):
                        preferences = prefs

            except Exception as e:
                logger.error(f"LLM Summary Failed: {e}")

        # 4. Construct Final Display Message
        final_display = (
            f"📝 **CALL SUMMARY**\n"
            f"🕒 Time: {timestamp}\n\n"
            f"📌 **Discussion**: {discussion_summary}\n"
            f"❤️ **Preferences**: {preferences}\n\n"
            f"📅 **Appointments**:\n{booking_text}"
        )

        # 5. Send to UI (Before Ending)
        try:
            logger.info(f"Publishing Summary to UI...")
            await self.room.local_participant.publish_data(
                payload=final_display.encode("utf-8"), 
                topic="chat",
                reliable=True
            )
        except Exception as e:
            logger.error(f"Failed to publish summary: {e}")

        return "TERMINATE"