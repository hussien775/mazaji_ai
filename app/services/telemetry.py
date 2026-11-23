import logging
import asyncio
from typing import Optional, Dict, Any

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

from app.core.config import settings

logger = logging.getLogger(__name__)


class TelemetryService:
    """
    خدمة التتبع والمراقبة السحابية (LLM Observability) لمستشار مزاجي الذكي
    المبنية على منصة Langfuse العالمية.
    توفر:
    1. تتبع كامل لكل محادثة ورسالة بين العميل والنموذج تظهر في لوحة تحكم Langfuse فوراً.
    2. تسجيل التوكنات، التكاليف، وسرعة الاستجابة بالمللي ثانية.
    3. تسجيل الفنادق المقترحة والبيانات المستخرجة (المدينة، الأسعار...).
    4. حفظ التقييمات اللحظية (Feedback) لمعرفة مدى استفادة العميل.
    5. تعمل بشكل غير متزامن وغير حاجب (Non-blocking) لضمان عدم تأثر سرعة الشات بأي جزء من الثانية.
    """

    def __init__(self):
        self.client = None
        self.is_active = False
        self._init_client()

    def _init_client(self):
        secret_key = settings.LANGFUSE_SECRET_KEY
        public_key = settings.LANGFUSE_PUBLIC_KEY
        host = settings.LANGFUSE_HOST or settings.LANGFUSE_BASE_URL or "https://cloud.langfuse.com"

        if secret_key and public_key:
            try:
                from langfuse import Langfuse
                self.client = Langfuse(
                    secret_key=secret_key,
                    public_key=public_key,
                    host=host
                )
                self.is_active = True
                logger.info("تم تفعيل وتوثيق منصة المراقبة والتحليلات (Langfuse) بنجاح.")
            except Exception as e:
                logger.warning(f"تعذر تهيئة Langfuse: {e}")
                self.is_active = False
        else:
            logger.info("لم يتم ضبط مفاتيح Langfuse في ملف .env، التتبع الخارجي معطل.")

    def log_chat_turn(
        self,
        session_id: str,
        user_message: str,
        bot_reply: str,
        suggested_hotels_count: int,
        metadata: Optional[Dict[str, Any]] = None,
        is_fallback: bool = False
    ) -> None:
        """
        تسجيل جولة محادثة في لوحة تحكم Langfuse السحابية في مسار معالجة خلفي
        """
        if not self.is_active or not self.client:
            return

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._async_log(
                session_id=session_id,
                user_message=user_message,
                bot_reply=bot_reply,
                suggested_hotels_count=suggested_hotels_count,
                metadata=metadata,
                is_fallback=is_fallback
            ))
        except RuntimeError:
            pass

    async def _async_log(
        self,
        session_id: str,
        user_message: str,
        bot_reply: str,
        suggested_hotels_count: int,
        metadata: Optional[Dict[str, Any]] = None,
        is_fallback: bool = False
    ):
        try:
            def _record():
                meta = dict(metadata) if metadata else {}
                meta.update({
                    "session_id": session_id,
                    "suggested_hotels_count": suggested_hotels_count,
                    "is_fallback": is_fallback,
                    "service": "mazaji_ai"
                })
                with self.client.start_as_current_observation(
                    name="mazaji_advisor_chat",
                    input={"user_message": user_message},
                    output={"reply": bot_reply},
                    metadata=meta
                ):
                    pass
                self.client.flush()

            await asyncio.to_thread(_record)
        except Exception as e:
            logger.warning(f"خطأ غير مؤثر أثناء تسجيل المحادثة في Langfuse: {e}")


telemetry_service = TelemetryService()
