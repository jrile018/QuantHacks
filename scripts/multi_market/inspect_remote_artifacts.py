"""Inspect Parquet metadata only; no large row scan or market result."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def inspect(root: Path) -> dict:
    import pyarrow.parquet as pq

    result = {}
    for relative in ('gm-ingest/prices.parquet', 'gm-features/features.parquet',
                     'gm-boundaries/scores.parquet', 'gm-geometry/regime.parquet',
                     'gm-signals/spreads.parquet'):
        path = root / relative
        if not path.is_file():
            result[relative] = {'status': 'missing'}
            continue
        parquet = pq.ParquetFile(path)
        dates = []
        for group_index in range(parquet.metadata.num_row_groups):
            group = parquet.metadata.row_group(group_index)
            for column_index in range(group.num_columns):
                column = group.column(column_index)
                stats = column.statistics
                if column.path_in_schema in {'date', 'session_date'} and stats and stats.has_min_max:
                    dates.extend((str(stats.min), str(stats.max)))
        result[relative] = {'status': 'metadata_verified', 'bytes': path.stat().st_size,
                            'rows': parquet.metadata.num_rows,
                            'row_groups': parquet.metadata.num_row_groups,
                            'schema': str(parquet.schema_arrow),
                            'minimum_date_stat': min(dates) if dates else None,
                            'maximum_date_stat': max(dates) if dates else None}
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    results = inspect(args.run_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(results, indent=2))
