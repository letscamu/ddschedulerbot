#!/usr/bin/env python3
"""
EstradaBot Feedback Processing Pipeline

Fetches user feedback from GCS (or local storage), processes it into
structured formats for dev review and agent consumption.

Usage:
    python tools/feedback_pipeline.py fetch                  # Fetch all unprocessed feedback
    python tools/feedback_pipeline.py fetch --all            # Fetch all feedback regardless of status
    python tools/feedback_pipeline.py fetch --category "Bug Report"
    python tools/feedback_pipeline.py fetch --since 2026-02-01
    python tools/feedback_pipeline.py mark <index> ingested  # Mark as ingested into dev session
    python tools/feedback_pipeline.py mark <index> actioned  # Mark as acted upon
    python tools/feedback_pipeline.py mark <index> closed    # Mark as closed
    python tools/feedback_pipeline.py create-issue <index>   # Create GitHub issue from entry
    python tools/feedback_pipeline.py create-issues          # Batch create issues for all unprocessed
    python tools/feedback_pipeline.py stats                  # Show feedback summary stats

Output:
    feedback/inbox.json   — Structured JSON for programmatic access
    feedback/brief.md     — Human-readable markdown brief for review

Environment:
    Reads storage config from .env (USE_LOCAL_STORAGE, GCS_BUCKET, etc.)
    Run from the repo root: python tools/feedback_pipeline.py fetch
"""

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

# Add parent dir so we can import backend modules
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Check for --prod flag before loading .env so we can override storage config
_use_prod = '--prod' in sys.argv
if _use_prod:
    os.environ['USE_LOCAL_STORAGE'] = 'false'
    os.environ['GCS_BUCKET'] = 'ddschedulerbot-files'
    print("[Pipeline] Using PRODUCTION GCS bucket: ddschedulerbot-files")

# Load .env if present (uses setdefault so --prod overrides above take priority)
_env_path = REPO_ROOT / '.env'
if _env_path.exists():
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, value = line.partition('=')
                os.environ.setdefault(key.strip(), value.strip())

from backend import gcs_storage

# Output directory
FEEDBACK_DIR = REPO_ROOT / 'feedback'
INBOX_JSON = FEEDBACK_DIR / 'inbox.json'
BRIEF_MD = FEEDBACK_DIR / 'brief.md'


def ensure_output_dir():
    """Create feedback output directory if it doesn't exist."""
    FEEDBACK_DIR.mkdir(exist_ok=True)


def fetch_feedback(args):
    """Fetch feedback from GCS and write to local output files."""
    print("[Pipeline] Fetching feedback from storage...")
    all_entries = gcs_storage.load_feedback()

    if not all_entries:
        print("[Pipeline] No feedback entries found.")
        return

    print(f"[Pipeline] Loaded {len(all_entries)} total entries")

    # Apply filters
    entries = all_entries
    if not args.all:
        # Default: only unprocessed (no dev_status or dev_status == 'unprocessed')
        entries = [e for e in entries
                   if e.get('dev_status', 'unprocessed') == 'unprocessed']

    if args.category:
        entries = [e for e in entries
                   if e.get('category', '').lower() == args.category.lower()]

    if args.status:
        entries = [e for e in entries
                   if e.get('status', '').lower() == args.status.lower()]

    if args.since:
        try:
            since_dt = datetime.fromisoformat(args.since)
            entries = [e for e in entries
                       if datetime.fromisoformat(e.get('submitted_at', '')) >= since_dt]
        except ValueError:
            print(f"[Pipeline] Invalid date format: {args.since} (use YYYY-MM-DD)")
            sys.exit(1)

    if args.priority:
        entries = [e for e in entries
                   if e.get('priority', '').lower() == args.priority.lower()]

    # Sort newest first
    entries.sort(key=lambda e: e.get('submitted_at', ''), reverse=True)

    print(f"[Pipeline] {len(entries)} entries after filtering")

    if not entries:
        print("[Pipeline] No entries match the filter criteria.")
        return

    ensure_output_dir()

    # Build inbox with original indices for mark-back operations
    inbox = []
    for entry in entries:
        # Find original index in full list
        orig_idx = all_entries.index(entry)
        inbox_entry = {
            'pipeline_index': orig_idx,
            **entry
        }
        inbox.append(inbox_entry)

    # Write JSON output
    output = {
        'fetched_at': datetime.now().isoformat(),
        'total_in_storage': len(all_entries),
        'filtered_count': len(entries),
        'filters_applied': {
            'all': args.all,
            'category': args.category,
            'status': args.status,
            'since': args.since,
            'priority': args.priority,
        },
        'entries': inbox,
    }

    with open(INBOX_JSON, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"[Pipeline] Wrote {INBOX_JSON}")

    # Write markdown brief
    brief = generate_brief(output)
    with open(BRIEF_MD, 'w') as f:
        f.write(brief)
    print(f"[Pipeline] Wrote {BRIEF_MD}")

    # Mark fetched entries as ingested in GCS
    if not args.no_mark:
        mark_ingested(all_entries, entries)

    print(f"\n[Pipeline] Done. Review feedback in:")
    print(f"  Markdown: {BRIEF_MD}")
    print(f"  JSON:     {INBOX_JSON}")


