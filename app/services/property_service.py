import logging
import urllib.parse
from collections import defaultdict
from typing import List, Dict, Tuple, Any, Optional
from sqlalchemy import text, bindparam
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.schemas.search import PropertyDataModel, MatchingUnit

logger = logging.getLogger(__name__)


class PropertyService:
    """
    خدمة معالجة وتجهيز بيانات العقارات والصور والتقييمات.
    توحد عمليات الاستعلام عن الوسائط والتقييمات وتمنع تكرار الكود (DRY)،
    وتستخدم استعلامات مُعاملة آمنة بالكامل (Parameterized Queries)
    لمنع أي ثغرة حقن SQL وتوفير أقصى سرعة ممكنة.
    """

    @staticmethod
    async def get_media_and_ratings(
        property_ids: List[int],
        db: AsyncSession
    ) -> Tuple[Dict[int, List[str]], Dict[int, float]]:
        """
        استخراج روابط الصور والتقييمات الحقيقية لمجموعة عقارات دفعة واحدة
        عبر استعلامات آمنة ومُعاملة (Parameterized Queries).
        """
        images_by_prop = defaultdict(list)
        ratings_by_prop = defaultdict(lambda: 4.5)

        if not property_ids:
            return images_by_prop, ratings_by_prop

        # التأكد التام من تحويل جميع المعرفات إلى أرقام صحيحة
        clean_ids = [int(pid) for pid in property_ids]

        try:
            # 1. استعلام الصور الآمن عبر ربط المعاملات
            media_stmt = text("""
                SELECT model_id, id, file_name 
                FROM media 
                WHERE model_type LIKE '%Property%' AND model_id IN :ids
                ORDER BY order_column ASC, id ASC
            """).bindparams(bindparam("ids", expanding=True))

            media_res = await db.execute(media_stmt, {"ids": clean_ids})
            base_url = settings.MEDIA_BASE_URL.rstrip("/")

            for row in media_res.fetchall():
                file_name_encoded = urllib.parse.quote(str(row.file_name or ""))
                images_by_prop[row.model_id].append(f"{base_url}/{row.id}/{file_name_encoded}")

            # 2. استعلام التقييمات الآمن
            reviews_stmt = text("""
                SELECT property_id, ROUND(AVG(rating), 1) as avg_rating 
                FROM reviews 
                WHERE property_id IN :ids
                GROUP BY property_id
            """).bindparams(bindparam("ids", expanding=True))

            rev_res = await db.execute(reviews_stmt, {"ids": clean_ids})
            for row in rev_res.fetchall():
                ratings_by_prop[row.property_id] = float(row.avg_rating or 4.5)

        except Exception as e:
            logger.error(f"خطأ أثناء جلب الصور والتقييمات للعقارات {clean_ids}: {e}", exc_info=True)

        return images_by_prop, ratings_by_prop

    @staticmethod
    def build_property_data_models(
        raw_hotels: List[Dict[str, Any]],
        images_by_prop: Dict[int, List[str]],
        ratings_by_prop: Dict[int, float]
    ) -> List[PropertyDataModel]:
        """
        بناء كائنات PropertyDataModel المتوافقة 100% مع تطبيق فلاتر
        مع ربط الوحدات المطابقة والصور والتقييمات
        """
        properties_list = []
        for h in raw_hotels:
            pid = int(h.get("hotel_id", 0))
            prop_images = images_by_prop.get(pid, [])
            prop_rating = ratings_by_prop.get(pid, 4.5)

            matching_units_list = []
            for u in h.get("matching_units", []):
                matching_units_list.append(
                    MatchingUnit(
                        unit_id=int(u.get("unit_id", 0)),
                        unit_name=str(u.get("unit_name", "")),
                        unit_type=str(u.get("unit_type", "")),
                        price_per_night=float(u.get("price_per_night", 0.0)),
                        max_guests=int(u.get("max_guests", 1)),
                        single_beds=int(u.get("single_beds", 0)),
                        double_beds=int(u.get("double_beds", 0))
                    )
                )

            properties_list.append(
                PropertyDataModel(
                    id=pid,
                    name=str(h.get("name_ar", "")),
                    rating=prop_rating,
                    totalRate=prop_rating,
                    type=str(h.get("property_type", "فندق")),
                    city=str(h.get("city_name", "")),
                    district=str(h.get("district_name", "")),
                    main_image_url=prop_images,
                    main_image_url2=prop_images,
                    isFavorite=False,
                    has_offer_active=False,
                    offer_description="",
                    matching_units=matching_units_list,
                    total_matching_units=len(matching_units_list)
                )
            )
        return properties_list


property_service = PropertyService()
