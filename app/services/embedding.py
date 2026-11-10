import logging
import asyncio
from typing import List
from google import genai
from app.core.config import settings
from app.core.key_rotator import key_rotator

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    خدمة التضمين الدلالي عالية الأداء باستخدام نموذج جوجل الحديث.
    مزودة بنظام التدوير الذكي لمفاتيح الربط والتحويل التلقائي عند نفاد الحصص،
    وتنتج متجهات دلالية بحجم 3072 بعداً مع دعم كامل للعمليات غير المتزامنة (Async).
    """
    def __init__(self):
        self.model_name = settings.EMBEDDING_MODEL

    async def get_embedding_async(self, text: str) -> List[float]:
        """
        توليد متجه دلالي بشكل غير متزامن مع التدوير التلقائي الفوري بين المفاتيح الاحتياطية.
        إذا استنفد المفتاح الأول حصته، ينتقل تلقائياً للمفتاح التالي دون شعور المستخدم.
        """
        async def _call(client: genai.Client):
            response = await client.aio.models.embed_content(
                model=self.model_name,
                contents=text
            )
            return response.embeddings[0].values

        try:
            return await key_rotator.execute_with_failover("توليد المتجه الدلالي", _call)
        except Exception as e:
            logger.error(f"خطأ أثناء توليد المتجه الدلالي عبر مسبح المفاتيح: {str(e)}")
            raise e

    def get_embedding(self, text: str) -> List[float]:
        """
        توليد متجه دلالي بشكل متزامن (مخصص لخطوط المعالجة الدفعية والسكريبتات الخلفية).
        """
        _, client = asyncio.run(key_rotator.get_client()) if asyncio.get_event_loop().is_running() else (None, next(iter(key_rotator._clients.values())))
        try:
            response = client.models.embed_content(
                model=self.model_name,
                contents=text
            )
            return response.embeddings[0].values
        except Exception as e:
            logger.error(f"Error generating sync embedding: {str(e)}")
            raise e

    def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        توليد متجهات دلالية لمجموعة نصوص دفعة واحدة لتسريع الفهرسة الأولية.
        """
        client = next(iter(key_rotator._clients.values()))
        try:
            response = client.models.embed_content(
                model=self.model_name,
                contents=texts
            )
            return [item.values for item in response.embeddings]
        except Exception as e:
            logger.error(f"Error generating batch embeddings: {str(e)}")
            raise e


# نسخة عامة أحادية (Singleton)
embedding_service = EmbeddingService()
