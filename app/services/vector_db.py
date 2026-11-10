import asyncio
import logging
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient, AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)
from app.core.config import settings
from app.services.query_parser import query_parser

logger = logging.getLogger(__name__)


class VectorDBService:
    """
    خدمة إدارة قاعدة بيانات المتجهات كيو-درانت للبحث الدلالي الفائق.
    تدعم معمارية ثنائية متقدمة:
    1. في بيئة السيرفر الإنتاجي: تتصل بالخادم المستقل عبر الشبكة (AsyncQdrantClient)
       بشكل غير متزامن بالكامل، مما يمنع قفل الملفات ويتيح عمل مئات المعالجات معاً.
    2. في بيئة التطوير المحلية: تعمل على التخزين المحلي، مع نقل عمليات الفحص إلى
       مسارات معالجة خلفية (asyncio.to_thread) لمنع حظر أو تجميد مسار الطلبات (Event Loop).
    """
    COLLECTION_NAME = "hotels"
    VECTOR_SIZE = 3072  # أبعاد نموذج جوجل الحديث

    def __init__(self):
        self.is_remote = bool(settings.QDRANT_URL)
        if self.is_remote:
            logger.info(f"الاتصال بخادم كيو-درانت المستقل: {settings.QDRANT_URL}")
            self.client = QdrantClient(
                url=settings.QDRANT_URL,
                api_key=settings.QDRANT_API_KEY
            )
            self.async_client = AsyncQdrantClient(
                url=settings.QDRANT_URL,
                api_key=settings.QDRANT_API_KEY
            )
        else:
            logger.info(f"تشغيل محرك كيو-درانت المحلي: {settings.QDRANT_PATH}")
            self.client = QdrantClient(path=settings.QDRANT_PATH)
            self.async_client = None

        self.ensure_collection_exists()

    def ensure_collection_exists(self):
        """
        إنشاء مجموعة الفنادق إذا لم تكن موجودة مسبقاً
        """
        try:
            existing = [c.name for c in self.client.get_collections().collections]
            if self.COLLECTION_NAME not in existing:
                self.client.create_collection(
                    collection_name=self.COLLECTION_NAME,
                    vectors_config=VectorParams(
                        size=self.VECTOR_SIZE,
                        distance=Distance.COSINE
                    )
                )
        except Exception as e:
            logger.error(f"خطأ أثناء التحقق من وجود مجموعة المتجهات: {e}")

    def upsert_hotels(self, hotels_data: List[Dict[str, Any]], vectors: List[List[float]]):
        """
        إيداع وتحديث متجهات الفنادق مع بياناتها الوصفية وقائمة وحداتها بالتفصيل
        """
        points = []
        for hotel, vector in zip(hotels_data, vectors):
            point = PointStruct(
                id=int(hotel["id"]),
                vector=vector,
                payload={
                    "hotel_id": int(hotel["id"]),
                    "name_ar": str(hotel.get("name_ar", "")),
                    "property_type": str(hotel.get("property_type", "")),
                    "city_name": str(hotel.get("city_name", "")),
                    "district_name": str(hotel.get("district_name", "")),
                    "min_price": float(hotel.get("min_price", 0)),
                    "max_price": float(hotel.get("max_price", 0)),
                    "amenities": hotel.get("amenities", []),
                    "unit_types": hotel.get("unit_types", []),
                    "units": hotel.get("units", []),
                    "rich_document": str(hotel.get("rich_document", ""))
                }
            )
            points.append(point)

        self.client.upsert(
            collection_name=self.COLLECTION_NAME,
            points=points
        )

    def _build_filter(self, city_name: Optional[str]) -> Optional[Filter]:
        """بناء فلتر المدينة الصارم"""
        if not city_name:
            return None
        return Filter(
            must=[
                FieldCondition(
                    key="city_name",
                    match=MatchValue(value=city_name)
                )
            ]
        )

    def _process_search_results(
        self,
        points: List[Any],
        limit: int,
        unit_type: Optional[str],
        max_price: Optional[float],
        guests: Optional[int]
    ) -> List[Dict[str, Any]]:
        """
        معالجة نقاط المتجهات المسترجعة وتطبيق المطابقة الهجينة الدقيقة للوحدات والأسعار
        """
        matched_hotels = []
        fallback_hotels = []

        for point in points:
            payload = point.payload or {}
            hotel_units = payload.get("units", [])

            # مطابقة الوحدات الداخلية للفندق وفق شروط البحث الصارمة
            matching_units = []
            for u in hotel_units:
                # 1. مطابقة نوع الوحدة (مثل: طيرمانة، غرفة، جناح...)
                if unit_type:
                    norm_req = query_parser.normalize_arabic(unit_type)
                    norm_u_type = query_parser.normalize_arabic(u.get("unit_type", ""))
                    norm_u_name = query_parser.normalize_arabic(u.get("unit_name", ""))
                    if (norm_req not in norm_u_type) and (norm_req not in norm_u_name):
                        continue

                # 2. مطابقة سعة النزلاء (يجب أن تتسع الوحدة للعدد المطلوب على الأقل)
                if guests:
                    if u.get("max_guests", 1) < guests:
                        continue

                # 3. مطابقة السعر المحدد للوحدة (يجب ألا يتجاوز السعر الحد المطلوب)
                if max_price:
                    if u.get("price_per_night", 0) > max_price:
                        continue

                matching_units.append(u)

            hotel_entry = {
                "hotel_id": payload.get("hotel_id"),
                "name_ar": payload.get("name_ar"),
                "property_type": payload.get("property_type"),
                "city_name": payload.get("city_name"),
                "district_name": payload.get("district_name"),
                "min_price": payload.get("min_price"),
                "max_price": payload.get("max_price"),
                "amenities": payload.get("amenities", []),
                "similarity_score": round(float(point.score), 4),
                "rich_document": payload.get("rich_document"),
                "matching_units": matching_units,
                "total_matching_units": len(matching_units),
                "_all_units": hotel_units
            }

            if unit_type or guests or max_price:
                if matching_units:
                    matched_hotels.append(hotel_entry)
                else:
                    fallback_hotels.append(hotel_entry)
            else:
                matched_hotels.append(hotel_entry)

        # 1. في حال وجود مطابقة تامة للشروط
        if matched_hotels:
            for h in matched_hotels:
                h.pop("_all_units", None)
            return matched_hotels[:limit]

        # 2. في حال عدم وجود وحدات تطابق السعر المنخفض جداً، إظهار أقرب الوحدات المتاحة من نفس النوع
        for h in fallback_hotels:
            all_u = h.pop("_all_units", [])
            closest = []
            for u in all_u:
                if unit_type:
                    norm_req = query_parser.normalize_arabic(unit_type)
                    norm_u_type = query_parser.normalize_arabic(u.get("unit_type", ""))
                    norm_u_name = query_parser.normalize_arabic(u.get("unit_name", ""))
                    if (norm_req in norm_u_type) or (norm_req in norm_u_name):
                        closest.append(u)
                else:
                    closest.append(u)
            # ترتيب الأقرب حسب السعر الأقل
            closest.sort(key=lambda x: x.get("price_per_night", 0))
            h["matching_units"] = closest[:3]
            h["total_matching_units"] = len(closest)

        return fallback_hotels[:limit]

    def _sync_query(self, query_vector: List[float], query_filter: Optional[Filter], candidate_limit: int):
        """تنفيذ استعلام المتجهات المتزامن"""
        return self.client.query_points(
            collection_name=self.COLLECTION_NAME,
            query=query_vector,
            query_filter=query_filter,
            limit=candidate_limit,
            with_payload=True
        )

    async def search_async(
        self,
        query_vector: List[float],
        limit: int = 5,
        city_name: Optional[str] = None,
        unit_type: Optional[str] = None,
        max_price: Optional[float] = None,
        guests: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        البحث الذكي غير المتزامن (Async/Non-blocking):
        مخصص لنقاط نهاية الويب والشات لضمان عدم حظر مسار المعالجة الرئيسي للطلبات المتزامنة.
        """
        query_filter = self._build_filter(city_name)
        candidate_limit = 50 if (city_name or unit_type or max_price or guests) else limit

        if self.is_remote and self.async_client:
            # استعلام غير متزامن بالكامل عبر الشبكة نحو خادم كيو-درانت المستقل
            response = await self.async_client.query_points(
                collection_name=self.COLLECTION_NAME,
                query=query_vector,
                query_filter=query_filter,
                limit=candidate_limit,
                with_payload=True
            )
        else:
            # تشغيل الاستعلام المحلي داخل مسار معالجة فرعي لمنع تجمد السيرفر
            response = await asyncio.to_thread(
                self._sync_query,
                query_vector,
                query_filter,
                candidate_limit
            )

        return self._process_search_results(
            points=response.points,
            limit=limit,
            unit_type=unit_type,
            max_price=max_price,
            guests=guests
        )

    def search(
        self,
        query_vector: List[float],
        limit: int = 5,
        city_name: Optional[str] = None,
        unit_type: Optional[str] = None,
        max_price: Optional[float] = None,
        guests: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        البحث المتزامن (مخصص لسكريبتات الفهرسة وتجارب الطرفية)
        """
        query_filter = self._build_filter(city_name)
        candidate_limit = 50 if (city_name or unit_type or max_price or guests) else limit
        response = self._sync_query(query_vector, query_filter, candidate_limit)

        return self._process_search_results(
            points=response.points,
            limit=limit,
            unit_type=unit_type,
            max_price=max_price,
            guests=guests
        )


vector_db_service = VectorDBService()
