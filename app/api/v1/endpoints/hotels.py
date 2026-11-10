from fastapi import APIRouter , Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import List
from app.models.property import Property
from sqlalchemy import select
from app.db.session import get_db
from app.schemas.hotels import HotelResponse

router = APIRouter()
@router.get("/sample",response_model=List[HotelResponse])
async def get_sample_hotel(db:AsyncSession = Depends(get_db)):
    statement = select(Property).where(Property.status == 1).limit(5)
    result = await db.scalars(statement)
    hotels = result.all()
    return hotels

