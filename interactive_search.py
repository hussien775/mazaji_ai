import sys
import os

# ضبط ترميز النصوص العربية في طرفية ويندوز
sys.stdout.reconfigure(encoding='utf-8')

from app.services.embedding import embedding_service
from app.services.vector_db import vector_db_service


def run_interactive_search():
    print("=" * 65)
    print("    مرحباً بك في نظام البحث الذكي لتطبيق مزاجي (تجربة حية)    ")
    print("=" * 65)
    print("اكتب أي جملة بحث باللهجة العامية أو الفصحى (أو اكتب 'خروج' للإنهاء):\n")

    while True:
        try:
            query = input("\n🔍 أدخل نص البحث: ").strip()
            
            if not query:
                continue

            if query.lower() in ["خروج", "exit", "quit", "q"]:
                print("\nشكراً لك، تم إنهاء جلسة البحث التجريبية.")
                break

            print("\n⏳ جاري تحليل المعنى والبحث في قاعدة المتجهات...")
            
            # 1. توليد المتجه الدلالي للبحث
            query_vector = embedding_service.get_embedding(query)

            # 2. البحث في قاعدة المتجهات كيو-درانت
            results = vector_db_service.search(query_vector=query_vector, limit=3)

            if not results:
                print("❌ لم يتم العثور على فنادق مطابقة.")
                continue

            print(f"\n🎯 أفضل {len(results)} نتائج مطابقة لطلبك:")
            print("-" * 65)

            for rank, r in enumerate(results, 1):
                score_pct = r['similarity_score'] * 100
                print(f"[{rank}] {r['name_ar']}  |  نسبة التطابق الذكي: {score_pct:.2f}%")
                print(f"    📍 الموقع: {r['city_name']} {r['district_name']}  |  نوع العقار: {r['property_type']}")
                print(f"    💰 نطاق السعر: من {r['min_price']:,.0f} إلى {r['max_price']:,.0f} ريال")
                
                amenities = r.get('amenities', [])
                if amenities:
                    print(f"    ✨ المرافق الفعلية: {', '.join(amenities)}")
                
                doc = r.get('rich_document', '')
                if doc:
                    snippet = doc[:120].replace('\n', ' ')
                    print(f"    📝 الهوية الدلالية: {snippet}...")
                print("-" * 65)

        except KeyboardInterrupt:
            print("\nتم إنهاء البحث.")
            break
        except Exception as e:
            print(f"\n⚠️ حدث خطأ أثناء البحث: {e}")


if __name__ == "__main__":
    run_interactive_search()
