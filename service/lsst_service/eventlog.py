"""Append-only, checksummed, triple-copy event log.

Requirements: REQ-DAT-001 .. REQ-DAT-006 (docs/02-requirements.md).

Record format (one per line, newline terminated, identical to the browser build):
    [seq, type, payload, prev_crc, crc]
where crc = CRC-32 (IEEE) of the JSON text of [seq, type, payload, prev_crc].
The JSON text must match JavaScript's JSON.stringify byte for byte, so it is
written with compact separators and without ASCII escaping.

Write protocol for one record:
    1. serialize and checksum in memory
    2. append the full line to every copy with a single write() each
    3. fsync() each copy before moving to the next
    4. only then return to the caller (the UI never shows unsynced state)
"""
from __future__ import annotations

import json
import os
import random
import time
import zlib
from dataclasses import dataclass, field

GENESIS_PREV = "00000000"


def js_compatible(obj):
    """Match JavaScript's JSON.stringify for numbers: 5.0 is written as 5.

    Records written here are re-serialised and checksummed by the UI (REQ-VER-003); without
    this, any whole-number float from Python would fail the UI's CRC check."""
    if isinstance(obj, float) and obj.is_integer() and abs(obj) < 2 ** 53:
        return int(obj)
    if isinstance(obj, dict):
        return {k: js_compatible(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [js_compatible(v) for v in obj]
    return obj


def dumps(obj) -> str:
    return json.dumps(js_compatible(obj), separators=(",", ":"), ensure_ascii=False)


def crc_hex(text: str) -> str:
    return format(zlib.crc32(text.encode("utf-8")) & 0xFFFFFFFF, "08x")


def make_line(seq: int, rtype: str, payload, prev: str) -> str:
    body = dumps([seq, rtype, payload, prev])
    return dumps([seq, rtype, payload, prev, crc_hex(body)])


def parse_line(line: str):
    """Return a record dict, or None if the line is torn or fails its checksum."""
    try:
        a = json.loads(line)
    except (ValueError, TypeError):
        return None
    if not isinstance(a, list) or len(a) != 5:
        return None
    if crc_hex(dumps(a[:4])) != a[4]:
        return None
    return {"seq": a[0], "type": a[1], "payload": a[2], "prev": a[3], "crc": a[4], "line": line}


def _fsync_dir(path: str) -> None:
    try:
        fd = os.open(os.path.dirname(os.path.abspath(path)) or ".", os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write(path: str, text: str) -> None:
    """Write a whole file so that a crash leaves either the old or the new version."""
    tmp = f"{path}.tmp-{os.getpid()}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, text.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, path)
    _fsync_dir(path)


def read_text(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return f.read().decode("utf-8", errors="replace")
    except FileNotFoundError:
        return ""


@dataclass
class RecoveryReport:
    copies: list = field(default_factory=list)
    repaired: int = 0
    unrecoverable: list = field(default_factory=list)
    torn: int = 0
    corrupt: int = 0
    chain_breaks: int = 0
    uncommitted: int = 0
    votes: int = 0
    total: int = 0

    def as_dict(self) -> dict:
        return {
            "copies": self.copies, "repaired": self.repaired, "unrecoverable": self.unrecoverable,
            "torn": self.torn, "corrupt": self.corrupt, "chainBreaks": self.chain_breaks,
            "uncommitted": self.uncommitted, "votes": self.votes, "total": self.total,
        }


class EventLog:
    def __init__(self, copy_paths: list[str], state_dir: str):
        if len(copy_paths) < 3:
            raise ValueError("REQ-DAT-003 needs three log copies")
        self.paths = list(copy_paths)
        self.state_dir = state_dir
        os.makedirs(state_dir, exist_ok=True)
        for p in self.paths:
            os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
        self.records: list[dict] = []
        self.last_crc = GENESIS_PREV

    # ---------- markers ----------
    def _marker(self, name: str) -> str:
        return os.path.join(self.state_dir, name)

    def is_init(self) -> bool:
        return read_text(self._marker("init")).strip() == "1"

    def mark_init(self) -> None:
        atomic_write(self._marker("init"), "1")

    def alive(self) -> None:
        atomic_write(self._marker("alive"), str(int(time.time() * 1000)))

    def last_alive(self) -> int:
        try:
            return int(read_text(self._marker("alive")).strip() or 0)
        except ValueError:
            return 0

    # ---------- write path ----------
    def _append_raw(self, path: str, data: bytes) -> None:
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            size = os.fstat(fd).st_size
            if size > 0:
                # defensive: never glue a new record onto a torn, unterminated tail
                with open(path, "rb") as f:
                    f.seek(size - 1)
                    if f.read(1) != b"\n":
                        data = b"\n" + data
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        if size == 0:
            _fsync_dir(path)

    def append(self, rtype: str, payload) -> dict:
        seq = (self.records[-1]["seq"] if self.records else 0) + 1
        line = make_line(seq, rtype, payload, self.last_crc)
        data = (line + "\n").encode("utf-8")
        for p in self.paths:
            self._append_raw(p, data)
        rec = parse_line(line)
        self.records.append(rec)
        self.last_crc = rec["crc"]
        return rec

    # ---------- recovery ----------
    def recover(self) -> RecoveryReport:
        rep = RecoveryReport()
        copies = []
        for i, p in enumerate(self.paths):
            raw = read_text(p)
            lines = raw.split("\n")
            if lines and lines[-1] == "":
                lines.pop()
            parsed = [parse_line(l) for l in lines]
            ok = sum(1 for x in parsed if x)
            torn = 1 if parsed and parsed[-1] is None else 0
            bad = len(parsed) - ok - torn
            rep.copies.append({"name": "ABC"[i] if i < 3 else str(i), "ok": ok, "bad": bad, "torn": torn})
            rep.torn += torn
            rep.corrupt += bad
            copies.append((p, raw, parsed))

        by_seq: dict[int, list[dict]] = {}
        max_seq = 0
        for _, _, parsed in copies:
            for r in parsed:
                if r and isinstance(r["seq"], int):
                    by_seq.setdefault(r["seq"], []).append(r)
                    max_seq = max(max_seq, r["seq"])

        accepted: list[dict] = []
        prev = GENESIS_PREV
        for s in range(1, max_seq + 1):
            cands = by_seq.get(s, [])
            # a tail record present in only one copy was never acknowledged: drop it
            if s == max_seq and len(cands) == 1 and s > 1 and len(self.paths) >= 3:
                rep.uncommitted = 1
                break
            if not cands:
                rep.unrecoverable.append(s)
                prev = None
                continue
            votes: dict[str, int] = {}
            for c in cands:
                votes[c["line"]] = votes.get(c["line"], 0) + 1
            if len(votes) > 1 or len(cands) < len(self.paths):
                rep.votes += 1
            best = max(votes, key=lambda k: votes[k])
            rec = next(c for c in cands if c["line"] == best)
            if prev is not None and rec["prev"] != prev:
                rep.chain_breaks += 1
            accepted.append(rec)
            prev = rec["crc"]

        canon = "".join(r["line"] + "\n" for r in accepted)
        for p, raw, _ in copies:
            if raw != canon:
                rep.repaired += 1
                atomic_write(p, canon)
        self.records = accepted
        self.last_crc = accepted[-1]["crc"] if accepted else GENESIS_PREV
        rep.total = len(accepted)
        return rep

    # ---------- A/B snapshots ----------
    def _snap_path(self, slot: str) -> str:
        return self._marker(f"snap.{slot}")

    def read_snapshot(self) -> dict:
        valid = {}
        for slot in ("A", "B"):
            try:
                o = json.loads(read_text(self._snap_path(slot)) or "null")
            except ValueError:
                o = None
            if isinstance(o, dict) and crc_hex(dumps([o.get("seq"), o.get("hash"), o.get("at")])) == o.get("crc"):
                valid[slot] = o
        ptr = read_text(self._marker("snap.ptr")).strip() or None
        pick = max(valid.values(), key=lambda o: o["seq"]) if valid else None
        return {"pick": pick, "ptr": ptr, "valid": sorted(valid), "ptrValid": ptr in valid}

    def write_snapshot(self, seq: int, state_hash: str) -> str:
        ptr = read_text(self._marker("snap.ptr")).strip()
        slot = "B" if ptr == "A" else "A"
        at = int(time.time() * 1000)
        atomic_write(self._snap_path(slot), dumps({"seq": seq, "hash": state_hash, "at": at,
                                                   "crc": crc_hex(dumps([seq, state_hash, at]))}))
        atomic_write(self._marker("snap.ptr"), slot)   # the flip is a single atomic rename
        return slot

    # ---------- fault injection (verification only, REQ-VER-002) ----------
    @staticmethod
    def _flip(line: str) -> str:
        if len(line) < 12:
            return line + "#"
        j = 6 + random.randrange(len(line) - 12)
        ch = line[j]
        rep = "3" if ch == "7" else "7" if ch.isdigit() else "a" if ch == "e" else "e"
        return line[:j] + rep + line[j + 1:]

    def corrupt(self, copy_idx: int, line_idx: int | None = None):
        p = self.paths[copy_idx]
        lines = read_text(p).split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        if not lines:
            return None
        i = line_idx if line_idx is not None else random.randrange(max(1, len(lines) - 1))
        i = max(0, min(i, len(lines) - 1))
        lines[i] = self._flip(lines[i])
        atomic_write(p, "".join(l + "\n" for l in lines))
        return i

    def corrupt_snapshot(self):
        ptr = read_text(self._marker("snap.ptr")).strip()
        if ptr:
            atomic_write(self._snap_path(ptr), '{"seq":1,')
        return ptr or None

    def torn_append(self, rtype: str, payload) -> int:
        """Simulate power loss mid-append: copy A complete, copy B half written, copy C untouched."""
        seq = (self.records[-1]["seq"] if self.records else 0) + 1
        line = make_line(seq, rtype, payload, self.last_crc)
        self._append_raw(self.paths[0], (line + "\n").encode("utf-8"))
        self._append_raw(self.paths[1], line[: len(line) // 2].encode("utf-8"))
        return seq

    def wipe(self) -> None:
        for p in self.paths:
            atomic_write(p, "")
        for slot in ("A", "B"):
            atomic_write(self._snap_path(slot), "")
        self.records = []
        self.last_crc = GENESIS_PREV

    def line_counts(self) -> list[int]:
        out = []
        for p in self.paths:
            raw = read_text(p)
            out.append(len([l for l in raw.split("\n") if l != ""]))
        return out
