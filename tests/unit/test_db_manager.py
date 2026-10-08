# -*- coding: utf-8 -*-
"""
Testes unitários para o gerenciador de banco de dados SQLite (src.database.db_manager).
Testa inicialização, delta sincronização, metadados e persistência de cotações/dados fundamentalistas.
"""
import os
import tempfile
import unittest
import pandas as pd
from pathlib import Path

import tests.test_helpers
import src.database.db_manager as db_mod

class BaseIsolatedDbTest(unittest.TestCase):
    """Fixture base que isola o SQLite em pasta temporária para cada caso de teste."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_db_dir = Path(self.temp_dir.name) / "data"
        self.test_db_dir.mkdir(parents=True, exist_ok=True)
        self.test_db_path = self.test_db_dir / "investimentos_test.db"

        self._orig_dir = db_mod.DB_DIR
        self._orig_path = db_mod.DB_PATH

        db_mod.DB_DIR = str(self.test_db_dir)
        db_mod.DB_PATH = str(self.test_db_path)

        db_mod.init_db()

    def tearDown(self):
        db_mod.DB_DIR = self._orig_dir
        db_mod.DB_PATH = self._orig_path
        self.temp_dir.cleanup()

class TestDbManager(BaseIsolatedDbTest):
    """Testes de operações no SQLite."""

    def test_init_db_creates_tables(self):
        conn = db_mod.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cursor.fetchall()]
        conn.close()

        expected = ["ordens", "despesas", "receitas", "dividendos", "sync_metadata", "precos_historicos", "dados_fundamentalistas"]
        for tbl in expected:
            self.assertIn(tbl, tables)

    def test_sync_metadata(self):
        initial = db_mod.get_last_sync_time()
        self.assertEqual(initial, "Nunca sincronizado")

        db_mod.set_last_sync_time()
        updated = db_mod.get_last_sync_time()
        self.assertNotEqual(updated, "Nunca sincronizado")
        self.assertIn(":", updated)

    def test_save_dataframe_delta_and_get_table_data(self):
        df_desp = pd.DataFrame([
            {"Gasto em": "2026-10-01", "Valor": 150.0, "Nome": "Supermercado XYZ", "Categoria": "Alimentação"},
            {"Gasto em": "2026-10-02", "Valor": 55.0, "Nome": "Farmácia Popular", "Categoria": "Saúde"}
        ])

        inserted = db_mod.save_dataframe_delta("despesas", df_desp)
        self.assertEqual(inserted, 2)

        df_lido = db_mod.get_table_data("despesas")
        self.assertEqual(len(df_lido), 2)
        self.assertIn("nome", df_lido.columns)

    def test_clear_table(self):
        df_desp = pd.DataFrame([{"Gasto em": "2026-10-01", "Valor": 100.0, "Nome": "Teste", "Categoria": "Outros"}])
        db_mod.save_dataframe_delta("despesas", df_desp)
        self.assertEqual(len(db_mod.get_table_data("despesas")), 1)

        db_mod.clear_table("despesas")
        self.assertEqual(len(db_mod.get_table_data("despesas")), 0)

    def test_save_and_retrieve_historical_prices(self):
        prices = [
            ("PETR4.SA", "2026-10-01", 38.50),
            ("PETR4.SA", "2026-10-02", 39.10),
            ("VALE3.SA", "2026-10-02", 60.00)
        ]
        affected = db_mod.save_historical_prices(prices)
        self.assertEqual(affected, 3)

        df_precos = db_mod.get_table_data("precos_historicos")
        self.assertEqual(len(df_precos), 3)

    def test_save_and_get_fundamental_data(self):
        df_mock = pd.DataFrame(
            {"2025-12-31": [1000.0, 500.0], "2024-12-31": [900.0, 450.0]},
            index=["Receita Líquida", "Lucro Líquido"]
        )
        saved = db_mod.save_fundamental_data("WEGE3", "dre", "anual", df_mock)
        self.assertGreater(saved, 0)

        df_fund = db_mod.get_fundamental_data("WEGE3", "dre", "anual")
        self.assertFalse(df_fund.empty)
        self.assertIn("Receita Líquida", df_fund.index)
        self.assertEqual(df_fund.loc["Receita Líquida", "2025-12-31"], 1000.0)

if __name__ == '__main__':
    unittest.main()
