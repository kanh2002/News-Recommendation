import scrapy


class DantriSpider(scrapy.Spider):
    name = "dantri"
    allowed_domains = ["dantri.com.vn"]

    start_urls = [
        "https://dantri.com.vn/xa-hoi.htm",
        "https://dantri.com.vn/the-gioi.htm",
        "https://dantri.com.vn/kinh-doanh.htm",
        "https://dantri.com.vn/lao-dong-viec-lam.htm",
        "https://dantri.com.vn/the-thao.htm",
        "https://dantri.com.vn/giao-duc.htm",
        "https://dantri.com.vn/suc-khoe.htm",
        "https://dantri.com.vn/van-hoa.htm",
        "https://dantri.com.vn/giai-tri.htm",
        "https://dantri.com.vn/phap-luat.htm",
        "https://dantri.com.vn/du-lich.htm",
        "https://dantri.com.vn/o-to-xe-may.htm",
        "https://dantri.com.vn/khoa-hoc-cong-nghe.htm",
    ]

    custom_settings = {
        "DEPTH_LIMIT": 80,
        "DOWNLOAD_DELAY": 0.5,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
    }

    def parse(self, response):
        article_links = response.css(
            "h2 a::attr(href), h3 a::attr(href), article a::attr(href)"
        ).getall()

        for link in article_links:
            if "/20" in link and (".htm" in link or ".html" in link):
                yield response.follow(link, self.parse_article)

        next_page = response.css(
            "a.page-link.next::attr(href), a.next-page::attr(href), a[rel='next']::attr(href)"
        ).get()
        if next_page:
            yield response.follow(next_page, self.parse)

    def parse_article(self, response):
        categories = response.css(
            "ol.breadcrumb li a::text, ul.breadcrumb li a::text"
        ).getall()
        ignore = {"Trang chủ", "Home", "Dân trí", "Dantri"}
        main_categories = [c.strip() for c in categories if c and c.strip() not in ignore]
        category = main_categories[0] if main_categories else ""

        title = response.css("h1.title-page::text, h1.article-title::text").get()
        description = response.css(
            "h2.singular-sapo::text, div.singular-sapo::text, p.sapo::text"
        ).get()

        date = response.css(
            "time.author-time::attr(datetime), time::attr(datetime), span.author-time::text"
        ).get()

        author = response.css(
            ".author-name::text, .singular-author .name::text, .author::text"
        ).get()
        author = author.strip() if author else "DanTri"

        paragraphs = response.css(
            "article.singular-container p::text, div.e-magazine p::text, article p::text"
        ).getall()
        paragraphs = [p.strip() for p in paragraphs if p and p.strip()]
        content = " ".join(paragraphs).strip()

        tags = response.css("meta[name='keywords']::attr(content)").get()
        images = response.css(
            "article.singular-container img::attr(src), article img::attr(src)"
        ).getall()
        images = [img for img in images if img]

        yield {
            "source": "dantri",
            "url": response.url,
            "category": category,
            "title": title.strip() if title else None,
            "description": description.strip() if description else None,
            "author": author,
            "date": date.strip() if date else None,
            "tags": tags,
            "paragraphs": paragraphs,
            "content": content,
            "images": images,
            "image_count": len(images),
            "word_count": len(content.split()),
        }
