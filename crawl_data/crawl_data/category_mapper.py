# -*- coding: utf-8 -*-
import re
import unicodedata


STANDARD_CATEGORIES = {
    "Thời sự",
    "Thế giới",
    "Kinh tế",
    "Công nghệ",
    "Thể thao",
    "Giáo dục",
    "Sức khỏe",
    "Văn hóa",
    "Giải trí",
    "Đời sống",
    "Du lịch",
    "Pháp luật",
    "Ô tô & Xe máy",
    "Khác",
}


CATEGORY_MAPPING = {
    # Thời sự
    "thoi-su": "Thời sự",
    "thời sự": "Thời sự",
    "xa-hoi": "Thời sự",
    "xã hội": "Thời sự",
    "chinh-tri": "Thời sự",
    "chính trị": "Thời sự",
    "goc-nhin": "Thời sự",
    "góc nhìn": "Thời sự",
    "y-kien": "Thời sự",
    "ý kiến": "Thời sự",
    "ban-doc": "Thời sự",
    "bạn đọc": "Thời sự",

    # Thế giới
    "the-gioi": "Thế giới",
    "thế giới": "Thế giới",
    "quoc-te": "Thế giới",
    "quốc tế": "Thế giới",

    # Kinh tế
    "kinh-te": "Kinh tế",
    "kinh tế": "Kinh tế",
    "kinh-doanh": "Kinh tế",
    "kinh doanh": "Kinh tế",
    "tai-chinh": "Kinh tế",
    "tài chính": "Kinh tế",
    "chung-khoan": "Kinh tế",
    "chứng khoán": "Kinh tế",
    "bat-dong-san": "Kinh tế",
    "bất động sản": "Kinh tế",
    "thi-truong": "Kinh tế",
    "thị trường": "Kinh tế",
    "doanh-nghiep": "Kinh tế",
    "doanh nghiệp": "Kinh tế",
    "ngan-hang": "Kinh tế",
    "ngân hàng": "Kinh tế",

    # Công nghệ
    "cong-nghe": "Công nghệ",
    "công nghệ": "Công nghệ",
    "khoa-hoc-cong-nghe": "Công nghệ",
    "khoa học công nghệ": "Công nghệ",
    "so-hoa": "Công nghệ",
    "số hóa": "Công nghệ",

    # Thể thao
    "the-thao": "Thể thao",
    "thể thao": "Thể thao",
    "bong-da": "Thể thao",
    "bóng đá": "Thể thao",
    "tennis": "Thể thao",
    "golf": "Thể thao",

    # Giáo dục
    "giao-duc": "Giáo dục",
    "giáo dục": "Giáo dục",
    "hoc-duong": "Giáo dục",
    "học đường": "Giáo dục",
    "tuyen-sinh": "Giáo dục",
    "tuyển sinh": "Giáo dục",
    "du-hoc": "Giáo dục",
    "du học": "Giáo dục",

    # Sức khỏe
    "suc-khoe": "Sức khỏe",
    "sức khỏe": "Sức khỏe",
    "y-te": "Sức khỏe",
    "y tế": "Sức khỏe",
    "dinh-duong": "Sức khỏe",
    "dinh dưỡng": "Sức khỏe",
    "lam-dep": "Sức khỏe",
    "làm đẹp": "Sức khỏe",
    "gioi-tinh": "Sức khỏe",
    "giới tính": "Sức khỏe",

    # Văn hóa
    "van-hoa": "Văn hóa",
    "văn hóa": "Văn hóa",
    "sach": "Văn hóa",
    "sách": "Văn hóa",
    "nghe-thuat": "Văn hóa",
    "nghệ thuật": "Văn hóa",

    # Giải trí
    "giai-tri": "Giải trí",
    "giải trí": "Giải trí",
    "sao": "Giải trí",
    "star": "Giải trí",
    "showbiz": "Giải trí",
    "cine": "Giải trí",
    "cinema": "Giải trí",
    "phim": "Giải trí",
    "phim-anh": "Giải trí",
    "phim ảnh": "Giải trí",
    "am-nhac": "Giải trí",
    "âm nhạc": "Giải trí",
    "music": "Giải trí",
    "tv-show": "Giải trí",
    "tv show": "Giải trí",
    "hoa-hau": "Giải trí",
    "hoa hậu": "Giải trí",
    "khoai-moi": "Giải trí",
    "spotlight": "Giải trí",

    # Đời sống
    "doi-song": "Đời sống",
    "đời sống": "Đời sống",
    "tam-su": "Đời sống",
    "tâm sự": "Đời sống",
    "thu-gian": "Đời sống",
    "thư giãn": "Đời sống",
    "gia-dinh": "Đời sống",
    "gia đình": "Đời sống",
    "am-thuc": "Đời sống",
    "ẩm thực": "Đời sống",
    "mon-ngon": "Đời sống",
    "món ngon": "Đời sống",
    "thoi-trang": "Đời sống",
    "thời trang": "Đời sống",

    # Du lịch
    "du-lich": "Du lịch",
    "du lịch": "Du lịch",
    "diem-den": "Du lịch",
    "điểm đến": "Du lịch",
    "tour": "Du lịch",
    "khach-san": "Du lịch",
    "khách sạn": "Du lịch",

    # Pháp luật
    "phap-luat": "Pháp luật",
    "pháp luật": "Pháp luật",
    "an-ninh": "Pháp luật",
    "an ninh": "Pháp luật",
    "hinh-su": "Pháp luật",
    "hình sự": "Pháp luật",
    "toa-an": "Pháp luật",
    "tòa án": "Pháp luật",

    # Ô tô & Xe máy
    "oto-xe-may": "Ô tô & Xe máy",
    "o-to-xe-may": "Ô tô & Xe máy",
    "xe": "Ô tô & Xe máy",
    "xe-co": "Ô tô & Xe máy",
    "xe cộ": "Ô tô & Xe máy",
    "giao-thong": "Ô tô & Xe máy",
    "giao thông": "Ô tô & Xe máy",
    "oto": "Ô tô & Xe máy",
    "ô tô": "Ô tô & Xe máy",
    "xe-may": "Ô tô & Xe máy",
    "xe máy": "Ô tô & Xe máy",

    # Không rõ
    "anh": "Khác",
    "ảnh": "Khác",
    "infographics": "Khác",
    "video": "Khác",
}


