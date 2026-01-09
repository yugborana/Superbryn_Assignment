# email_manager.py
import smtplib
import os
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = os.getenv("SMTP_EMAIL")
SENDER_PASSWORD = os.getenv("SMTP_PASSWORD")

logger = logging.getLogger("email-manager")

class EmailManager:
    def send_confirmation(self, recipient_email: str, name: str, date: str, time: str, service: str):
        if not recipient_email or "@" not in recipient_email:
            logger.warning("Invalid email address, skipping notification.")
            return "Skipped: Invalid email."

        try:
            msg = MIMEMultipart()
            msg['From'] = SENDER_EMAIL
            msg['To'] = recipient_email
            msg['Subject'] = f"Appointment Confirmed: {service} on {date}"

            body = f"""
            Hello {name},

            Your appointment has been successfully booked!
            
            📅 Date: {date}
            ⏰ Time: {time}
            doctor Service: {service}
            📍 Location: Clinic Main Office

            If you need to reschedule, please ask the voice assistant.
            
            Best,
            Clinic AI Team
            """
            
            msg.attach(MIMEText(body, 'plain'))

            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            text = msg.as_string()
            server.sendmail(SENDER_EMAIL, recipient_email, text)
            server.quit()
            
            logger.info(f"Email sent to {recipient_email}")
            return "Email notification sent."

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return "Error sending email."