# -*- coding: utf-8 -*-
import scrapy
from crawl_data.category_mapper import normalize_category


class BaomoiSpider(scrapy.Spider):
    name = "baomoi"
    allowed_domains = ["baomoi.com"]

    # Chọn các chủ đề gần tương đương bộ category đang dùng
    start_urls = [
        "https://baomoi.com/thoi-su.epi",
        "https://baomoi.com/the-gioi.epi",
        "https://baomoi.com/kinh-te.epi",
        "https://baomoi.com/cong-nghe.epi",
        "https://baomoi.com/the-thao.epi",
        "https://baomoi.com/giao-duc.epi",
        "https://baomoi.com/suc-khoe.epi",
        "https://baomoi.com/van-hoa.epi",
        "https://baomoi.com/giai-tri.epi",
        "https://baomoi.com/doi-song.epi",
        "https://baomoi.com/du-lich.epi",
        "https://baomoi.com/phap-luat.epi",
        "https://baomoi.com/xe-co.epi",
    ]

    custom_settings = {
        "DEPTH_LIMIT": 120,
        "DOWNLOAD_DELAY": 0.6,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
    }

    def start_requests(self):
        for url in self.start_urls:
            slug = url.split("/")[-1].replace(".epi", "")
            yield scrapy.Request(url, callback=self.parse, meta={"category": slug})

    def parse(self, response):
        category = response.meta.get("category", "")

        # Lấy link bài viết
        links = response.css(
            "h2 a::attr(href), "
            "h3 a::attr(href), "
            "article a::attr(href), "
            "a[href*='.epi']::attr(href), "
            "a.bm-title::attr(href)"
        ).getall()

        seen = set()
        for link in links:
            if not link:
                continue
            if link in seen:
                continue
            seen.add(link)

            # Chỉ follow link bài
            if ".epi" in link:
                yield response.follow(link, callback=self.parse_article, meta={"category": category})

        # Phân trang
        next_page = response.css(
            "a.next::attr(href), "
            "a[rel='next']::attr(href), "
            "a.pagination-next::attr(href)"
        ).get()
        if next_page:
            yield response.follow(next_page, callback=self.parse, meta={"category": category})

    def parse_article(self, response):
        raw_category = response.meta.get("category", "")
        category = normalize_category(raw_category)

        title = (
            response.css("h1::text").get() or
            response.css("h1.bm-title::text").get() or
            response.css("meta[property='og:title']::attr(content)").get() or
            ""
        )

        description = (
            response.css("meta[property='og:description']::attr(content)").get() or
            response.css("p.sapo::text, p.description::text").get() or
            ""
        )

        date = (
            response.css("time::attr(datetime)").get() or
            response.css("meta[property='article:published_time']::attr(content)").get() or
            response.css("span.time::text, span.date::text").get() or
            ""
        )

        author = (
            response.css(".author::text, .writer::text").get() or
            response.css("meta[name='author']::attr(content)").get() or
            "BaoMoi"
        )
        author = author.strip() if author else "BaoMoi"

        paragraphs = response.xpath(
            "//article//p/text() | "
            "//div[contains(@class,'content')]//p/text() | "
            "//div[contains(@class,'detail')]//p/text()"
        ).getall()

        cleaned_para = [p.strip() for p in paragraphs if p and p.strip() and len(p.strip()) > 5]
        content = " ".join(cleaned_para).strip()

        tags = response.css("meta[name='keywords']::attr(content)").get() or ""

        images = response.css(
            "meta[property='og:image']::attr(content), "
            "article img::attr(src), "
            ".content img::attr(src)"
        ).getall()
        images = list(dict.fromkeys([img for img in images if img and img.startswith("http")]))

        if content and title:
            yield {
                "source": "baomoi",
                "url": response.url,
                "category": category,
                "title": title.strip(),
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
