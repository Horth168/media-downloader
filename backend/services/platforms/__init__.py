from services.platforms.direct import DirectLink
from services.platforms.ytdlp import Douyin, Facebook, Instagram, TikTok, YouTube

# Order matters: specific platforms first, generic direct links last.
PLATFORMS = [TikTok(), Douyin(), Instagram(), Facebook(), YouTube()]
DIRECT = DirectLink()


def detect(url):
    for p in PLATFORMS:
        if p.matches(url):
            return p
    return DIRECT


def all_platforms():
    return [p.describe() for p in PLATFORMS + [DIRECT]]
