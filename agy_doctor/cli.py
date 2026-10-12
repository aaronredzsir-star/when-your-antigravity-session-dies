"""
Command Line Interface for Antigravity Doctor.
"""

import sys
import argparse
from .core import scan_sessions, heal_session, restore_session
from . import __version__

BANNER = f"""
  ___       _   _                      _ _            ____             _             
 / _ \\     | | (_)                    (_) |          |  _ \\           | |            
/ /_\\ \\_ __| |_ _  __ _ _ __ __ ___   ___| |_ _   _  | | | | ___   ___| |_ ___  _ __ 
|  _  | '_ \\ __| |/ _` | '__/ _` \\ \\ / / | __| | | | | | | |/ _ \\ / __| __/ _ \\| '__|
| | | | | | | |_| | (_| | | | (_| |\\ V /| | |_| |_| | | |_| | (_) | (__| || (_) | |   
\\_| |_/_| |_|\\__|_|\\__, |_|  \\__,_| \\_/ |_|\\__|\\__, | |____/ \\___/ \\___|\\__\\___/|_|   
                    __/ |                        __/ |                                
                   |___/                        |___/   v{__version__}
Context hygiene, payload pruning, and crash recovery toolkit for Google Antigravity.
"""

def print_table(headers, rows):
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(val)))
            
    header_str = "  ".join(f"{h:<{col_widths[i]}}" for i, h in enumerate(headers))
    sep_str = "  ".join("-" * col_widths[i] for i in range(len(headers)))
    print(header_str)
    print(sep_str)
    for row in rows:
        print("  ".join(f"{str(val):<{col_widths[i]}}" for i, val in enumerate(row)))


def cmd_scan(args):
    print(BANNER)
    print("[*] Scanning Antigravity sessions...\n")
    sessions = scan_sessions()
    
    if not sessions:
        print("[-] No Antigravity conversation sessions found.")
        return

    headers = ["ID (Short)", "Status", "Size", "Steps", "Health", "Title / Note"]
    table_rows = []
    
    bricked_count = 0
    warning_count = 0
    
    for s in sessions:
        sid = s["id"][:8] + "..."
        status = "RUNNING" if s["status"] == "CASCADE_RUN_STATUS_RUNNING" else "IDLE"
        size = f"{s['size_mb']:.1f} MB"
        steps = str(s["total_steps"])
        health = s["health"]
        title = s["title"][:30]
        
        if health == "BRICKED":
            bricked_count += 1
            health = "[!] BRICKED"
        elif health == "WARNING":
            warning_count += 1
            health = "[?] WARNING"
        else:
            health = "[+] OK"
            
        table_rows.append([sid, status, size, steps, health, title])
        
    print_table(headers, table_rows)
    print(f"\nTotal: {len(sessions)} sessions | Bricked: {bricked_count} | Warning: {warning_count}")
    
    if bricked_count > 0 or warning_count > 0:
        print("\nTip: Run `agydoc heal --all` to automatically rescue stuck sessions and prune bloated history.")


def cmd_heal(args):
    print(BANNER)
    sessions = scan_sessions()
    target_sessions = []
    
    if args.all:
        target_sessions = [s for s in sessions if s["health"] in ["BRICKED", "WARNING"]]
    elif args.session_id:
        target_sessions = [s for s in sessions if s["id"].startswith(args.session_id)]
    else:
        # Default: heal all bricked sessions
        target_sessions = [s for s in sessions if s["health"] == "BRICKED"]
        
    if not target_sessions:
        print("[+] No sessions need healing! All scanned sessions are healthy.")
        return
        
    print(f"[*] Found {len(target_sessions)} session(s) to heal:")
    for s in target_sessions:
        print(f"  - {s['id']} ({s['title']}) [{s['health']}]")
        
    for s in target_sessions:
        print(f"\n[+] Healing {s['id']}...")
        res = heal_session(s, dry_run=args.dry_run)
        print(f"    - Removed hanging errors : {res['deleted_error_steps']}")
        print(f"    - Pruned bloated steps   : {res['pruned_steps']}")
        print(f"    - Reclaimed payload size : {res['saved_kb']:.1f} KB")
        print(f"    - Database integrity     : {res['integrity']}")
        print(f"    - Safety backup saved to : {res['backup_path']}")
        print(f"    -> Session successfully recovered to IDLE state!")
        
    print("\n[V] All targeted sessions healed! You can now restart Antigravity and continue work.")


def cmd_restore(args):
    print(BANNER)
    print(f"[*] Attempting rollback for session {args.session_id}...")
    bak = restore_session(args.session_id)
    if bak:
        print(f"[V] Successfully restored from backup: {bak}")
    else:
        print(f"[-] No backup files found for session ID {args.session_id}")


def main():
    parser = argparse.ArgumentParser(
        description="Antigravity Doctor: Context hygiene & crash recovery toolkit for Google Antigravity",
        prog="agydoc"
    )
    subparsers = parser.add_subparsers(dest="command")
    
    # scan
    p_scan = subparsers.add_parser("scan", help="Scan and diagnose all Antigravity sessions")
    
    # heal
    p_heal = subparsers.add_parser("heal", help="Rescue stuck sessions and prune bloated tool history")
    p_heal.add_argument("session_id", nargs="?", help="Specific session ID or prefix to heal")
    p_heal.add_argument("--all", action="store_true", help="Heal all bricked and warning sessions")
    p_heal.add_argument("--dry-run", action="store_true", help="Inspect without modifying files")
    
    # restore
    p_res = subparsers.add_parser("restore", help="Restore session from latest safety backup")
    p_res.add_argument("session_id", help="Session ID to restore")
    
    args = parser.parse_args()
    
    if args.command == "scan":
        cmd_scan(args)
    elif args.command == "heal":
        cmd_heal(args)
    elif args.command == "restore":
        cmd_restore(args)
    else:
        # Default behavior: scan
        cmd_scan(args)


if __name__ == "__main__":
    main()
