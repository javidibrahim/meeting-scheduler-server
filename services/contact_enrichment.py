import logging
import requests
from db.mongo import db
from datetime import datetime
import json
import os
from bson import ObjectId
from services.gemini_service import GeminiService

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ContactEnrichmentService:
    """Service to enrich contact data from Hubspot and LinkedIn."""
    
    def __init__(self):
        self.hubspot_api_key = os.environ.get("HUBSPOT_API_KEY")
        self.gemini_service = GeminiService()
        logger.info("ContactEnrichmentService initialized")
        if self.hubspot_api_key:
            logger.info("HubSpot API key found")
        else:
            logger.warning("HubSpot API key not found - HubSpot enrichment will be unavailable")
    
    async def find_hubspot_contact(self, email):
        """
        Find a contact in Hubspot that matches the email.
        
        Args:
            email (str): The email address to search for
            
        Returns:
            dict: The contact data if found, None otherwise
        """
        logger.info(f"Finding HubSpot contact for email: {email}")
        
        if not self.hubspot_api_key:
            logger.warning("HubSpot API key not found in environment variables")
            return None
        
        try:
            # Get HubSpot connection from the database
            hubspot_connection = await db["hubspot_connections"].find_one({})
            
            if not hubspot_connection or not hubspot_connection.get("access_token"):
                logger.warning("No HubSpot connection found in database")
                return None
                
            access_token = hubspot_connection.get("access_token")
            logger.info(f"HubSpot connection found - using access token (last 4): ...{access_token[-4:] if access_token else 'None'}")
            
            # Query HubSpot API for contact with the email
            url = f"https://api.hubapi.com/crm/v3/objects/contacts/search"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            payload = {
                "filterGroups": [
                    {
                        "filters": [
                            {
                                "propertyName": "email",
                                "operator": "EQ",
                                "value": email
                            }
                        ]
                    }
                ],
                "properties": ["email", "firstname", "lastname", "notes_last_updated", "notes_last_contacted", "hs_notes_body"]
            }
            
            logger.info(f"Sending request to HubSpot API: {url}")
            response = requests.post(url, headers=headers, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])
                
                if results:
                    contact = results[0]
                    contact_id = contact.get("id")
                    properties = contact.get("properties", {})
                    firstname = properties.get("firstname", "")
                    lastname = properties.get("lastname", "")
                    
                    logger.info(f"Found HubSpot contact: {contact_id} - {firstname} {lastname}")
                    logger.info(f"Contact has notes: {bool(properties.get('hs_notes_body'))}")
                    return contact
                    
                logger.info(f"No HubSpot contact found for email: {email}")
                return None
                
            else:
                logger.error(f"Error querying HubSpot API: {response.status_code}, {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error finding HubSpot contact: {str(e)}")
            return None
    
    async def scrape_linkedin_summary(self, linkedin_url):
        """
        Scrape a LinkedIn profile's summary and recent posts using SerpApi.
        """
        logger.info(f"Attempting to scrape LinkedIn profile: {linkedin_url}")
        
        api_key = os.getenv("SERPAPI_KEY")
        if not api_key:
            logger.warning("SerpApi key not set in environment - LinkedIn scraping unavailable")
            return None

        try:
            logger.info(f"Setting up SerpApi request for LinkedIn URL: {linkedin_url}")
            params = {
                "engine": "linkedin_profile",
                "url": linkedin_url,
                "api_key": api_key
            }

            logger.info("Sending request to SerpApi")
            response = requests.get("https://serpapi.com/search", params=params)
            
            if response.status_code == 200:
                logger.info("Successfully received SerpApi response")
                data = response.json()
                
                # Extract profile information
                summary = data.get("about", "")
                name = data.get("personal_info", {}).get("name", "")
                headline = data.get("personal_info", {}).get("headline", "")
                location = data.get("personal_info", {}).get("location", "")
                
                logger.info(f"LinkedIn data found for: {name} - {headline}")
                logger.info(f"Location: {location}")
                logger.info(f"Summary length: {len(summary)} characters")
                
                # Extract posts
                posts = data.get("highlighted_posts", [])
                logger.info(f"Found {len(posts)} posts from LinkedIn profile")

                # Extract post texts
                post_texts = []
                for i, post in enumerate(posts):
                    content = post.get("text") or post.get("title") or ""
                    if content:
                        post_texts.append(content.strip())
                        content_preview = content[:50] + "..." if len(content) > 50 else content
                        logger.info(f"Post {i+1}: {content_preview}")

                post_context = "\n\n".join(post_texts[:3])

                full_context = f"{summary}\n\nRecent Posts:\n{post_context}" if summary else post_context
                
                if full_context:
                    logger.info(f"Successfully scraped LinkedIn profile: {len(full_context)} characters of content")
                else:
                    logger.warning("LinkedIn profile found but no content extracted")
                
                return full_context or "No LinkedIn context found"

            else:
                logger.error(f"Failed LinkedIn scrape: {response.status_code} {response.text}")
                return None

        except Exception as e:
            logger.error(f"LinkedIn scraping error: {str(e)}")
            return None
    
    async def generate_augmented_note(self, client_email, answers, hubspot_contact, linkedin_summary):
        """
        Generate an augmented note using context from Hubspot and LinkedIn.
        Now using Gemini service for more advanced note generation.
        
        Args:
            client_email (str): The client's email address
            answers (list): The answers from the scheduling form
            hubspot_contact (dict): The contact data from Hubspot
            linkedin_summary (str): The scraped LinkedIn summary
            
        Returns:
            str: The augmented note
        """
        logger.info(f"Generating augmented note for client: {client_email}")
        logger.info(f"Data sources available - HubSpot: {bool(hubspot_contact)}, LinkedIn: {bool(linkedin_summary)}")
        logger.info(f"Client provided {len(answers)} answers to questions")
        
        try:
            logger.info("Calling Gemini service to generate augmented note")
            # Call Gemini service to generate the augmented note
            augmented_note = await self.gemini_service.generate_augmented_note(
                client_email=client_email,
                answers=answers,
                hubspot_data=hubspot_contact,
                linkedin_data=linkedin_summary
            )
            
            if not augmented_note:
                logger.warning("Gemini service returned empty note, using fallback")
                # Fallback to basic note generation
                hubspot_context = ""
                if hubspot_contact:
                    properties = hubspot_contact.get("properties", {})
                    hs_notes = properties.get("hs_notes_body", "")
                    if hs_notes:
                        hubspot_context += f"HubSpot Notes: {hs_notes}\n\n"
                
                linkedin_context = ""
                if linkedin_summary:
                    linkedin_context = f"LinkedIn Summary: {linkedin_summary}\n\n"
                
                # Create a basic context note
                augmented_note = "Meeting Preparation Notes:\n\n"
                
                if hubspot_context:
                    augmented_note += f"HubSpot Context:\n{hubspot_context}\n"
                
                if linkedin_context:
                    augmented_note += f"LinkedIn Context:\n{linkedin_context}\n"
                
                augmented_note += "Client Responses:\n"
                for answer in answers:
                    question = answer.get("question", "")
                    answer_text = answer.get("answer", "")
                    if question and answer_text:
                        augmented_note += f"- {question}: {answer_text}\n"
                
                logger.info("Generated fallback note instead of using Gemini")
            else:
                logger.info(f"Successfully generated augmented note with Gemini: {len(augmented_note)} characters")
            
            return augmented_note
            
        except Exception as e:
            logger.error(f"Error generating augmented note: {str(e)}")
            return "Error generating meeting insights."
    
    async def enrich_contact(self, email, linkedin_url, answers):
        """
        Enrich contact data from Hubspot and LinkedIn.
        
        Args:
            email (str): The contact's email address
            linkedin_url (str): The contact's LinkedIn profile URL
            answers (list): The answers from the scheduling form
            
        Returns:
            dict: The enriched contact data containing:
                - hubspot_contact: The contact data from Hubspot if found
                - linkedin_summary: The scraped LinkedIn summary if available
                - augmented_note: The generated augmented note
        """
        logger.info(f"Starting contact enrichment process for: {email}")
        
        # Find contact in Hubspot
        logger.info(f"Step 1: Searching for {email} in HubSpot")
        hubspot_contact = await self.find_hubspot_contact(email)
        
        # Scrape LinkedIn profile (even if HubSpot contact is found)
        logger.info(f"Step 2: Scraping LinkedIn profile: {linkedin_url if linkedin_url else 'No URL provided'}")
        linkedin_summary = None
        if linkedin_url:
            linkedin_summary = await self.scrape_linkedin_summary(linkedin_url)
        
        # Generate augmented note
        logger.info(f"Step 3: Generating augmented meeting note")
        augmented_note = await self.generate_augmented_note(email, answers, hubspot_contact, linkedin_summary)
        
        logger.info(f"Contact enrichment completed for {email}")
        
        return {
            "hubspot_contact": hubspot_contact,
            "linkedin_summary": linkedin_summary,
            "augmented_note": augmented_note,
            "enriched_at": datetime.utcnow()
        } 