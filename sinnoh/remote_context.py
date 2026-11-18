"""Read linked-thread measurements from T3 Desktop's own connection cache."""
import io
import json
import logging
import os
from pathlib import Path
import sys

from .paths import atomic_write


def profile_store():
    if sys.platform == "darwin":
        base = Path.home() / "Library/Application Support"
    elif sys.platform == "win32":
        base = Path(os.environ["APPDATA"])
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "t3code-v2/IndexedDB/t3code_app_0.indexeddb.leveldb"


def percentage(used, maximum):
    if type(used) is int and type(maximum) is int and used >= 0 and maximum > 0:
        return min(100, (200 * used + maximum) // (2 * maximum))
    return None


def snapshot_percent(snapshot, env, thread):
    if snapshot.get("environmentId") != env or snapshot.get("threadId") != thread:
        return None
    projection = snapshot["snapshot"]["projection"]
    owner = projection["thread"]
    if owner.get("id") != thread:
        return None
    active = owner.get("activeProviderThreadId")
    turns = [turn["tokenUsage"] for turn in projection.get("providerTurns", [])
             if (not active or turn.get("providerThreadId") == active) and turn.get("tokenUsage")]
    if turns:
        latest = max(turns, key=lambda turn: turn.get("updatedAt", ""))
        return percentage(latest.get("usedTokens"), latest.get("maxTokens"))
    for provider in projection.get("providerThreads", []):
        if active and provider.get("id") == active:
            usage = provider.get("contextUsage") or {}
            return percentage(usage.get("usedTokens"), usage.get("maxTokens"))
    return None


def latest_records(records, prefixes):
    """Resolve updates and tombstones before opening any thread payloads."""
    latest = {}
    for rec in records:
        key = rec.user_key
        if key.startswith(prefixes) and (key not in latest or rec.seq > latest[key].seq):
            latest[key] = rec
    return latest


def read_value(db, key, record, external, blob_dir, db_id):
    from ccl_chromium_reader import ccl_chromium_indexeddb as idb
    from ccl_chromium_reader.serialization_formats import ccl_v8_value_deserializer as v8
    from cramjam import snappy

    stream = io.BytesIO(record.value)
    idb.read_le_varint(stream)  # IndexedDB object-store version
    value = stream.read()
    if value.startswith(b"\xff\x11\x01"):
        # Chromium externalizes large serialized values. Use the live external-object
        # record for this exact key, never an older blob left behind after compaction.
        if not external or not external.value:
            return None
        info = idb.IndexedDBExternalObject.from_stream(io.BytesIO(external.value))
        number = info.blob_number
        if number is None:
            return None
        file = blob_dir / f"{db_id:x}/{(number >> 8) & 255:02x}/{number:x}"
        value = file.read_bytes()
        if len(value) != info.size:
            return None
    if value.startswith(b"\xff\x11\x02"):
        value = bytes(snappy.decompress_raw(value[3:]))
    if value[:2] == b"\xff\x11":
        return None
    # With the single string unwrapped, CCL handles Blink/V8 version and encoding.
    _, payload, _, _ = db.read_record_precursor(key, db_id, 0, value, None)
    return json.loads(v8.Deserializer(payload, host_object_delegate=None).read())


def recent_visits(db, records, store, db_id, blob_dir, local_env):
    from ccl_chromium_reader import ccl_chromium_indexeddb as idb

    visits = {}
    data = db.make_prefix(db_id, store, 1)
    blobs = db.make_prefix(db_id, store, 3)
    for raw, rec in records.items():
        if not raw.startswith(data) or not rec.value:
            continue
        suffix = raw[len(data):]
        key = idb.IdbKey(suffix)
        if key.value == local_env:
            continue
        try:
            envelope = read_value(db, key, rec, records.get(blobs + suffix), blob_dir, db_id)
            if not envelope or envelope.get("environmentId") != key.value:
                continue
            for thread in envelope["snapshot"]["threads"]:
                visited = thread.get("lastVisitedAt") or thread.get("updatedAt")
                if isinstance(visited, str):
                    visits[key.value, thread["id"]] = visited
        except (ValueError, OSError, TypeError, KeyError, IndexError, EOFError):
            continue
    return visits


def remote_rows(root, local_env):
    from ccl_chromium_reader import ccl_chromium_indexeddb as idb

    store_path = profile_store()
    if not store_path.is_dir():
        return []
    blob_dir = store_path.with_suffix(".blob")
    cache_file = root / "caches/sinnoh-lake/context-index-v1.json"
    try:
        old = json.loads(cache_file.read_bytes())
    except (ValueError, OSError):
        old = {}
    if not isinstance(old, dict):
        old = {}
    current = {}
    rows = []
    with idb.IndexedDb(store_path, blob_dir) as db:
        db_id = next((d.dbid_no for d in db.global_metadata.db_ids
                      if d.name == "t3code:connection-runtime"), None)
        if db_id is None:
            return []
        count = db.get_database_metadata(db_id, idb.DatabaseMetadataType.MaximumObjectStoreId)
        stores = {db.get_object_store_metadata(db_id, i, idb.ObjectStoreMetadataType.StoreName): i
                  for i in range(1, count + 1)}
        if "thread" not in stores:
            return []
        store = stores["thread"]
        data = db.make_prefix(db_id, store, 1)
        blobs = db.make_prefix(db_id, store, 3)
        # CCL's public iterator decodes historical values before yielding their
        # sequence numbers. Reconcile its raw records first to avoid stale readings.
        prefixes = [data, blobs]
        if "shell" in stores:
            prefixes.extend(db.make_prefix(db_id, stores["shell"], typ) for typ in (1, 3))
        records = latest_records(db._fetched_records, tuple(prefixes))
        visits = (recent_visits(db, records, stores["shell"], db_id, blob_dir, local_env)
                  if "shell" in stores else {})
        for raw, rec in records.items():
            if not raw.startswith(data) or not rec.value:
                continue
            suffix = raw[len(data):]
            key = idb.IdbKey(suffix)
            if not isinstance(key.value, str):
                continue
            env, _, thread = key.value.partition(":")
            if env == local_env or not env or not thread:
                continue
            external = records.get(blobs + suffix)
            stamp = [rec.seq, external.seq if external else None]
            cached = old.get(key.value)
            if isinstance(cached, list) and len(cached) == 3 and cached[:2] == stamp:
                result = cached[2]
            else:
                try:
                    snapshot = read_value(db, key, rec, external, blob_dir, db_id)
                    if not isinstance(snapshot, dict):
                        continue
                    result = snapshot_percent(snapshot, env, thread)
                except (ValueError, OSError, TypeError, KeyError, IndexError, EOFError):
                    continue  # Chromium may replace a blob during the scan. Retry next tick.
            current[key.value] = [*stamp, result]
            if type(result) is int and 0 <= result <= 100:
                rows.append((visits.get((env, thread), ""), rec.seq, env, thread, result))
    if current != old:
        atomic_write(cache_file, json.dumps(current, separators=(",", ":")).encode())
    return [(env, thread, result) for _, _, env, thread, result in sorted(rows, reverse=True)]


def linked_readings(root, local_env):
    try:
        return remote_rows(root, local_env)
    except Exception as error:
        # The context/solar helpers must keep working if an Electron update changes
        # its cache format or the live DB is rotating. Never log snapshot contents.
        logging.warning("Linked context cache unavailable (%s)", type(error).__name__)
        return []
