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

    def test_identify_internal_transfer_and_bill_payment(self):
        df_batch = pd.DataFrame([
            {"Data": "2026-09-22", "Valor": 3958.09, "Descricao": "Pix recebido - Paulo Henrique Goncalves Rezende", "Categoria": "Transferência Interna"},
            {"Data": "2026-09-22", "Valor": 3958.09, "Descricao": "Pagamento Fatura - PAULO HENRIQUE GONCALVES REZENDE", "Categoria": "Outros"},
            {"Data": "2026-09-23", "Valor": 50.0, "Descricao": "Posto Shell", "Categoria": "Combustível"}
        ])

        resultado = identify_duplicates(df_batch)
        # Pix de mesma titularidade
        self.assertEqual(resultado.loc[0, "Status"], "🔄 Transf. Interna")
        self.assertFalse(resultado.loc[0, "Importar"])

        # Pagamento de fatura
        self.assertEqual(resultado.loc[1, "Status"], "📄 Pgto Fatura")
        self.assertFalse(resultado.loc[1, "Importar"])

    def test_identify_proventos_duplicate_against_existing_b3(self):
        # Transações já gravadas (vindas da B3)
        df_existentes = pd.DataFrame([
            {"Data": "2026-09-01", "Valor": 2.61, "Descricao": "ITUB3 - JCP", "Categoria": "Juros sobre Capital Próprio"},
            {"Data": "2026-09-02", "Valor": 57.05, "Descricao": "FLRY3 - Dividendo", "Categoria": "Dividendo BR"},
            {"Data": "2026-09-28", "Valor": 144.81, "Descricao": "FLRY3 - Reembolso", "Categoria": "Juros sobre Capital Próprio"}
        ])

        # Novos registros vindo do extrato bancário (descrição do banco ligeiramente diferente)
        df_novos_banco = pd.DataFrame([
            {"Data": "2026-09-01", "Valor": 2.61, "Descricao": "ITUB3 - Juros S/capital 174", "Categoria": "Juros sobre Capital Próprio", "Tipo": "Receita"},
            {"Data": "2026-09-02", "Valor": 57.05, "Descricao": "FLRY3 - Dividendos 438", "Categoria": "Dividendo BR", "Tipo": "Receita"},
            {"Data": "2026-09-28", "Valor": 144.81, "Descricao": "FLRY3 - Reembolso Jcp - Aluguel", "Categoria": "Juros sobre Capital Próprio", "Tipo": "Receita"},
            {"Data": "2026-09-29", "Valor": 25.00, "Descricao": "Pix enviado - Amigo Restaurante", "Categoria": "Alimentação", "Tipo": "Despesa"}
        ])

        resultado = identify_duplicates(df_novos_banco, existentes_df=df_existentes)

        # Proventos do banco devem ser identificados como duplicados com Importar=False
        self.assertEqual(resultado.loc[0, "Status"], "⚠️ Duplicado")
        self.assertFalse(resultado.loc[0, "Importar"])

        self.assertEqual(resultado.loc[1, "Status"], "⚠️ Duplicado")
        self.assertFalse(resultado.loc[1, "Importar"])

        self.assertEqual(resultado.loc[2, "Status"], "⚠️ Duplicado")
        self.assertFalse(resultado.loc[2, "Importar"])

        # Pix comum para outra pessoa continua Novo e Importar=True
        self.assertEqual(resultado.loc[3, "Status"], "Novo")
        self.assertTrue(resultado.loc[3, "Importar"])

if __name__ == '__main__':
    unittest.main()

