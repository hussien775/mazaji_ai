from pydantic import BaseModel
from typing import Optional


class HotelResponse(BaseModel):
    id: int
    name_ar: str
    description_ar: Optional[str] = None

    class Config:
        from_attributes = True
