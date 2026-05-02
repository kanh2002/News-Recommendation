from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings


process = CrawlerProcess(get_project_settings())

spiders = [
    "baomoi",
    "dantri",
    "kenh14",
    "thanhnien",
    "vietnamnet",
    "vnexpress",
]

for spider in spiders:
    process.crawl(spider)

process.start()