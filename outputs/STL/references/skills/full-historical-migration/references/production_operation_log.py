"""Durable append-only operations. Callers must hold the production writer lock."""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


class OperationLog:
    def __init__(self, directory, identity):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'operations.jsonl'
        self.identity = identity
        self.events = self.replay()

    def _signature(self):
        if not self.path.exists():return None
        stat=self.path.stat()
        return (stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)

    def replay(self):
        events = []
        if not self.path.exists():
            self._validated_signature=None
            return events
        raw = self.path.read_bytes()
        if raw and not raw.endswith(b'\n'):
            raise RuntimeError('Incomplete operation log; readback recovery required')
        for line in raw.splitlines():
            event = json.loads(line)
            if event['identity'] != self.identity or event['sequence'] != len(events) + 1:
                raise RuntimeError('Operation log identity or sequence conflict')
            previous = events[-1]['hash'] if events else None
            actual = event.pop('hash')
            if event['previous_hash'] != previous or actual != self._hash(event):
                raise RuntimeError('Operation log checksum conflict')
            event['hash'] = actual
            events.append(event)
        self._states(events)
        self._validated_signature=self._signature()
        if self._validated_signature[0]!=len(raw):raise RuntimeError('Operation log changed during replay')
        return events

    @staticmethod
    def _hash(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf8')).hexdigest()

    @staticmethod
    def _states(events):
        states = {}
        for event in events:
            oid = event['operation_id']
            if event['kind'] == 'intent':
                if oid in states:
                    raise RuntimeError('Duplicate operation intent')
            elif event['kind'] not in ('result', 'uncertain') or oid not in states or states[oid]['kind'] == 'result':
                raise RuntimeError('Invalid operation transition')
            states[oid] = event
        return states

    def _append(self, kind, operation_id, payload):
        # Detect an external append before writing; the OS lock remains mandatory.
        # Full checksum replay runs at construction, group handoff and each
        # checkpoint. While holding the OS writer lock, unchanged file size and
        # nanosecond timestamps prove there was no intervening external write;
        # replay immediately if any signature component changes.
        if self._signature()!=self._validated_signature:
            disk=self.replay()
            if disk!=self.events:raise RuntimeError('Operation log changed outside active writer')
        # Normalize JSON keys/tuples before hashing and retaining the in-memory
        # event. Otherwise integer map keys differ from replayed JSON strings.
        payload = json.loads(json.dumps(payload, ensure_ascii=False))
        event = dict(sequence=len(self.events) + 1, identity=self.identity,
                     previous_hash=self.events[-1]['hash'] if self.events else None,
                     utc=datetime.now(timezone.utc).isoformat(), kind=kind,
                     operation_id=operation_id, payload=payload)
        self._states(self.events + [event])
        event['hash'] = self._hash(event)
        encoded = (json.dumps(event, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf8')
        with self.path.open('ab') as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        self.events.append(event)
        self._validated_signature=self._signature()
        return event

    def append_intent(self, operation):
        if self.unresolved():
            raise RuntimeError('Unresolved operation blocks new mutation')
        return self._append('intent', operation['operation_id'], operation)

    def append_result(self, operation_id, result):
        return self._append('result', operation_id, result)

    def mark_uncertain(self, operation_id, error):
        return self._append('uncertain', operation_id, {'error': str(error)})

    def unresolved(self):
        return {oid: event for oid, event in self._states(self.events).items() if event['kind'] != 'result'}

    def build_checkpoint(self):
        disk=self.replay()
        if disk!=self.events:raise RuntimeError('Operation log changed before checkpoint')
        if self.unresolved():
            raise RuntimeError('Cannot checkpoint unresolved mutations')
        result = dict(identity=self.identity, sequence=len(self.events),
                      log_hash=self.events[-1]['hash'] if self.events else None,
                      operations=self._states(self.events))
        temp = self.directory / 'operations-checkpoint.json.tmp'
        with temp.open('w', encoding='utf8') as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(self.directory / 'operations-checkpoint.json')
        return result

    def assert_checkpoint_current(self):
        checkpoint = json.loads((self.directory / 'operations-checkpoint.json').read_text(encoding='utf8'))
        if self.unresolved() or checkpoint['identity'] != self.identity or checkpoint['sequence'] != len(self.events) or checkpoint['log_hash'] != (self.events[-1]['hash'] if self.events else None):
            raise RuntimeError('Legacy adapter checkpoint is stale or unresolved')
        return checkpoint
