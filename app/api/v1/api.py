from fastapi import APIRouter, Depends
from app.core.security import verify_api_key
from app.api.v1.endpoints import health, hotels, search, chat

api_router = APIRouter()

# 1. مسار فحص الحالة (عام لخدمات المراقبة دون مفتاح)
api_router.include_router(health.router, tags=["System Health"])

# 2. مسار الفنادق التقليدي (محمي بمفتاح الأمان)
api_router.include_router(
    hotels.router,
    prefix="/hotels",
    tags=["Hotels"],
    dependencies=[Depends(verify_api_key)]
)

# 3. مسار البحث الذكي بالذكاء الاصطناعي (محمي بمفتاح الأمان)
api_router.include_router(
    search.router,
    prefix="/search",
    tags=["Smart AI Search"],
    dependencies=[Depends(verify_api_key)]
)

# 4. مسار المستشار الفندقي الذكي والشات (محمي بمفتاح الأمان)
api_router.include_router(
    chat.router,
    prefix="/chat",
    tags=["AI Hotel Advisor Chat"],
    dependencies=[Depends(verify_api_key)]
)
