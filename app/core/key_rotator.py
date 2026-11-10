import time
import logging
import asyncio
from typing import List, Dict, Optional, Tuple, Callable, Any
from google import genai
from app.core.config import settings

logger = logging.getLogger(__name__)


class GeminiKeyRotator:
    """
    المدير المركزي لمسبح مفاتيح الذكاء الاصطناعي (API Key Pool Rotator):
    1. تدوير المفاتيح بالتناوب (Round-Robin) لتوزيع الحمل وتفادي الوصول للحد الأقصى.
    2. التحويل التلقائي الفوري (Automatic Failover): عند استنفاد حصة أي مفتاح (خطأ 429)،
       يتم تجميده مؤقتاً والتبديل فوراً وبشكل غير مرئي للعميل إلى المفتاح الاحتياطي التالي.
    """

    def __init__(self):
        self._keys: List[str] = []
        self._clients: Dict[str, genai.Client] = {}
        # تتبع وقت تجميد المفاتيح المستنفدة: key -> cooldown_until_timestamp
        self._cooldowns: Dict[str, float] = {}
        self._current_index: int = 0
        self._lock = asyncio.Lock()
        self.reload_keys()

    def reload_keys(self):
        """تحميل وتحديث مفاتيح جوجل المتاحة وتجهيز عملاء الاتصال"""
        raw_keys = settings.all_gemini_keys
        self._keys = raw_keys
        self._clients.clear()

        for k in self._keys:
            try:
                self._clients[k] = genai.Client(api_key=k)
            except Exception as e:
                logger.error(f"خطأ أثناء تهيئة عميل المفتاح: {e}")

        logger.info(f"تم بنجاح تحميل مسبح مفاتيح الذكاء الاصطناعي بإجمالي: {len(self._keys)} مفتاحاً.")

    def _is_key_available(self, key: str, now: float) -> bool:
        """فحص ما إذا كان المفتاح نشطاً ولم يتم تجميده بسبب استنفاد الحصة"""
        cooldown_until = self._cooldowns.get(key, 0)
        return now >= cooldown_until

    async def get_client(self) -> Tuple[str, genai.Client]:
        """
        الحصول على العميل والمفتاح النشط التالي بنمط التدوير المتوازن (Round-Robin)
        مع استبعاد المفاتيح المستنفدة مؤقتاً.
        """
        async with self._lock:
            if not self._keys:
                raise ValueError("لا يوجد أي مفتاح GEMINI_API_KEY مهيأ في الإعدادات أو ملف البيئة!")

            now = time.time()
            total = len(self._keys)

            # البحث عن أول مفتاح متاح بدءاً من المؤشر الحالي
            for _ in range(total):
                key = self._keys[self._current_index]
                self._current_index = (self._current_index + 1) % total

                if self._is_key_available(key, now):
                    return key, self._clients[key]

            # إذا كانت جميع المفاتيح مجمدة، نعيد أول مفتاح كخيار أخير مع تحذير
            logger.warning("تنبيه أمني: جميع مفاتيح الذكاء الاصطناعي في وضع التجميد المؤقت، جاري استخدام المفتاح الأول كخيار أخير.")
            fallback_key = self._keys[0]
            return fallback_key, self._clients[fallback_key]

    def mark_key_exhausted(self, key: str, cooldown_seconds: int = 60):
        """
        تجميد المفتاح مؤقتاً عند رصد خطأ نفاد الحصة (429 Resource Exhausted)
        لمدة دقيقة كاملة ليتعافى، وتوجيه الحركة للمفاتيح الاحتياطية الأخرى.
        """
        now = time.time()
        self._cooldowns[key] = now + cooldown_seconds
        masked = f"{key[:6]}...{key[-4:]}" if len(key) > 10 else "***"
        logger.warning(
            f"تم رصد نفاد حصة المفتاح ({masked}). تم تجميده مؤقتاً لمدة {cooldown_seconds} ثانية، "
            f"والتحويل التلقائي للمفاتيح الاحتياطية التالية."
        )

    async def execute_with_failover(
        self,
        operation_name: str,
        coro_func: Callable[[genai.Client], Any]
    ) -> Any:
        """
        منظومة التنفيذ الذاتي الآمن مع التحويل الاحتياطي:
        تنفذ العملية، وإذا واجهت خطأ نفاد الحصة في المفتاح الحالي،
        تقوم فوراً بتجميده وإعادة المحاولة بالمفتاح الاحتياطي التالي تلقائياً!
        """
        attempts = max(len(self._keys), 1)
        last_error = None

        for attempt in range(attempts):
            key, client = await self.get_client()
            try:
                # تنفيذ العملية عبر العميل المختار
                return await coro_func(client)
            except Exception as e:
                err_str = str(e).lower()
                # فحص ما إذا كان الخطأ بسبب نفاد الحصة أو ضغط الطلبات (429 أو ResourceExhausted)
                if "429" in err_str or "resource_exhausted" in err_str or "quota" in err_str:
                    self.mark_key_exhausted(key, cooldown_seconds=60)
                    last_error = e
                    logger.info(f"جاري إعادة محاولة عملية ({operation_name}) بالمفتاح الاحتياطي التالي (المحاولة {attempt + 1}/{attempts})...")
                    continue
                else:
                    # أي خطأ آخر غير نفاد الحصة يتم رميه مباشرة
                    raise e

        # إذا نفدت كافة المفاتيح
        raise last_error or RuntimeError(f"فشلت عملية ({operation_name}) بعد استنفاد كافة المفاتيح المتاحة.")


# نسخة مركزية أحادية
key_rotator = GeminiKeyRotator()
