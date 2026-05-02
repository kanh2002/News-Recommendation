# -*- coding: utf-8 -*-
import scrapy
from crawl_data.category_mapper import normalize_category


class ThanhNienSpider(scrapy.Spider):
    name = "thanhnien"
    allowed_domains = ["thanhnien.vn"]

    # Mở rộng categories tương tự VnExpress - 18+ chủ đề
    start_urls = [
        "https://thanhnien.vn/thoi-su.htm",
        "https://thanhnien.vn/the-gioi.htm",
        "https://thanhnien.vn/kinh-te.htm",
        "https://thanhnien.vn/suc-khoe.htm",
        "https://thanhnien.vn/giao-duc.htm",
        "https://thanhnien.vn/giai-tri.htm",
        "https://thanhnien.vn/the-thao.htm",
        "https://thanhnien.vn/van-hoa.htm",
        "https://thanhnien.vn/doi-song.htm",
        "https://thanhnien.vn/cong-nghe.htm",
        "https://thanhnien.vn/du-lich.htm",
        "https://thanhnien.vn/xe.htm",
        "https://thanhnien.vn/gioi-tre.htm",
        "https://thanhnien.vn/phap-luat.htm",
        "https://thanhnien.vn/bat-dong-san.htm",
        "https://thanhnien.vn/ban-doc.htm",
    ]

    custom_settings = {
        "DEPTH_LIMIT": 50,
        "DOWNLOAD_DELAY": 0.6,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
    }

    def start_requests(self):
        """Extract category từ URL và pass qua meta dict"""
        for url in self.start_urls:
            # "https://thanhnien.vn/thoi-su.htm" -> "thoi-su"
            category = url.split("/")[-1].replace(".htm", "")
            yield scrapy.Request(url, meta={"category": category})

    def parse(self, response):
        """Extract article links từ category page"""
        category = response.meta.get("category", "")
        
        # Selectors cho article links - multiple fallbacks
        article_links = response.css(
            "h2 a::attr(href), "
            "h3 a::attr(href), "
            "h4 a::attr(href), "
            "article a::attr(href), "
            "a.title-news::attr(href), "
            "a.article-title::attr(href)"
        ).getall()
        
        for link in article_links:
            # Chỉ follow links có "-" (thanhnien article ID pattern)
            if link and ("-" in link or ".htm" in link):
                yield response.follow(link, self.parse_article, meta={"category": category})

        # Pagination - multiple patterns
        next_page = response.css(
            "a.next::attr(href), "
            "a[rel='next']::attr(href), "
            "a.pagination-next::attr(href), "
            "li.next a::attr(href), "
            "a.btn-page.next::attr(href)"
        ).get()
        
        if next_page:
            yield response.follow(next_page, self.parse, meta={"category": category})

    def parse_article(self, response):
        """Extract article content"""
        raw_category = response.meta.get("category", "")
        category = normalize_category(raw_category)
        
        # Title - multiple fallbacks
        title = (
            response.css("span[data-role='title']::text").get() or
            response.css("h1.detail-title span::text").get() or
            response.css("meta[property='og:title']::attr(content)").get() or
            ""
        )
        
        # Description - multiple fallbacks
        description = (
            response.css("p.sapo::text, p.description::text").get() or
            response.css("meta[property='og:description']::attr(content)").get() or
            ""
        )
        
        # Date - multiple patterns
        date = (
            response.css("time::attr(datetime)").get() or
            response.css("span.time::text, span.detail-time::text").get() or
            response.css("meta[property='article:published_time']::attr(content)").get() or
            ""
        )
        
        # Author
        author = (
            response.css(".author::text, .detail-author::text, .writer::text").get() or
            response.css("meta[name='author']::attr(content)").get() or
            "ThanhNien"
        )
        author = author.strip() if author else "ThanhNien"
        
        # Paragraphs - multiple XPath patterns
        paragraphs = response.xpath(
            "//div[contains(@class,'detail-content')]//p/text() | "
            "//article//p/text() | "
            "//div[contains(@class,'fck_detail')]//p/text() | "
            "//div[contains(@class,'story-content')]//p/text()"
        ).getall()
        
        # Clean paragraphs - remove short ones, trim whitespace
        cleaned_para = [
            p.strip() for p in paragraphs 
            if p and p.strip() and len(p.strip()) > 5
        ]
        content = " ".join(cleaned_para).strip()
        
        # Tags
        tags = response.css("meta[name='keywords']::attr(content)").get() or ""
        
        # Images - multiple patterns
        images = response.css(
            "meta[property='og:image']::attr(content), "
            "div.detail-content img::attr(src), "
            "article img::attr(src), "
            "img.article-thumbnail::attr(src)"
        ).getall()
        
        # Remove duplicates và filter valid images
        images = list(dict.fromkeys([
            img for img in images 
            if img and ("thanhnien" in str(img) or img.startswith("http"))
        ]))
        
        # Only yield nếu có content và title
        if content and title:
            yield {
                "source": "thanhnien",
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
