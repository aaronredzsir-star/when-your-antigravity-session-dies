"""
Unit tests for Antigravity Doctor (agydoc).
"""

import unittest
import sqlite3
import tempfile
from pathlib import Path

from agy_doctor.proto_utils import decode_fields, encode_field, encode_varint
from agy_doctor.core import compact_session, heal_session


class TestProtoUtils(unittest.TestCase):
    def test_varint_roundtrip(self):
        for val in [0, 1, 127, 128, 300, 100000, 2**20]:
            encoded = encode_varint(val)
            # Decode via field helper
            field_bytes = encode_field(1, 0, val)
            decoded = decode_fields(field_bytes)
            self.assertEqual(decoded[0][0], 1)
            self.assertEqual(decoded[0][1], 0)
            self.assertEqual(decoded[0][2], val)

    def test_length_delimited_roundtrip(self):
        test_strings = [
            b"",
            b"hello world",
            "测试中文字符串".encode("utf-8"),
            b"x" * 10000
        ]
        for s in test_strings:
            field_bytes = encode_field(5, 2, s)
            decoded = decode_fields(field_bytes)
            self.assertEqual(decoded[0][0], 5)
            self.assertEqual(decoded[0][1], 2)
            self.assertEqual(decoded[0][2], s)


class TestCompactionAndHealing(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_session.db"
        self.summ_path = Path(self.temp_dir.name) / "conversation_summaries.db"

        # Initialize mock conversation DB
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE steps (idx INTEGER PRIMARY KEY, step_type INTEGER, step_payload BLOB)")
        
        # Insert initial checkpoint at idx 0
        inner_summary = encode_field(5, 2, b"<summary>\nInitial task overview\n</summary>") + encode_field(12, 0, 0)
        f1 = encode_field(1, 0, 23)
        f4 = encode_field(4, 0, 3)
        f5 = encode_field(5, 2, b"metadata")
        f30 = encode_field(30, 2, inner_summary)
        ckp_payload = f1 + f4 + f5 + f30
        conn.execute("INSERT INTO steps VALUES (0, 23, ?)", (ckp_payload,))

        # Insert some intermediate work steps (15 and 132)
        for i in range(1, 10):
            st = 15 if i % 2 == 1 else 132
            payload = encode_field(1, 0, st) + encode_field(5, 2, b"step output payload " * 100)
            conn.execute("INSERT INTO steps VALUES (?, ?, ?)", (i, st, payload))

        # Insert trailing user prompt at idx 10
        user_prompt_payload = encode_field(1, 0, 14) + encode_field(19, 2, "请帮我修改图2的配色".encode("utf-8"))
        conn.execute("INSERT INTO steps VALUES (10, 14, ?)", (user_prompt_payload,))
        conn.commit()
        conn.close()

        # Initialize mock summary DB
        s_conn = sqlite3.connect(self.summ_path)
        s_conn.execute("CREATE TABLE conversation_summaries (conversation_id TEXT PRIMARY KEY, title TEXT, status TEXT, step_count INTEGER, last_modified_time TEXT, not_fully_idle INTEGER)")
        s_conn.execute("INSERT INTO conversation_summaries VALUES ('test_session', 'Test Title', 'CASCADE_RUN_STATUS_RUNNING', 11, '2026-10-14', 1)")
        s_conn.commit()
        s_conn.close()

        self.session_info = {
            "id": "test_session",
            "title": "Test Title",
            "db_path": str(self.db_path),
            "summ_db_path": str(self.summ_path)
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_compact_session_preserves_prompt(self):
        res = compact_session(self.session_info, preserve_trailing_prompt=True)
        self.assertTrue(res["preserved_prompt"])
        self.assertEqual(res["checkpoint_idx"], 10)
        self.assertEqual(res["final_step_idx"], 11)
        self.assertEqual(res["integrity"], "ok")

        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT idx, step_type FROM steps ORDER BY idx ASC").fetchall()
        conn.close()

        # Step 10 should be checkpoint (type 23)
        self.assertEqual(rows[-2], (10, 23))
        # Step 11 should be preserved user prompt (type 14)
        self.assertEqual(rows[-1], (11, 14))

        # Check summary DB status reset to IDLE and step_count = 12
        s_conn = sqlite3.connect(self.summ_path)
        s_row = s_conn.execute("SELECT status, step_count, not_fully_idle FROM conversation_summaries WHERE conversation_id = 'test_session'").fetchone()
        s_conn.close()
        self.assertEqual(s_row[0], "CASCADE_RUN_STATUS_IDLE")
        self.assertEqual(s_row[1], 12)
        self.assertEqual(s_row[2], 0)

    def test_heal_session_cleans_errors(self):
        # Append error steps 17 and 15 retry to tail
        conn = sqlite3.connect(self.db_path)
        conn.execute("INSERT INTO steps VALUES (11, 17, X'08111003')")
        conn.execute("INSERT INTO steps VALUES (12, 15, X'080F1003')")
        conn.execute("INSERT INTO steps VALUES (13, 17, X'08111003')")
        conn.commit()
        conn.close()

        res = heal_session(self.session_info, auto_compact=False)
        self.assertEqual(res["deleted_error_steps"], 3)
        self.assertEqual(res["integrity"], "ok")

        conn = sqlite3.connect(self.db_path)
        max_idx = conn.execute("SELECT MAX(idx) FROM steps").fetchone()[0]
        conn.close()
        self.assertEqual(max_idx, 10)

    def test_backup_rotation_prevents_bloat(self):
        # Multiple heal calls with create_backup=True should only produce 1 .bak file, not timestamp proliferation
        heal_session(self.session_info, auto_compact=False, create_backup=True)
        heal_session(self.session_info, auto_compact=False, create_backup=True)
        bak_files = list(Path(self.temp_dir.name).glob("*.bak*"))
        # Only test_session.db.bak and conversation_summaries.db.bak should exist
        self.assertEqual(len(bak_files), 2)
        self.assertTrue((Path(self.temp_dir.name) / "test_session.db.bak").exists())


if __name__ == "__main__":
    unittest.main()