KEYWORD_RULES = [
    ("Sức khỏe", [
        "sức khỏe", "ung thư", "bệnh", "bác sĩ", "dinh dưỡng", "giảm cân",
        "sinh sản", "tinh hoàn", "cổ tử cung", "buồng trứng", "gan", "thận",
        "huyết áp", "tiểu đường", "detox", "phụ nữ", "nam giới", "ăn uống",
        "béo phì", "giảm mỡ", "hệ sinh sản", "cân nặng"
    ]),
    ("Pháp luật", [
        "khởi tố", "bắt giữ", "công an", "tòa án", "xét xử", "truy tố",
        "lừa đảo", "ma túy", "án tù", "bị bắt"
    ]),
    ("Giáo dục", [
        "học sinh", "sinh viên", "đại học", "tuyển sinh", "thi tốt nghiệp",
        "điểm thi", "du học", "trường học"
    ]),
    ("Kinh tế", [
        "giá vàng", "chứng khoán", "vn-index", "doanh nghiệp", "bất động sản",
        "lãi suất", "ngân hàng", "tỷ giá", "thị trường"
    ]),
    ("Công nghệ", [
        "trí tuệ nhân tạo", "chatgpt", "iphone", "samsung", "robot",
        "công nghệ", "ứng dụng", "mạng xã hội"
    ]),
    ("Thể thao", [
        "bóng đá", "v-league", "ngoại hạng anh", "world cup", "ronaldo",
        "messi", "hlv", "cầu thủ", "tennis"
    ]),
    ("Giải trí", [
        "ngọc trinh", "hoa hậu", "ca sĩ", "diễn viên", "showbiz", "sao việt",
        "đám cưới", "chú rể", "cô dâu", "minh hoàng", "phương nhi",
        "phim", "concert", "âm nhạc", "người đẹp", "hậu công khai", "mxh"
    ]),
    ("Đời sống", [
        "gia đình", "món ăn", "nấu ăn", "mẹo", "rau sạch", "nhà cửa",
        "tình yêu", "hôn nhân", "thời trang"
    ]),
    ("Thế giới", [
        "ukraine", "nga", "mỹ", "trung quốc", "israel", "gaza", "châu âu",
        "liên hợp quốc", "nato", "tổng thống"
    ]),
    ("Ô tô & Xe máy", [
        "ô tô", "xe máy", "vinfast", "toyota", "honda", "mercedes",
        "giao thông", "đăng kiểm"
    ]),
    ("Du lịch", [
        "du lịch", "du khách", "khách sạn", "tour", "vé máy bay", "điểm đến"
    ]),
    ("Thời sự", [
        "chính phủ", "quốc hội", "ubnd", "hà nội", "tp.hcm", "bộ trưởng",
        "thủ tướng", "dự án", "quy hoạch"
    ]),
]


