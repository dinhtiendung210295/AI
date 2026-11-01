"""RPC timings without credentials, arguments or response contents."""
import json
import time
from contextlib import contextmanager


class Metrics:
    def __init__(self):
        self.rows = []

    @contextmanager
    def measure(self, model, method, record_count=None):
        row = dict(model=model, method=method, record_count=record_count)
        started = time.perf_counter()
        try:
            yield row
            row['success'] = True
        except Exception:
            row['success'] = False
            raise
        finally:
            row['elapsed_seconds'] = time.perf_counter() - started
            self.rows.append(row)

    def call(self, reader, model, method, args, kwargs=None):
        count = len(args[0]) if method == 'read' and args else None
        with self.measure(model, method, count) as row:
            value = reader.call(model, method, args, kwargs)
            row['result_bytes'] = len(json.dumps(value, ensure_ascii=False).encode('utf8'))
            if isinstance(value, list):
                row['result_records'] = len(value)
            return value
