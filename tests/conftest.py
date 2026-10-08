# -*- coding: utf-8 -*-
"""
Configurações e fixtures globais de teste para pytest e unittest.
Garante isolamento de banco de dados e ambiente seguro durante os testes.
"""
import os
import sys
import tempfile
from pathlib import Path
import pytest

# Garante raiz do projeto e src/ no sys.path
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))
SRC_DIR = ROOT_DIR / "src"
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))

# Mocks universais seguros
import tests.test_helpers

@pytest.fixture(autouse=True)
def isolated_db(monkeypatch, tmp_path):
    """
    Garante que cada teste execute com um banco SQLite temporário isolado em tmp_path,
    sem afetar a base de dados real do usuário em data/investimentos.db.
    """
    test_db_dir = tmp_path / "data"
    test_db_dir.mkdir(parents=True, exist_ok=True)
    test_db_path = test_db_dir / "test_investimentos.db"

    monkeypatch.setattr("src.database.db_manager.DB_DIR", str(test_db_dir))
    monkeypatch.setattr("src.database.db_manager.DB_PATH", str(test_db_path))

    from src.database.db_manager import init_db
    init_db()

    yield test_db_path