def remove_accents(text: str) -> str:
    text = unicodedata.normalize("NFD", str(text or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "D")
    return text


def clean_text(text: str) -> str:
    text = str(text or "").strip().lower()
    text = text.replace("_", "-")
    text = re.sub(r"\s+", " ", text)
    text = text.replace(".htm", "").replace(".html", "").replace(".epi", "").replace(".chn", "")
    text = text.strip("/ ")
    return text


def normalize_key(text: str) -> str:
    text = clean_text(text)
    text = remove_accents(text)
    text = re.sub(r"[^a-z0-9\s\-&]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


NORMALIZED_MAPPING = {
    normalize_key(k): v for k, v in CATEGORY_MAPPING.items()
}


def phrase_match(text: str, keyword: str) -> bool:
    """
    Match cụm từ an toàn, tránh substring sai.
    Ví dụ không để 'du' match nhầm trong từ khác.
    """
    if not text or not keyword:
        return False

    keyword = re.escape(keyword.strip())
    pattern = rf"(?<!\w){keyword}(?!\w)"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def normalize_category(raw_category):
    if not raw_category or not isinstance(raw_category, str):
        return "Khác"

    raw = clean_text(raw_category)

    if raw in STANDARD_CATEGORIES:
        return raw

    raw_norm = normalize_key(raw)

    # Chỉ exact match, không partial match để tránh sai kiểu du/du lịch.
    if raw in CATEGORY_MAPPING:
        return CATEGORY_MAPPING[raw]

    if raw_norm in NORMALIZED_MAPPING:
        return NORMALIZED_MAPPING[raw_norm]

    return "Khác"


def infer_category_from_text(article: dict) -> str:
    """
    Ưu tiên:
    1. Category crawler đã lấy được và normalize được.
    2. URL slug.
    3. Keyword trong title/description/content/tags.
    """

    raw = article.get("category") or ""
    normalized = normalize_category(raw)

    if normalized != "Khác":
        return normalized

    url = str(article.get("url") or "")
    url_parts = re.split(r"[/?#&=._\-]+", remove_accents(url.lower()))

    for part in url_parts:
        cat = normalize_category(part)
        if cat != "Khác":
            return cat

    text = " ".join([
        str(article.get("title") or ""),
        str(article.get("description") or ""),
        str(article.get("content") or ""),
        str(article.get("tags") or ""),
    ]).lower()

    text_no_accents = remove_accents(text)

    for category, keywords in KEYWORD_RULES:
        for keyword in keywords:
            k_raw = keyword.lower()
            k_norm = remove_accents(k_raw)

            if phrase_match(text, k_raw) or phrase_match(text_no_accents, k_norm):
                return category

    return "Khác"