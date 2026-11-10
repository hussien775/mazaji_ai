import uuid
from pydantic import BaseModel, Field
from typing import List, Optional
from app.schemas.search import HotelSearchResult


class ChatMessageRequest(BaseModel):
    session_id: Optional[str] = Field(
        default=None,
        description="معرف جلسة المحادثة (اختياري، وإذا لم يُرسل يتم توليده تلقائياً)",
        example="b7e28935-86b2-4d2b-9279-7f9cb8cf6161"
    )
    message: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="نص رسالة أو سؤال العميل لمساعد مزاجي",
        example="أشتي فندق هادئ ومريح في صنعاء وفيه مسبح وجاكوزي ومعي أهلي"
    )


class ChatMessageResponse(BaseModel):
    session_id: str
    reply: str
    suggested_hotels: List[HotelSearchResult] = []
