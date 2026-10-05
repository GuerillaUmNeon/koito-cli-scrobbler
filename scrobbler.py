#!/usr/bin/env python3
"""
Scrobble a full album from a MusicBrainz release MBID to multi-scrobbler
(via its ListenBrainz endpoint), as if you just finished listening to it.

Usage:
  python scrobble.py <release_mbid>
  python scrobble.py               # interactive search by artist + album title

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
import urllib.parse
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
    """
    Fetch a full release with artists, recordings, media (tracks), and labels.
    """
    url = f"{MB_BASE}/release/{release_mbid}?inc=artists+recordings+media+labels"
    return fetch_json(url)


def search_release_groups(artist_name, album_title, limit=10):
    """
    Search MusicBrainz for release-groups matching artist + album title.
    Returns a list of release-group dicts.
    """
    query_parts = []
    if artist_name:
        query_parts.append(f'artist:"{artist_name}"')
    if album_title:
        query_parts.append(f'releasegroup:"{album_title}"')

    query = " AND ".join(query_parts)
    params = {
        "query": query,
        "fmt": "json",
        "limit": str(limit),
    }

    url = f"{MB_BASE}/release-group/?{urllib.parse.urlencode(params)}"
    data = fetch_json(url)
    return data.get("release-groups", [])


def get_release_group(release_group_mbid):
    """
    Fetch a release-group with its releases included (minimal metadata).
    """
    url = (
        f"{MB_BASE}/release-group/{release_group_mbid}"
        "?inc=artists+releases"
    )
    return fetch_json(url)


def compute_release_stats(release):
    """
    Compute:
      - track_count
      - total_duration_ms
      - format (media format summary)
      - barcode
      - label + catalog-number info
    for a given full release object (with media and labels).
    """
    media = release.get("media", [])
    track_count = 0
    total_duration_ms = 0

    for m in media:
        tracks = m.get("tracks", [])
        track_count += len(tracks)
        for t in tracks:
            length = t.get("recording", {}).get("length")
            if length:
                total_duration_ms += int(length)

    # Format: derive from media[].format
    formats = [m.get("format") for m in media if m.get("format")]
    if formats:
        seen = set()
        format_str_parts = []
        for f in formats:
            if f not in seen:
                seen.add(f)
                format_str_parts.append(f)
        format_str = " / ".join(format_str_parts)
    else:
        format_str = ""

    # Barcode
    barcode = release.get("barcode", "")

    # Label + catalog-number
    label_info = release.get("label-info", [])
    labels_parts = []
    for li in label_info:
        label = li.get("label", {}) or {}
        label_name = label.get("name", "")
        catalog_number = li.get("catalog-number", "")
        if label_name or catalog_number:
            part = ""
            if label_name:
                part += label_name
            if catalog_number:
                part += f" ({catalog_number})" if part else catalog_number
            labels_parts.append(part)

    labels_str = "; ".join(labels_parts) if labels_parts else ""

    return {
        "track_count": track_count,
        "total_duration_ms": total_duration_ms,
        "format": format_str,
        "barcode": barcode,
        "labels": labels_str,
    }


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

    listens = []
    t = end_time

    for trk in reversed(tracks):
        duration_s = trk["duration_ms"] // 1000 if trk["duration_ms"] else 0
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


def pick_release_group_from_search(artist_name, album_title):
    print("Searching MusicBrainz for release groups...")
    groups = search_release_groups(artist_name, album_title, limit=15)

    if not groups:
        print("No release groups found for that artist/album combination.")
        sys.exit(1)

    print(f"\nFound {len(groups)} matching release group(s):\n")
    for i, rg in enumerate(groups, start=1):
        mbid = rg.get("id", "")
        title = rg.get("title", "(no title)")
        date = rg.get("first-release-date", "")
        primary_type = rg.get("primary-type", "")
        secondary_types = rg.get("secondary-types", [])
        artists = " / ".join(
            ac.get("artist", {}).get("name", "")
            for ac in rg.get("artist-credit", [])
            if ac.get("artist", {}).get("name")
        ) or "Unknown Artist"

        type_info = []
        if primary_type:
            type_info.append(primary_type)
        if secondary_types:
            type_info.extend(secondary_types)
        type_str = " / ".join(type_info) if type_info else ""

        print(f"{i}. {title}")
        print(f"   Artist: {artists}")
        if date:
            print(f"   First release: {date}", end="")
        if type_str:
            print(f"  Type: {type_str}", end="")
        print()
        print(f"   MBID: {mbid}")
        print()

    while True:
        choice = input(f"Select a release group (1-{len(groups)}) or 'q' to quit: ").strip().lower()
        if choice == "q":
            print("Aborted.")
            sys.exit(0)

        if not choice.isdigit():
            print("Invalid input. Enter a number or 'q'.")
            continue

        idx = int(choice) - 1
        if 0 <= idx < len(groups):
            return groups[idx]

        print(f"Please enter a number between 1 and {len(groups)}.")


def pick_release_from_group(release_group):
    """
    Given a release-group object (with 'releases' included), let the user pick
    a specific release, showing:
      - title
      - date, country
      - track count
      - total length
      - format (Vinyl, CD, Digital Media, etc.)
      - barcode
      - label + catalog-number

    For each release, we fetch a full version with media/recordings/labels to
    compute correct stats.
    """
    releases_summary = release_group.get("releases", [])
    if not releases_summary:
        print("This release group has no releases.")
        sys.exit(1)

    print(f"\nRelease group: {release_group.get('title', '(no title)')}")
    print(f"Releases available: {len(releases_summary)}")
    print("Fetching detailed info for each release (tracks, length, format, label, barcode)...\n")

    enriched = []
    for i, r_sum in enumerate(releases_summary, start=1):
        mbid = r_sum.get("id")
        print(f"[{i}/{len(releases_summary)}] Fetching release {mbid}...")
        try:
            r_full = get_release(mbid)
        except Exception as e:
            print(f"  Error fetching release {mbid}: {e}")
            continue

        stats = compute_release_stats(r_full)
        enriched.append({
            "release": r_full,
            "stats": stats,
        })

    if not enriched:
        print("No releases could be loaded with track data.")
        sys.exit(1)

    print()

    for i, item in enumerate(enriched, start=1):
        r = item["release"]
        stats = item["stats"]

        title = r.get("title", "(no title)")
        date = r.get("date", "")
        country = r.get("country", "")
        mbid = r.get("id", "")

        track_count = stats["track_count"]
        total_ms = stats["total_duration_ms"]
        total_s = total_ms // 1000
        total_min = total_s // 60
        total_sec = total_s % 60
        length_str = f"{total_min}m {total_sec}s" if total_ms else "unknown"

        format_str = stats["format"] or "unknown format"
        barcode = stats["barcode"] or ""
        labels_str = stats["labels"] or ""

        print(f"{i}. {title}")
        print(f"   Date: {date}  Country: {country}")
        print(f"   Tracks: {track_count}  Length: ~{length_str}")
        print(f"   Format: {format_str}")
        if barcode:
            print(f"   Barcode: {barcode}")
        if labels_str:
            print(f"   Label(s): {labels_str}")
        print(f"   MBID: {mbid}")
        print()

    while True:
        choice = input(f"Select a release (1-{len(enriched)}) or 'q' to quit: ").strip().lower()
        if choice == "q":
            print("Aborted.")
            sys.exit(0)

        if not choice.isdigit():
            print("Invalid input. Enter a number or 'q'.")
            continue

        idx = int(choice) - 1
        if 0 <= idx < len(enriched):
            return enriched[idx]["release"]

        print(f"Please enter a number between 1 and {len(enriched)}.")


def print_track_list(tracks):
    """
    Print a numbered track list with durations in mm:ss.
    """
    print("\nTrack list:")
    for i, trk in enumerate(tracks, start=1):
        duration_ms = trk["duration_ms"]
        if duration_ms:
            total_s = duration_ms // 1000
            m = total_s // 60
            s = total_s % 60
            dur_str = f"{m}:{s:02d}"
        else:
            dur_str = "--:--"

        artist = trk["artist_name"]
        title = trk["track_name"]
        print(f"{i:2d}. {artist} - {title} ({dur_str})")
    print()


def main():
    if not MS_BASE_URL or not MS_TOKEN:
        print("Error: MS_BASE_URL and MS_TOKEN environment variables must be set.")
        sys.exit(1)

    # Case 1: MBID provided on command line (treated as release MBID)
    if len(sys.argv) >= 2:
        release_mbid = sys.argv[1]
        print("Fetching release from MusicBrainz...")
        release = get_release(release_mbid)
    else:
        # Case 2: interactive search by artist + album title
        artist_name = input("Artist name: ").strip()
        album_title = input("Album title: ").strip()

        if not artist_name and not album_title:
            print("You must provide at least an artist name or album title.")
            sys.exit(1)

        # Step A: pick release group
        release_group = pick_release_group_from_search(artist_name, album_title)

        # Step B: fetch full release-group with releases (minimal metadata)
        print("\nFetching release-group details with releases...")
        rg_full = get_release_group(release_group["id"])

        # Step C: pick specific release (with full media data fetched per release)
        release = pick_release_from_group(rg_full)

        # At this point `release` is already a full release object with media/tracks

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
    print(f"\nRelease: {release_name}")
    print(f"Tracks:  {len(tracks)}")
    print(f"Length:  ~{total_min}m {total_sec}s\n")

    # Show full track list before confirmation
    print_track_list(tracks)

    answer = input("Scrobble full album now? [Y/n] ").strip().lower()
    if answer not in ("", "y", "yes"):
        print("Aborted.")
        return

    scrobble_album_to_ms(tracks)


if __name__ == "__main__":
    main()