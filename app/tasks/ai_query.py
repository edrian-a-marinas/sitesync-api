import asyncio
import logging

from groq import Groq
from sqlalchemy.future import select

from app.core.celery import celery_app
from app.core.settings import settings
from app.database import AsyncSessionLocal
from app.models.ai_query import AIQuery
from app.services.ai_query import retrieve_context

logger = logging.getLogger(__name__)


def get_groq_client() -> Groq:
    if not settings.GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is not set")
    return Groq(api_key=settings.GROQ_API_KEY, max_retries=0, timeout=12.0)


@celery_app.task(name="process_ai_query")
def process_ai_query(query_id: int):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_process_ai_query(query_id))
    finally:
        loop.close()


async def _process_ai_query(query_id: int):
    async with AsyncSessionLocal() as db:
        query = (await db.execute(select(AIQuery).where(AIQuery.id == query_id))).scalar_one_or_none()
        if not query:
            logger.error(f"AI_QUERY | query_id={query_id} | status=failed | reason=not found")
            return
        try:
            client = get_groq_client()
            context = await retrieve_context(db, query.question, query.project_id)
            prompt = f"""You are SiteSync AI, an assistant for construction project management.
Answer directly and concisely based only on the data provided. No preambles, no unsolicited advice.
RULES:
1. Answer only what was asked.
2. Use specific numbers from the data.
3. If data is insufficient, say so briefly.
4. Never make up data not present in the context.
5. Keep answers short — 2-3 sentences max unless a breakdown is needed.
PROJECT DATA:
{context}
QUESTION: {query.question}"""

            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
            )

            query.answer = response.choices[0].message.content
            query.status = "Done"
            logger.info(f"AI_QUERY | query_id={query_id} | status=done")

        except Exception as e:
            query.status = "Failed"
            logger.error(f"AI_QUERY | query_id={query_id} | status=failed | reason={str(e)}")

        await db.commit()
