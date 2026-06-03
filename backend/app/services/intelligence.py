import google.generativeai as genai
from sqlalchemy.orm import Session
from app.core.config import settings
from sqlalchemy import select
from app.models.metric import DailyMetric
from datetime import date, timedelta

class IntelligenceService:
    def __init__(self):
        genai.configure(api_key=settings.GOOGLE_API_KEY)
        self.model = genai.GenerativeModel('gemini-2.5-flash')

    async def answer_question(self, db: Session, question: str):
        context_data = self.get_recent_metrics_summary(db, days=60)

        today_str = date.today().isoformat()

        prompt = f"""
        You are a Health Intelligence Assistant.
        Today is {today_str}.
        You are looking at the user's Oura Ring data for the last 60 days.

        DATA:
        {context_data}

        USER QUESTION:
        {question}

        INSTRUCTIONS:
         - Use the provided DATA to answer the QUESTION.
         - If the data is missing or insufficient, say so.
         - If the most recent data is several weeks old, mention that.
         - Be concise and grounded in the numbers (mention specific scores).
         - IMPORTANT: Do not give medical advice. You are a data interpreter.
        """

        response = self.model.generate_content(prompt)
        return response.text
    
    def get_recent_metrics_summary(self, db: Session, days: int = 7):
        """
        Fetches metrics from DB and formats for LLM.
        """
        start_date = date.today() - timedelta(days=days)

        # building queries w sqlalchemy
        # query = select(DailyMetric).where(DailyMetric.day >= start_date)
        query = select(DailyMetric)
        result = db.execute(query)
        metrics = result.scalars().all()

        context_parts = []
        for m in metrics:
            context_parts.append(f"{m.day}: {m.metric} is {m.value}")

        return "\n".join(context_parts)
    