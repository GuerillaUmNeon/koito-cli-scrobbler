#!/usr/bin/env python3
"""
Scrobble a full album from a MusicBrainz release MBID to multi-scrobbler
(via its ListenBrainz endpoint), as if you just finished listening to it.

Usage:
  python scrobble_full_album_mbid.py <release_mbid>

Environment variables:
  MS_BASE_URL  - multi-scrobbler base URL, e.g. http://192.168.1.10:9078
  MS_TOKEN     - MS_TOKEN from multi-scrobbler config
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from dotenv import load_dotenv

load_dotenv()  # loads .env from current directory

MS_BASE_URL = os.getenv("MS_BASE_URL")
MS_TOKEN = os.getenv("MS_TOKEN")
USER_AGENT = "script-album-scrobbler/1.0"


MB_BASE = "https://musicbrainz.org/ws/2"

def fetch_json(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json"
        }
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))

def get_release(release_mbid):
    url = f"{MB_BASE}/release/{release_mbid}?inc=artists+recordings+media"
    return fetch_json(url)

def extract_tracks(release):
    """
    Returns a list of dicts:
    [
      {
        "artist_name": "...",
        "track_name": "...",
        "release_name": "...",
        "duration_ms": 123456
      },
      ...
    ]
    in correct album order.
    """
    media = release.get("media", [])
    if not media:
        raise ValueError("No media/tracks found for this release")

    release_name = release.get("title", "")
    tracks = []

    for m in media:
        for t in m.get("tracks", []):
            track_name = t.get("title", "")
            duration_ms = int(t.get("recording", {}).get("length", 0) or 0) or 0

            artist_credit = (
                t.get("artist-credit")
                or release.get("artist-credit")
                or []
            )
            artist_name = " / ".join(
                ac.get("artist", {}).get("name", "")
                for ac in artist_credit
                if ac.get("artist", {}).get("name")
            ) or "Unknown Artist"

            tracks.append({
                "artist_name": artist_name,
                "track_name": track_name,
                "release_name": release_name,
                "duration_ms": duration_ms,
            })

    return tracks

def scrobble_album_to_ms(tracks, end_time=None):
    """
    Submit a full album as a batch of 'single' listens, back-dated so that
    the last track ends at end_time (default: now).
    """
    if end_time is None:
        end_time = int(time.time())

    # Build listens in reverse so we can subtract durations from the end
    listens = []
    t = end_time

    for trk in reversed(tracks):
        duration_s = trk["duration_ms"] // 1000 if trk["duration_ms"] else 0
        # If unknown duration, assume 4 minutes
        if duration_s == 0:
            duration_s = 240

        listened_at = t - duration_s
        listens.append({
            "listened_at": listened_at,
            "track_metadata": {
                "artist_name": trk["artist_name"],
                "track_name": trk["track_name"],
                "release_name": trk["release_name"],
                "additional_info": {
                    "duration_ms": trk["duration_ms"] or None,
                    "media_player": "vinyl-album-scrobbler-mbid"
                }
            }
        })
        t = listened_at

    # Reverse back to album order
    listens.reverse()

    payload = {
        "listen_type": "single",
        "payload": listens
    }

    url = f"{MS_BASE_URL}/1/submit-listens"
    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Token {MS_TOKEN}",
            "User-Agent": USER_AGENT
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
            print(f"Album scrobble submitted: {len(listens)} tracks.")
            print("Response:", body)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        print("HTTP error:", e.code, e.reason)
        print("Response:", err_body)
        sys.exit(1)

def main():
    if len(sys.argv) < 2:
        print("Usage: python scrobble_full_album_mbid.py <release_mbid>")
        sys.exit(1)

    release_mbid = sys.argv[1]

    print("Fetching release from MusicBrainz...")
    release = get_release(release_mbid)
    tracks = extract_tracks(release)

    if not tracks:
        print("No tracks found for this release.")
        sys.exit(1)

    total_duration_s = sum(
        (trk["duration_ms"] // 1000 if trk["duration_ms"] else 240)
        for trk in tracks
    )
    total_min = total_duration_s // 60
    total_sec = total_duration_s % 60

    release_name = tracks[0]["release_name"]
    print(f"Release: {release_name}")
    print(f"Tracks:  {len(tracks)}")
    print(f"Length:  ~{total_min}m {total_sec}s")

    answer = input("Scrobble full album now? [Y/n] ").strip().lower()
    if answer not in ("", "y", "yes"):
        print("Aborted.")
        return

    scrobble_album_to_ms(tracks)

if __name__ == "__main__":
    main()