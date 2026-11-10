import sys
sys.stdout.reconfigure(encoding='utf-8')

import numpy as np
from app.services.embedding import embedding_service


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """
    حساب تشابه جيب التمام بين متجهين
    """
    a = np.array(vec_a)
    b = np.array(vec_b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def main():
    print("Generating embeddings using Google Gemini...\n")

    # نصوص تجريبية
    query = "أريد فندق هادئ ومريح للاستجمام والراحة"
    hotel_1 = "منتجع سياحي فاخر بعيد عن صخب المدينة ومناسب للاسترخاء"
    hotel_2 = "فندق في قلب المنطقة التجارية الصاخبة بالقرب من الأسواق والمحلات"
    unrelated = "ورشة لتصليح سيارات الدفع الرباعي وتغيير الزيوت"

    texts = [query, hotel_1, hotel_2, unrelated]
    vectors = embedding_service.get_embeddings_batch(texts)

    query_vec = vectors[0]
    hotel_1_vec = vectors[1]
    hotel_2_vec = vectors[2]
    unrelated_vec = vectors[3]

    sim_1 = cosine_similarity(query_vec, hotel_1_vec)
    sim_2 = cosine_similarity(query_vec, hotel_2_vec)
    sim_3 = cosine_similarity(query_vec, unrelated_vec)

    print(f"جملة بحث المستخدم: '{query}'\n")
    print(f"1. الفندق الأول (للاسترخاء والابتعاد عن الصخب):")
    print(f"   نسبة التطابق الذكي: {sim_1 * 100:.2f}%\n")

    print(f"2. الفندق الثاني (منطقة تجارية وصاخبة):")
    print(f"   نسبة التطابق الذكي: {sim_2 * 100:.2f}%\n")

    print(f"3. النص غير المرتبط نهائياً (ورشة سيارات):")
    print(f"   نسبة التطابق الذكي: {sim_3 * 100:.2f}%\n")


if __name__ == "__main__":
    main()
