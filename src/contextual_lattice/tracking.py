"""Immutable run registration and hash chained append-only lifecycle events."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      default=str, allow_nan=False).encode('utf-8')


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _file_record(path: str | Path) -> dict:
    resolved = Path(path).resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f'not a file: {resolved}')
    return {'path': str(resolved), 'sha256': file_sha256(resolved), 'bytes': resolved.stat().st_size}


def write_frozen_manifest(run_directory: str | Path, config: Mapping,
                          source_paths: Mapping[str, str | Path]) -> dict:
    """Reserve a new run directory and record configuration and source bytes.

    Call before any fitting. Existing directories are never reused, even when
    their names match the same hypothesis.
    """
    if not config or not source_paths:
        raise ValueError('nonempty frozen config and source files required')
    sources = {name: _file_record(path) for name, path in sorted(source_paths.items())}
    frozen_config = json.loads(_canonical(config))
    directory = Path(run_directory)
    directory.mkdir(parents=True, exist_ok=False)
    manifest = {'schema_version': 1, 'config': frozen_config, 'config_sha256': _hash(frozen_config),
                'sources': sources, 'lifecycle': [{'stage': 'frozen_before_fit'}]}
    with (directory / 'manifest.json').open('x', encoding='utf-8') as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write('\n')
    frozen = {'stage': 'frozen_before_fit', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
              'config_sha256': manifest['config_sha256'],
              'source_sha256': {name: item['sha256'] for name, item in sources.items()},
              'previous_event_sha256': None}
    frozen['event_sha256'] = _hash(frozen)
    with (directory / 'events.jsonl').open('x', encoding='utf-8') as handle:
        handle.write(_canonical(frozen).decode('utf-8') + '\n')
    return manifest


def append_lifecycle_event(run_directory: str | Path, stage: str,
                           output_paths: Mapping[str, str | Path] | None = None,
                           *, details: Mapping | None = None) -> dict:
    """Add a unique stage after validating the frozen source and event chain."""
    directory = Path(run_directory)
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    events_path = directory / 'events.jsonl'
    events = [json.loads(line) for line in events_path.read_text(encoding='utf-8').splitlines()]
    if not events or events[0]['config_sha256'] != manifest['config_sha256'] or _hash(manifest['config']) != manifest['config_sha256']:
        raise ValueError('frozen configuration integrity failure')
    for i, event in enumerate(events):
        without_hash = {k: v for k, v in event.items() if k != 'event_sha256'}
        if _hash(without_hash) != event.get('event_sha256'):
            raise ValueError('lifecycle event integrity failure')
        if i and event.get('previous_event_sha256') != events[i - 1]['event_sha256']:
            raise ValueError('lifecycle event chain failure')
    if not stage or any(event['stage'] == stage for event in events):
        raise ValueError('lifecycle stage already recorded or empty')
    for source in manifest['sources'].values():
        if file_sha256(source['path']) != source['sha256']:
            raise ValueError('frozen source changed after registration')
    outputs = {name: _file_record(path) for name, path in sorted((output_paths or {}).items())}
    event = {'stage': stage, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
             'config_sha256': manifest['config_sha256'], 'outputs': outputs,
             'details': json.loads(_canonical(details or {})),
             'previous_event_sha256': events[-1]['event_sha256']}
    event['event_sha256'] = _hash(event)
    with events_path.open('a', encoding='utf-8') as handle:
        handle.write(_canonical(event).decode('utf-8') + '\n')
    return event
