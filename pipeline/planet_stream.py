"""Stream a large remote file to stdout using parallel HTTP range requests.

Used as a fallback when Overpass is unreachable: the OpenStreetMap planet
published on the AWS Open Data registry (bucket ``osm-pds``) is streamed into
``osmium extract --strategy simple`` (single pass, reads from stdin), so the
~95 GB file never touches the disk.

Usage:
    python -m pipeline.planet_stream URL | osmium extract -s simple -b BBOX -F pbf - -o out.osm.pbf
"""

from __future__ import annotations

import argparse
import os
import ssl
import sys
import threading
import time
import urllib.request

CHUNK = 64 * 1024 * 1024


def _context() -> ssl.SSLContext:
    cafile = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    return ssl.create_default_context(cafile=cafile) if cafile else ssl.create_default_context()


def remote_size(url: str) -> int:
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, context=_context(), timeout=60) as resp:
        return int(resp.headers["Content-Length"])


def fetch_range(url: str, start: int, end: int, retries: int = 6) -> bytes:
    delay = 2.0
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}"})
            with urllib.request.urlopen(req, context=_context(), timeout=120) as resp:
                data = resp.read()
            if len(data) != end - start + 1:
                raise IOError(f"short read {len(data)} != {end - start + 1}")
            return data
        except Exception as exc:  # noqa: BLE001 - retried, then re-raised
            if attempt == retries - 1:
                raise
            print(f"[planet_stream] retry {attempt + 1} for {start}: {exc}", file=sys.stderr)
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")


def stream(url: str, workers: int = 6, ahead: int = 10) -> None:
    size = remote_size(url)
    n_chunks = (size + CHUNK - 1) // CHUNK
    print(f"[planet_stream] {url} size={size / 1e9:.1f} GB chunks={n_chunks}", file=sys.stderr)

    results: dict[int, bytes] = {}
    cond = threading.Condition()
    next_to_fetch = 0
    next_to_write = 0
    failed: list[BaseException] = []

    def worker() -> None:
        nonlocal next_to_fetch
        while True:
            with cond:
                # Bound memory: never fetch more than `ahead` chunks past the writer.
                while next_to_fetch < n_chunks and next_to_fetch >= next_to_write + ahead and not failed:
                    cond.wait()
                if next_to_fetch >= n_chunks or failed:
                    return
                idx = next_to_fetch
                next_to_fetch += 1
            start = idx * CHUNK
            end = min(size, start + CHUNK) - 1
            try:
                data = fetch_range(url, start, end)
            except BaseException as exc:  # noqa: BLE001
                with cond:
                    failed.append(exc)
                    cond.notify_all()
                return
            with cond:
                results[idx] = data
                cond.notify_all()

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(workers)]
    for t in threads:
        t.start()

    out = sys.stdout.buffer
    t0 = time.time()
    while next_to_write < n_chunks:
        with cond:
            while next_to_write not in results and not failed:
                cond.wait()
            if failed:
                raise RuntimeError(f"download failed: {failed[0]}")
            data = results.pop(next_to_write)
        out.write(data)
        with cond:
            next_to_write += 1
            cond.notify_all()
        if next_to_write % 50 == 0 or next_to_write == n_chunks:
            done = next_to_write * CHUNK / 1e9
            rate = done / max(time.time() - t0, 1e-6)
            print(f"[planet_stream] {done:.1f}/{size / 1e9:.1f} GB ({rate * 1000:.0f} MB/s)", file=sys.stderr)
    out.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--ahead", type=int, default=10)
    args = parser.parse_args()
    try:
        stream(args.url, args.workers, args.ahead)
    except BrokenPipeError:
        sys.exit(1)


if __name__ == "__main__":
    main()
