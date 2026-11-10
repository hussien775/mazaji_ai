from pydantic import BaseModel, Field
from typing import List, Optional


class SmartSearchRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="نص البحث الذكي الموحد",
        example="اريد طيرمانه في صنعاء بسعر 10000 لسبعه اشخاص"
    )
    page: int = Field(1, ge=1, description="رقم الصفحة الحالية (Pagination)")
    per_page: int = Field(5, ge=1, le=50, description="عدد النتائج في الصفحة الواحدة")


class MatchingUnit(BaseModel):
    unit_id: int
    unit_name: str
    unit_type: str
    price_per_night: float
    max_guests: int
    single_beds: int = 0
    double_beds: int = 0


class PropertyDataModel(BaseModel):
    id: int
    name: str
    rating: float = 0.0
    totalRate: float = 0.0
    type: str = "مكان إقامة"
    city: str = ""
    district: str = ""
    main_image_url: List[str] = []
    main_image_url2: List[str] = []
    isFavorite: bool = False
    has_offer_active: bool = False
    offer_description: str = ""
    matching_units: List[MatchingUnit] = []
    total_matching_units: int = 0


# الاسم البديل لضمان التوافق مع خدمات الشات
HotelSearchResult = PropertyDataModel


class PaginationData(BaseModel):
    current_page: int
    last_page: int
    per_page: int
    total: int
    data: List[PropertyDataModel]


class FlutterPaginationResponse(BaseModel):
    status: bool = True
    message: str = "تمت عملية البحث الذكي بنجاح"
    data: PaginationData
