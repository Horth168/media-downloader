from services.platforms.direct import DirectLink
from services.platforms.meta import Facebook, Instagram
from services.platforms.unsupported import Douyin, TikTok, YouTube

# Order matters: specific platforms first, generic direct links last.
PLATFORMS = [YouTube(), TikTok(), Douyin(), Instagram(), Facebook()]
DIRECT = DirectLink()


def detect(url):
    for p in PLATFORMS:
        if p.matches(url):
            return p
    return DIRECT


def all_platforms():
    return [p.describe() for p in PLATFORMS + [DIRECT]]
