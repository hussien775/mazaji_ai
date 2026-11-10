import json
import time
import logging
import asyncio
from typing import List, Dict, Optional
from collections import OrderedDict

from app.core.config import settings

logger = logging.getLogger(__name__)


class LocalTTLSessionStore:
    """
    مخزن جلسات محلي ذكي مع انتهاء صلاحية تلقائي (TTL) وحد أقصى للذاكرة (LRU).
    يعمل كبديل آمن وسريع في بيئة التطوير المحلية دون الحاجة لتثبيت أي برامج إضافية.
    يحمي الذاكرة من التسريب عبر حذف الجلسات القديمة التي تجاوزت المدة المحددة.
    """
    def __init__(self, ttl_seconds: int = 86400, max_sessions: int = 5000):
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        # تخزين مرتب: session_id -> {"last_active": timestamp, "history": list}
        self._store: OrderedDict[str, Dict] = OrderedDict()
        self._lock = asyncio.Lock()

    def _cleanup_expired(self):
        """تنظيف الجلسات المنتهية صلاحيتها تلقائياً"""
        now = time.time()
        expired_keys = [
            sid for sid, data in self._store.items()
            if now - data["last_active"] > self.ttl_seconds
        ]
        for sid in expired_keys:
            del self._store[sid]

    async def get_history(self, session_id: str) -> List[Dict[str, str]]:
        async with self._lock:
            self._cleanup_expired()
            if session_id not in self._store:
                return []
            entry = self._store[session_id]
            entry["last_active"] = time.time()
            self._store.move_to_end(session_id)
            return list(entry["history"])

    async def save_turn(self, session_id: str, user_text: str, model_text: str, max_turns: int = 10) -> None:
        async with self._lock:
            self._cleanup_expired()
            if session_id in self._store:
                entry = self._store[session_id]
            else:
                # إذا تجاوز عدد الجلسات الحد الأقصى نحذف أقدم جلسة (LRU Eviction)
                if len(self._store) >= self.max_sessions:
                    self._store.popitem(last=False)
                entry = {"last_active": time.time(), "history": []}
                self._store[session_id] = entry

            entry["history"].append({"role": "user", "text": user_text})
            entry["history"].append({"role": "model", "text": model_text})

            if len(entry["history"]) > max_turns:
                entry["history"] = entry["history"][-max_turns:]

            entry["last_active"] = time.time()
            self._store.move_to_end(session_id)

    async def clear_session(self, session_id: str) -> None:
        async with self._lock:
            if session_id in self._store:
                del self._store[session_id]


class SessionManager:
    """
    المدير المركزي لجلسات ومحادثات المستشار الذكي.
    يدعم معمارية ثنائية متقدمة:
    1. في بيئة الإنتاج السحابية: يستخدم نظام الذاكرة السريعة المستقل (Redis)
       مما يتيح تشغيل أي عدد من المعالجات (Workers) والسيرفرات المتزامنة دون فقدان السياق.
    2. في بيئة التطوير المحلية: يتحول تلقائياً إلى مخزن الذاكرة الذكي مع التنظيف التلقائي.
    """
    def __init__(self):
        self.redis_client = None
        self.local_store = LocalTTLSessionStore(
            ttl_seconds=settings.SESSION_TTL_SECONDS,
            max_sessions=5000
        )
        self.is_redis_active = False
        self._init_redis()

    def _init_redis(self):
        if settings.REDIS_URL:
            try:
                import redis.asyncio as aioredis
                self.redis_client = aioredis.from_url(
                    settings.REDIS_URL,
                    decode_responses=True,
                    socket_connect_timeout=2
                )
                self.is_redis_active = True
                logger.info(f"تم ربط نظام الذاكرة السريعة (Redis) بنجاح: {settings.REDIS_URL}")
            except Exception as e:
                logger.warning(f"تعذر الاتصال بـ Redis، سيتم استخدام المخزن المحلي الذكي: {e}")
                self.is_redis_active = False
        else:
            logger.info("لم يتم ضبط رابط REDIS_URL، يتم تشغيل المخزن المحلي الذكي مع خاصية انتهاء الصلاحية التلقائي.")

    async def get_history(self, session_id: str) -> List[Dict[str, str]]:
        """
        استرجاع سجل الرسائل السابقة لجلسة معينة
        """
        if not session_id:
            return []

        if self.is_redis_active and self.redis_client:
            try:
                key = f"chat:session:{session_id}"
                data = await self.redis_client.get(key)
                if data:
                    # تجديد وقت انتهاء الصلاحية للجلسة
                    await self.redis_client.expire(key, settings.SESSION_TTL_SECONDS)
                    return json.loads(data)
                return []
            except Exception as e:
                logger.error(f"خطأ أثناء قراءة الجلسة من Redis: {e}")
                return await self.local_store.get_history(session_id)

        return await self.local_store.get_history(session_id)

    async def save_turn(self, session_id: str, user_text: str, model_text: str) -> None:
        """
        حفظ رسالة العميل ورد المستشار في سجل الجلسة وتجديد وقت انتهاء الصلاحية
        """
        if not session_id:
            return

        max_turns = settings.MAX_SESSION_HISTORY

        if self.is_redis_active and self.redis_client:
            try:
                key = f"chat:session:{session_id}"
                history = await self.get_history(session_id)
                history.append({"role": "user", "text": user_text})
                history.append({"role": "model", "text": model_text})

                if len(history) > max_turns:
                    history = history[-max_turns:]

                await self.redis_client.setex(
                    name=key,
                    time=settings.SESSION_TTL_SECONDS,
                    value=json.dumps(history, ensure_ascii=False)
                )
                return
            except Exception as e:
                logger.error(f"خطأ أثناء حفظ الجلسة في Redis: {e}")

        # الحفظ في المخزن المحلي كبديل أو افتراضي
        await self.local_store.save_turn(
            session_id=session_id,
            user_text=user_text,
            model_text=model_text,
            max_turns=max_turns
        )

    async def clear_session(self, session_id: str) -> None:
        """
        مسح جلسة المحادثة بالكامل
        """
        if not session_id:
            return

        if self.is_redis_active and self.redis_client:
            try:
                await self.redis_client.delete(f"chat:session:{session_id}")
            except Exception as e:
                logger.error(f"خطأ أثناء مسح الجلسة من Redis: {e}")

        await self.local_store.clear_session(session_id)


# نسخة أحادية مركزية للاستخدام في جميع أنحاء النظام
session_manager = SessionManager()
