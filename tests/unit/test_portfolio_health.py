import unittest
import pandas as pd
from src.services.portfolio_health import (
    calculate_portfolio_health_indicators,
    generate_portfolio_health_diagnosis,
    calculate_portfolio_rebalancing
)


class TestPortfolioHealth(unittest.TestCase):
    def setUp(self):
        # Cria holdings simulados
        self.df_holdings = pd.DataFrame([
            {"ticker": "PETR4", "tipo": "Ações", "valor_atual": 4000.0},
            {"ticker": "HGLG11", "tipo": "FIIs", "valor_atual": 3000.0},
            {"ticker": "TESOURO SELIC", "tipo": "Renda Fixa", "valor_atual": 3000.0},
        ])

        # Cria despesas simuladas
        self.df_despesas = pd.DataFrame([
            {"Nome": "Aluguel", "Valor": 1000.0, "Gasto em": "05/08/2026", "Essencial vs. Não Essencial": "Essencial"},
            {"Nome": "Supermercado", "Valor": 500.0, "Gasto em": "10/08/2026", "Essencial vs. Não Essencial": "Essencial"},
            {"Nome": "Restaurante", "Valor": 200.0, "Gasto em": "15/08/2026", "Essencial vs. Não Essencial": "Não Essencial"},
        ])

        # Cria performance simulada
        self.df_perf = pd.DataFrame({
            "Retorno Carteira Acumulado (%)": [5.0, 15.0],
            "IPCA Acumulado (%)": [2.0, 5.0],
            "CDI Acumulado (%)": [4.0, 10.0]
        }, index=pd.to_datetime(["2026-01-01", "2026-10-01"]))

    def test_calculate_portfolio_health_indicators(self):
        ind = calculate_portfolio_health_indicators(
            self.df_holdings,
            self.df_despesas,
            df_perf=self.df_perf
        )
        self.assertEqual(ind["total_patrimonio"], 10000.0)
        self.assertEqual(ind["reserva_liquidez"], 3000.0)
        # Gasto essencial mensal foi 1500.0, então meses de cobertura = 3000 / 1500 = 2.0
        self.assertAlmostEqual(ind["meses_cobertura_reserva"], 2.0)
        # Retorno real: (1 + 0.15) / (1 + 0.05) - 1 = 1.15 / 1.05 - 1 = 9.5238%
        self.assertAlmostEqual(ind["retorno_real_acum"], ((1.15 / 1.05) - 1) * 100.0)

    def test_generate_portfolio_health_diagnosis(self):
        ind = calculate_portfolio_health_indicators(
            self.df_holdings,
            self.df_despesas,
            df_perf=self.df_perf
        )
        diag = generate_portfolio_health_diagnosis(ind)
        self.assertTrue(len(diag) >= 3)
        titulos = [d["titulo"] for d in diag]
        self.assertIn("Reserva Vulnerável", titulos)  # 2.0 meses (< 3 meses)
        self.assertIn("Poder de Compra Protegido", titulos)  # > 2% real
        self.assertIn("Superando o CDI", titulos)  # 15% vs 10% CDI (150% do CDI)

    def test_calculate_portfolio_rebalancing(self):
        df_rebal = calculate_portfolio_rebalancing(self.df_holdings)
        self.assertFalse(df_rebal.empty)
        self.assertEqual(len(df_rebal), 3)
        self.assertIn("Classe", df_rebal.columns)
        self.assertIn("Desvio (%)", df_rebal.columns)
        self.assertIn("Direcionamento", df_rebal.columns)


if __name__ == "__main__":
    unittest.main()
