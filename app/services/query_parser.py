import re
import difflib
from typing import Optional, Dict, Any, List


class QueryParserService:
    """
    خدمة الفهم الطبيعي لنصوص البحث واستخراج الكيانات مع معالجة الأخطاء الإملائية الشائعة
    وتطبيع الحروف العربية واللهجة اليمنية (الهمزات، التاء المربوطة، أل التعريف، حروف الجر المتصلة)،
    واستخراج المحافظات، أنواع الوحدات (طيرمانة، غرفة، جناح...)، سعة النزلاء والأسرة، والأسعار.
    """

    # قاموس المحافظات والمدن اليمنية مع مرادفاتها وأحيائها الشهيرة
    CITIES_MAP = {
        "صنعاء": ["صنعاء", "صنعا", "امانة العاصمة", "امانه العاصمه", "حدة", "حده", "السبعين", "التحرير"],
        "عدن": ["عدن", "خور مكسر", "كريتر", "المعلا", "التواهي", "الشيخ عثمان", "المنصورة", "البريقة"],
        "تعز": ["تعز", "الحوبان", "صالة", "المظفر", "القاهرة"],
        "الحديدة": ["الحديدة", "الحديده", "حديدة", "حديده", "زبيد", "بيت الفقيه", "باجل"],
        "إب": ["إب", "اب", "جبلة", "جبله", "القفر", "يريم", "العدين"],
        "حضرموت": ["حضرموت", "المكلا", "المكلى", "سيئون", "تريم", "الشحر", "دوعن", "شحن"],
        "مأرب": ["مأرب", "مارب", "صرواح", "الوادي"],
        "ذمار": ["ذمار", "معبر", "ضوران", "عنس"],
        "البيضاء": ["البيضاء", "البيضا", "رداع", "مكيراس"],
        "شبوة": ["شبوة", "شبوه", "عتق", "بيحان", "بلحاف"],
        "المهرة": ["المهرة", "المهره", "الغيضة", "الغيضه", "حوف"],
        "سقطرى": ["سقطرى", "سقطري", "سقطرا", "حديبو", "قلنسية"],
        "لحج": ["لحج", "الحوطة", "الحوطه", "طور الباحة", "يافع"],
        "أبين": ["أبين", "ابين", "زنجبار", "جعار", "خنفر", "لودر"],
        "صعدة": ["صعدة", "صعده"],
        "حجة": ["حجة", "حجه", "حرض", "ميدي"],
        "عمران": ["عمران", "خمر", "ريدة"],
        "الضالع": ["الضالع", "دمت", "قعطبة"],
        "المحويت": ["المحويت", "شبام كوكبان"],
        "ريمة": ["ريمة", "ريمه", "الجبين"],
        "الجوف": ["الجوف", "الحزم"]
    }

    # قاموس أنواع الوحدات والغرف مع مرادفاتها وصيغ الجمع
    UNIT_TYPES_MAP = {
        "طيرمانة": ["طيرمانة", "طيرمانه", "طيرمانات", "طيرمان"],
        "غرفة": ["غرفة", "غرفه", "غرف", "غرفة عائلية", "غرفة مفردة", "غرفة مزدوجة", "غرفة عرسان"],
        "جناح": ["جناح", "اجنحة", "أجنحة", "جناح ملكي", "جناح صغير", "جناح رئاسي", "جناح عائلي", "اجنحه"],
        "شقة": ["شقة", "شقه", "شقق", "شقة متوسطة", "شقة كبيرة", "شقق مفروشة"],
        "شاليه": ["شاليه", "شالية", "شاليهات", "شاليه كبير", "شاليه وسط"],
        "مجلس": ["مجلس", "مجالس", "ديوان"],
        "قاعة": ["قاعة", "قاعه", "صالة", "صاله", "قاعات"],
        "خيمة": ["خيمة", "خيمه", "خيام"],
        "استوديو": ["استوديو", "استديو"],
        "بنت هاوس": ["بنت هاوس", "بنتهاوس"],
        "بيت شعبي": ["بيت شعبي", "فيلا"]
    }

    # قاموس تحويل الأعداد المكتوبة نصاً إلى أرقام صحيحة لسعة النزلاء
    ARABIC_NUMBER_WORDS = {
        "واحد": 1,
        "شخص": 1,
        "شخصين": 2,
        "شخصان": 2,
        "سريرين": 2,
        "سريران": 2,
        "اثنين": 2,
        "اثنان": 2,
        "ثلاثة": 3,
        "ثلاثه": 3,
        "ثلاث": 3,
        "اربعة": 4,
        "اربعه": 4,
        "اربع": 4,
        "خمسة": 5,
        "خمسه": 5,
        "خمس": 5,
        "ستة": 6,
        "سته": 6,
        "ست": 6,
        "سبعة": 7,
        "سبعه": 7,
        "سبع": 7,
        "ثمانية": 8,
        "ثمانيه": 8,
        "ثمان": 8,
        "ثماني": 8,
        "تسعة": 9,
        "تسعه": 9,
        "تسع": 9,
        "عشرة": 10,
        "عشره": 10,
        "عشر": 10,
        "احد عشر": 11,
        "اثنا عشر": 12,
        "عشرين": 20,
        "ثلاثين": 30
    }

    def parse_query(self, text: str) -> Dict[str, Any]:
        """
        تحليل نص البحث واستخراج:
        1. المحافظة بدقة (حتى مع الأخطاء الإملائية واللهجات)
        2. نوع الوحدة (طيرمانة، غرفة، جناح...)
        3. عدد الأشخاص أو الأسرة المطلوبة
        4. الحد الأقصى للسعر
        """
        detected_city = self._extract_city_robust(text)
        detected_unit_type = self._extract_unit_type(text)
        detected_guests = self._extract_guests_count(text)
        detected_max_price = self._extract_max_price(text)

        applied_filters = []
        if detected_city:
            applied_filters.append(f"تصفية حصرية على محافظة: {detected_city}")
        if detected_unit_type:
            applied_filters.append(f"نوع الوحدة المطلوب: {detected_unit_type}")
        if detected_guests:
            applied_filters.append(f"سعة الأشخاص / الأسرة: {detected_guests} على الأقل")
        if detected_max_price:
            applied_filters.append(f"الحد الأقصى للسعر: {detected_max_price:,.0f} ريال")

        return {
            "original_query": text,
            "detected_city": detected_city,
            "detected_unit_type": detected_unit_type,
            "detected_guests": detected_guests,
            "detected_max_price": detected_max_price,
            "applied_filters": applied_filters
        }

    @staticmethod
    def normalize_arabic(word: str) -> str:
        """
        تطبيع الحروف العربية وتوحيد الهمزات والتاء المربوطة وإزالة التشكيل
        """
        if not word:
            return ""
        # 1. إزالة التشكيل والتنوين والمد
        word = re.sub(r'[\u064B-\u0652\u0670\u0640]', '', word)
        # 2. توحيد الهمزات بأنواعها إلى ألف مجردة
        word = re.sub(r'[إأآٱ]', 'ا', word)
        # 3. توحيد التاء المربوطة إلى هاء
        word = re.sub(r'ة', 'ه', word)
        # 4. توحيد الألف المقصورة والياء المتطرفة (ى -> ي)
        word = re.sub(r'ى', 'ي', word)
        # 5. معالجة الهمزة المتطرفة بعد الألف مثل (صنعاء -> صنعا، البيضاء -> البيضا)
        word = re.sub(r'اء\b', 'ا', word)
        return word.strip().lower()

    def _extract_city_robust(self, text: str) -> Optional[str]:
        """
        استخراج المحافظة حتى في حال وجود أخطاء إملائية أو حروف جر متصلة أو مطابقة تقريبية
        """
        norm_text = self.normalize_arabic(text)
        words = re.findall(r'\b\w+\b', norm_text)

        for official_city, aliases in self.CITIES_MAP.items():
            norm_aliases = [self.normalize_arabic(a) for a in aliases]

            for w in words:
                # تجريد حروف الجر والعطف المتصلة في البداية (بـ، فـ، وـ، لـ) إذا كانت الكلمة أطول من 3 أحرف
                clean_w = re.sub(r'^[بوفل]', '', w) if len(w) > 3 else w

                # 1. فحص التطابق التام بعد التطبيع
                if w in norm_aliases or clean_w in norm_aliases:
                    return official_city

                # 2. فحص المطابقة التقريبية للأخطاء الطباعية (Fuzzy Matching)
                for a in norm_aliases:
                    if len(a) >= 3:
                        if difflib.SequenceMatcher(None, clean_w, a).ratio() >= 0.85:
                            return official_city

        return None

    def _extract_unit_type(self, text: str) -> Optional[str]:
        """
        استخراج نوع الوحدة المطلوبة (طيرمانة، غرفة، جناح، شقة، شاليه...) مع دعم أل التعريف
        """
        norm_text = self.normalize_arabic(text)
        for canonical, aliases in self.UNIT_TYPES_MAP.items():
            for alias in aliases:
                norm_alias = self.normalize_arabic(alias)
                # نمط يدعم وجود (الـ) التعريف الاختيارية
                pattern = r'\b(?:ال)?' + re.escape(norm_alias) + r'\b'
                if re.search(pattern, norm_text):
                    return canonical
        return None

    def _extract_guests_count(self, text: str) -> Optional[int]:
        """
        استخراج عدد النزلاء أو الأسرة من النصوص الشائعة واللهجة اليمنية:
        (لسبعة أشخاص، لشخصين، سريرين، 4 أفراد، 2 سرير، لـ 5 اشخاص)
        """
        norm_text = self.normalize_arabic(text)

        # 1. فحص الأسرة المحددة (مثل: سريرين، سرير واحد، 3 أسرة)
        if re.search(r'\b(سريرين|سريران)\b', norm_text):
            return 2
        if re.search(r'\b(سرير واحد|سرير فردي)\b', norm_text):
            return 1
        m_beds = re.search(r'(\d{1,2})\s*(?:اسرة|أسرة|سراير|سرير)\b', norm_text)
        if m_beds:
            return int(m_beds.group(1))

        # 2. فحص الأعداد المكتوبة نصاً (مثل: لسبعة أشخاص، لشخصين، أربعة أشخاص)
        m_words = re.search(
            r'\b(?:لـ?|ل)?(واحد|شخصين|شخصان|اثنين|اثنان|ثلاثة|ثلاثه|ثلاث|اربعة|اربعه|اربع|خمسة|خمسه|خمس|ستة|سته|ست|سبعة|سبعه|سبع|ثمانية|ثمانيه|ثمان|تسعة|تسعه|تسع|عشرة|عشره|عشر)\s*(?:اشخاص|أشخاص|شخص|انفار|نفر|افراد|أفراد|نزلاء|نزيل)?\b',
            norm_text
        )
        if m_words:
            word = m_words.group(1)
            if word in self.ARABIC_NUMBER_WORDS:
                return self.ARABIC_NUMBER_WORDS[word]

        # 3. فحص الأرقام المباشرة المرفقة بكلمات الأشخاص (مثل: 7 أشخاص، لـ 5 اشخاص، 3 نزلاء)
        m_digits = re.search(
            r'(?:لـ?|ل|سعة|حجم|تسع|تكفي)?\s*(\d{1,2})\s*(?:اشخاص|أشخاص|شخص|نفر|انفار|افراد|أفراد|نزلاء|نزيل)',
            text
        )
        if m_digits:
            return int(m_digits.group(1))

        # 4. فحص صيغة لـ مع رقم مباشر (مثل: لـ 7 أو لـ8)
        m_prefixed_num = re.search(r'\bلـ?\s*(\d{1,2})\b', text)
        if m_prefixed_num:
            return int(m_prefixed_num.group(1))

        return None

    def _extract_max_price(self, text: str) -> Optional[float]:
        """
        استخراج ميزانية السعر من الصيغ الفصحى والعامية اليمنية:
        (ماتتجاوزش 20000، ما تتعداش 15 الف، أقل من 20 ألف، تحت 30000، بسعر 10000، ب 5000)
        """
        norm_text = self.normalize_arabic(text)

        # 1. نمط الأرقام مع كلمة (ألف / الف / k / K)
        pattern_thousands = r"(?:بـ?|ب|بسعر|سعر|ميزانية|حدود|بحدود|تحت|أقل من|اقل من|لا يتجاوز|ما يتعدى|ماتتجاوزش|ما تتجاوزش|مايتعداش|ما يتعداش|مايزيدش|ما يزيدش)?\s*(\d+(?:\.\d+)?)\s*(?:ألف|الف|k|K)\b"
        match_thousands = re.search(pattern_thousands, text)
        if match_thousands:
            val = float(match_thousands.group(1))
            return val * 1000

        # 2. نمط الأرقام المسبوقة بمؤشرات السعر واللهجة اليمنية
        pattern_exact = r"(?:بـ?|ب|بسعر|سعر|ميزانية|حدود|بحدود|تحت|أقل من|اقل من|لا يتجاوز|ما يتعدى|ماتتجاوزش|ما تتجاوزش|مايتعداش|ما يتعداش|مايزيدش|ما يزيدش)\s*(\d{3,7})\b"
        match_exact = re.search(pattern_exact, norm_text)
        if match_exact:
            return float(match_exact.group(1))

        # 3. نمط الأرقام المتبوعة بكلمة ريال
        pattern_rial = r"(\d{3,7})\s*(?:ريال|ر\.ي)\b"
        match_rial = re.search(pattern_rial, text)
        if match_rial:
            return float(match_rial.group(1))

        return None


query_parser = QueryParserService()
