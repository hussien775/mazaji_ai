import json
import logging
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from app.schemas.chat import ChatMessageRequest, ChatMessageResponse
from app.services.chat import chat_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/message", response_model=ChatMessageResponse, status_code=status.HTTP_200_OK)
async def send_chat_message(request: ChatMessageRequest):
    """
    نقطة النهاية لمحادثة المستشار الفندقي الذكي لتطبيق مزاجي (الرد المكتمل):
    تستقبل رسالة العميل مع معرف الجلسة، وتقوم باسترجاع الفنادق المناسبة
    وصياغة مشورة فندقية موثقة بلهجة يمنية مضيافة،
    وإرجاع الرد مع بطاقات الفنادق والوحدات المقترحة ليعرضها تطبيق فلاتر.
    """
    try:
        response_data = await chat_service.reply_to_user(
            session_id=request.session_id,
            message=request.message
        )
        return response_data
    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="حدث خطأ غير متوقع أثناء معالجة رسالتك، يرجى المحاولة لاحقاً."
        )


@router.post("/stream")
async def send_chat_message_stream(request: ChatMessageRequest):
    """
    نقطة النهاية للبث اللحظي المباشر لرسائل المستشار الذكي (Server-Sent Events):
    ترسل كروت الفنادق المقترحة فور استرجاعها مباشرة، ثم تبث كلمات الرد
    حرفاً بحرف في أجزاء من الثانية مما يلغي أي انتظار ويمنح المستخدم تجربة تفاعلية فائقة.
    """
    async def event_generator():
        try:
            async for packet in chat_service.reply_to_user_stream(
                session_id=request.session_id,
                message=request.message
            ):
                event_name = packet.get("event", "message")
                raw_data = packet.get("data", "")
                data_payload = json.dumps(raw_data, ensure_ascii=False) if isinstance(raw_data, (dict, list)) else str(raw_data)
                yield f"event: {event_name}\ndata: {data_payload}\n\n"
        except Exception as err:
            logger.error(f"خطأ غير متوقع أثناء تدفق رسائل الشات: {err}", exc_info=True)
            yield f"event: error\ndata: حدث خطأ أثناء بث الرد، يرجى إعادة المحاولة\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
