"""Local OS lock shared by production migration writers; no database mutations."""
import os
import json
from pathlib import Path

class ProductionWriteLock:
    def __init__(self,directory):
        self.handle=None
        path=Path(directory)/'py19-main-33843450.production-write.lock'
        path.parent.mkdir(parents=True,exist_ok=True)
        handle=path.open('a+b')
        if path.stat().st_size==0:handle.write(b'1');handle.flush()
        handle.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            handle.close();raise RuntimeError('Another production migration writer holds the database lock')
        self.handle=handle
    def close(self):
        if self.handle is not None:self.handle.close();self.handle=None
    def __del__(self):self.close()

def acquire(directory):
    # Cooperative handoff is checked before opening/acquiring the lock. The
    # active group always finishes first; no in-flight RPC is interrupted.
    request=Path(directory)/'phases/stop-short-so-runner.json'
    if request.exists():
        data=json.loads(request.read_text(encoding='utf8'))
        if data.get('pid')==os.getpid():
            raise RuntimeError('Cooperative handoff requested for this SO process')
    return ProductionWriteLock(directory)
