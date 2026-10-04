"""Offline, bounded clock packet generation; no source acquisition or consumer edits."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.reit_publication_clocks import build_packet, build_peer_packet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collection-manifest', required=True)
    parser.add_argument('--snapshot-sources')
    parser.add_argument('--peer-manifest')
    parser.add_argument('--broker-receipts')
    parser.add_argument('--source-grades')
    parser.add_argument('--project-root',default=str(ROOT),help='Runtime checkout/data root; defaults to this script checkout')
    parser.add_argument('--origin-project-root',help='Opt-in absolute Windows project root recorded in original input references')
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--review-at-utc', default=datetime.now(timezone.utc).isoformat())
    args = parser.parse_args()
    if args.peer_manifest:
        if not args.broker_receipts:
            parser.error('--peer-manifest requires --broker-receipts')
        result = build_peer_packet(args.peer_manifest,args.broker_receipts,args.collection_manifest,args.output_dir,
            root=args.project_root,review_at_utc=args.review_at_utc,source_grades=args.source_grades,
            origin_project_root=args.origin_project_root)
    else:
        if not args.snapshot_sources:
            parser.error('current packet requires --snapshot-sources')
        result = build_packet(args.collection_manifest,args.snapshot_sources,args.output_dir,
                              root=args.project_root,review_at_utc=args.review_at_utc,
                              origin_project_root=args.origin_project_root)
    print(json.dumps({key:result[key] for key in ('row_count','issuer_count','accession_count',
        'replay_proxy_candidate_count','observed_ready_count','actual_first_public_known_count',
        'exclusion_counts','outputs','supported_mode')},indent=2))


if __name__ == '__main__':
    main()
