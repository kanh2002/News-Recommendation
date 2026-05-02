# Vietnamese News Crawling Dataset

This dataset contains approximately 12k records collected from Vietnamese news websites.

## 1) Crawling tools

- Main framework: Scrapy
- Language: Python 3

## 2) Crawling sources

The project currently crawls data from 5 sources:

- VnExpress
- Vietnamnet
- Thanh Nien
- Kenh14
- Bao Moi

## 3) Collected data structure (main schema)

- source: news source
- url: article URL
- category: section/topic (normalized via mapper)
- title: article title
- description: short description/sapo
- author: author (if available)
- date: publication datetime
- tags: article keywords
- paragraphs: list of extracted paragraphs
- content: concatenated full article content
- images: list of image URLs
- image_count: number of images
- word_count: number of words in content

