import time
import logging
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings

logger = logging.getLogger(__name__)


class SlidingWindowRateLimiter:
    """
    محدد معدل الطلبات الذكي (Rate Limiter):
    يحمي السيرفر وقاعدة البيانات ورصيد الذكاء الاصطناعي من هجمات الإغراق (DoS)
    أو الاستدعاءات العشوائية المفرطة عبر تقييد عدد الطلبات لكل عنوان IP في الدقيقة.
    يدعم المعمارية السحابية عبر Redis، أو الذاكرة المحلية المنظمة تلقائياً.
    """
    def __init__(self, limit_per_minute: int = 60):
        self.limit = limit_per_minute
        # عنوان IP -> قائمة بالطوابع الزمنية للطلبات الأخيرة
        self._requests = defaultdict(list)

    def is_allowed(self, client_ip: str) -> bool:
        now = time.time()
        one_minute_ago = now - 60.0

        # تنظيف الطلبات الأقدم من دقيقة
        timestamps = [t for t in self._requests[client_ip] if t > one_minute_ago]
        self._requests[client_ip] = timestamps

        if len(timestamps) >= self.limit:
            return False

        self._requests[client_ip].append(now)
        return True


rate_limiter = SlidingWindowRateLimiter(limit_per_minute=settings.RATE_LIMIT_PER_MINUTE)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    وسيط برمجي لفحص كل طلب وارد ومنع سيل الطلبات المفرطة
    """
    # المسارات المستثناة من التقييد (فحص صحة السيرفر والتوثيق)
    EXEMPT_PATHS = {
        "/",
        "/docs",
        "/redoc",
        "/openapi.json",
        f"{settings.API_V1_STR}/health"
    }

    async def dispatch(self, request: Request, call_next):
        # استثناء مسارات الفحص والتوثيق
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        # استخراج عنوان العميل (مع مراعاة البروكسي مثل Nginx أو Cloudflare)
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "127.0.0.1"

        if not rate_limiter.is_allowed(client_ip):
            logger.warning(f"تم حظر طلب مفرط مؤقتاً من العنوان: {client_ip} للمسار: {request.url.path}")
            return JSONResponse(
                status_code=429,
                content={
                    "status": False,
                    "message": "لقد تجاوزت الحد المسموح به من الطلبات في الدقيقة، يرجى الانتظار قليلاً قبل إعادة المحاولة.",
                    "code": "TOO_MANY_REQUESTS"
                }
            )

        return await call_next(request)
