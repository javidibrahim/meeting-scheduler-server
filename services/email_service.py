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

async def send_meeting_notification(advisor_email, client_email, scheduled_date, duration, answers=None, client_linkedin=None, scheduling_link_id=None):
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
    
    try:
        # SMTP server settings - from environment variables
        smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_username = os.getenv("SMTP_USERNAME")
        smtp_password = os.getenv("SMTP_PASSWORD")
        
        # Debug information for SMTP configuration
        logger.info(f"Using SMTP server: {smtp_server}:{smtp_port}")
        logger.info(f"SMTP username configured: {'Yes' if smtp_username else 'No'}")
        logger.info(f"SMTP password configured: {'Yes' if smtp_password else 'No'}")
        
        # If email credentials are not configured, log and return
        if not smtp_username or not smtp_password:
            logger.warning("Email notification skipped: SMTP credentials not configured")
            logger.warning("Please set the following environment variables: SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD")
            return False
        
        # Format the date for display
        formatted_date = scheduled_date.strftime("%A, %B %d, %Y at %I:%M %p")
        
        # Create message
        message = MIMEMultipart()
        message["From"] = smtp_username
        message["To"] = advisor_email
        message["Subject"] = "New Meeting Scheduled"
        
        logger.info(f"Email subject: {message['Subject']}")
        
        # Create email body
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 5px;">
                <h2 style="color: #4a5568; border-bottom: 1px solid #eee; padding-bottom: 10px;">New Meeting Scheduled</h2>
                <p>A new meeting has been scheduled with <strong>{client_email}</strong></p>
                
                <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 15px 0;">
                    <h3 style="margin-top: 0; color: #4a5568;">Meeting Details:</h3>
                    <ul style="padding-left: 20px;">
                        <li><strong>Date and Time:</strong> {formatted_date}</li>
                        <li><strong>Duration:</strong> {duration} minutes</li>
                        <li><strong>Client Email:</strong> {client_email}</li>
                        {f'<li><strong>LinkedIn Profile:</strong> <a href="{client_linkedin}">{client_linkedin}</a></li>' if client_linkedin else ''}
                    </ul>
                </div>
        """
        
        # Add answers to custom questions if provided
        if answers and len(answers) > 0:
            logger.info(f"Including {len(answers)} custom question answers in email")
            
            # Try to find the customQuestions from the scheduling link
            custom_questions = []
            if scheduling_link_id:
                try:
                    # Convert string ID to ObjectId if necessary
                    link_id = scheduling_link_id
                    if isinstance(scheduling_link_id, str):
                        link_id = ObjectId(scheduling_link_id)
                    
                    link = await db["schedule_links"].find_one({"_id": link_id})
                    if link and "customQuestions" in link:
                        custom_questions = link.get("customQuestions", [])
                        logger.info(f"Found {len(custom_questions)} custom questions from scheduling link")
                except Exception as e:
                    logger.error(f"Error retrieving custom questions: {str(e)}")
            
            # Only include the section if we have answers
            body += """
            <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 15px 0;">
                <h3 style="margin-top: 0; color: #4a5568;">Client's Responses:</h3>
                <ul style="padding-left: 20px;">
            """
            
            answer_list = []
            for answer in answers:
                try:
                    # Try dictionary access first
                    answer_text = answer.get('answer', '')
                    question_id = answer.get('question_id', '')
                except AttributeError:
                    # If it's a Pydantic model, access attributes directly
                    answer_text = getattr(answer, 'answer', '')
                    question_id = getattr(answer, 'question_id', '')
                    
                # Extract the index from question_id (assume format q0, q1, etc.)
                try:
                    if question_id.startswith('q'):
                        index = int(question_id[1:])
                    else:
                        index = int(question_id)
                except (ValueError, IndexError):
                    index = -1
                    
                answer_list.append((index, answer_text))
            
            # Sort answers by the extracted index
            answer_list.sort(key=lambda x: x[0])
            
            # Match answers with questions or use simple labels
            for i, (index, answer_text) in enumerate(answer_list):
                if i < len(custom_questions):
                    # Use the actual question text
                    question_text = custom_questions[i]
                else:
                    # Fallback to a generic question label
                    question_text = f"Question {i+1}"
                
                body += f'<li><strong>{question_text}:</strong> {answer_text}</li>'
                
            body += """
                </ul>
            </div>
            """
        
        body += """
                <p style="font-size: 0.9em; color: #718096; margin-top: 30px; text-align: center;">
                    This is an automated notification from your scheduling system.
                </p>
            </div>
        </body>
        </html>
        """
        
        message.attach(MIMEText(body, "html"))
        
        # Connect to SMTP server and send email
        logger.info(f"Connecting to SMTP server: {smtp_server}:{smtp_port}")
        
        try:
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                logger.info("SMTP connection established, initiating TLS")
                server.starttls()
                
                logger.info(f"Attempting login with username: {smtp_username}")
                server.login(smtp_username, smtp_password)
                
                logger.info(f"Sending email to: {advisor_email}")
                server.send_message(message)
                logger.info("Email sent successfully")
        except smtplib.SMTPAuthenticationError:
            logger.error("SMTP authentication failed - check username and password")
            return False
        except smtplib.SMTPException as smtp_err:
            logger.error(f"SMTP error occurred: {str(smtp_err)}")
            return False
        except Exception as conn_err:
            logger.error(f"Connection error: {str(conn_err)}")
            return False
            
        logger.info(f"Email notification successfully sent to {advisor_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email notification due to unexpected error: {str(e)}")
        # Log the full stack trace for debugging
        import traceback
        logger.error(f"Stack trace: {traceback.format_exc()}")
        return False 