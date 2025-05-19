import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import logging
from datetime import datetime
from db.mongo import db
from bson import ObjectId

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        self.collection = db["schedule_links"]
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_username = os.getenv("SMTP_USERNAME")
        self.smtp_password = os.getenv("SMTP_PASSWORD")

    async def send_meeting_notification(
        self,
        advisor_email: str,
        client_email: str,
        scheduled_date: datetime,
        duration: int,
        answers: list = None,
        client_linkedin: str = None,
        scheduling_link_id: str = None
    ) -> bool:
        """
        Send an email notification to the advisor about a new scheduled meeting
        
        Parameters:
        - advisor_email: The email of the advisor who will receive the notification
        - client_email: The email of the client who booked the meeting
        - scheduled_date: The datetime of the scheduled meeting
        - duration: The duration of the meeting in minutes
        - answers: List of client's answers to custom questions (optional)
        - client_linkedin: The client's LinkedIn profile URL (optional)
        - scheduling_link_id: The ID of the scheduling link used for booking (optional)
        
        Returns:
        - bool: True if the email was sent successfully, False otherwise
        """
        logger.info(f"Preparing email notification for advisor: {advisor_email}")
        logger.info(f"Meeting details: client={client_email}, time={scheduled_date}, duration={duration}min")
        
        # Get scheduling link data if ID is provided
        link_data = None
        if scheduling_link_id:
            try:
                link_data = await self.collection.find_one({"_id": ObjectId(scheduling_link_id)})
                if link_data:
                    logger.info(f"Found scheduling link: {link_data.get('slug')}")
                else:
                    logger.warning(f"Scheduling link with ID {scheduling_link_id} not found")
            except Exception as e:
                logger.error(f"Error retrieving scheduling link {scheduling_link_id}: {str(e)}")
        
        # Format date
        formatted_date = scheduled_date.strftime("%A, %B %d, %Y at %I:%M %p")
        
        # Build email subject
        subject = f"New meeting scheduled for {formatted_date}"
        
        # Build email content
        message = MIMEMultipart()
        message["From"] = self.smtp_username
        message["To"] = advisor_email
        message["Subject"] = subject
        
        # Email body
        html = f"""
        <html>
        <body>
            <h2>New Meeting Scheduled</h2>
            <p>A new meeting has been scheduled with {client_email}.</p>
            <h3>Meeting Details:</h3>
            <ul>
                <li><strong>Date and Time:</strong> {formatted_date}</li>
                <li><strong>Duration:</strong> {duration} minutes</li>
                <li><strong>Client Email:</strong> {client_email}</li>
        """
        
        # Add LinkedIn profile if available
        if client_linkedin:
            html += f'<li><strong>LinkedIn Profile:</strong> <a href="{client_linkedin}">{client_linkedin}</a></li>'
        
        # Add scheduling link details if available
        if link_data:
            link_title = link_data.get("title", "Unknown")
            html += f'<li><strong>Scheduling Link Used:</strong> {link_title}</li>'
        
        # Add answers to custom questions if available
        if answers and len(answers) > 0:
            html += """
            <h3>Client's Responses:</h3>
            <ul>
            """
            for answer in answers:
                html += f'<li><strong>{answer.question}:</strong> {answer.answer}</li>'
            html += "</ul>"
        
        html += """
            </ul>
            <p>This meeting has been automatically added to your calendar.</p>
        </body>
        </html>
        """
        
        message.attach(MIMEText(html, "html"))
        
        # Send email
        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(message)
                logger.info(f"Meeting notification email sent to {advisor_email}")
                return True
        except Exception as e:
            logger.error(f"Failed to send meeting notification email: {str(e)}")
            return False

# Create an instance of EmailService
email_service = EmailService()

# Expose the send_meeting_notification function
async def send_meeting_notification(*args, **kwargs):
    """Wrapper function to call send_meeting_notification on the email_service instance"""
    return await email_service.send_meeting_notification(*args, **kwargs) 