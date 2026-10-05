# multiscrobbler-cli

Command-line tool to scrobble a full album to **Multi Scrobbler** (via its ListenBrainz-compatible API) using a MusicBrainz release.

Supports two modes:

- Direct mode: provide a MusicBrainz **release MBID** on the command line.
- Interactive mode: search by **artist name** and **album title**, pick a release group, then a specific release (with track count, length, format, barcode, and label/catalog info), and scrobble the whole album.

## Requirements

- Python 3.8+
- A running instance of [Multi Scrobbler](https://github.com/FoxxMD/multi-scrobbler) with ListenBrainz API enabled.
- A `MS_TOKEN` configured in your Multi Scrobbler instance.

## Installation

```bash
git clone [https://github.com/GuerillaUmNeon/multiscrobbler-cli.git](https://github.com/GuerillaUmNeon/multiscrobbler-cli.git)
cd multiscrobbler-cli

# Create and activate a virtual environment (optional but recommended)
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Configuration

1. Copy the example environment file:

   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and set your values:

   ```env
   MS_BASE_URL=http://192.168.1.10:9078/api/listenbrainz
   MS_TOKEN=your_ms_token_here
   ```

Notes:

- `MS_BASE_URL` must point to the **ListenBrainz-compatible base path** exposed by Multi Scrobbler, *without* the `/1/submit-listens` suffix.  
  Examples:
  - `http://192.168.1.10:9078/api/listenbrainz`
  - `http://192.168.1.10:9078/listenbrainz`
- `MS_TOKEN` is the token you configured in Multi Scrobbler for ListenBrainz clients.

The script will load these variables from `.env` automatically via `python-dotenv`.

## Usage

### Scrobble by release MBID

```bash
python scrobble.py <release_mbid>
```

Example:

```bash
python scrobble.py 8d6a1d13-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

The script will:

1. Fetch the release from MusicBrainz.
2. Show release name, track count, and total length.
3. Print the full track list with durations.
4. Ask for confirmation before submitting.

### Interactive search (artist + album)

```bash
python scrobble.py
```

You will be prompted to:

1. Enter **artist name**.
2. Enter **album title**.
3. Choose a **release group** from search results.
4. Choose a **release** from that group, with details:
   - date, country
   - track count and total length
   - format (Vinyl, CD, Digital Media, etc.)
   - barcode
   - label name(s) and catalog number(s)
5. Review the **track list** with durations.
6. Confirm or abort the scrobble.

On confirmation, the full album is submitted to Multi Scrobbler as a batch of “single” listens, back-dated so that the last track ends at the current time.

## How it works

- Uses the MusicBrainz XML Web Service (`https://musicbrainz.org/ws/2`) to:
  - Search release groups by artist and album title.
  - Fetch release groups with their releases.
  - Fetch full release data (with media, recordings, and labels).
- Submits listens to Multi Scrobbler using its ListenBrainz-compatible endpoint:
  - `POST {MS_BASE_URL}/1/submit-listens`
  - Payload format follows the ListenBrainz JSON API.

Each track is scrobbled with:

- `artist_name`
- `track_name`
- `release_name`
- `listened_at` (computed so the album plays end-to-end ending now)
- `additional_info.duration_ms`
- `additional_info.media_player = "vinyl-album-scrobbler-mbid"`

## Troubleshooting

- **HTML response instead of JSON**:  
  Your `MS_BASE_URL` is pointing to the Multi Scrobbler UI root instead of the ListenBrainz API path. Adjust `MS_BASE_URL` to include the correct path (e.g. `/api/listenbrainz`).

- **502 Bad Gateway**:  
  Multi Scrobbler’s ListenBrainz module may be misconfigured or not running. Check:
  - Multi Scrobbler config (`listenbrainz.enabled`, `listenbrainz.path`)
  - Multi Scrobbler logs
  - That the container/service is healthy

- **No tracks found**:  
  The selected release may have no media/tracks in MusicBrainz, or the release fetch failed. Try a different release.

## License

```text
MIT License – see LICENSE file.
```