def generate_brief(output: dict) -> str:
    """Generate a human-readable markdown brief from fetched feedback."""
    entries = output['entries']
    now = datetime.now().strftime('%Y-%m-%d %H:%M')

    lines = [
        f"# EstradaBot Feedback Brief",
        f"",
        f"**Generated:** {now}  ",
        f"**Total in storage:** {output['total_in_storage']}  ",
        f"**Entries in this brief:** {output['filtered_count']}",
        f"",
    ]

    # Summary stats
    categories = Counter(e.get('category', 'Unknown') for e in entries)
    priorities = Counter(e.get('priority', 'Unknown') for e in entries)
    statuses = Counter(e.get('status', 'Unknown') for e in entries)
    pages = Counter(e.get('page', 'Not specified') for e in entries)

    lines.append("## Summary")
    lines.append("")
    lines.append("| Category | Count |")
    lines.append("|----------|-------|")
    for cat, count in categories.most_common():
        lines.append(f"| {cat} | {count} |")
    lines.append("")

    lines.append("| Priority | Count |")
    lines.append("|----------|-------|")
    for pri, count in priorities.most_common():
        lines.append(f"| {pri} | {count} |")
    lines.append("")

    lines.append("| Admin Status | Count |")
    lines.append("|--------------|-------|")
    for st, count in statuses.most_common():
        lines.append(f"| {st} | {count} |")
    lines.append("")

    if any(p and p != 'Not specified' for p in pages):
        lines.append("| Related Page | Count |")
        lines.append("|--------------|-------|")
        for pg, count in pages.most_common():
            if pg and pg != 'Not specified':
                lines.append(f"| {pg} | {count} |")
        lines.append("")

    # Group entries by category, then priority
    lines.append("---")
    lines.append("")
    lines.append("## Feedback Entries")
    lines.append("")

    priority_order = {'High': 0, 'Medium': 1, 'Low': 2}
    sorted_entries = sorted(entries,
                            key=lambda e: (priority_order.get(e.get('priority', 'Medium'), 1),
                                           e.get('submitted_at', '')))

    # Group by category
    by_category = {}
    for entry in sorted_entries:
        cat = entry.get('category', 'Other')
        by_category.setdefault(cat, []).append(entry)

    for cat in ['Bug Report', 'Feature Request', 'Data Issue',
                'UI/UX Improvement', 'Example File', 'Other']:
        if cat not in by_category:
            continue
        cat_entries = by_category[cat]
        lines.append(f"### {cat} ({len(cat_entries)})")
        lines.append("")

        for entry in cat_entries:
            idx = entry.get('pipeline_index', '?')
            priority = entry.get('priority', 'Medium')
            status = entry.get('status', 'New')
            dev_status = entry.get('dev_status', 'unprocessed')
            user = entry.get('username', 'unknown')
            page = entry.get('page', '')
            date = entry.get('submitted_at', '')[:10]
            message = entry.get('message', '').strip()

            priority_icon = {'High': '!!! ', 'Medium': '', 'Low': ''}
            lines.append(f"**[#{idx}]** {priority_icon.get(priority, '')}"
                         f"**{priority}** | {status} | dev:{dev_status} | "
                         f"by {user} on {date}"
                         f"{f' | page: {page}' if page else ''}")
            lines.append(f"> {message}")

            if entry.get('attachment'):
                att = entry['attachment']
                lines.append(f"> *Attachment: {att['filename']} "
                             f"({att.get('size', 0) // 1024}KB, {att.get('type', '')})*")

            lines.append("")

    # Agent processing section
    lines.append("---")
    lines.append("")
    lines.append("## Processing Notes")
    lines.append("")
    lines.append("Use `python tools/feedback_pipeline.py mark <index> <status>` "
                 "to update dev_status.")
    lines.append("")
    lines.append("| dev_status | Meaning |")
    lines.append("|------------|---------|")
    lines.append("| unprocessed | Not yet reviewed in a dev session |")
    lines.append("| ingested | Pulled into a dev session for review |")
    lines.append("| actioned | Changes made or issue created in response |")
    lines.append("| closed | No further action needed |")
    lines.append("")

    return '\n'.join(lines)


