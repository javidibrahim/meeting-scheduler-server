import os
import logging
import requests
from typing import List, Dict, Any, Optional

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GeminiService:
    """Service to generate content using Google's Gemini API."""
    
    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY")
        self.model = "gemini-1.5-pro"
        self.api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
    
    async def generate_augmented_note(
        self, 
        client_email: str,
        answers: List[Dict[str, str]], 
        hubspot_data: Optional[Dict[str, Any]] = None, 
        linkedin_data: Optional[str] = None
    ) -> str:
        """
        Generate an augmented note using context from Hubspot and LinkedIn via Gemini.
        
        Args:
            client_email: The client's email address
            answers: List of question-answer pairs
            hubspot_data: Optional HubSpot contact data
            linkedin_data: Optional LinkedIn profile summary
            
        Returns:
            str: The augmented note from Gemini
        """
        if not self.api_key:
            logger.error("Gemini API key not found in environment variables")
            return "Could not generate insights - API key missing"
            
        try:
            # Prepare context for the model
            context_parts = []
            
            # Add HubSpot context if available
            if hubspot_data:
                properties = hubspot_data.get("properties", {})
                hubspot_context = []
                
                if properties.get("firstname") or properties.get("lastname"):
                    name = f"{properties.get('firstname', '')} {properties.get('lastname', '')}".strip()
                    hubspot_context.append(f"Name: {name}")
                
                if properties.get("hs_notes_body"):
                    hubspot_context.append(f"HubSpot Notes: {properties.get('hs_notes_body')}")
                    
                if hubspot_context:
                    context_parts.append("HUBSPOT INFORMATION:\n" + "\n".join(hubspot_context))
            
            # Add LinkedIn context if available
            if linkedin_data:
                context_parts.append(f"LINKEDIN INFORMATION:\n{linkedin_data}")
            
            # Format answers
            formatted_answers = []
            for answer in answers:
                question = answer.get("question", "")
                answer_text = answer.get("answer", "")
                if question and answer_text:
                    formatted_answers.append(f"Question: {question}\nAnswer: {answer_text}")
            
            answers_text = "\n\n".join(formatted_answers)
            context_parts.append(f"CLIENT ANSWERS:\n{answers_text}")
            
            # Build the full context
            full_context = "\n\n".join(context_parts)
            
            # Create prompt for Gemini
            prompt = f"""
You are an AI assistant helping to prepare for a client meeting. 
Please analyze the information provided and generate insights for the upcoming meeting with {client_email}.

CONTEXT INFORMATION:
{full_context}

Based on this information, please:
1. Summarize key points from the client's answers
2. Identify potential talking points or areas of interest
3. Note any connections between their answers and information from HubSpot or LinkedIn
4. Suggest follow-up questions that would be valuable to ask during the meeting

Format your response in a clean, organized way with clear sections. Be specific and actionable.
Provide insights that would be genuinely helpful for preparing for this meeting.
"""

            # Request parameters
            params = {"key": self.api_key}
            
            # Request body
            request_body = {
                "contents": [{
                    "role": "user",
                    "parts": [{"text": prompt}]
                }],
                "generationConfig": {
                    "temperature": 0.4,
                    "topK": 32,
                    "topP": 0.8,
                    "maxOutputTokens": 2048,
                }
            }
            
            # Make request to Gemini API
            response = requests.post(
                self.api_url, 
                params=params, 
                json=request_body,
                headers={"Content-Type": "application/json"}
            )
            
            # Check response
            if response.status_code == 200:
                response_data = response.json()
                generated_text = response_data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                
                if generated_text:
                    logger.info("Successfully generated augmented note")
                    return generated_text
                else:
                    logger.warning("Empty response from Gemini API")
                    return "Could not generate insights - empty response from AI service"
            else:
                logger.error(f"Error from Gemini API: {response.status_code}, {response.text}")
                return f"Could not generate insights - API error: {response.status_code}"
                
        except Exception as e:
            logger.error(f"Error generating augmented note: {str(e)}")
            return f"Error generating insights: {str(e)}" 