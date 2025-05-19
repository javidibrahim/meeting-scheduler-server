from google import genai
import os
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GeminiService:
    """Service to generate content using Google's Gemini API."""

    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set")
        self.client = genai.Client(api_key=self.api_key)
        logger.info("Initialized GeminiService with Gemini Pro model")

    def generate_linkedin_analysis(self, posts: str, questions: str = "", answers: str = "") -> str:
        """Generate a short summary or insight based on LinkedIn posts and Q&A."""
        try:
            if not posts.strip() and not questions.strip() and not answers.strip():
                return "No content to enrich."

            prompt = (
                f"Analyze this LinkedIn user based on their posts and prior Q&A.\n"
                f"Posts:\n{posts or 'No posts provided.'}\n\n"
                f"Questions:\n{questions or 'No questions provided.'}\n\n"
                f"Answers:\n{answers or 'No answers provided.'}\n\n"
                "Write no more than 2 very short sentences. Be brief and factual. "
                "Highlight clear connections between Q&A and posts. "
                "If not related, summarize only based on the posts. "
                "Do not assume anything not directly mentioned. "
                "If there's nothing useful, say: 'No content to enrich.'"
            )

            response = self.client.models.generate_content(
                model="gemini-1.5-pro",
                contents=[prompt],
                config={
                    "maxOutputTokens": 100,
                    "temperature": 0.7,
                    "topP": 0.95,
                    "topK": 40
                }
            )

            return response.text.strip() if response.text else "No summary generated."

        except Exception as e:
            logger.error(f"Error in generate_linkedin_analysis: {str(e)}")
            return f"Error: {str(e)}"
