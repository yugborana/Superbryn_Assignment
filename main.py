import os
import asyncio
from livekit.agents import (
    AgentSession,
    AutoSubscribe,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
    metrics,
    RoomInputOptions,
)
from livekit.plugins import noise_cancellation, silero, bey

from assistant import ClinicAssistant
from dependencies import logger

def prewarm(proc: JobProcess):
    """
    OPTIMIZATION: VAD Pre-warming.
    This function runs when the server starts, BEFORE any user joins.
    We load the 'Silero VAD' (Voice Activity Detection) model into memory here.
    Benefit: Saves ~500ms of lag when the first user connects, making the bot feel instant.
    """
    try:
        proc.userdata["vad"] = silero.VAD.load()
    except Exception as e:
        logger.warning(f"⚠️ VAD Prewarm failed: {e}. It will load lazily later.")

async def entrypoint(ctx: JobContext):
    """
    The Main Event Loop.
    This function runs once for EVERY separate user that calls the agent.
    """
    logger.info(f"connecting to room {ctx.room.name}")
    
    try:
        # 1. CONNECT TO ROOM
        # We subscribe to 'AUDIO_ONLY'. The agent does not need to download the 
        # user's video feed (if any), saving massive bandwidth on the server.
        await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    except Exception as e:
        logger.critical(f"❌ Failed to connect to LiveKit Room: {e}")
        return # Exit the session if we can't connect

    # 2. INITIALIZE AGENT LOGIC
    my_agent = ClinicAssistant(room=ctx.room)

    # 3. WAIT FOR HUMAN
    # The script pauses here until a user actually enters the room.
    participant = await ctx.wait_for_participant()
    
    # 4. SETUP METRICS
    # This collects data on latency and token usage for the LiveKit dashboard.
    usage_collector = metrics.UsageCollector()
    def on_metrics_collected(agent_metrics: metrics.AgentMetrics):
        usage_collector.collect(agent_metrics)

    # 5. CONFIGURE SESSION & VAD
    # 🛡️ Fallback: If prewarm failed, VAD might be missing. We check and load it now if needed.
    vad_instance = ctx.proc.userdata.get("vad")
    if not vad_instance:
        logger.info("Loading VAD lazily...")
        vad_instance = silero.VAD.load()

    session = AgentSession(
        vad=vad_instance,
        # LATENCY TUNING:
        # 0.1s: The agent considers you "finished talking" after just 100ms of silence.
        # This makes the conversation feel snappy and interruptible.
        min_endpointing_delay=0.1,
        max_endpointing_delay=5.0,
    )
    session.on("metrics_collected", on_metrics_collected)

    # --- 🛡️ AVATAR ERROR HANDLING (Graceful Degradation) ---
    # The Avatar is the heaviest component (Video Stream).
    # If it fails (bad internet, invalid key), we catch the error so the 
    # Voice Agent can still work (Voice Only) instead of crashing entirely.
    try:
        api_key = os.environ.get("BEYOND_PRESENCE_API_KEY")
        avatar_id = os.environ.get("BEYOND_PRESENCE_AVATAR_ID")
        
        if api_key and avatar_id:
            logger.info("Initializing Avatar...")
            avatar = bey.AvatarSession(api_key=api_key, avatar_id=avatar_id)
            # Starts the video stream in the room
            await avatar.start(session, room=ctx.room)
        else:
            logger.warning("⚠️ Avatar Keys missing. Starting in Voice-Only mode.")
            
    except Exception as e:
        logger.error(f"❌ Avatar failed to start: {e}")
        logger.info("⚠️ Continuing in Voice-Only mode (Graceful Degradation).")

    # 6. DISCONNECT HANDLER
    # When the call ends, this triggers to save the conversation summary.
    @ctx.room.on("disconnected")
    def on_disconnect():
        logger.info("Room disconnected.")
        try:
            if my_agent.chat_ctx:
                history = my_agent.chat_ctx.messages
                conversation_text = "\n".join([f"{m.role}: {m.content}" for m in history])
                logger.info(f"FINAL SUMMARY:\n{conversation_text}")
        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")

    # 7. START THE AGENT LOOP
    # This begins the cycle of Listening -> STT -> LLM -> TTS -> Speaking.
    try:
        await session.start(
            room=ctx.room,
            agent=my_agent,
            room_input_options=RoomInputOptions(
                # NOISE CANCELLATION: Cleans up background noise from the user's mic
                # so the STT engine gets clear audio.
                noise_cancellation=noise_cancellation.BVC(), 
            ),
        )
    except Exception as e:
        logger.critical(f"❌ Agent Session Crashed: {e}")

if __name__ == "__main__":
    # The standard entry point. 'cli.run_app' handles the worker process 
    # management, re-connection logic, and health checks.
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm,
        ),
    )