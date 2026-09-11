AINEWS Channel Configuration
=============================

This channel uses RSS feeds for news headlines, processed via the news_pipeline.

Features:
- 5 shorts per run from RSS news feeds
- 0 long-form videos
- No background music (original audio preserved)
- Independent YouTube OAuth credentials
- Free local Piper TTS for voice synthesis

RSS Feeds:
- https://feeds.bbci.co.uk/news/world/rss.xml
- https://www.reutersagency.com/feed/?best-topics=world&post_type=best
- https://techcrunch.com/feed/
- https://news.google.com/rss/search?q=technology&hl=en-US&gl=US&ceid=US:en

Token File: data/channels/AINEWS/token.json
GitHub Secret: YOUTUBE_TOKEN_AINEWS