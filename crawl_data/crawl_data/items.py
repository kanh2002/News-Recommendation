# # Define here the models for your scraped items
# #
# # See documentation in:
# # https://docs.scrapy.org/en/latest/topics/items.html

# import scrapy


# class CrawlDataItem(scrapy.Item):
#     # define the fields for your item here like:
#     # name = scrapy.Field()
#     pass
import scrapy


class ProductReviewItem(scrapy.Item):
    source = scrapy.Field()
    product_name = scrapy.Field()
    product_url = scrapy.Field()
    category = scrapy.Field()
    price = scrapy.Field()
    rating = scrapy.Field()
    review_text = scrapy.Field()
    review_star = scrapy.Field()
    review_date = scrapy.Field()