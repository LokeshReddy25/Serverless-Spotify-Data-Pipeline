"""Generate a SYNTHETIC Spotify "playlist tracks" response for local benchmarking.

This does NOT call the Spotify API. The structure contains only the fields that
src/transform_lambda/lambda_function.py actually reads (process_album / process_artist /
process_track). Real Spotify responses contain many more fields (available_markets,
images, preview_url, ...), so sizes measured on this file are NOT representative of the
real raw JSON size.

The file is serialised with json.dumps(data) -- the same call the extract Lambda uses
before put_object -- so its byte size equals what the extract Lambda would write for
this input.

Usage: python benchmarks/make_sample.py [n_items] [out_path]
"""
import json
import random
import string
import sys
from pathlib import Path

SEED = 42
B62 = string.ascii_letters + string.digits


def sid(rng):
    return "".join(rng.choice(B62) for _ in range(22))  # Spotify IDs are 22-char base62


def build(n_items=50, n_albums=40, n_artists=35, seed=SEED):
    rng = random.Random(seed)
    artists = [{"id": sid(rng), "name": f"Synthetic Artist {i:03d}"} for i in range(n_artists)]
    for a in artists:
        a["external_urls"] = {"spotify": f"https://open.spotify.com/artist/{a['id']}"}
    albums = []
    for i in range(n_albums):
        aid = sid(rng)
        # Spotify release_date precision can be day or year; include both.
        rd = f"{rng.randint(2015, 2026)}" if i % 10 == 0 else \
            f"{rng.randint(2015, 2026)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
        albums.append({"id": aid, "name": f"Synthetic Album {i:03d}", "release_date": rd,
                       "total_tracks": rng.randint(1, 20),
                       "external_urls": {"spotify": f"https://open.spotify.com/album/{aid}"}})
    items = []
    for i in range(n_items):
        track_artists = [artists[i % n_artists]]
        if i % 5 == 0:  # every 5th track has a featured artist
            track_artists.append(artists[(i + 7) % n_artists])
        items.append({
            "added_at": f"2026-0{rng.randint(1, 9)}-{rng.randint(10, 28)}T{rng.randint(10, 23)}:00:00Z",
            "track": {"id": sid(rng), "name": f"Synthetic Track {i:03d}",
                      "popularity": rng.randint(40, 100), "duration_ms": rng.randint(120000, 300000),
                      "album": albums[i % n_albums], "artists": track_artists},
        })
    return {"items": items, "total": n_items, "limit": 100, "offset": 0, "next": None}


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else \
        Path(__file__).parent / "sample_data" / f"synthetic_playlist_{n}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(build(n))  # identical serialisation to the extract Lambda
    out.write_bytes(payload.encode("utf-8"))
    print(f"wrote {out} bytes={len(payload.encode('utf-8'))} items={n}")
