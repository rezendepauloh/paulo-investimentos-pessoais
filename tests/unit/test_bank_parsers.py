# -*- coding: utf-8 -*-
"""
Testes unitários para o subsistema de Parsers Dedicados por Instituição Financeira
(src.services.parsers).
"""
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

    def test_dispatcher_parse_bank_file(self):
        csv_data = (
            "Data,Descricao,Valor\n"
            "01/10/2026,Supermercado Central,-120.00\n"
        ).encode("utf-8")

        df = parse_bank_file(csv_data, filename="extrato.csv", institution_key="generic")
        self.assertEqual(len(df), 1)
        self.assertEqual(df.loc[0, "Categoria"], "Supermercado")

if __name__ == "__main__":
    unittest.main()
