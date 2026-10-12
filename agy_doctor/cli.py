"""
Command Line Interface for Antigravity Doctor.
"""

import sys
import shutil
import argparse
from pathlib import Path

from .core import scan_sessions, heal_session, restore_session
from .watcher import run_watch_loop
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
        print("     Or run `agydoc watch` / `agydoc install-plugin` for continuous auto-healing.")


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


def cmd_watch(args):
    print(BANNER)
    run_watch_loop(interval_sec=args.interval)


def get_plugin_src_dir() -> Path:
    # Try finding plugins/antigravity-doctor relative to package or repo root
    current_file = Path(__file__).resolve()
    candidates = [
        current_file.parent.parent / "plugins" / "antigravity-doctor",
        current_file.parent / "plugins" / "antigravity-doctor",
        Path.cwd() / "plugins" / "antigravity-doctor"
    ]
    for c in candidates:
        if c.exists() and (c / "plugin.json").exists():
            return c
    raise FileNotFoundError("Could not locate plugin source directory (plugins/antigravity-doctor).")


def cmd_install_plugin(args):
    print(BANNER)
    try:
        src = get_plugin_src_dir()
    except FileNotFoundError as e:
        print(f"[-] Error: {e}")
        return

    if args.workspace:
        dest = Path.cwd() / ".agents" / "plugins" / "antigravity-doctor"
        scope = "Workspace (.agents/plugins)"
    else:
        dest = Path.home() / ".gemini" / "config" / "plugins" / "antigravity-doctor"
        scope = "Global (~/.gemini/config/plugins)"

    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)

    shutil.copytree(src, dest)
    print(f"[+] Successfully installed Antigravity Doctor plugin to:")
    print(f"    {dest}")
    print(f"\n[*] Scope: {scope}")
    print(f"[*] The plugin is now active! It will automatically:")
    print(f"    1. Prune bloated tool output before prefill (preventing gateway EOFs).")
    print(f"    2. Clear hanging error loops on disconnect so sessions never brick.")


def cmd_uninstall_plugin(args):
    print(BANNER)
    if args.workspace:
        dest = Path.cwd() / ".agents" / "plugins" / "antigravity-doctor"
    else:
        dest = Path.home() / ".gemini" / "config" / "plugins" / "antigravity-doctor"

    if dest.exists():
        shutil.rmtree(dest)
        print(f"[+] Successfully removed plugin from {dest}")
    else:
        print(f"[-] Plugin not found at {dest}")


def main():
    parser = argparse.ArgumentParser(
        description="Antigravity Doctor: Context hygiene & crash recovery toolkit for Google Antigravity",
        prog="agydoc"
    )
    subparsers = parser.add_subparsers(dest="command")
    
    # scan
    subparsers.add_parser("scan", help="Scan and diagnose all Antigravity sessions")
    
    # heal
    p_heal = subparsers.add_parser("heal", help="Rescue stuck sessions and prune bloated tool history")
    p_heal.add_argument("session_id", nargs="?", help="Specific session ID or prefix to heal")
    p_heal.add_argument("--all", action="store_true", help="Heal all bricked and warning sessions")
    p_heal.add_argument("--dry-run", action="store_true", help="Inspect without modifying files")
    
    # restore
    p_res = subparsers.add_parser("restore", help="Restore session from latest safety backup")
    p_res.add_argument("session_id", help="Session ID to restore")

    # watch
    p_watch = subparsers.add_parser("watch", help="Run background watcher to auto-heal stuck/bloated sessions")
    p_watch.add_argument("--interval", type=int, default=15, help="Check interval in seconds (default: 15)")

    # install-plugin
    p_inst = subparsers.add_parser("install-plugin", help="Install the native Antigravity auto-healing plugin")
    p_inst.add_argument("--workspace", action="store_true", help="Install to local workspace (.agents) instead of global (~/.gemini)")

    # uninstall-plugin
    p_uninst = subparsers.add_parser("uninstall-plugin", help="Uninstall the native Antigravity auto-healing plugin")
    p_uninst.add_argument("--workspace", action="store_true", help="Uninstall from workspace instead of global")
    
    args = parser.parse_args()
    
    if args.command == "scan":
        cmd_scan(args)
    elif args.command == "heal":
        cmd_heal(args)
    elif args.command == "restore":
        cmd_restore(args)
    elif args.command == "watch":
        cmd_watch(args)
    elif args.command == "install-plugin":
        cmd_install_plugin(args)
    elif args.command == "uninstall-plugin":
        cmd_uninstall_plugin(args)
    else:
        cmd_scan(args)


if __name__ == "__main__":
    main()