def mark_ingested(all_entries, fetched_entries):
    """Mark fetched entries as 'ingested' in GCS."""
    changed = False
    for entry in fetched_entries:
        if entry.get('dev_status', 'unprocessed') == 'unprocessed':
            # Find in all_entries by reference match
            idx = all_entries.index(entry)
            all_entries[idx]['dev_status'] = 'ingested'
            all_entries[idx]['dev_ingested_at'] = datetime.now().isoformat()
            changed = True

    if changed:
        _save_all(all_entries)
        print(f"[Pipeline] Marked fetched entries as 'ingested' in storage")


def mark_status(args):
    """Update the dev_status of a feedback entry."""
    valid_statuses = ['unprocessed', 'ingested', 'actioned', 'closed']
    if args.dev_status not in valid_statuses:
        print(f"[Pipeline] Invalid status '{args.dev_status}'. "
              f"Must be one of: {', '.join(valid_statuses)}")
        sys.exit(1)

    all_entries = gcs_storage.load_feedback()
    idx = args.index

    if idx < 0 or idx >= len(all_entries):
        print(f"[Pipeline] Index {idx} out of range (0-{len(all_entries) - 1})")
        sys.exit(1)

    entry = all_entries[idx]
    old_status = entry.get('dev_status', 'unprocessed')
    entry['dev_status'] = args.dev_status
    entry['dev_status_updated_at'] = datetime.now().isoformat()

    _save_all(all_entries)
    print(f"[Pipeline] Entry #{idx}: dev_status '{old_status}' -> '{args.dev_status}'")
    print(f"  Category: {entry.get('category')}")
    print(f"  Message:  {entry.get('message', '')[:80]}...")


def show_stats(args):
    """Show summary statistics for all feedback."""
    all_entries = gcs_storage.load_feedback()

    if not all_entries:
        print("[Pipeline] No feedback entries found.")
        return

    total = len(all_entries)
    categories = Counter(e.get('category', 'Unknown') for e in all_entries)
    priorities = Counter(e.get('priority', 'Unknown') for e in all_entries)
    admin_statuses = Counter(e.get('status', 'Unknown') for e in all_entries)
    dev_statuses = Counter(e.get('dev_status', 'unprocessed') for e in all_entries)

    print(f"\n{'='*50}")
    print(f"  EstradaBot Feedback Stats")
    print(f"  Total entries: {total}")
    print(f"{'='*50}")

    print(f"\n  By Category:")
    for cat, count in categories.most_common():
        print(f"    {cat:<25} {count:>3}")

    print(f"\n  By Priority:")
    for pri, count in priorities.most_common():
        print(f"    {pri:<25} {count:>3}")

    print(f"\n  By Admin Status:")
    for st, count in admin_statuses.most_common():
        print(f"    {st:<25} {count:>3}")

    print(f"\n  By Dev Pipeline Status:")
    for ds, count in dev_statuses.most_common():
        print(f"    {ds:<25} {count:>3}")

    # Actionable summary
    unprocessed = dev_statuses.get('unprocessed', 0)
    ingested = dev_statuses.get('ingested', 0)
    print(f"\n  Actionable: {unprocessed} unprocessed, {ingested} ingested (awaiting action)")
    print()


