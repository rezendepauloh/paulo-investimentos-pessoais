import hashlib
import datetime
import pandas as pd
from typing import Union, Optional, Any
from src.utils.formatting import normalize_text
from src.database import db_manager

def generate_transaction_hash(data: Any, valor: Any, descricao: Any) -> str:
    """
    Gera um hash SHA-256 único e determinístico para uma transação financeira de forma defensiva.
    Trata com segurança valores NaT, None, NaN, datas em múltiplos formatos e strings vazias.
    """
    # 1. Tratamento seguro de Data
    if data is None or pd.isna(data) or data is pd.NaT or str(data).strip() in ["", "nan", "NaT", "None"]:
        data_norm = "1970-01-01"
    elif isinstance(data, (datetime.date, datetime.datetime, pd.Timestamp)):
        try:
            data_norm = data.strftime("%Y-%m-%d")
        except Exception:
            data_norm = "1970-01-01"
    else:
        try:
            d_str = str(data).strip()
            if "-" in d_str and len(d_str.split("-")[0]) == 4:
                parsed = pd.to_datetime(d_str, format="mixed", errors="coerce")
            else:
                parsed = pd.to_datetime(d_str, dayfirst=True, format="mixed", errors="coerce")

            if pd.notna(parsed) and parsed is not pd.NaT:
                data_norm = parsed.strftime("%Y-%m-%d")
            else:
                data_norm = "1970-01-01"
        except Exception:
            data_norm = "1970-01-01"

    # 2. Tratamento seguro de Valor
    try:
        val_float = float(valor) if pd.notna(valor) else 0.0
        val_norm = f"{abs(val_float):.2f}"
    except (ValueError, TypeError):
        val_norm = "0.00"

    # 3. Tratamento seguro de Descrição
    desc_str = str(descricao) if pd.notna(descricao) else ""
    desc_norm = normalize_text(desc_str)
    if not desc_norm:
        desc_norm = "".join(e for e in desc_str.lower().strip() if e.isalnum())

    raw_key = f"{data_norm}_{val_norm}_{desc_norm}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

def get_persisted_hashes() -> set:
    """
    Coleta todos os hashes das transações existentes gravadas no banco SQLite local (despesas e receitas).
    """
    hashes = set()
    try:
        df_desp = db_manager.get_table_data("despesas")
        if not df_desp.empty:
            for _, r in df_desp.iterrows():
                h = generate_transaction_hash(
                    r.get("gasto_em", r.get("Gasto em", "")),
                    r.get("valor", r.get("Valor", 0.0)),
                    r.get("nome", r.get("Nome", ""))
                )
                hashes.add(h)

        df_rec = db_manager.get_table_data("receitas")
        if not df_rec.empty:
            for _, r in df_rec.iterrows():
                h = generate_transaction_hash(
                    r.get("recebido_em", r.get("Recebido em", "")),
                    r.get("valor", r.get("Valor", 0.0)),
                    r.get("nome", r.get("Nome", ""))
                )
                hashes.add(h)
    except Exception:
        pass
    return hashes

def identify_duplicates(novos_df: pd.DataFrame, existentes_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """
    Identifica duplicidades comparando o hash dos novos registros contra:
      1. Os registros do SQLite local (despesas e receitas persistidas).
      2. O DataFrame de existentes fornecido (ex: carregado do Google Sheets).
      3. O próprio lote novo (linhas duplicadas no mesmo arquivo importado).
    
    Adiciona as colunas:
      - 'Hash': hash SHA-256 único de cada transação.
      - 'Status': 'Novo' ou '⚠️ Duplicado'.
      - 'Importar': True para novos, False para duplicados (permitindo edição manual posterior).
    """
    if novos_df.empty:
        return novos_df

    df = novos_df.copy()

    # Gera hash para novos se ainda não existir
    if "Hash" not in df.columns or df["Hash"].isnull().any() or (df["Hash"] == "").any():
        df["Hash"] = df.apply(
            lambda r: generate_transaction_hash(
                r.get("Data", r.get("Gasto em", r.get("Recebido em", ""))),
                r.get("Valor", 0.0),
                r.get("Descricao", r.get("Nome", ""))
            ),
            axis=1
        )

    # Coleta conjunto global de hashes já conhecidos
    existing_hashes = get_persisted_hashes()

    if existentes_df is not None and not existentes_df.empty:
        if "Hash" in existentes_df.columns:
            existing_hashes.update(existentes_df["Hash"].dropna().astype(str).tolist())
        else:
            for _, r in existentes_df.iterrows():
                h = generate_transaction_hash(
                    r.get("Data", r.get("Gasto em", r.get("Recebido em", r.get("data_envio", "")))),
                    r.get("Valor", r.get("valor", 0.0)),
                    r.get("Descricao", r.get("Nome", r.get("nome", "")))
                )
                existing_hashes.add(h)

    # Identifica duplicatas no lote
    seen_in_batch = set()
    statuses = []
    importar_flags = []

    for _, row in df.iterrows():
        h = row["Hash"]
        if h in existing_hashes or h in seen_in_batch:
            statuses.append("⚠️ Duplicado")
            importar_flags.append(False)
        else:
            statuses.append("Novo")
            importar_flags.append(True)
            seen_in_batch.add(h)

    df["Status"] = statuses
    df["Importar"] = importar_flags
    return df
