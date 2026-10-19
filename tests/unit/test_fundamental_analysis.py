import unittest
import pandas as pd
from src.services.fundamental_analysis import calculate_fundamental_ratios, generate_fundamental_diagnosis


class TestFundamentalAnalysis(unittest.TestCase):
    def setUp(self):
        # Cria balanço simulado
        self.df_balanco = pd.DataFrame(
            {
                "2025-12-31": [1000.0, 400.0, 100.0, 80.0, 200.0, 600.0, 300.0, 100.0, 50.0],
                "2024-12-31": [900.0, 350.0, 90.0, 60.0, 180.0, 550.0, 250.0, 90.0, 40.0],
            },
            index=[
                "Total Assets",
                "Current Assets",
                "Inventory",
                "Cash And Cash Equivalents",
                "Current Liabilities",
                "Stockholders Equity",
                "Total Debt",
                "Current Debt",
                "Long Term Debt"
            ]
        )

        # Cria DRE simulada
        self.df_dre = pd.DataFrame(
            {
                "2025-12-31": [800.0, 400.0, 200.0, 250.0, 120.0],
                "2024-12-31": [700.0, 350.0, 160.0, 200.0, 90.0],
            },
            index=[
                "Total Revenue",
                "Gross Profit",
                "EBIT",
                "EBITDA",
                "Net Income"
            ]
        )

    def test_calculate_fundamental_ratios(self):
        ratios = calculate_fundamental_ratios(self.df_balanco, self.df_dre)
        self.assertFalse(ratios.empty)
        
        # Liquidez Corrente 2025: 400 / 200 = 2.0
        self.assertAlmostEqual(ratios.loc["Liquidez Corrente", "2025-12-31"], 2.0)
        # Liquidez Seca 2025: (400 - 100) / 200 = 1.5
        self.assertAlmostEqual(ratios.loc["Liquidez Seca", "2025-12-31"], 1.5)
        # Liquidez Imediata 2025: 80 / 200 = 0.4
        self.assertAlmostEqual(ratios.loc["Liquidez Imediata", "2025-12-31"], 0.4)
        # Margem Bruta 2025: 400 / 800 = 0.5 (50%)
        self.assertAlmostEqual(ratios.loc["Margem Bruta", "2025-12-31"], 0.5)
        # Margem Líquida 2025: 120 / 800 = 0.15 (15%)
        self.assertAlmostEqual(ratios.loc["Margem Líquida", "2025-12-31"], 0.15)
        # ROE 2025: 120 / 600 = 0.20 (20%)
        self.assertAlmostEqual(ratios.loc["ROE (Retorno s/ Patrimônio Líquido)", "2025-12-31"], 0.20)
        # Dívida Líquida / EBITDA: (300 - 80) / 250 = 220 / 250 = 0.88
        self.assertAlmostEqual(ratios.loc["Dívida Líquida / EBITDA", "2025-12-31"], 0.88)

    def test_generate_fundamental_diagnosis(self):
        ratios = calculate_fundamental_ratios(self.df_balanco, self.df_dre)
        diagnosticos = generate_fundamental_diagnosis(ratios, self.df_dre)
        self.assertTrue(len(diagnosticos) >= 4)
        
        titulos = [d["titulo"] for d in diagnosticos]
        self.assertIn("Liquidez Corrente Saudável", titulos)
        self.assertIn("Endividamento Sob Controle", titulos)
        self.assertIn("ROE Excelente (Alta Rentabilidade)", titulos)
        self.assertIn("Margem Líquida Robusta", titulos)


if __name__ == "__main__":
    unittest.main()
