"""load_sync_codes 回归测试：同步清单 = stock_kline ∪ stock_info（新IPO自动纳入）"""
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data'))
from sync_incremental_eastmoney import load_sync_codes  # noqa: E402


class TestLoadSyncCodes(unittest.TestCase):
    def _make_db(self):
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE stock_kline (stock_code TEXT, trade_date TEXT)")
        conn.execute("CREATE TABLE stock_info (stock_code TEXT PRIMARY KEY, stock_name TEXT)")
        return conn, path

    def test_union_includes_new_ipo(self):
        conn, path = self._make_db()
        try:
            conn.executemany("INSERT INTO stock_kline VALUES (?, ?)",
                             [("600001", "20260801"), ("600001", "20260804"),
                              ("000001", "20260804")])
            conn.executemany("INSERT INTO stock_info (stock_code, stock_name) VALUES (?, ?)",
                             [("600001", "老股"), ("000001", "平安银行"), ("688999", "新IPO股")])
            conn.commit()
            codes = load_sync_codes(conn)
            self.assertEqual(codes, ["000001", "600001", "688999"])  # 去重+排序+新股在内
        finally:
            conn.close()
            os.unlink(path)

    def test_kline_only_stock_kept(self):
        """stock_info 缺失的老股票（如有）不丢"""
        conn, path = self._make_db()
        try:
            conn.execute("INSERT INTO stock_kline VALUES ('300001', '20260804')")
            conn.commit()
            self.assertEqual(load_sync_codes(conn), ["300001"])
        finally:
            conn.close()
            os.unlink(path)


if __name__ == '__main__':
    unittest.main()
