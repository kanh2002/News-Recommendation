import scrapy
import re
from urllib.parse import urlsplit
from crawl_data.category_mapper import normalize_category


class VietnamnetSpider(scrapy.Spider):
    name = "vietnamnet"
    allowed_domains = ["vietnamnet.vn"]

    start_urls = [
        "https://vietnamnet.vn/thoi-su",
        "https://vietnamnet.vn/the-gioi",
        "https://vietnamnet.vn/kinh-doanh",
        "https://vietnamnet.vn/giao-duc",
        "https://vietnamnet.vn/suc-khoe",
        "https://vietnamnet.vn/the-thao",
        "https://vietnamnet.vn/van-hoa",
        "https://vietnamnet.vn/giai-tri",
        "https://vietnamnet.vn/doi-song",
        "https://vietnamnet.vn/cong-nghe",
    ]

    custom_settings = {
        "DEPTH_LIMIT": 80,
        "DOWNLOAD_DELAY": 0.5,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
        "SEEN_URLS_PATH": "seen_urls_vietnamnet.txt",
    }

    article_pattern = re.compile(r"-[0-9]{6,}\.html(?:\?|$)")

    def start_requests(self):
        for url in self.start_urls:
            category = url.split("vietnamnet.vn/")[1]
            yield scrapy.Request(url, meta={"category": category})

    def parse(self, response):
        category = response.meta.get("category", "")

        links = response.css(
            "h2 a::attr(href), "
            "h3 a::attr(href), "
            "h4 a::attr(href), "
            "article a::attr(href), "
            "a[href*='.html']::attr(href)"
        ).getall()

        for link in links:
            if not link:
                continue
            link = link.strip()
            if not link:
                continue

            if self.article_pattern.search(link):
                yield response.follow(link, self.parse_article, meta={"category": category})

        listing_links = response.css("a::attr(href)").getall()
        for link in listing_links:
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
        raw_category = response.meta.get("category", "")
        category = normalize_category(raw_category)
        
        title = response.css("h1::text, meta[property='og:title']::attr(content)").get()
        description = response.css("meta[property='og:description']::attr(content), .sapo::text, p.intro::text").get()
        date = response.css("time::attr(datetime), meta[property='article:published_time']::attr(content), span.time::text").get()
        author = response.css(".author::text, .writer::text, meta[name='author']::attr(content)").get()
        author = author.strip() if author else "VietnamNet"

        paragraphs = response.xpath("//div[contains(@class,'content')] | //article | //div[contains(@class,'detail')]").xpath(".//p/text()").getall()
        cleaned_para = [p.strip() for p in paragraphs if p.strip() and len(p.strip()) > 5]
        content = " ".join(cleaned_para).strip()

        tags = response.css("meta[name='keywords']::attr(content)").get()
        images = response.css("meta[property='og:image']::attr(content), .content img::attr(src), article img::attr(src)").getall()
        images = list(dict.fromkeys([img for img in images if img and "vietnamnet" in str(img)]))

        if content and title:
            yield {
                "source": "vietnamnet",
                "url": response.url,
                "category": category,
                "title": title.strip() if title else "",
                "description": description.strip() if description else "",
                "author": author,
                "date": date.strip() if date else "",
                "tags": tags if tags else "",
                "paragraphs": cleaned_para,
                "content": content,
                "images": images,
                "image_count": len(images),
                "word_count": len(content.split()),
            }

    def _should_follow_listing_link(self, link):
        lower_link = link.lower()
        if lower_link.startswith(("javascript:", "mailto:", "tel:", "#")):
            return False

        parsed = urlsplit(lower_link)
        path = parsed.path or ""
        if not path:
            return False

        if any(path.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".css", ".js", ".pdf")):
            return False

        listing_markers = (
            "/trang-",
            "?page=",
            "/timeline",
            "/tin-",
            "/su-kien/",
        )
        return any(marker in lower_link for marker in listing_markers)