def create_issue(args):
    """Create a GitHub issue from a single feedback entry."""
    all_entries = gcs_storage.load_feedback()
    idx = args.index

    if idx < 0 or idx >= len(all_entries):
        print(f"[Pipeline] Index {idx} out of range (0-{len(all_entries) - 1})")
        sys.exit(1)

    entry = all_entries[idx]

    if entry.get('github_issue'):
        print(f"[Pipeline] Entry #{idx} already has GitHub issue: "
              f"#{entry['github_issue']['number']}")
        if not args.force:
            print("  Use --force to create another issue anyway.")
            return

    issue_url = _create_gh_issue(entry, idx)
    if issue_url:
        # Store issue link back on the feedback entry
        all_entries[idx]['github_issue'] = {
            'url': issue_url,
            'number': _parse_issue_number(issue_url),
            'created_at': datetime.now().isoformat(),
        }
        all_entries[idx]['dev_status'] = 'actioned'
        all_entries[idx]['dev_status_updated_at'] = datetime.now().isoformat()
        _save_all(all_entries)
        print(f"[Pipeline] Issue created: {issue_url}")
        print(f"[Pipeline] Entry #{idx} dev_status → 'actioned'")


def create_issues_batch(args):
    """Create GitHub issues for all unprocessed or ingested feedback entries."""
    all_entries = gcs_storage.load_feedback()

    eligible = []
    for i, entry in enumerate(all_entries):
        dev_status = entry.get('dev_status', 'unprocessed')
        if dev_status in ('unprocessed', 'ingested') and not entry.get('github_issue'):
            eligible.append((i, entry))

    if not eligible:
        print("[Pipeline] No eligible entries for issue creation.")
        return

    print(f"[Pipeline] Found {len(eligible)} entries to create issues for:")
    for i, entry in eligible:
        print(f"  #{i}: [{entry.get('category')}] {entry.get('message', '')[:60]}...")

    if not args.yes:
        confirm = input(f"\nCreate {len(eligible)} GitHub issues? [y/N] ").strip().lower()
        if confirm != 'y':
            print("[Pipeline] Aborted.")
            return

    created = 0
    for i, entry in eligible:
        issue_url = _create_gh_issue(entry, i)
        if issue_url:
            all_entries[i]['github_issue'] = {
                'url': issue_url,
                'number': _parse_issue_number(issue_url),
                'created_at': datetime.now().isoformat(),
            }
            all_entries[i]['dev_status'] = 'actioned'
            all_entries[i]['dev_status_updated_at'] = datetime.now().isoformat()
            created += 1

    _save_all(all_entries)
    print(f"\n[Pipeline] Created {created}/{len(eligible)} GitHub issues")


