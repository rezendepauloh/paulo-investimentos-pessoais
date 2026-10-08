# -*- coding: utf-8 -*-
"""
Testes unitários para geração de hash determinístico e detecção de duplicidades financeiras (src.services.deduplication).
"""
import unittest
import datetime
import pandas as pd
import tempfile
from pathlib import Path

import tests.test_helpers
import src.database.db_manager as db_mod
from src.services.deduplication import generate_transaction_hash, identify_duplicates

class TestDeduplication(unittest.TestCase):
    """Valida cálculo de hash SHA-256 e detecção de lançamentos duplicados."""

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

    def test_hash_deterministic(self):
        h1 = generate_transaction_hash("2026-10-01", 150.50, "Supermercado Pão de Açúcar")
        h2 = generate_transaction_hash("2026-10-01", 150.50, "supermercado pao de acucar")
        self.assertEqual(h1, h2)

    def test_hash_resilience_to_types_and_nones(self):
        dt = datetime.date(2026, 10, 5)
        h_date = generate_transaction_hash(dt, "200.00", "Aluguel")
        h_str = generate_transaction_hash("2026-10-05", 200, "aluguel")
        self.assertEqual(h_date, h_str)

        # None / NaN defensivo
        h_none = generate_transaction_hash(None, None, None)
        self.assertTrue(isinstance(h_none, str))
        self.assertEqual(len(h_none), 64)

    def test_identify_duplicates_in_batch(self):
        df_batch = pd.DataFrame([
            {"Data": "2026-10-01", "Valor": 100.0, "Descricao": "Farmácia A"},
            {"Data": "2026-10-01", "Valor": 100.0, "Descricao": "Farmácia A"},  # Duplicado no próprio lote
            {"Data": "2026-10-02", "Valor": 50.0, "Descricao": "Cafeteria"}
        ])

        resultado = identify_duplicates(df_batch)
        self.assertEqual(resultado.loc[0, "Status"], "Novo")
        self.assertTrue(resultado.loc[0, "Importar"])
        self.assertEqual(resultado.loc[1, "Status"], "⚠️ Duplicado")
        self.assertFalse(resultado.loc[1, "Importar"])
        self.assertEqual(resultado.loc[2, "Status"], "Novo")
        self.assertTrue(resultado.loc[2, "Importar"])

    def test_identify_duplicates_against_existing_dataframe(self):
        df_existentes = pd.DataFrame([
            {"Data": "2026-09-20", "Valor": 80.0, "Descricao": "Restaurante Bom Sabor"}
        ])

        df_novos = pd.DataFrame([
            {"Data": "2026-09-20", "Valor": 80.0, "Descricao": "Restaurante Bom Sabor"},
            {"Data": "2026-09-25", "Valor": 30.0, "Descricao": "Estacionamento"}
        ])

        resultado = identify_duplicates(df_novos, existentes_df=df_existentes)
        self.assertEqual(resultado.loc[0, "Status"], "⚠️ Duplicado")
        self.assertEqual(resultado.loc[1, "Status"], "Novo")

if __name__ == '__main__':
    unittest.main()
