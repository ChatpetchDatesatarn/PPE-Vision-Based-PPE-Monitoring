"""Steady helmet / vest status per person (pure Python, 3.6-compatible, no DeepStream imports).

For each person (by uid) keep, for the last `window` frames in which that person was seen, whether a helmet /
vest was assigned to them in that frame (ppe_assign). The status of each item is then:
- True  (✓) when the item was there in at least `on_frac` of the frames in the window
- False (✗) when it was there in less than `off_frac`
- in between: the previous status is kept (hysteresis); a person with no status yet stays None
- None  (?) while the person has been seen in fewer than `min_frames` frames
Frames where the person is hidden are not added (the status stays as it was).
"""
from collections import deque

WINDOW = 20
ON_FRAC = 0.30
OFF_FRAC = 0.10
MIN_FRAMES = 8


class _Track(object):
    __slots__ = ("h", "v", "h_state", "v_state")

    def __init__(self, window):
        self.h = deque(maxlen=window)
        self.v = deque(maxlen=window)
        self.h_state = None
        self.v_state = None


class PpeSmoother(object):
    def __init__(self, window=WINDOW, on_frac=ON_FRAC, off_frac=OFF_FRAC, min_frames=MIN_FRAMES):
        self.window = window
        self.on_frac = on_frac
        self.off_frac = off_frac
        self.min_frames = min_frames
        self.tracks = {}    # uid -> _Track

    def _decide(self, hist, prev):
        n = len(hist)
        if n < self.min_frames:
            return None
        frac = sum(hist) / float(n)
        if frac >= self.on_frac - 1e-9:
            return True
        if frac < self.off_frac - 1e-9:
            return False
        return prev

    def update(self, uid, has_helmet, has_vest):
        """Add one frame in which person uid was seen. Returns (helmet, vest), each True / False / None.
        has_helmet / has_vest None = that item could not be judged in this frame (person seen only in part): its
        history and state are left as they were; the other item is updated as usual."""
        tr = self.tracks.get(uid)
        if tr is None:
            tr = self.tracks[uid] = _Track(self.window)
        if has_helmet is not None:
            tr.h.append(1 if has_helmet else 0)
            tr.h_state = self._decide(tr.h, tr.h_state)
        if has_vest is not None:
            tr.v.append(1 if has_vest else 0)
            tr.v_state = self._decide(tr.v, tr.v_state)
        return tr.h_state, tr.v_state

    def status(self, uid):
        """Last (helmet, vest) of uid without adding a frame; (None, None) for an unknown uid."""
        tr = self.tracks.get(uid)
        return (tr.h_state, tr.v_state) if tr is not None else (None, None)

    def forget(self, keep_uids):
        """Drop every uid not in keep_uids (people who left the frame)."""
        keep = set(keep_uids)
        for uid in list(self.tracks):
            if uid not in keep:
                del self.tracks[uid]
