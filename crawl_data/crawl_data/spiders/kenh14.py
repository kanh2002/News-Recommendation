# -*- coding: utf-8 -*-
import json
import re
from urllib.parse import urlsplit
import scrapy
from crawl_data.category_mapper import normalize_category


class Kenh14Spider(scrapy.Spider):
    name = "kenh14"
    allowed_domains = ["kenh14.vn"]

    # Kenh14 focus trên sao, giải trí, đời sống
    start_urls = [
        "https://kenh14.vn/sao.html",
        "https://kenh14.vn/giai-tri.html",
        "https://kenh14.vn/doi-song.html",
        "https://kenh14.vn/the-gioi.html",
        "https://kenh14.vn/thoi-trang.html",
        "https://kenh14.vn/khoai-moi.html",
        "https://kenh14.vn/thoi-su.html",
        "https://kenh14.vn/goc-nhin.html",
        "https://kenh14.vn/suc-khoe.html",
        "https://kenh14.vn/the-thao.html",
        "https://kenh14.vn/du-lich.html",
        "https://kenh14.vn/van-hoa.html",
        "https://kenh14.vn/cong-nghe.html",
    ]

    custom_settings = {
        "DEPTH_LIMIT": 150,
        "DOWNLOAD_DELAY": 0.5,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
    }

    article_pattern = re.compile(r"-[0-9]{10,}\.chn(?:\?|$)")
    canonical_categories = {
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
    }

    def start_requests(self):
        """Extract category từ URL và pass qua meta dict"""
        for url in self.start_urls:
            # "https://kenh14.vn/sao.html" -> "sao"
            category = url.split("/")[-1].replace(".html", "").replace(".chn", "")
            yield scrapy.Request(url, meta={"category": category})

    def parse(self, response):
        """Extract article links từ category page"""
        category = response.meta.get("category", "")
        path_slug = response.url.split("/")[-1].replace(".html", "").replace(".chn", "")
        if path_slug:
            category = path_slug
        
        # Selectors cho article links - multiple fallbacks
        article_links = response.css(
            "h2 a::attr(href), "
            "h3 a::attr(href), "
            "h4 a::attr(href), "
            "article a::attr(href), "
            "a.title-news::attr(href), "
            "a.article-title::attr(href), "
            "div.item-list a::attr(href)"
        ).getall()
        
        for link in article_links:
            if not link:
                continue
            link = link.strip()
            if not link:
                continue

            # Kenh14 article URLs usually end with "-<long_id>.chn"
            if self.article_pattern.search(link):
                yield response.follow(link, self.parse_article, meta={"category": category})

        # Follow all listing/pagination links to keep exploring category pages.
        all_links = response.css("a::attr(href)").getall()
        for link in all_links:
            if not link:
                continue
            link = link.strip()
            if not link:
                continue

            if self.article_pattern.search(link):
                continue

            if self._should_follow_listing_link(link):
                yield response.follow(link, self.parse, meta={"category": category})

    def parse_article(self, response):
        """Extract article content"""
        category = self._resolve_category(response)
        
        # Title - multiple fallbacks
        title = (
            response.css("h1.kbwc-title::text").get() or
            response.css("h1::text").get() or
            response.css("h1.title::text").get() or
            response.css("meta[property='og:title']::attr(content)").get() or
            ""
        )
        
        # Description - ưu tiên sapo thực tế, rồi tới metadata
        description_candidates = [
            response.css("h2.knc-sapo *::text, h2.knc-sapo::text").getall(),
            response.css("p.summary *::text, p.summary::text, p.description *::text, p.description::text, p.sapo *::text, p.sapo::text").getall(),
            [response.css("meta[property='og:description']::attr(content)").get()],
            [response.css("meta[name='description']::attr(content)").get()],
            [response.css("meta[name='twitter:description']::attr(content)").get()],
            [self._extract_jsonld_value(response, "description")],
        ]
        description = self._pick_first_meaningful_text(description_candidates)
        
        # Date - multiple patterns
        date = (
            response.css("time::attr(datetime)").get() or
            response.css("span.time::text, span.date::text").get() or
            response.css("meta[property='article:published_time']::attr(content)").get() or
            ""
        )
        
        # Author
        author = (
            response.css(".kbwcm-author::text").get() or
            response.css("meta[property='article:author']::attr(content)").get() or
            self._extract_jsonld_author(response) or
            response.css(".author::text, .writer::text").get() or
            response.css("meta[name='author']::attr(content)").get() or
            "Kenh14"
        )
        author = author.strip().rstrip(",") if author else "Kenh14"
        
        # Paragraphs - multiple XPath patterns
        paragraphs = response.xpath(
            "//div[contains(@class,'knc-content')]//p/text() | "
            "//div[contains(@class,'content')]//p/text() | "
            "//article//p/text() | "
            "//div[contains(@class,'detail')]//p/text() | "
            "//div[contains(@class,'article-content')]//p/text() | "
            "//div[contains(@class,'story-content')]//p/text()"
        ).getall()
        
        # Clean paragraphs
        cleaned_para = [
            p.strip() for p in paragraphs 
            if p and p.strip() and len(p.strip()) > 5
        ]
        content = " ".join(cleaned_para).strip()

        if not description:
            description = self._build_description_from_paragraphs(cleaned_para)
        
        # Tags
        tags = response.css("meta[name='keywords']::attr(content)").get() or ""
        
        # Images - multiple patterns
        images = response.css(
            "meta[property='og:image']::attr(content), "
            ".content img::attr(src), "
            "article img::attr(src), "
            "img.article-image::attr(src)"
        ).getall()
        
        # Remove duplicates và filter valid images
        images = list(dict.fromkeys([
            img for img in images 
            if img and ("kenh14" in str(img) or img.startswith("http"))
        ]))
        
        # Only yield nếu có content và title
        if content and title:
            yield {
                "source": "kenh14",
                "url": response.url,
                "category": category,
                "title": title.strip() if title else "",
                "description": description.strip() if description else "",
                "author": author,
                "date": date.strip() if date else "",
                "tags": tags.strip() if tags else "",
                "paragraphs": cleaned_para,
                "content": content,
                "images": images,
                "image_count": len(images),
                "word_count": len(content.split()),
            }

    def _build_description_from_paragraphs(self, paragraphs):
        for p in paragraphs:
            text = self._normalize_text(p)
            if not text:
                continue
            lowered = text.lower()
            if lowered.startswith("ảnh") or lowered.startswith("video"):
                continue
            if len(text) < 40:
                continue
            if len(text) > 240:
                return text[:237].rstrip() + "..."
            return text
        return ""

    def _normalize_text(self, value):
        if not isinstance(value, str):
            return ""
        text = re.sub(r"\s+", " ", value).strip()
        if not text:
            return ""
        # Một số mô tả chỉ là dấu câu/placeholder, coi như rỗng
        if re.fullmatch(r"[\W_]+", text, flags=re.UNICODE):
            return ""
        return text

    def _pick_first_meaningful_text(self, candidate_groups):
        for group in candidate_groups:
            if not group:
                continue
            if isinstance(group, str):
                group = [group]
            parts = [self._normalize_text(item) for item in group if item]
            parts = [p for p in parts if p]
            if not parts:
                continue

            joined = self._normalize_text(" ".join(parts))
            if joined and len(joined) >= 20:
                return joined

            for p in parts:
                if len(p) >= 20:
                    return p
        return ""

    def _should_follow_listing_link(self, link):
        lower_link = link.lower()
        if lower_link.startswith(("javascript:", "mailto:", "tel:", "#")):
            return False

        parsed = urlsplit(lower_link)
        path = parsed.path or ""
        if not path:
            return False

        # Skip clearly non-listing resources.
        if any(path.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".css", ".js", ".pdf")):
            return False

        listing_markers = (
            "/trang-",
            "?page=",
            "/timeline",
            "/c",
            ".html",
        )
        return any(marker in lower_link for marker in listing_markers)

    def _extract_jsonld_objects(self, response):
        objects = []
        scripts = response.xpath("//script[@type='application/ld+json']/text()").getall()
        for script in scripts:
            if not script:
                continue
            text = script.strip()
            if not text:
                continue
            try:
                data = json.loads(text)
            except Exception:
                continue

            if isinstance(data, list):
                objects.extend([d for d in data if isinstance(d, dict)])
            elif isinstance(data, dict):
                graph = data.get("@graph")
                if isinstance(graph, list):
                    objects.extend([d for d in graph if isinstance(d, dict)])
                else:
                    objects.append(data)
        return objects

    def _extract_jsonld_value(self, response, key):
        for obj in self._extract_jsonld_objects(response):
            value = obj.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _extract_jsonld_author(self, response):
        for obj in self._extract_jsonld_objects(response):
            author = obj.get("author")
            if isinstance(author, dict):
                name = author.get("name")
                if isinstance(name, str) and name.strip():
                    return name.strip()
            elif isinstance(author, list):
                for item in author:
                    if isinstance(item, dict):
                        name = item.get("name")
                        if isinstance(name, str) and name.strip():
                            return name.strip()
                    elif isinstance(item, str) and item.strip():
                        return item.strip()
            elif isinstance(author, str) and author.strip():
                return author.strip()
        return ""

    def _extract_breadcrumb_category(self, response):
        breadcrumb_text = response.css("ul.kbread li a::text, .kbreadcrumb a::text").getall()
        cleaned = [t.strip() for t in breadcrumb_text if t and t.strip()]
        for text in cleaned:
            if text.lower() not in {"trang chủ", "home"}:
                return text

        for obj in self._extract_jsonld_objects(response):
            if obj.get("@type") != "BreadcrumbList":
                continue
            items = obj.get("itemListElement", [])
            names = []
            for it in items:
                if not isinstance(it, dict):
                    continue
                item = it.get("item")
                if isinstance(item, dict):
                    name = item.get("name")
                else:
                    name = None
                if isinstance(name, str) and name.strip():
                    names.append(name.strip())

            for name in names:
                if name.lower() not in {"trang chủ", "home"}:
                    return name
        return ""

    def _resolve_category(self, response):
        meta_category = response.meta.get("category", "")
        breadcrumb_category = self._extract_breadcrumb_category(response)
        section_meta = (
            response.css("meta[property='article:section']::attr(content)").get()
            or self._extract_jsonld_value(response, "articleSection")
            or ""
        )

        # Ưu tiên nhóm lớn ổn định từ URL/start page để tránh nhánh con như "cine".
        candidates = [meta_category, section_meta, breadcrumb_category]
        for raw in candidates:
            normalized = normalize_category(raw)
            if normalized in self.canonical_categories:
                return normalized

        # Nếu không xác định được nhóm lớn, trả về nhãn mặc định.
        return "Khác"
