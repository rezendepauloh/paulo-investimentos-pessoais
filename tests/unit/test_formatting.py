# -*- coding: utf-8 -*-
"""
Testes unitários para o utilitário de formatação numérica e texto (src.utils.formatting).
"""
import unittest
import pandas as pd
import tests.test_helpers
from src.utils.formatting import normalize_text, format_number

class TestFormatting(unittest.TestCase):
    """Valida as regras de normalização textual e formatação monetária/numérica."""

    def test_normalize_text_accents_and_case(self):
        self.assertEqual(normalize_text("Açúcar & Café!"), "acucar cafe")
        self.assertEqual(normalize_text("  TRANSFERÊNCIA PIX - BANCO  "), "transferencia pix banco")

    def test_normalize_text_empty_and_none(self):
        self.assertEqual(normalize_text(""), "")
        self.assertEqual(normalize_text(None), "")
        self.assertEqual(normalize_text(float("nan")), "")

    def test_format_number_currency_brl(self):
        formatted = format_number(1234567.89, is_currency=True, currency="BRL")
        self.assertEqual(formatted, "R$ 1.234.567,89")

    def test_format_number_currency_usd(self):
        formatted = format_number(9876.50, is_currency=True, currency="USD")
        self.assertEqual(formatted, "US$ 9.876,50")

    def test_format_number_privacy_mask(self):
        self.assertEqual(format_number(1500.0, is_currency=True, currency="BRL", mask_privacy=True), "R$ ••••••")
        self.assertEqual(format_number(1500.0, is_currency=True, currency="USD", mask_privacy=True), "US$ ••••••")
        self.assertEqual(format_number(1500.0, is_currency=False, mask_privacy=True), "••••••")

    def test_format_number_invalid_or_none(self):
        self.assertEqual(format_number(None), "")
        self.assertEqual(format_number("texto_invalido"), "texto_invalido")

if __name__ == '__main__':
    unittest.main()
