#!/usr/bin/env python3
"""历史数据导入安全回归；不联网，不写仓库文件。"""
import contextlib
import io
import json
import sqlite3
import unittest
from unittest.mock import mock_open, patch

import build_bulletin_history as history


class BulletinHistoryTests(unittest.TestCase):
    def test_valid_cutoff_output_is_unchanged(self):
        cut = {"EB-2": {"CN": {"A": "2024-02-29", "B": "current"},
                        "IN": {"A": "unavailable", "B": "2026-10-01"}}}
        self.assertEqual(history.cutoff_block_text(cut),
                         "var CUTOFF_DATA = {\n"
                         "  'EB-2': { 'CN': { A: '2024-02-29', B: 'current' }, "
                         "'IN': { A: 'unavailable', B: '2026-10-01' } }\n"
                         "}; // CUTOFF_DATA_END")

    def test_cutoff_serialization_rejects_injection_and_invalid_dates(self):
        values = ["2026-10-01' + (globalThis.compromised = 1) + '",
                  '</script><script>alert(1)</script>', '2026-02-29',
                  '2026-04-31', '0000-01-01', '2026-1-01', '２０２６-10-01',
                  '2026-10-01\n', 'C', None, 20261001, {}]
        for value in values:
            for table in ('A', 'B'):
                with self.subTest(value=value, table=table), self.assertRaises(ValueError):
                    cell = {'A': 'current', 'B': 'unavailable', table: value}
                    history.cutoff_block_text({'EB-2': {'CN': cell}})

    def test_valid_history_compression_is_unchanged(self):
        self.assertEqual(history.compress({'2024-01': '2024-02-29', '2024-02': '2024-02-29',
                                           '2024-03': 'C', '2024-04': 'U'}),
                         [['2024-01-15', '2024-02-29'], ['2024-03-15', 'C'], ['2024-04-15', 'U']])

    def test_history_serialization_rejects_invalid_months(self):
        for month in ['2026-00', '2026-13', '0000-10', '2026-1', '2026-10\n',
                      '2026-10</script><script>alert(1)</script>', None]:
            with self.subTest(month=month), self.assertRaises(ValueError):
                history.compress({month: 'C'})

    def test_history_serialization_rejects_invalid_cutoffs(self):
        for value in ['</script><script>alert(1)</script>', '2026-02-29', 'current', None]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                history.compress({'2026-10': value})

    def database(self, published, cutoff, current=0, unavailable=0):
        connection = sqlite3.connect(':memory:')
        self.addCleanup(connection.close)
        connection.execute('CREATE TABLE bulletin (id INTEGER, publication_date TEXT)')
        connection.execute('CREATE TABLE visa_cutoff_date (bulletin_id INTEGER, visa_class TEXT, '
                           'action_type TEXT, country TEXT, cutoff_date TEXT, is_current INTEGER, '
                           'is_unavailable INTEGER, visa_category TEXT)')
        connection.execute('INSERT INTO bulletin VALUES (1, ?)', (published,))
        connection.execute('INSERT INTO visa_cutoff_date VALUES (1, ?, ?, ?, ?, ?, ?, ?)',
                           ('2nd', 'final_action', 'china', cutoff, current, unavailable, 'employment_based'))
        return connection

    def test_database_import_preserves_dates_and_sentinels(self):
        for cutoff, current, unavailable, expected in [('2024-02-29', 0, 0, '2024-02-29'),
                                                       (None, 1, 0, 'C'), (None, 0, 1, 'U')]:
            with self.subTest(expected=expected):
                connection = self.database('2026-10-01', cutoff, current, unavailable)
                with patch.object(history.sqlite3, 'connect', return_value=connection):
                    self.assertEqual(history.load_db('fixture'), {('EB2', 'china', 'A'): {'2026-10': expected}})

    def test_database_import_rejects_invalid_dates(self):
        for published, cutoff in [('2026-02-30', '2024-01-01'), ('2026-13-01', '2024-01-01'),
                                  ('2026-10-01', "2026-10-01' + alert(1) + '"),
                                  ('2026-10-01', '2026-02-29')]:
            with self.subTest(published=published, cutoff=cutoff):
                connection = self.database(published, cutoff)
                with patch.object(history.sqlite3, 'connect', return_value=connection), self.assertRaises(ValueError):
                    history.load_db('fixture')

    def bulletin(self):
        return {'id': '2026-10', 'tables': {
            table: {category: {country: '2024-01-01' for country in history.PDT_CO.values()}
                    for category in history.PDT_CAT.values()} for table in ('A', 'B')}}

    def assert_import_rejected_without_writes(self, bulletin):
        opened = mock_open(read_data=json.dumps({'bulletins': [bulletin]}))
        with patch.object(history, 'load_db', return_value={}), patch('builtins.open', opened), \
                patch('sys.argv', ['build_bulletin_history.py', '--vyakunin-db', 'fixture.db',
                                   '--pd-tracker', 'fixture.json', '--inject']), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(ValueError):
                history.main()
        self.assertTrue(all('w' not in call.kwargs.get('mode', call.args[1] if len(call.args) > 1 else 'r')
                            for call in opened.call_args_list), opened.call_args_list)

    def test_json_import_rejects_invalid_month_before_any_write(self):
        for month in ['2026-13', '2026-00', '2026-10</script>']:
            with self.subTest(month=month):
                bulletin = self.bulletin()
                bulletin['id'] = month
                self.assert_import_rejected_without_writes(bulletin)

    def test_json_import_rejects_invalid_cutoff_before_any_write(self):
        for cutoff in ["2026-10-01' + (globalThis.compromised = 1) + '",
                       '</script><script>alert(1)</script>', '2026-02-29', 20261001, {}]:
            with self.subTest(cutoff=cutoff):
                bulletin = self.bulletin()
                bulletin['tables']['A']['EB-2']['CHINA'] = cutoff
                self.assert_import_rejected_without_writes(bulletin)


if __name__ == '__main__':
    unittest.main()
