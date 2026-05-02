# -*- coding: utf-8 -*-

CATEGORY_MAPPING = {
    # URL slugs từ vnexpress.vn
    "thoi-su": "Thời sự",
    "the-gioi": "Thế giới",
    "kinh-doanh": "Kinh tế",
    "kinh-te": "Kinh tế",
    "cong-nghe": "Công nghệ",
    "khoa-hoc-cong-nghe": "Công nghệ",
    "the-thao": "Thể thao",
    "giao-duc": "Giáo dục",
    "suc-khoe": "Sức khỏe",
    "van-hoa": "Văn hóa",
    "giai-tri": "Giải trí",
    "doi-song": "Đời sống",
    "du-lich": "Du lịch",
    "phap-luat": "Pháp luật",
    "oto-xe-may": "Ô tô & Xe máy",
    "bat-dong-san": "Kinh tế",
    "goc-nhin": "Thời sự",
    "spotlight": "Giải trí",
    "anh": "Khác",
    "infographics": "Khác",
    "y-kien": "Thời sự",
    "tam-su": "Đời sống",
    "thu-gian": "Đời sống",
    
    # URL slugs từ thanhnien.vn
    "xe": "Ô tô & Xe máy",
    "gioi-tre": "Giải trí",
    "ban-doc": "Khác",
    
    # URL slugs từ vietnamnet.vn
    "xe-co": "Ô tô & Xe máy",
    "giao-thong": "Ô tô & Xe máy",
    
    # URL slugs từ kenh14.vn
    "star": "Giải trí",
    "showbiz": "Giải trí",
    "cine": "Giải trí",
    "cinema": "Giải trí",
    "phim": "Giải trí",
    "phim-anh": "Giải trí",
    "music": "Giải trí",
    "am-nhac": "Giải trí",
    "tv-show": "Giải trí",
    "tv show": "Giải trí",
    "sao": "Giải trí",
    "khoai-moi": "Giải trí",
    "thoi-trang": "Đời sống",
    "thoi-su": "Thời sự",
    "the-gioi": "Thế giới",
    "kinh-te": "Kinh tế",
    "cong-nghe": "Công nghệ",
    "the-thao": "Thể thao",
    "giao-duc": "Giáo dục",
    "suc-khoe": "Sức khỏe",
    "van-hoa": "Văn hóa",
    "giai-tri": "Giải trí",
    "doi-song": "Đời sống",
    "du-lich": "Du lịch",
    "phap-luat": "Pháp luật",
    "xe-co": "Ô tô & Xe máy",
}


def normalize_category(raw_category):
    """
    Chuẩn hóa tên category từ các nguồn khác nhau thành tên chuẩn.
    
    Args:
        raw_category: String loại category từ URL hoặc breadcrumb
        
    Returns:
        String category chuẩn hóa. Nếu không tìm thấy thì trả về "Khác"
    """
    if not raw_category or not isinstance(raw_category, str):
        return "Khác"
    
    raw_category = raw_category.strip()
    
    # Bước 1: Exact match
    if raw_category in CATEGORY_MAPPING:
        return CATEGORY_MAPPING[raw_category]
    
    # Bước 2: Case-insensitive match
    for key, value in CATEGORY_MAPPING.items():
        if key.lower() == raw_category.lower():
            return value
    
    # Bước 3: Partial match - nếu category chứa key nào từ mapping
    raw_lower = raw_category.lower()
    for key, value in CATEGORY_MAPPING.items():
        if key.lower() in raw_lower:
            return value
    
    # Fallback: ép về nhãn chuẩn
    return "Khác"