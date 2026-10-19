# -*- coding: utf-8 -*-
"""
Testes unitários para o módulo de Projeção de Parcelas de Cartão de Crédito
(src.services.credit_card_projection).
"""
import unittest
import pandas as pd
from src.services.credit_card_projection import (
    extract_installment_info,
    calculate_credit_card_projections,
    calculate_credit_card_health_indicators,
    generate_credit_card_diagnosis,
)

class TestCreditCardProjection(unittest.TestCase):
    def test_extract_installment_info(self):
        # Casos com notação de parcelas
        c, t, name = extract_installment_info("AREZZO 2/6 (Compra: 04/07)")
        self.assertEqual(c, 2)
        self.assertEqual(t, 6)
        self.assertEqual(name, "AREZZO")

        c, t, name = extract_installment_info("SHOPEE *BUBUWEBSTORE 11/12")
        self.assertEqual(c, 11)
        self.assertEqual(t, 12)
        self.assertEqual(name, "SHOPEE *BUBUWEBSTORE")

        c, t, name = extract_installment_info("PET DOG INBOX - Parcela 2/3")
        self.assertEqual(c, 2)
        self.assertEqual(t, 3)
        self.assertEqual(name, "PET DOG INBOX")

        # Casos sem parcelamento
        c, t, name = extract_installment_info("CASA LUGANO (Compra: 23/07)")
        self.assertEqual(c, 0)
        self.assertEqual(t, 0)
        self.assertEqual(name, "CASA LUGANO (Compra: 23/07)")

    def test_calculate_credit_card_projections(self):
        df_sample = pd.DataFrame([
            {
                "nome": "Notebook Dell 1/10",
                "valor": 500.0,
                "categoria": "Compras",
                "gasto_em": "2026-08-10",
                "conta_debitada": "Cartão de crédito"
            },
            {
                "nome": "Notebook Dell 2/10",
                "valor": 500.0,
                "categoria": "Compras",
                "gasto_em": "2026-09-10",
                "conta_debitada": "Cartão de crédito"
            },
            {
                "nome": "Mouse Gamer 2/2",
                "valor": 80.0,
                "categoria": "Compras",
                "gasto_em": "2026-09-10",
                "conta_debitada": "Cartão de crédito"
            },
            {
                "nome": "Conta de Energia",
                "valor": 250.0,
                "categoria": "Luz",
                "gasto_em": "2026-09-10",
                "conta_debitada": "Conta corrente"
            }
        ])

        res = calculate_credit_card_projections(df_sample)

        # 1 compra ativa (Notebook Dell com 8 parcelas restantes de R$ 500)
        df_ativas = res["compras_ativas"]
        self.assertEqual(len(df_ativas), 1)
        self.assertEqual(df_ativas.iloc[0]["nome_base"], "Notebook Dell")
        self.assertEqual(df_ativas.iloc[0]["parcelas_restantes"], 8)
        self.assertEqual(df_ativas.iloc[0]["valor_restante"], 4000.0)

        # 1 compra quitada (Mouse Gamer 2/2)
        df_quitadas = res["compras_quitadas"]
        self.assertEqual(len(df_quitadas), 1)
        self.assertEqual(df_quitadas.iloc[0]["nome_base"], "Mouse Gamer")

        # Projeção mensal e métricas
        self.assertEqual(res["resumo"]["total_comprometido"], 4000.0)
        self.assertEqual(res["resumo"]["qtd_compras_ativas"], 1)
        self.assertEqual(len(res["detalhes_futuros"]), 8)

        # Primeiro mês projetado é outubro/2026 (1 mês após 09/2026)
        self.assertEqual(res["resumo"]["primeiro_mes_projetado"], "10/2026")

        # Testa indicadores contábeis e diagnósticos
        df_receitas = pd.DataFrame([
            {"Nome": "Salário", "Valor": 5000.0, "Recebido em": "05/09/2026"},
            {"Nome": "Salário", "Valor": 5000.0, "Recebido em": "05/08/2026"},
        ])
        indicators = calculate_credit_card_health_indicators(df_sample, res, df_receitas)
        self.assertAlmostEqual(indicators["taxa_comprometimento_renda"], 500.0 / 5000.0)  # 10%
        self.assertAlmostEqual(indicators["meses_alavancagem_futura"], 4000.0 / 5000.0)   # 0.8 meses

        diag = generate_credit_card_diagnosis(indicators)
        self.assertTrue(len(diag) >= 2)
        titulos = [d["titulo"] for d in diag]
        self.assertIn("Comprometimento Saudável", titulos)
        self.assertIn("Alavancagem Curta / Baixa", titulos)

if __name__ == "__main__":
    unittest.main()
