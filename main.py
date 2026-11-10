import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.rate_limiter import RateLimitMiddleware
from app.api.v1.api import api_router

logger = logging.getLogger(__name__)

# Initialize FastAPI application
app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Intelligent Semantic Search and AI Booking Engine for Mazaji",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 1. وسيط الحماية من سيل الطلبات المفرطة (Rate Limiting)
app.add_middleware(RateLimitMiddleware)

# 2. وسيط مشاركة الموارد الآمن (CORS Security)
cors_allow_credentials = False if settings.CORS_ORIGINS == ["*"] else True
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 3. معالج الأخطاء العام لحجب تفاصيل السيرفر الداخلية أمنياً (Error Masking)
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"خطأ داخلي غير متوقع في المسار {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "status": False,
            "message": "حدث خطأ غير متوقع أثناء معالجة طلبك، يرجى إعادة المحاولة لاحقاً.",
            "code": "INTERNAL_SERVER_ERROR"
        }
    )


# Include v1 API router
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/")
async def root():
    return {
        "message": f"Welcome to {settings.PROJECT_NAME} Backend",
        "docs": "/docs",
        "health": f"{settings.API_V1_STR}/health"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
