from src.utils.time import iso


def ledger_batch(item, latest=None):
    return {
        "id": item.id, "name": item.name, "version": item.version,
        "parent_batch_id": item.parent_batch_id,
        "machine_filename": item.machine_filename, "caliper_filename": item.caliper_filename,
        "machine_count": item.machine_count, "caliper_count": item.caliper_count,
        "window_seconds": item.window_seconds, "checksum": item.checksum,
        "author": item.author, "created_at": iso(item.created_at),
        "latest_snapshot_id": latest.id if latest else None,
        "confident_count": latest.confident_count if latest else None,
        "review_pair_count": latest.review_pair_count if latest else None,
        "pending_count": latest.pending_count if latest else None,
    }


def snapshot(item):
    return {
        "id": item.id, "ledger_batch_id": item.ledger_batch_id, "version": item.version,
        "window_seconds": item.window_seconds, "confident_count": item.confident_count,
        "review_pair_count": item.review_pair_count, "pending_count": item.pending_count,
        "checksum": item.checksum, "author": item.author, "created_at": iso(item.created_at),
        "result": item.result,
    }
