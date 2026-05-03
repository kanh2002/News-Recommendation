import scrapy

from crawl_data.category_mapper import normalize_category
class VnexpressSpider(scrapy.Spider):

    name = "vnexpress"

    allowed_domains = ["vnexpress.net"]

    start_urls = [
        "https://vnexpress.net/thoi-su",
        "https://vnexpress.net/the-gioi",
        "https://vnexpress.net/kinh-doanh",
        "https://vnexpress.net/khoa-hoc-cong-nghe", 
        "https://vnexpress.net/goc-nhin",
        "https://vnexpress.net/spotlight",
        "https://vnexpress.net/bat-dong-san",
        "https://vnexpress.net/suc-khoe",
        "https://vnexpress.net/giai-tri",
        "https://vnexpress.net/the-thao",
        "https://vnexpress.net/phap-luat",
        "https://vnexpress.net/giao-duc",
        "https://vnexpress.net/doi-song",
        "https://vnexpress.net/oto-xe-may",
        "https://vnexpress.net/du-lich",
        "https://vnexpress.net/anh",
        "https://vnexpress.net/infographics",
        "https://vnexpress.net/y-kien",
        "https://vnexpress.net/tam-su",
        "https://vnexpress.net/thu-gian",
    ]

    custom_settings = {
        "DEPTH_LIMIT": 10,
        "DOWNLOAD_DELAY": 0.5,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
    }


    def parse(self, response):

        article_links = response.css(
            "h1.title-news a::attr(href), "
            "h2.title-news a::attr(href), "
            "h3.title-news a::attr(href), "
            "h4.title-news a::attr(href)"
        ).getall()


        for link in article_links:
            if ".html" in link:
                yield response.follow(link, self.parse_article)

        next_page = response.css(
            "a.page_next::attr(href), "
            "a.btn-page.next::attr(href), "
            "a.next::attr(href), "
            "a.next-page::attr(href), "
            "a[rel='next']::attr(href)"
        ).get()

        if next_page:
            yield response.follow(next_page, self.parse)
    def parse_article(self, response):

        categories = response.css(
            "ul.breadcrumb li a::text"
        ).getall()
        ignore = {"Trang chủ", "Home", "VnExpress"}
        main_categories = [c for c in categories if c not in ignore]
        category = normalize_category(main_categories[0]) if main_categories else "Khác"

        

        title = response.css(
            "h1.title-detail::text"
        ).get()

        description = response.css(
            "p.description::text"
        ).get()

        date = response.css(
            "span.date::text"
        ).get()

        author_list = response.css(
            "article.fck_detail p strong::text"
        ).getall()

        author = author_list[-1].strip() if author_list else "VNExpress"

        paragraphs = response.css(
            "article.fck_detail p::text"
        ).getall()

        content = " ".join(paragraphs).strip()

        tags = response.css(
            "meta[name='keywords']::attr(content)"
        ).get()

        images = response.css(
            "article.fck_detail img::attr(src)"
        ).getall()

        word_count = len(content.split())

        yield {
            "source": "vnexpress",
            "url": response.url,
            "category": category,
            "title": title,
            "description": description,
            "author": author,
            "date": date,
            "tags": tags,
            "paragraphs": paragraphs,
            "content": content,
            "images": images,
            "image_count": len(images),
            "word_count": word_count,
        }
