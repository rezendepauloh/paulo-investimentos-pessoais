# -*- coding: utf-8 -*-
"""
Testes unitários para o subsistema de Parsers Dedicados por Instituição Financeira
(src.services.parsers).
"""
import os
import unittest
import pandas as pd
from unittest.mock import patch, MagicMock

import tests.test_helpers
from src.services.parsers import (
    get_parser,
    parse_bank_file,
    UI_INSTITUTION_OPTIONS,
    get_institution_guidelines,
    SicrediParser,
    NubankParser,
    InterParser,
    GenericBankParser
)
from src.services.parsers.base_parser import STANDARD_COLUMNS

class TestBankParsers(unittest.TestCase):
    """Valida o funcionamento do registry, dispatcher e parsers específicos."""

    def test_registry_and_get_parser(self):
        self.assertIsInstance(get_parser("sicredi"), SicrediParser)
        self.assertIsInstance(get_parser("nubank"), NubankParser)
        self.assertIsInstance(get_parser("inter"), InterParser)
        self.assertIsInstance(get_parser("inexistente"), GenericBankParser)

    def test_ui_options_and_guidelines(self):
        self.assertTrue(len(UI_INSTITUTION_OPTIONS) >= 7)
        sicredi_guide = get_institution_guidelines("sicredi")
        self.assertIn("Sicredi", sicredi_guide)

    def test_sicredi_parser_csv(self):
        # CSV típico do Sicredi com ponto-e-vírgula e prefixos
        csv_sicredi = (
            "Data;Descricao;Valor;Tipo\n"
            "05/10/2026;PIX ENVIADO - Supermercado Cooperativa;-180,50;D\n"
            "06/10/2026;PIX RECEBIDO - Reembolso Despesa;75,00;C\n"
            "07/10/2026;COMPRA CARTAO DEB - Farmacia Popular;-42,10;D\n"
        ).encode("latin1")

        parser = get_parser("sicredi")
        df = parser.parse_csv(csv_sicredi, filename="extrato_sicredi.csv")

        self.assertEqual(len(df), 3)
        for col in STANDARD_COLUMNS:
            self.assertIn(col, df.columns)

        # Verifica limpeza de prefixo e forma de pagamento
        self.assertEqual(df.loc[0, "Descricao"], "Supermercado Cooperativa")
        self.assertEqual(df.loc[0, "Forma_Pagamento"], "Pix")
        self.assertEqual(df.loc[0, "Tipo"], "Despesa")
        self.assertEqual(df.loc[0, "Conta debitada"], "Sicredi")

        self.assertEqual(df.loc[1, "Descricao"], "Reembolso Despesa")
        self.assertEqual(df.loc[1, "Tipo"], "Receita")
        self.assertEqual(df.loc[1, "Conta creditada"], "Sicredi")

        self.assertEqual(df.loc[2, "Descricao"], "Farmacia Popular")
        self.assertEqual(df.loc[2, "Forma_Pagamento"], "Débito")
        self.assertEqual(df.loc[2, "Categoria"], "Medicamentos")

    def test_nubank_parser_card_csv(self):
        # CSV típico de fatura de cartão Nubank: date, category, title, amount
        csv_nubank = (
            "date,category,title,amount\n"
            "2026-10-01,transporte,Uber 1234,22.90\n"
            "2026-10-02,restaurante,iFood Refeição,55.00\n"
            "2026-10-03,outros,Pagamento de fatura,-250.00\n"
        ).encode("utf-8")

        parser = get_parser("nubank")
        df = parser.parse_csv(csv_nubank, filename="nubank-fatura.csv")

        self.assertEqual(len(df), 3)
        self.assertEqual(df.loc[0, "Tipo"], "Despesa")
        self.assertEqual(df.loc[0, "Conta debitada"], "Nubank")
        self.assertEqual(df.loc[0, "Forma_Pagamento"], "Cartão de crédito")

        # Pagamento de fatura deve ser classificado como Receita/Estorno
        self.assertEqual(df.loc[2, "Tipo"], "Receita")
        self.assertEqual(df.loc[2, "Conta creditada"], "Nubank")

    def test_inter_parser_csv(self):
        # CSV típico do Banco Inter com metadados no topo e proventos B3
        csv_inter = (
            "Extrato Conta Corrente \n"
            "Conta ;7214685\n"
            "Período ;01/09/2026 a 30/09/2026\n"
            "Saldo ;10,00\n"
            "\n"
            "Data Lançamento;Histórico;Descrição;Valor;Saldo\n"
            "30/09/2026;Credito B3 Btb;* Prov * Nota De Aluguel - 30/09/2026;0,09;171,69\n"
            "28/09/2026;Credito B3 Btb;* Prov * Reembolso Jcp - Aluguel Flry3;144,81;156,42\n"
            "22/09/2026;Pix recebido;Paulo Henrique Goncalves Rezende;3.958,09;10,00\n"
            "22/09/2026;Pagamento efetuado;Pagamento Fatura - PAULO HENRIQUE GONCALVES REZENDE;-3.958,09;-3.962,18\n"
            "15/09/2026;Crédito Evento B3;* Prov * Rendimento 33                 Knri11;36,30;178,16\n"
            "02/09/2026;Crédito Evento B3;* Prov * Dividendos 438                Flry3;57,05;10,00\n"
            "01/09/2026;Crédito Evento B3;* Prov * Juros S/capital 174                Itub3;2,61;129,19\n"
        ).encode("utf-8")

        parser = get_parser("inter")
        df = parser.parse_csv(csv_inter, filename="Extrato-01-09-2026-a-30-09-2026-CSV.csv")

        self.assertEqual(len(df), 7)
        for col in STANDARD_COLUMNS:
            self.assertIn(col, df.columns)

        # Proventos B3
        self.assertEqual(df.loc[0, "Categoria"], "Aluguel Ações BR")
        self.assertEqual(df.loc[0, "Conta creditada"], "Inter")
        self.assertEqual(df.loc[0, "Tipo"], "Receita")

        # Rendimento FII
        self.assertEqual(df.loc[4, "Categoria"], "Rendimento FII")
        self.assertIn("KNRI11", df.loc[4, "Descricao"].upper())

        # JCP
        self.assertEqual(df.loc[6, "Categoria"], "Juros sobre Capital Próprio")

        # Pagamento fatura
        self.assertEqual(df.loc[3, "Tipo"], "Despesa")
        self.assertEqual(df.loc[3, "Conta debitada"], "Inter")

        # Transferência Interna (Pix recebido de Paulo Henrique Rezende)
        self.assertEqual(df.loc[2, "Categoria"], "Transferência Interna")
        self.assertEqual(df.loc[2, "Tipo"], "Receita")

    def test_inter_parser_ofx(self):
        # Validação com arquivo OFX real emitido pelo Banco Inter
        with open("temp/Extrato-01-09-2026-a-30-09-2026-OFX.ofx", "rb") as f:
            ofx_bytes = f.read()

        parser = get_parser("inter")
        df = parser.parse_ofx(ofx_bytes, filename="Extrato-01-09-2026-a-30-09-2026-OFX.ofx")

        self.assertEqual(len(df), 26)
        for col in STANDARD_COLUMNS:
            self.assertIn(col, df.columns)

        # Proventos B3
        self.assertEqual(df.loc[0, "Categoria"], "Aluguel Ações BR")
        self.assertEqual(df.loc[0, "Conta creditada"], "Inter")
        self.assertIn("Nota De Aluguel", df.loc[0, "Descricao"])

        # Rendimento FII Knri11
        fii_row = df[df["Descricao"].str.contains("Knri11", case=False, na=False)].iloc[0]
        self.assertEqual(fii_row["Categoria"], "Rendimento FII")
        self.assertEqual(fii_row["Conta creditada"], "Inter")

        # JCP Itub3
        jcp_row = df[df["Descricao"].str.contains("Itub3", case=False, na=False)].iloc[0]
        self.assertEqual(jcp_row["Categoria"], "Juros sobre Capital Próprio")

        # Pagamento Fatura
        fat_row = df[df["Descricao"].str.contains("Pagamento Fatura", case=False, na=False)].iloc[0]
        self.assertEqual(fat_row["Tipo"], "Despesa")
        self.assertEqual(fat_row["Conta debitada"], "Inter")
        self.assertEqual(fat_row["Forma_Pagamento"], "Cartão de crédito")

        # Pix de mesma titularidade (Paulo Henrique Goncalves Rezende)
        pix_self_row = df[df["Descricao"].str.contains("Paulo Henrique", case=False, na=False) & (df["Tipo"] == "Receita")].iloc[0]
        self.assertEqual(pix_self_row["Categoria"], "Transferência Interna")

    def test_dispatcher_parse_bank_file(self):
        csv_data = (
            "Data,Descricao,Valor\n"
            "01/10/2026,Supermercado Central,-120.00\n"
        ).encode("utf-8")

        df = parse_bank_file(csv_data, filename="extrato.csv", institution_key="generic")
        self.assertEqual(len(df), 1)
        self.assertEqual(df.loc[0, "Categoria"], "Supermercado")

    def test_b3_parser_excel(self):
        # Validação com arquivo Excel real exportado da Área do Investidor B3
        with open("temp/movimentacao-2026-10-10-12-45-10.xlsx", "rb") as f:
            excel_bytes = f.read()

        parser = get_parser("b3")
        df = parser.parse_excel(excel_bytes, filename="movimentacao-2026-10-10-12-45-10.xlsx")

        self.assertEqual(len(df), 34)
        for col in STANDARD_COLUMNS:
            self.assertIn(col, df.columns)

        # Proventos com ticker exato
        azza_aluguel = df[df["Descricao"].str.contains("AZZA3", case=False, na=False)].iloc[0]
        self.assertEqual(azza_aluguel["Valor"], 24.53)
        self.assertEqual(azza_aluguel["Categoria"], "Aluguel Ações BR")
        self.assertEqual(azza_aluguel["Conta creditada"], "Inter")

        # Rendimento FII
        knri_inter = df[(df["Descricao"].str.contains("KNRI11")) & (df["Conta creditada"] == "Inter")].iloc[0]
        self.assertEqual(knri_inter["Valor"], 36.30)
        self.assertEqual(knri_inter["Categoria"], "Rendimento FII")

        knri_xp = df[(df["Descricao"].str.contains("KNRI11")) & (df["Conta creditada"] == "XP")].iloc[0]
        self.assertEqual(knri_xp["Valor"], 63.80)
        self.assertEqual(knri_xp["Categoria"], "Rendimento FII")

        # JCP Itub3
        itub_jcp = df[df["Descricao"].str.contains("ITUB3 - JCP")].iloc[0]
        self.assertEqual(itub_jcp["Valor"], 2.61)
        self.assertEqual(itub_jcp["Categoria"], "Juros sobre Capital Próprio")

        # Auto-detecção no dispatcher
        df_disp = parse_bank_file(excel_bytes, filename="movimentacao-2026-10-10-12-45-10.xlsx", institution_key="generic")
        self.assertEqual(len(df_disp), 34)

    def test_inter_parser_pdf(self):
        # Validação da fatura de cartão de crédito em PDF do Banco Inter protegida por senha
        fpath = "temp/Fatura.pdf"
        if not os.path.exists(fpath):
            self.skipTest(f"Arquivo {fpath} não encontrado no ambiente local.")
        with open(fpath, "rb") as f:
            pdf_bytes = f.read()

        parser = get_parser("inter")
        df = parser.parse_pdf(pdf_bytes, filename="Fatura.pdf", password="046376")

        self.assertEqual(len(df), 57)
        for col in STANDARD_COLUMNS:
            self.assertIn(col, df.columns)

        # Soma total bate exatamente com a fatura: R$ 5.172,77
        self.assertAlmostEqual(df["Valor"].sum(), 5172.77, places=2)

        # Checa data de fechamento contábil da fatura (dia 20 do mês de vencimento)
        self.assertEqual(df.loc[0, "Data"].strftime("%Y-%m-%d"), "2026-08-20")

        # Checa conta debitada
        self.assertTrue((df["Conta debitada"] == "Cartão de crédito").all())

        # Checa normalização de parcelas com data de compra
        shopee = df[df["Descricao"].str.contains("SHPSTECNOLOGIA")].iloc[0]
        self.assertEqual(shopee["Descricao"], "SHOPEE *SHPSTECNOLOGIA 1/7 (Compra: 23/07)")
        self.assertEqual(shopee["Valor"], 66.02)

        # Auto-detecção no dispatcher com extensão .pdf
        df_disp = parse_bank_file(pdf_bytes, filename="Fatura.pdf", institution_key="inter")
        self.assertEqual(len(df_disp), 57)

    def test_c6_parser_pdf(self):
        # Validação das faturas de cartão de crédito em PDF do C6 Bank protegidas por senha
        fpath_09 = "temp/09 - Fatura-CPF.pdf"
        fpath_10 = "temp/10 - Fatura-CPF.pdf"

        if not os.path.exists(fpath_09) or not os.path.exists(fpath_10):
            self.skipTest("Arquivos de fatura do C6 Bank não encontrados no ambiente.")

        parser = get_parser("c6")

        # 1. Fatura de Setembro (09)
        with open(fpath_09, "rb") as f:
            pdf_bytes_09 = f.read()

        df_09 = parser.parse_pdf(pdf_bytes_09, filename="09 - Fatura-CPF.pdf", password="046376")
        self.assertEqual(len(df_09), 64)
        self.assertAlmostEqual(df_09["Valor"].sum(), 6431.75, places=2)
        self.assertEqual(df_09.loc[0, "Data"].strftime("%Y-%m-%d"), "2026-09-10")
        self.assertTrue((df_09["Conta debitada"] == "Cartão de crédito").all())
        self.assertTrue((df_09["Forma_Pagamento"] == "Cartão de crédito").all())
        # Confirma que nenhuma despesa caiu como Outros
        self.assertEqual(len(df_09[df_09["Categoria"] == "Outros"]), 0)

        # 2. Fatura de Outubro (10) - inclui compra internacional em USD e IOF
        with open(fpath_10, "rb") as f:
            pdf_bytes_10 = f.read()

        df_10 = parser.parse_pdf(pdf_bytes_10, filename="10 - Fatura-CPF.pdf", password="046376")
        self.assertEqual(len(df_10), 54)
        self.assertAlmostEqual(df_10["Valor"].sum(), 6152.99, places=2)
        self.assertEqual(df_10.loc[0, "Data"].strftime("%Y-%m-%d"), "2026-10-10")
        self.assertTrue((df_10["Conta debitada"] == "Cartão de crédito").all())
        self.assertEqual(len(df_10[df_10["Categoria"] == "Outros"]), 0)

        # Valida compra internacional e IOF
        petro_iof = df_10[df_10["Descricao"].str.contains("IOF PETROBRAS")].iloc[0]
        self.assertEqual(petro_iof["Valor"], 4.45)
        self.assertEqual(petro_iof["Categoria"], "Tributo")

        petro_compra = df_10[df_10["Descricao"] == "PETROBRAS - SHOPPING (Compra: 05/09)"].iloc[0]
        self.assertEqual(petro_compra["Valor"], 127.21)
        self.assertEqual(petro_compra["Categoria"], "Combustível")

        # Auto-detecção no dispatcher
        df_disp = parse_bank_file(pdf_bytes_09, filename="09 - Fatura-CPF.pdf", institution_key="c6")
        self.assertEqual(len(df_disp), 64)

if __name__ == "__main__":
    unittest.main()


