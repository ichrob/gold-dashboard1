"""Bounded background dispatch: immediate input delivery, one newest pending job."""
import copy
import math
import threading
import time


class LatestWorker:
    def __init__(self):
        self.lock = threading.Lock()
        self.thread = None
        self.pending = None
        self.latest_clock = None
        self.state = dict(accepted=0, completed=0, failed=0, coalesced=0,
                          rejectedOlder=0, lastAcceptedAt=None, lastCompletedAt=None,
                          lastError=None, processing=False, lastSourceAt=None,
                          lastCompletedSourceAt=None, lastDurationMs=None)

    def submit(self, bundle, process, deliver=lambda bundle: None):
        snapshot = copy.deepcopy(bundle)
        clock = snapshot.get('fetched_at')
        clock = clock if type(clock) in (int, float) and math.isfinite(clock) else None
        with self.lock:
            if clock is not None and self.latest_clock is not None and clock < self.latest_clock:
                self.state['rejectedOlder'] += 1
                return False
            # These are bounded enqueue operations, never DB/network evaluation.
            # Serialize delivery so an older HTTP request cannot overwrite newer inputs.
            deliver(snapshot)
            if self.pending is not None:
                self.state['coalesced'] += 1
            self.pending = (snapshot, process)
            if clock is not None:
                self.latest_clock = clock
            self.state.update(accepted=self.state['accepted']+1, lastAcceptedAt=time.time(),
                              lastSourceAt=(snapshot.get('spots') or {}).get('spot_price_as_of'))
            if self.thread is None or not self.thread.is_alive():
                self.thread = threading.Thread(target=self._run, name='bob-background-evaluation', daemon=True)
                try:
                    self.thread.start()
                except Exception:
                    self.thread = None
                    self.pending = None
                    raise
            return True

    def _run(self):
        while True:
            with self.lock:
                if self.pending is None:
                    self.thread = None
                    self.state['processing'] = False
                    return
                bundle, process = self.pending
                self.pending = None
                self.state['processing'] = True
            started = time.monotonic()
            try:
                process(bundle)
            except Exception as exc:
                with self.lock:
                    self.state.update(failed=self.state['failed']+1, lastError=type(exc).__name__)
                print('BOB_BACKGROUND_WORKER error='+type(exc).__name__, flush=True)
            else:
                with self.lock:
                    self.state.update(completed=self.state['completed']+1,
                                      lastCompletedAt=time.time(), lastError=None,
                                      lastCompletedSourceAt=(bundle.get('spots') or {}).get('spot_price_as_of'))
            finally:
                with self.lock:
                    self.state['lastDurationMs'] = round((time.monotonic()-started)*1000)

    def status(self):
        with self.lock:
            return dict(self.state, pending=self.pending is not None,
                        scope='accepted-inputs-and-completed-jobs-not-push-delivery')


worker = LatestWorker()
