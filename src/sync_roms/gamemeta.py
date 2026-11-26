"""The background per-system scraped-metadata loader the game lists share (years, genres, ...)."""
import json
import queue
import threading

from . import metafilter, s3, scrape_plan, ui

LOADING = "loading"
_metadata = {}  # system bucket -> metafilter.index, kept for the session so entering a system again doesn't fetch it
# again; while its read runs, the Metadata reading it, which later ones for the bucket wait on instead of reading too


def _spawn(fn):
    threading.Thread(target=fn, daemon=True).start()


class Metadata:
    """A system's scraped metadata.json as a metafilter.index, read once per session on a background thread (the
    worker never touches the screen). A failed read is not kept, so the next visit tries again."""

    def __init__(self, bucket):
        self.bucket = bucket
        self.done = queue.Queue()
        found = _metadata.get(bucket, LOADING)
        self.reader = found if isinstance(found, Metadata) else self
        self.result = LOADING if self.reader is not self else found
        if self.result is LOADING and self.reader is self:
            _metadata[bucket] = self
            _spawn(self._load)

    def _load(self):
        try:
            with ui.silent_thread():
                text = s3.get_text(scrape_plan.metadata_key(self.bucket))
            result = metafilter.index(json.loads(text), self.bucket)
        except (Exception, SystemExit):  # missing, unreadable or not JSON: no metadata
            result = None
        self.done.put(result)

    def get(self):
        """The index, None when there is none, or LOADING. Never waits."""
        if self.result is LOADING and self.reader is not self:
            self.result = self.reader.get()
        elif self.result is LOADING:
            try:
                self.result = self.done.get_nowait()
            except queue.Empty:
                return LOADING
            if self.result is not None:
                _metadata[self.bucket] = self.result
            elif _metadata.get(self.bucket) is self:
                del _metadata[self.bucket]
        return self.result
