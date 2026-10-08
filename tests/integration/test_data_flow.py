# -*- coding: utf-8 -*-
"""
Testes de integração: fluxo completo de ingestão e reconciliação financeira
(leitura de extrato/ordens -> geração de hash -> persistência no SQLite -> consulta consolidada).
"""
import unittest
import tempfile
import pandas as pd
from pathlib import Path

import tests.test_helpers
import src.database.db_manager as db_mod
from src.services.ingestion_parser import parse_csv
from src.services.deduplication import identify_duplicates
from src.services.analytics import calculate_portfolio_holdings

class TestIntegrationDataFlow(unittest.TestCase):
    """Testa integração ponta a ponta dos serviços de dados e banco SQLite."""

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

    def test_end_to_end_statement_import_and_persistence(self):
        # 1. Simula arquivo CSV bancário recebido
        csv_bytes = (
            "Data,Descricao,Valor\n"
            "05/10/2026,Aluguel Apartamento,-1800.00\n"
            "06/10/2026,Supermercado Angeloni,-450.20\n"
            "07/10/2026,Salario Empresa X,7500.00\n"
        ).encode("utf-8")

        df_parsed = parse_csv(csv_bytes, filename="extrato.csv")
        self.assertEqual(len(df_parsed), 3)

        # 2. Passa pelo módulo de deduplicação
        df_checked = identify_duplicates(df_parsed)
        self.assertTrue((df_checked["Status"] == "Novo").all())

        # 3. Segrega despesas e receitas e salva no banco de dados via Delta
        df_desp = df_checked[df_checked["Tipo"] == "Despesa"].copy()
        df_desp = df_desp.rename(columns={"Data": "Gasto em", "Descricao": "Nome"})
        inserted_desp = db_mod.save_dataframe_delta("despesas", df_desp)
        self.assertEqual(inserted_desp, 2)

        df_rec = df_checked[df_checked["Tipo"] == "Receita"].copy()
        df_rec = df_rec.rename(columns={"Data": "Recebido em", "Descricao": "Nome"})
        inserted_rec = db_mod.save_dataframe_delta("receitas", df_rec)
        self.assertEqual(inserted_rec, 1)

        # 4. Verifica se a leitura do SQLite reflete os dados salvos
        db_desp = db_mod.get_table_data("despesas")
        self.assertEqual(len(db_desp), 2)
        total_despesas = db_desp["valor"].sum()
        self.assertAlmostEqual(total_despesas, 2250.20, places=2)

        db_rec = db_mod.get_table_data("receitas")
        self.assertEqual(len(db_rec), 1)
        self.assertEqual(db_rec.iloc[0]["valor"], 7500.00)

        # 5. Tentativa de reimportar o mesmo lote deve ser detectada como Duplicada
        df_reimport = identify_duplicates(df_parsed)
        self.assertTrue((df_reimport["Status"] == "⚠️ Duplicado").all())
        self.assertFalse(df_reimport["Importar"].any())

    def test_end_to_end_order_and_portfolio_calculation(self):
        # 1. Salva ordens de compra no banco
        df_orders = pd.DataFrame([
            {
                "Data envio": "2026-09-10",
                "Compra/Venda": "Compra",
                "Papel": "VALE3",
                "Qtd Executada": 50,
                "Preço médio": 60.0,
                "Total líquido": 3000.0,
                "Moeda": "BRL",
                "Tipo": "Ações",
                "Setor Econômico": "Mineração"
            },
            {
                "Data envio": "2026-09-15",
                "Compra/Venda": "Compra",
                "Papel": "ITUB4",
                "Qtd Executada": 100,
                "Preço médio": 32.0,
                "Total líquido": 3200.0,
                "Moeda": "BRL",
                "Tipo": "Ações",
                "Setor Econômico": "Financeiro"
            }
        ])

        db_mod.save_dataframe_delta("ordens", df_orders)

        # 2. Recupera e calcula custódia
        saved_orders = db_mod.get_table_data("ordens")
        holdings = calculate_portfolio_holdings(saved_orders)

        self.assertFalse(holdings.empty)
        tickers = holdings["ticker"].tolist()
        self.assertIn("VALE3", tickers)
        self.assertIn("ITUB4", tickers)

if __name__ == '__main__':
    unittest.main()
