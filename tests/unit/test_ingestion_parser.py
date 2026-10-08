# -*- coding: utf-8 -*-
"""
Testes unitários para regras de categorização e parser CSV de extratos bancários (src.services.ingestion_parser).
"""
import unittest
import pandas as pd
from unittest.mock import patch, MagicMock

import tests.test_helpers
from src.services.ingestion_parser import (
    normalize_expense_category,
    normalize_income_category,
    infer_nature_and_essentiality,
    parse_csv
)

class TestIngestionParser(unittest.TestCase):
    """Testa regras de classificação de despesas/receitas e parser de arquivos."""

    def test_normalize_expense_category(self):
        self.assertEqual(normalize_expense_category("pagamento uber viagem"), "Táxi / Uber")
        self.assertEqual(normalize_expense_category("compra mercado extra"), "Supermercado")
        self.assertEqual(normalize_expense_category("farmacia pague menos"), "Medicamentos")
        self.assertEqual(normalize_expense_category("mensalidade unigran"), "Escola/Faculdade")
        self.assertEqual(normalize_expense_category("netflix assinatura"), "Streaming")
        self.assertEqual(normalize_expense_category("descricao desconhecida 123"), "Outros")

    def test_normalize_income_category(self):
        self.assertEqual(normalize_income_category("provento dividendos petr4"), "Dividendo BR")
        self.assertEqual(normalize_income_category("pagamento salario mensal"), "Salário")
        self.assertEqual(normalize_income_category("recebimento plantao hospital"), "Plantão")
        self.assertEqual(normalize_income_category("cashback compras"), "Cashback")

    def test_infer_nature_and_essentiality(self):
        fixo_var, essencial = infer_nature_and_essentiality("Supermercado", "compras do mes")
        self.assertEqual(fixo_var, "Variável")
        self.assertEqual(essencial, "Essencial")

        fixo_var, essencial = infer_nature_and_essentiality("Streaming", "spotify")
        self.assertEqual(fixo_var, "Fixo")
        self.assertEqual(essencial, "Não essencial")

    def test_parse_csv_statement(self):
        csv_data = (
            "Data,Descricao,Valor\n"
            "01/10/2026,Supermercado Central,-150.00\n"
            "02/10/2026,Uber Corrida,-25.50\n"
            "03/10/2026,Recebimento Salario,5000.00\n"
        ).encode("utf-8")

        df = parse_csv(csv_data, filename="extrato.csv")
        self.assertEqual(len(df), 3)
        self.assertIn("Hash", df.columns)
        self.assertIn("Tipo", df.columns)
        self.assertEqual(df.loc[0, "Categoria"], "Supermercado")
        self.assertEqual(df.loc[1, "Tipo"], "Despesa")
        self.assertEqual(df.loc[2, "Tipo"], "Receita")

if __name__ == '__main__':
    unittest.main()
