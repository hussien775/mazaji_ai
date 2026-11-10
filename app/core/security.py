import re
import secrets
import logging
from typing import Optional
from fastapi import Header, HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)

# قائمة بالأنماط والعبارات التخريبية الشائعة لمحاولات حقن الأوامر (Prompt Injection)
INJECTION_PATTERNS = [
    r"تجاهل\s+(?:كل|جميع)?\s*(?:التعليمات|الأوامر|القواعد|ما\s*سبق)",
    r"انسى\s+(?:كل|جميع)?\s*(?:ما\s*سبق|التعليمات)",
    r"أنت\s+الآن\s+(?:لست|غير)",
    r"(?:اطبع|اكشف|اعطني|هات)\s+(?:التعليمات|المفاتيح|النظام|الكود|api[_\s-]?key)",
    r"ignore\s+(?:all\s+)?(?:previous\s+)?instructions",
    r"system\s*prompt",
    r"reveal\s+(?:the\s+)?(?:secret|key|prompt|instructions)",
    r"pretend\s+(?:you\s+are|to\s+be)",
    r"you\s+are\s+no\s+longer",
]

compiled_injection_regexes = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


def sanitize_prompt_input(user_text: str) -> str:
    """
    فحص مدخلات المستخدم وتحصينها ضد محاولات التلاعب وحقن الأوامر التوجيهية (Prompt Injection).
    يقوم بتحييد أي محاولة لتغيير شخصية النموذج أو سرقة التعليمات الحساسة.
    """
    if not user_text:
        return ""

    cleaned_text = user_text.strip()
    for pattern in compiled_injection_regexes:
        if pattern.search(cleaned_text):
            logger.warning(f"تم رصد محاولة تلاعب بالأوامر (Prompt Injection) في الرسالة: {cleaned_text}")
            # استبدال العبارة المشبوهة بنص آمن ومحايد
            cleaned_text = pattern.sub("[محتوى غير مسموح تم تحييده أمنياً]", cleaned_text)

    return cleaned_text


async def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization")
) -> bool:
    """
    وسيط التحقق الصارم من مفتاح الوصول المعتمد (API Key Guard):
    يحمي مسارات الذكاء الاصطناعي من أي وصول خارجي غير مصرح به.
    يدعم إرسال المفتاح عبر:
    - الترويسة المباشرة: X-API-Key: your_key
    - أو ترويسة التوثيق: Authorization: Bearer your_key
    يستخدم مقارنة آمنة زمنياً (Constant-Time Comparison) لمنع هجمات التوقيت (Timing Attacks).
    """
    expected_key = settings.API_SECRET_KEY

    # استخراج المفتاح من إحدى الترويستين
    provided_key = None
    if x_api_key:
        provided_key = x_api_key.strip()
    elif authorization and authorization.lower().startswith("bearer "):
        provided_key = authorization[7:].strip()

    if not provided_key:
        logger.warning("تم رفض طلب: مفتاح الأمان (API Key) مفقود في الترويسات.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "status": False,
                "message": "غير مصرح لك بالوصول: يرجى تقديم مفتاح الأمان المعتمد (X-API-Key).",
                "code": "MISSING_API_KEY"
            }
        )

    # فحص آمن ومقاوم لهجمات التوقيت
    if not secrets.compare_digest(provided_key, expected_key):
        logger.warning(f"تم رفض طلب: مفتاح الأمان المقدم غير صحيح: {provided_key[:5]}***")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "status": False,
                "message": "غير مصرح لك بالوصول: مفتاح الأمان غير صالح.",
                "code": "INVALID_API_KEY"
            }
        )

    return True
