# Scrapy settings for crawl_data project
#
# For simplicity, this file contains only settings considered important or
# commonly used. You can find more settings consulting the documentation:
#
#     https://docs.scrapy.org/en/latest/topics/settings.html
#     https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#     https://docs.scrapy.org/en/latest/topics/spider-middleware.html

BOT_NAME = "crawl_data"

SPIDER_MODULES = ["crawl_data.spiders"]
NEWSPIDER_MODULE = "crawl_data.spiders"

ADDONS = {}
ITEM_PIPELINES = {
    "crawl_data.pipelines.CrawlDataPipeline": 300,
}
SEEN_URLS_PATH = "seen_urls.txt"
SEED_DATASET_PATH = "vnexpress_dataset.jsonl"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}
ITEM_PIPELINES = {
    "crawl_data.pipelines.RedisDuplicateFilterPipeline": 100,
    "crawl_data.pipelines.KafkaNewsPipeline": 300,
}
# Crawl responsibly by identifying yourself (and your website) on the user-agent
#USER_AGENT = "crawl_data (+http://www.yourdomain.com)"

# Obey robots.txt rules
ROBOTSTXT_OBEY = True

# Tăng tốc độ crawl
CONCURRENT_REQUESTS = 32
CONCURRENT_REQUESTS_PER_DOMAIN = 8
DOWNLOAD_DELAY = 0.25  # Giảm delay

# Tăng depth limit
DEPTH_LIMIT = 10

# Tắt robots.txt nếu cần (không khuyến khích)
# ROBOTSTXT_OBEY = False

# Thêm timeout
DOWNLOAD_TIMEOUT = 30

# # Cache để tránh crawl lại
# HTTPCACHE_ENABLED = True
# HTTPCACHE_EXPIRATION_SECS = 86400  # 1 ngày
# # Thêm giới hạn depth để crawl nhiều trang phân trang
# DEPTH_LIMIT = 10  # Crawl tối đa 10 trang phân trang mỗi category
# Disable cookies (enabled by default)
#COOKIES_ENABLED = False

# Disable Telnet Console (enabled by default)
#TELNETCONSOLE_ENABLED = False

# Override the default request headers:
#DEFAULT_REQUEST_HEADERS = {
#    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
#    "Accept-Language": "en",
#}

# Enable or disable spider middlewares
# See https://docs.scrapy.org/en/latest/topics/spider-middleware.html
#SPIDER_MIDDLEWARES = {
#    "crawl_data.middlewares.CrawlDataSpiderMiddleware": 543,
#}

# Enable or disable downloader middlewares
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#DOWNLOADER_MIDDLEWARES = {
#    "crawl_data.middlewares.CrawlDataDownloaderMiddleware": 543,
#}

# Enable or disable extensions
# See https://docs.scrapy.org/en/latest/topics/extensions.html
#EXTENSIONS = {
#    "scrapy.extensions.telnet.TelnetConsole": None,
#}

# Configure item pipelines
# See https://docs.scrapy.org/en/latest/topics/item-pipeline.html
#ITEM_PIPELINES = {
#    "crawl_data.pipelines.CrawlDataPipeline": 300,
#}

# Enable and configure the AutoThrottle extension (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/autothrottle.html
#AUTOTHROTTLE_ENABLED = True
# The initial download delay
#AUTOTHROTTLE_START_DELAY = 5
# The maximum download delay to be set in case of high latencies
#AUTOTHROTTLE_MAX_DELAY = 60
# The average number of requests Scrapy should be sending in parallel to
# each remote server
#AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
# Enable showing throttling stats for every response received:
#AUTOTHROTTLE_DEBUG = False

# Enable and configure HTTP caching (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html#httpcache-middleware-settings
#HTTPCACHE_ENABLED = True
#HTTPCACHE_EXPIRATION_SECS = 0
#HTTPCACHE_DIR = "httpcache"
#HTTPCACHE_IGNORE_HTTP_CODES = []
#HTTPCACHE_STORAGE = "scrapy.extensions.httpcache.FilesystemCacheStorage"

# Set settings whose default value is deprecated to a future-proof value
FEED_EXPORT_ENCODING = "utf-8"
