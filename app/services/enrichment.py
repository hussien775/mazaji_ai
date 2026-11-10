from typing import List, Dict, Any, Optional
from collections import defaultdict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


class PropertyEnrichmentService:
    """
    خدمة استخراج وتجميع هوية الفنادق ووحداتها وخدماتها من مختلف الجداول
    لبناء وثيقة نصية متكاملة للذكاء الاصطناعي وهيكلة البيانات لمحرك البحث
    """

    async def fetch_all_active_properties(self, session: AsyncSession) -> List[Dict[str, Any]]:
        """
        استخراج جميع العقارات النشطة مع مدنها وأحيائها، وربطها بوحداتها ومرافقها
        عبر استعلامات مجمعة عالية الأداء لتفادي مشكلة الاستعلام المتكرر (N+1 Problem).
        """
        # 1. جلب العقارات النشطة الأساسية
        prop_query = text("""
            SELECT 
                p.id, 
                p.name_ar, 
                p.description_ar,
                p.description,
                COALESCE(pt.name_ar, 'مكان إقامة') AS property_type,
                pa.city_id,
                COALESCE(c.name_ar, 'غير محدد') AS city_name,
                pa.district_id,
                COALESCE(d.name_ar, '') AS district_name,
                COALESCE(MIN(u.price_per_night), 0) AS min_price,
                COALESCE(MAX(u.price_per_night), 0) AS max_price,
                COUNT(u.id) AS total_units
            FROM properties p
            LEFT JOIN property_types pt ON p.property_type_id = pt.id
            LEFT JOIN property_addresses pa ON pa.property_id = p.id
            LEFT JOIN cities c ON pa.city_id = c.id
            LEFT JOIN districts d ON pa.district_id = d.id
            LEFT JOIN units u ON u.property_id = p.id
            WHERE p.status = 1
            GROUP BY p.id, p.name_ar, p.description_ar, p.description, pt.name_ar, pa.city_id, c.name_ar, pa.district_id, d.name_ar
            ORDER BY p.id ASC
        """)
        
        result = await session.execute(prop_query)
        properties = [dict(row._mapping) for row in result.fetchall()]
        prop_ids = [p["id"] for p in properties]

        if not prop_ids:
            return []

        # 2. جلب جميع المرافق والخدمات دفعة واحدة
        amenities_query = text("""
            SELECT aa.assignable_id AS property_id, a.name_ar 
            FROM amenities a
            JOIN amenity_assignments aa ON aa.amenity_id = a.id
        """)
        amenities_res = await session.execute(amenities_query)
        amenities_by_prop = defaultdict(list)
        for row in amenities_res.fetchall():
            if row.name_ar:
                amenities_by_prop[row.property_id].append(row.name_ar.strip())

        # 3. جلب جميع الوحدات والغرف دفعة واحدة مع أنواعها وسعتها وأسعارها
        units_query = text("""
            SELECT 
                u.id AS unit_id,
                u.property_id,
                u.name AS unit_name,
                COALESCE(ut.name_ar, 'وحدة إقامة') AS unit_type,
                u.price_per_night,
                u.max_guests,
                u.single_beds,
                u.double_beds,
                u.is_available,
                u.status
            FROM units u
            LEFT JOIN unit_types ut ON u.unit_type_id = ut.id
            WHERE u.status = 1
            ORDER BY u.price_per_night ASC
        """)
        units_res = await session.execute(units_query)
        units_by_prop = defaultdict(list)
        for row in units_res.fetchall():
            units_by_prop[row.property_id].append({
                "unit_id": int(row.unit_id),
                "unit_name": str(row.unit_name or ""),
                "unit_type": str(row.unit_type or ""),
                "price_per_night": float(row.price_per_night or 0),
                "max_guests": int(row.max_guests or 1),
                "single_beds": int(row.single_beds or 0),
                "double_beds": int(row.double_beds or 0),
                "is_available": bool(row.is_available)
            })

        # 4. ربط البيانات بكل فندق وبناء المستند النصي المتكامل للذكاء الاصطناعي
        for prop in properties:
            p_id = prop["id"]
            prop["amenities"] = list(set(amenities_by_prop.get(p_id, [])))
            prop_units = units_by_prop.get(p_id, [])
            prop["units"] = prop_units
            prop["unit_types"] = list(set(u["unit_type"] for u in prop_units))

            # بناء الوثيقة الدلالية الغنية
            prop["rich_document"] = self.build_rich_document(prop)

        return properties

    def build_rich_document(self, prop: Dict[str, Any]) -> str:
        """
        دمج بيانات العقار ووحداته التفصيلية ومرافقه في فقرة متكاملة للذكاء الاصطناعي
        """
        parts = []

        # 1. الاسم ونوع العقار
        name = prop.get("name_ar", "فندق")
        prop_type = prop.get("property_type", "فندق")
        parts.append(f"{name}، نوع مكان الإقامة: {prop_type}.")

        # 2. الموقع والمدينة والحي
        city = prop.get("city_name", "")
        district = prop.get("district_name", "")
        if city:
            location_str = f"يقع في مدينة {city}"
            if district:
                location_str += f" - حي {district}"
            parts.append(f"{location_str}.")

        # 3. تفاصيل الوحدات والغرف المتاحة (الأنواع، السعة، ونطاق الأسعار)
        units = prop.get("units", [])
        if units:
            units_by_type = defaultdict(list)
            for u in units:
                units_by_type[u["unit_type"]].append(u)

            unit_summaries = []
            for u_type, u_list in units_by_type.items():
                min_u_price = min(u["price_per_night"] for u in u_list)
                max_u_price = max(u["price_per_night"] for u in u_list)
                max_capacity = max(u["max_guests"] for u in u_list)

                if min_u_price == max_u_price:
                    price_str = f"بسعر {min_u_price:,.0f} ريال"
                else:
                    price_str = f"بأسعار تتراوح بين {min_u_price:,.0f} و {max_u_price:,.0f} ريال"

                unit_summaries.append(f"{u_type} (تتسع حتى {max_capacity} أشخاص، {price_str})")

            parts.append(f"يوفر خيارات الإقامة والوحدات التالية: {'، '.join(unit_summaries)}.")
        else:
            min_p = float(prop.get("min_price", 0))
            max_p = float(prop.get("max_price", 0))
            if min_p > 0:
                parts.append(f"تتراوح أسعار الإقامة بين {min_p:,.0f} و {max_p:,.0f} ريال.")

        # 4. المرافق والخدمات المتاحة
        amenities = prop.get("amenities", [])
        if amenities:
            amenities_str = "، ".join(amenities[:15])  # أهم 15 ميزة
            parts.append(f"يحتوي المكان على خدمات وميزات تتضمن: {amenities_str}.")

        # 5. الوصف المسجل
        desc = prop.get("description_ar") or prop.get("description")
        if desc:
            clean_desc = desc.replace("\r", " ").replace("\n", " ").strip()
            parts.append(f"تفاصيل إضافية: {clean_desc}")

        return " ".join(parts)


enrichment_service = PropertyEnrichmentService()
