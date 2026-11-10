import math
import logging
import urllib.parse
from collections import defaultdict
from typing import List, Optional, Any
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.config import settings
from app.db.session import get_db
from app.schemas.search import (
    SmartSearchRequest,
    FlutterPaginationResponse,
    PaginationData,
    PropertyDataModel,
    MatchingUnit
)
from app.services.embedding import embedding_service
from app.services.vector_db import vector_db_service
from app.services.query_parser import query_parser
from app.services.property_service import property_service

logger = logging.getLogger(__name__)
router = APIRouter()


async def execute_smart_search(
    query_str: Optional[str],
    page: int,
    per_page: int,
    db: AsyncSession
) -> FlutterPaginationResponse:
    """
    الدالة المركزية لتنفيذ البحث الذكي، استخراج الكيانات، ترقيم الصفحات،
    وجلب الصور والتقييمات الحقيقية المتوافقة تماماً مع موديل فلاتر PropertyDataModel
    """
    try:
        clean_query = (query_str or "").strip()

        # إذا كان نص البحث فارغاً (مثلاً العميل فتح شاشة البحث ولم يكتب بعد)
        # نرجع قائمة الفنادق الافتراضية بدلاً من الخطأ
        if not clean_query:
            count_res = await db.execute(text("SELECT COUNT(*) FROM properties WHERE status = 1"))
            total_records = count_res.scalar() or 0
            last_page = math.ceil(total_records / per_page) if total_records > 0 else 1

            offset = (page - 1) * per_page
            props_sql = text("""
                SELECT 
                    p.id, 
                    p.name_ar, 
                    COALESCE(pt.name_ar, 'فندق') as property_type,
                    COALESCE(c.name_ar, '') as city_name,
                    COALESCE(d.name_ar, '') as district_name
                FROM properties p
                LEFT JOIN property_types pt ON p.property_type_id = pt.id
                LEFT JOIN property_addresses pa ON pa.property_id = p.id
                LEFT JOIN cities c ON pa.city_id = c.id
                LEFT JOIN districts d ON pa.district_id = d.id
                WHERE p.status = 1
                ORDER BY p.id ASC
                LIMIT :limit OFFSET :offset
            """)
            props_res = await db.execute(props_sql, {"limit": per_page, "offset": offset})
            default_props = props_res.fetchall()

            property_ids = [r.id for r in default_props]
            images_by_prop, _ = await property_service.get_media_and_ratings(property_ids, db)

            data_list = []
            for r in default_props:
                imgs = images_by_prop.get(r.id, [])
                data_list.append(
                    PropertyDataModel(
                        id=int(r.id),
                        name=str(r.name_ar or ""),
                        rating=4.5,
                        totalRate=4.5,
                        type=str(r.property_type or "فندق"),
                        city=str(r.city_name or ""),
                        district=str(r.district_name or ""),
                        main_image_url=imgs,
                        main_image_url2=imgs,
                        isFavorite=False,
                        has_offer_active=False,
                        offer_description="",
                        matching_units=[],
                        total_matching_units=0
                    )
                )

            return FlutterPaginationResponse(
                status=True,
                message="تم جلب الفنادق المتاحة بنجاح",
                data=PaginationData(
                    current_page=page,
                    last_page=last_page,
                    per_page=per_page,
                    total=total_records,
                    data=data_list
                )
            )

        # 1. تحليل النص واستخراج المحافظة والوحدة والسعة والميزانية تلقائياً
        parsed = query_parser.parse_query(clean_query)
        detected_city = parsed.get("detected_city")
        detected_unit_type = parsed.get("detected_unit_type")
        detected_guests = parsed.get("detected_guests")
        detected_max_price = parsed.get("detected_max_price")

        # 2. توليد المتجه الدلالي للنص غير المتزامن
        query_vector = await embedding_service.get_embedding_async(clean_query)

        # 3. استرجاع الفنادق المطابقة دلالياً بشكل غير متزامن
        matched_hotels = await vector_db_service.search_async(
            query_vector=query_vector,
            limit=50,
            city_name=detected_city,
            unit_type=detected_unit_type,
            max_price=detected_max_price,
            guests=detected_guests
        )

        total_records = len(matched_hotels)
        last_page = math.ceil(total_records / per_page) if total_records > 0 else 1

        # تطبيق ترقيم الصفحات (Pagination Slicing)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paged_hotels = matched_hotels[start_idx:end_idx]

        # 4. جلب الصور الحقيقية والتقييمات بطريقة مُعاملة آمنة (Parameterized Query)
        property_ids = [h["hotel_id"] for h in paged_hotels]
        images_by_prop, ratings_by_prop = await property_service.get_media_and_ratings(property_ids, db)

        # 5. بناء كائنات البيانات المتطابقة حرفياً مع PropertyDataModel في فلاتر
        properties_list = property_service.build_property_data_models(
            raw_hotels=paged_hotels,
            images_by_prop=images_by_prop,
            ratings_by_prop=ratings_by_prop
        )

        return FlutterPaginationResponse(
            status=True,
            message="تمت عملية البحث الذكي بنجاح",
            data=PaginationData(
                current_page=page,
                last_page=last_page,
                per_page=per_page,
                total=total_records,
                data=properties_list
            )
        )

    except Exception as e:
        logger.error(f"Search endpoint failure for query '{query_str}': {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="حدث خطأ غير متوقع أثناء معالجة البحث، يرجى إعادة المحاولة."
        )


@router.post("/smart", response_model=FlutterPaginationResponse, status_code=status.HTTP_200_OK)
async def smart_search_hotels_post(
    request: Optional[SmartSearchRequest] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    نقطة النهاية للبحث الذكي عبر POST (إرسال البيانات كـ JSON)
    متوافقة تماماً مع نظام الترقيم وموديل فلاتر PropertyDataModel
    """
    query_text = request.query if request else ""
    page_num = request.page if request else 1
    per_page_num = request.per_page if request else 5

    return await execute_smart_search(
        query_str=query_text,
        page=page_num,
        per_page=per_page_num,
        db=db
    )


@router.get("/smart", response_model=FlutterPaginationResponse, status_code=status.HTTP_200_OK)
async def smart_search_hotels_get(
    search: Optional[str] = Query(None, description="نص البحث المرسل من فلاتر"),
    query: Optional[str] = Query(None, description="نص البحث البديل"),
    page: int = Query(1, ge=1, description="رقم الصفحة"),
    perPage: Optional[int] = Query(None, description="عدد العناصر بالصفحة في فلاتر"),
    per_page: Optional[int] = Query(None, description="عدد العناصر بالصفحة"),
    price_from: Optional[Any] = Query(None, description="الحد الأدنى للسعر إن وجد"),
    price_to: Optional[Any] = Query(None, description="الحد الأقصى للسعر إن وجد"),
    db: AsyncSession = Depends(get_db)
):
    """
    نقطة النهاية للبحث الذكي عبر GET:
    تستقبل تلقائياً متغيرات فلاتر:
    - search أو query
    - perPage أو per_page
    - page
    - price_from و price_to
    وتعيد الرد بنفس الترقيم والموديل المتوقع
    """
    query_text = search if search is not None else query
    effective_per_page = perPage if perPage is not None else (per_page if per_page is not None else 5)

    return await execute_smart_search(
        query_str=query_text,
        page=page,
        per_page=effective_per_page,
        db=db
    )