def _create_gh_issue(entry: dict, index: int) -> str:
    """Create a GitHub issue using the gh CLI. Returns issue URL or empty string."""
    category = entry.get('category', 'Other')
    priority = entry.get('priority', 'Medium')
    page = entry.get('page', '')
    user = entry.get('username', 'unknown')
    date = entry.get('submitted_at', '')[:10]
    message = entry.get('message', '')

    # Map category to label
    label_map = {
        'Bug Report': 'bug',
        'Feature Request': 'enhancement',
        'Data Issue': 'data',
        'UI/UX Improvement': 'ui',
        'Example File': 'data',
        'Other': 'feedback',
    }
    label = label_map.get(category, 'feedback')

    # Build title
    title_prefix = {
        'Bug Report': 'Bug',
        'Feature Request': 'Feature',
        'Data Issue': 'Data',
        'UI/UX Improvement': 'UI/UX',
        'Example File': 'Example',
        'Other': 'Feedback',
    }
    prefix = title_prefix.get(category, 'Feedback')
    # Truncate message for title
    title_msg = message.split('\n')[0][:60]
    title = f"[{prefix}] {title_msg}"

    # Build body
    body_lines = [
        f"## User Feedback (#{index})",
        f"",
        f"**Category:** {category}  ",
        f"**Priority:** {priority}  ",
        f"**Submitted by:** {user} on {date}  ",
    ]
    if page:
        body_lines.append(f"**Related page:** {page}  ")

    body_lines.extend([
        f"",
        f"### Description",
        f"",
        message,
        f"",
    ])

    if entry.get('attachment'):
        att = entry['attachment']
        body_lines.extend([
            f"### Attachment",
            f"- **File:** {att.get('filename', 'unknown')}",
            f"- **Type:** {att.get('type', 'unknown')}",
            f"- **Size:** {att.get('size', 0) // 1024} KB",
            f"- **Stored as:** `{att.get('stored_as', '')}`",
            f"",
        ])

    body_lines.extend([
        f"---",
        f"*Created from feedback pipeline entry #{index}*",
    ])

    body = '\n'.join(body_lines)

    # Build labels list
    labels = [label, f"priority:{priority.lower()}", "from-feedback"]

    try:
        cmd = [
            'gh', 'issue', 'create',
            '--title', title,
            '--body', body,
            '--label', ','.join(labels),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            url = result.stdout.strip()
            print(f"  Created: {url}")
            return url
        else:
            stderr = result.stderr.strip()
            # If labels don't exist, retry without labels
            if 'label' in stderr.lower():
                print(f"  Warning: Labels may not exist. Retrying without labels...")
                cmd_no_labels = [
                    'gh', 'issue', 'create',
                    '--title', title,
                    '--body', body,
                ]
                result2 = subprocess.run(cmd_no_labels, capture_output=True, text=True, timeout=30)
                if result2.returncode == 0:
                    url = result2.stdout.strip()
                    print(f"  Created (no labels): {url}")
                    return url

            print(f"  Error creating issue: {stderr}")
            return ''
    except FileNotFoundError:
        print("[Pipeline] ERROR: 'gh' CLI not found. Install it: https://cli.github.com/")
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("  Error: gh command timed out")
        return ''


def _parse_issue_number(url: str) -> int:
    """Extract issue number from a GitHub issue URL."""
    try:
        return int(url.rstrip('/').split('/')[-1])
    except (ValueError, IndexError):
        return 0


def _save_all(entries):
    """Save the full feedback list back to storage."""
    if gcs_storage.USE_LOCAL_STORAGE:
        gcs_storage._local_save_json(gcs_storage.FEEDBACK_FILE, entries)
    else:
        bucket = gcs_storage.get_bucket()
        blob = bucket.blob(gcs_storage.FEEDBACK_FILE)
        blob.upload_from_string(
            json.dumps(entries, default=str),
            content_type='application/json'
        )


def main():
    parser = argparse.ArgumentParser(
        description='EstradaBot Feedback Processing Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--prod', action='store_true',
                        help='Read from production GCS bucket (ddschedulerbot-files)')
    subparsers = parser.add_subparsers(dest='command', help='Pipeline commands')

    # fetch command
    fetch_parser = subparsers.add_parser('fetch', help='Fetch feedback from storage')
    fetch_parser.add_argument('--all', action='store_true',
                              help='Fetch all entries (not just unprocessed)')
    fetch_parser.add_argument('--category', type=str,
                              help='Filter by category (e.g. "Bug Report")')
    fetch_parser.add_argument('--status', type=str,
                              help='Filter by admin status (e.g. "New")')
    fetch_parser.add_argument('--priority', type=str,
                              help='Filter by priority (Low, Medium, High)')
    fetch_parser.add_argument('--since', type=str,
                              help='Filter entries after this date (YYYY-MM-DD)')
    fetch_parser.add_argument('--no-mark', action='store_true',
                              help='Do not mark fetched entries as ingested')
    fetch_parser.set_defaults(func=fetch_feedback)

    # mark command
    mark_parser = subparsers.add_parser('mark',
                                        help='Update dev_status of a feedback entry')
    mark_parser.add_argument('index', type=int, help='Entry index (from inbox.json)')
    mark_parser.add_argument('dev_status', type=str,
                             help='New status: unprocessed, ingested, actioned, closed')
    mark_parser.set_defaults(func=mark_status)

    # create-issue command
    issue_parser = subparsers.add_parser('create-issue',
                                          help='Create a GitHub issue from a feedback entry')
    issue_parser.add_argument('index', type=int, help='Entry index')
    issue_parser.add_argument('--force', action='store_true',
                              help='Create even if issue already exists')
    issue_parser.set_defaults(func=create_issue)

    # create-issues command (batch)
    batch_parser = subparsers.add_parser('create-issues',
                                          help='Create GitHub issues for all unprocessed feedback')
    batch_parser.add_argument('--yes', '-y', action='store_true',
                              help='Skip confirmation prompt')
    batch_parser.set_defaults(func=create_issues_batch)

    # stats command
    stats_parser = subparsers.add_parser('stats', help='Show feedback summary stats')
    stats_parser.set_defaults(func=show_stats)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == '__main__':
    main()
