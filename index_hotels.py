import asyncio
import sys
sys.stdout.reconfigure(encoding='utf-8')

from app.db.session import async_session_factory, async_engine
from app.services.enrichment import enrichment_service
from app.services.embedding import embedding_service
from app.services.vector_db import vector_db_service


async def main():
    print("=== بدء خط معالجة وفهرسة فنادق تطبيق مزاجي بالذكاء الاصطناعي ===\n")

    # 1. استخراج الفنادق النشطة وإثراء نصوصها
    async with async_session_factory() as session:
        print("1. جاري استخراج وتجميع بيانات الفنادق من قاعدة البيانات...")
        hotels = await enrichment_service.fetch_all_active_properties(session)
        print(f"   تم بنجاح تجهيز هوية {len(hotels)} فندقاً نشطاً.")

    await async_engine.dispose()

    # 2. توليد التضمينات الرقمية عبر نموذج جوجل
    print("\n2. جاري توليد المتجهات الرياضية عبر نموذج جوجل (3072 بعداً)...")
    texts = [h["rich_document"] for h in hotels]
    
    # تقسيم النصوص إلى دفعات لتسريع الإرسال
    batch_size = 20
    all_vectors = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        print(f"   معالجة الدفعة من {i + 1} إلى {min(i + batch_size, len(texts))}...")
        vectors = embedding_service.get_embeddings_batch(batch)
        all_vectors.extend(vectors)

    print(f"   تم توليد متجهات جميع الفنادق ({len(all_vectors)} متجهاً).")

    # 3. حفظ المتجهات والبيانات في قاعدة بيانات المتجهات كيو-درانت
    print("\n3. جاري حفظ المتجهات والبيانات في قاعدة كيو-درانت...")
    vector_db_service.upsert_hotels(hotels, all_vectors)
    print("   تم الحفظ والفهرسة بنجاح تام داخل مجلد: qdrant_storage/")

    # 4. تجربة بحث ذكي حي للتحقق
    test_query = "أشتي فندق هادئ ومريح فيه جاكوزي وخدمات راقية في صنعاء"
    print(f"\n4. تجربة استعلام بحث حي ومباشر:")
    print(f"   نص البحث: '{test_query}'")

    # توليد متجه لجملة البحث
    query_vector = embedding_service.get_embedding(test_query)

    # البحث في كيو-درانت
    matches = vector_db_service.search(query_vector=query_vector, limit=3)

    print(f"\nأفضل {len(matches)} نتائج مطابقة لطلب المستخدم:")
    for rank, m in enumerate(matches, 1):
        print(f"\n[المركز {rank}] {m['name_ar']} (نسبة التطابق: {m['similarity_score'] * 100:.2f}%)")
        print(f"  المدينة: {m['city_name']} {m['district_name']}")
        print(f"  الأسعار: من {m['min_price']:,.0f} إلى {m['max_price']:,.0f}")
        print(f"  المرافق: {', '.join(m['amenities']) if m['amenities'] else 'غير محدد'}")


if __name__ == "__main__":
    asyncio.run(main())
