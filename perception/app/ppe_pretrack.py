"""Helmet / vest boxes taken before nvtracker (pure Python, 3.6-compatible, no DeepStream imports).

nvtracker drops the helmet / vest objects (only person boxes come out of it), so the app reads them on the
nvtracker sink pad and hands them to the OSD probe of the same frame. A frame is matched by key = (frame_num, pts).
assign_ppe then gives each item to at most one person seen in that frame; with nobody in the frame nothing counts.
"""
import threading
from collections import OrderedDict

from ppe_assign import assign_ppe


class PreTrackerPpe(object):
    def __init__(self, keep=30):
        self._lock = threading.Lock()
        self._frames = OrderedDict()   # key -> (helmets, vests), oldest first
        self.keep = keep
        self.missed = 0                # OSD frames that found no entry (should stay 0)

    def put(self, key, helmets, vests):
        """Boxes (left, top, width, height) seen before the tracker in frame key."""
        with self._lock:
            self._frames[key] = (list(helmets), list(vests))
            while len(self._frames) > self.keep:
                self._frames.popitem(last=False)

    def take(self, key):
        """(helmets, vests) of frame key; entries older than key are dropped. ([], []) if key is unknown."""
        with self._lock:
            if key not in self._frames:
                self.missed += 1
                return [], []
            while True:
                k, v = self._frames.popitem(last=False)
                if k == key:
                    return v

    def assign(self, key, persons):
        """take(key) + assign_ppe: ({person key: (has_helmet, has_vest)}, helmets, vests). persons = [(key, box)]."""
        helmets, vests = self.take(key)
        return assign_ppe(persons, helmets, vests), helmets, vests
