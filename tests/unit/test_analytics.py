# -*- coding: utf-8 -*-
"""
Testes unitários para cálculos de analytics e métricas de carteira (src.services.analytics).
"""
import unittest
import pandas as pd
import tests.test_helpers
from src.services.analytics import (
    normalize_ticker,
    is_valid_yfinance_ticker,
    calculate_portfolio_holdings
)

class TestAnalytics(unittest.TestCase):
    """Testa tratamento de tickers e cálculo consolidado de custódia (holdings)."""

    def test_normalize_ticker(self):
        self.assertEqual(normalize_ticker("PETR4"), "PETR4.SA")
        self.assertEqual(normalize_ticker("VALE3.SA"), "VALE3.SA")
        self.assertEqual(normalize_ticker("AAPL"), "AAPL")
        self.assertEqual(normalize_ticker("IVVB11"), "IVVB11.SA")

    def test_is_valid_yfinance_ticker(self):
        self.assertTrue(is_valid_yfinance_ticker("PETR4"))
        self.assertTrue(is_valid_yfinance_ticker("AAPL"))
        # Renda fixa ou caixa não devem ser enviados ao yfinance
        self.assertFalse(is_valid_yfinance_ticker("CDB BANCO INTER"))
        self.assertFalse(is_valid_yfinance_ticker("LCI 100%"))
        self.assertFalse(is_valid_yfinance_ticker("TESOURO SELIC 2029"))

    def test_calculate_portfolio_holdings_basic(self):
        df_ordens = pd.DataFrame([
            {
                "data envio": "2026-08-01",
                "Compra/Venda": "Compra",
                "Papel": "PETR4",
                "Qtd Executada": 100,
                "Preço médio": 30.0,
                "Total líquido": 3000.0,
                "Moeda": "BRL",
                "Tipo": "Ações",
                "Setor Econômico": "Petróleo e Gás"
            },
            {
                "data envio": "2026-08-10",
                "Compra/Venda": "Compra",
                "Papel": "PETR4",
                "Qtd Executada": 100,
                "Preço médio": 40.0,
                "Total líquido": 4000.0,
                "Moeda": "BRL",
                "Tipo": "Ações",
                "Setor Econômico": "Petróleo e Gás"
            },
            {
                "data envio": "2026-08-20",
                "Compra/Venda": "Venda",
                "Papel": "PETR4",
                "Qtd Executada": 50,
                "Preço médio": 45.0,
                "Total líquido": 2250.0,
                "Moeda": "BRL",
                "Tipo": "Ações",
                "Setor Econômico": "Petróleo e Gás"
            }
        ])

        holdings = calculate_portfolio_holdings(df_ordens)
        self.assertFalse(holdings.empty)
        petr4_row = holdings[holdings["ticker"] == "PETR4"].iloc[0]
        # 100 + 100 - 50 = 150 ações remanescentes
        self.assertEqual(petr4_row["quantidade"], 150)
        # Preço médio deve ser R$ 35,00
        self.assertAlmostEqual(petr4_row["preco_medio"], 35.0, places=2)
        self.assertEqual(petr4_row["tipo"], "Ações")

if __name__ == '__main__':
    unittest.main()
