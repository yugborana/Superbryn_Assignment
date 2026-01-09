# Superbryn Clinic Voice Assistant

A real-time voice assistant for clinic appointment management, built with LiveKit, Groq LLM, Cartesia TTS, and integrated with Google Calendar and Twilio SMS.

## Features

- **Voice Interaction**: Handles booking, canceling, and rescheduling appointments via natural speech.
- **AI-Powered**: Uses Groq's fast LLM for intelligent conversation flow.
- **Text-to-Speech**: Cartesia provides low-latency, high-quality voice synthesis.
- **Speech-to-Text**: Deepgram ensures accurate transcription.
- **Calendar Integration**: Syncs with Google Calendar for availability and bookings.
- **SMS Notifications**: Sends confirmation messages via Twilio.
- **Avatar Support**: Optional Beyond Presence avatar for visual interaction.
- **Noise Cancellation**: Improves audio quality with LiveKit's noise suppression.
- **Dockerized**: Easy deployment with containerization.

## Prerequisites

- Python 3.11+
- Docker (for containerized deployment)
- API Keys for:
  - LiveKit
  - Groq
  - Cartesia
  - Deepgram
  - Google Calendar (Service Account JSON)
  - Twilio
  - Beyond Presence (optional)

## Architecture

The Superbryn Clinic Voice Assistant is built as a real-time, event-driven voice pipeline that connects live audio streaming, AI reasoning, and external service integrations.

### High-Level Flow

1. **Client / Browser**
   - User speaks through a web or desktop client connected to LiveKit.
   - Audio streams are sent in real time to the LiveKit room.

2. **LiveKit Media Server**
   - Manages real-time audio streaming, noise cancellation, and session orchestration.
   - Routes audio data between the client and the voice assistant service.

3. **Speech-to-Text (Deepgram)**
   - Incoming audio is transcribed into text with low latency and high accuracy.
   - Transcriptions are streamed back to the assistant for intent understanding.

4. **LLM Orchestration (Groq)**
   - The transcribed text is sent to Groq’s LLM.
   - The model interprets user intent, manages dialogue flow, and decides which tools to invoke (calendar, SMS, etc.).

5. **Business Logic Layer**
   - Appointment workflows are handled in the assistant layer.
   - Tool calls integrate with:
     - **Google Calendar** for availability checks, booking, cancellation, and rescheduling.
     - **Twilio SMS** for sending confirmations and reminders.
     - **Local JSON Storage (Fallback)** for persistence when external services are unavailable.

6. **Text-to-Speech (Cartesia)**
   - The LLM’s response is converted into natural-sounding speech.
   - Audio is streamed back to the user through LiveKit.

7. **Optional Avatar (Beyond Presence)**
   - Provides a visual avatar synchronized with voice output for enhanced user interaction.

8. **Containerized Deployment**
   - All services are packaged using Docker for consistent deployment and portability.

### Data Flow Summary

![Data Flow Architecture](images/data_flow.png)

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yugborana/Superbryn_Assignment.git
   cd Superbryn_Assignment

2. Install Dependencies:
    pip install -r requirements.txt

3. Set up environment variables:
    - Make a .env file and fill in your API keys.
    - Place your_service_account.json in the root directory for Google Calendar access.

    - .env structure:    
        LIVEKIT_URL=
        LIVEKIT_API_KEY=
        LIVEKIT_API_SECRET=

        CARTESIA_API_KEY = 
        DEEPGRAM_API_KEY = 
        GROQ_API_KEY = 

        BEYOND_PRESENCE_API_KEY =
        BEYOND_PRESENCE_AVATAR_ID =

        GOOGLE_CALENDAR_CLIENT_ID = 
        GOOGLE_CALENDAR_CLIENT_SECRET = 

        TWILIO_ACCOUNT_SID = 
        TWILIO_AUTH_TOKEN = 
        TWILIO_PHONE_NUMBER = 


# Usage
## Local Development
    1. Run the agent:
        python main.py dev
        
    2. The agent connects to your LiveKit room and starts listening to commands.

## Docker Deployment
    1. Build the image:
        docker build -t superbryn-assistant .
    
    2. Run the container:
        docker run -e LIVEKIT_URL=your_url -e LIVEKIT_API_KEY=your_key -e LIVEKIT_API_SECRET=your_secret superbryn-assistant

# Configuration

## Environment Variables
All API keys are loaded from `.env` or system environment.

## Calendar Settings
Update `CALENDAR_ID` in `gcal_manager.py` for your Google Calendar.

## Service Durations
Modify the `SERVICES` dict in `gcal_manager.py` for custom appointment lengths.

## Prompts
Customize agent behavior in `prompts.py`.

---

# Project Structure

- **main.py** – Entry point and LiveKit session management.  
- **assistant.py** – Core agent logic with tools for appointment management.  
- **gcal_manager.py** – Google Calendar integration.  
- **sms_manager.py** – Twilio SMS handling.  
- **prompts.py** – System instructions for the LLM.  
- **dependencies.py** – Service initialization and logging.  
- **db_manager.py** – Local JSON-based appointment storage (fallback).  
- **agent.py** – Alternative agent implementation (similar to assistant.py).  
- **Dockerfile** – Containerization setup.  
- **requirements.txt** – Python dependencies.  

---

# Contributing

1. Fork the repository.  
2. Create a feature branch.  
3. Commit changes.  
4. Push and create a pull request.  

---

# License

This project is licensed under the MIT License. See LICENSE for details.



    
