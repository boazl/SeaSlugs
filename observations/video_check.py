"""Find observations whose YouTube video no longer exists (/admin/video-check/, video_check_views.py).

The site keeps only YouTube links (Sample.video_url) and cannot tell when a video was deleted on YouTube, so the
gallery and the species pages keep offering ▶ for it. A scan asks YouTube's public oEmbed endpoint about every
video id in use -- no API key, a few parallel requests -- and sorts each answer into a status:

  ok          200 -- the video exists and may be embedded
  not_found   404 / 400 -- deleted on YouTube (or the id never existed)
  restricted  401 / 403 -- private, or the owner blocked embedding; the site's player falls back to the photo
  error       no answer (network, timeout, another code) -- the check says nothing about the video
"""
import json
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from django.core.exceptions import ValidationError

STATUS_OK, STATUS_NOT_FOUND, STATUS_RESTRICTED, STATUS_ERROR = 'ok', 'not_found', 'restricted', 'error'
PROBLEM_STATUSES = (STATUS_NOT_FOUND, STATUS_RESTRICTED, STATUS_ERROR)
OEMBED_URL = 'https://www.youtube.com/oembed'
USER_AGENT = 'SeaSlugs.org.il video check'
WORKERS = 12
TIMEOUT = 15


def _oembed_code(video_id):
    """HTTP status code YouTube's oEmbed endpoint answers for this video id (None when there is no answer)."""
    query = urllib.parse.urlencode({'url': f'https://www.youtube.com/watch?v={video_id}', 'format': 'json'})
    request = urllib.request.Request(f'{OEMBED_URL}?{query}', headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            json.loads(response.read() or b'{}')
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
    except Exception:
        return None


def status_for_code(code):
    if code == 200: return STATUS_OK
    if code in (400, 404): return STATUS_NOT_FOUND
    if code in (401, 403): return STATUS_RESTRICTED
    return STATUS_ERROR


def check_video(video_id):
    return status_for_code(_oembed_code(video_id))


def video_ids(samples):
    """{youtube id: [samples]} for samples with a valid YouTube link."""
    from .models import youtube_id
    found = {}
    for sample in samples:
        try: vid = youtube_id(sample.video_url)
        except ValidationError: continue
        found.setdefault(vid, []).append(sample)
    return found


def scan(ids):
    """{video id: status} for every id, checked in parallel."""
    ids = sorted(set(ids))
    if not ids: return {}
    with ThreadPoolExecutor(max_workers=min(WORKERS, len(ids))) as pool:
        return dict(zip(ids, pool.map(check_video, ids)))
