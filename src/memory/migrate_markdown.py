
from __future__ import annotations

import argparse
from pathlib import Path

from src.memory.memory_manager import MemoryManager


def migrate(source_dir: Path, memory_manager: MemoryManager) -> int:
    imported = 0
    if not source_dir.exists():
        return imported

    for server_dir in sorted(path for path in source_dir.iterdir() if path.is_dir()):
        server_id = server_dir.name
        handoff_path = server_dir / "handoff.md"
        session_path = server_dir / "session.md"
        facts_path = server_dir / "server_facts.md"

        if handoff_path.exists():
            memory_manager.write_handoff(server_id, handoff_path.read_text(encoding="utf-8"))
            imported += 1
        if session_path.exists():
            memory_manager.write_session(server_id, session_path.read_text(encoding="utf-8"))
            imported += 1
        if facts_path.exists():
            content = facts_path.read_text(encoding="utf-8")
            memory_manager.update_server_facts(server_id, memory_manager._parse_sections(content))
            imported += 1
    return imported


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Import legacy ShellMate Markdown memory into SQLite.")
    parser.add_argument("--source", type=Path, default=project_root / "memory")
    parser.add_argument("--database", type=Path, default=project_root / "backend" / "data" / "memory.db")
    args = parser.parse_args()

    manager = MemoryManager(database_path=args.database)
    imported = migrate(args.source, manager)
    print(f"Imported {imported} Markdown memory documents into {args.database}.")
    print("Legacy Markdown files were preserved. Delete or archive them only after verification.")


if __name__ == "__main__":
    main()