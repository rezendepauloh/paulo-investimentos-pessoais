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

CATEGORIAS_PROVENTOS_SET = {
    "dividendo br",
    "dividendo eua",
    "rendimento fii",
    "aluguel ações br",
    "aluguel acoes br",
    "aluguel ações eua",
    "aluguel acoes eua",
    "juros sobre capital próprio",
    "juros sobre capital proprio",
    "rendimento renda fixa",
    "frações",
    "fracoes"
}

def extract_ticker_from_desc(text: str) -> str:
    """Extrai o ticker de ações/FIIs da descrição (ex: FLRY3, ITUB3, KNRI11)."""
    if not text:
        return ""
    m = pd.Series([str(text)]).str.extract(r'\b([A-Z]{4}[0-9]{1,2})\b', expand=False).iloc[0]
    return str(m).upper() if pd.notna(m) else ""

def _normalize_date_str(data: Any) -> str:
    """Normaliza data para o padrão YYYY-MM-DD."""
    if data is None or pd.isna(data) or data is pd.NaT or str(data).strip() in ["", "nan", "NaT", "None"]:
        return "1970-01-01"
    if isinstance(data, (datetime.date, datetime.datetime, pd.Timestamp)):
        try:
            return data.strftime("%Y-%m-%d")
        except Exception:
            return "1970-01-01"
    try:
        d_str = str(data).strip()
        if "-" in d_str and len(d_str.split("-")[0]) == 4:
            parsed = pd.to_datetime(d_str, format="mixed", errors="coerce")
        else:
            parsed = pd.to_datetime(d_str, dayfirst=True, format="mixed", errors="coerce")
        if pd.notna(parsed) and parsed is not pd.NaT:
            return parsed.strftime("%Y-%m-%d")
    except Exception:
        pass
    return "1970-01-01"

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

def get_persisted_proventos() -> list:
    """
    Retorna lista de dicionários com data, valor, ticker e categoria dos proventos já persistidos no SQLite.
    """
    proventos = []
    try:
        df_rec = db_manager.get_table_data("receitas")
        if not df_rec.empty:
            for _, r in df_rec.iterrows():
                cat = str(r.get("categoria", r.get("Categoria", ""))).strip().lower()
                nome = str(r.get("nome", r.get("Nome", ""))).strip()
                d_norm = _normalize_date_str(r.get("recebido_em", r.get("Recebido em", "")))
                try:
                    val = round(abs(float(r.get("valor", r.get("Valor", 0.0)))), 2)
                except Exception:
                    val = 0.0

                ticker = extract_ticker_from_desc(nome)
                is_prov = cat in CATEGORIAS_PROVENTOS_SET or bool(ticker) or any(k in nome.lower() for k in ["rendimento", "dividendo", "juros", "jcp", "reembolso", "aluguel"])
                if is_prov and val > 0:
                    proventos.append({
                        "data": d_norm,
                        "valor": val,
                        "ticker": ticker,
                        "categoria": cat,
                        "nome": nome
                    })
    except Exception:
        pass
    return proventos

def identify_duplicates(novos_df: pd.DataFrame, existentes_df: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """
    Identifica duplicidades comparando o hash dos novos registros contra:
      1. Os registros do SQLite local (despesas e receitas persistidas).
      2. O DataFrame de existentes fornecido (ex: carregado do Google Sheets).
      3. O próprio lote novo (linhas duplicadas no mesmo arquivo importado).
      4. Proventos de investimentos (B3 / Bancos) por Data, Valor e Ticker/Categoria.
    
    Adiciona as colunas:
      - 'Hash': hash SHA-256 único de cada transação.
      - 'Status': 'Novo', '⚠️ Duplicado', '🔄 Transf. Interna', '📄 Pgto Fatura'.
      - 'Importar': True para novos, False para duplicados/neutros.
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
    existing_proventos = get_persisted_proventos()

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

        # Enriquecimento com proventos do existentes_df (Google Sheets)
        for _, r in existentes_df.iterrows():
            cat = str(r.get("Categoria", r.get("categoria", ""))).strip().lower()
            nome = str(r.get("Descricao", r.get("Nome", r.get("nome", "")))).strip()
            d_norm = _normalize_date_str(r.get("Data", r.get("Gasto em", r.get("Recebido em", ""))))
            try:
                val = round(abs(float(r.get("Valor", r.get("valor", 0.0)))), 2)
            except Exception:
                val = 0.0

            ticker = extract_ticker_from_desc(nome)
            is_prov = cat in CATEGORIAS_PROVENTOS_SET or bool(ticker) or any(k in nome.lower() for k in ["rendimento", "dividendo", "juros", "jcp", "reembolso", "aluguel"])
            if is_prov and val > 0:
                existing_proventos.append({
                    "data": d_norm,
                    "valor": val,
                    "ticker": ticker,
                    "categoria": cat,
                    "nome": nome
                })

    # Identifica duplicatas e transações neutras no lote
    seen_in_batch = set()
    statuses = []
    importar_flags = []

    for _, row in df.iterrows():
        h = row["Hash"]
        d_raw = row.get("Data", row.get("Gasto em", row.get("Recebido em", "")))
        d_norm = _normalize_date_str(d_raw)
        desc_raw = str(row.get("Descricao", row.get("Nome", ""))).strip()
        d_low = desc_raw.lower()
        c_low = str(row.get("Categoria", "")).strip().lower()
        tipo_str = str(row.get("Tipo", "")).strip().lower()
        try:
            val_num = round(abs(float(row.get("Valor", 0.0))), 2)
        except Exception:
            val_num = 0.0

        ticker = extract_ticker_from_desc(desc_raw)
        is_provento_row = (
            tipo_str in ["receita", ""] and (
                c_low in CATEGORIAS_PROVENTOS_SET or
                bool(ticker) or
                any(k in d_low for k in ["rendimento", "dividendo", "juros", "jcp", "reembolso", "nota de aluguel", "aluguel"])
            )
        )

        # Checagem 1: Hash exato já persistido ou repetido no lote
        if h in existing_hashes or h in seen_in_batch:
            statuses.append("⚠️ Duplicado")
            importar_flags.append(False)
            continue

        # Checagem 2: Provento já persistido (ex: vindo da B3 oficial)
        # Se na mesma data e mesmo valor existir um provento com mesmo ticker (ou nota de aluguel já discriminada)
        provento_duplicado = False
        if is_provento_row and val_num > 0:
            for p in existing_proventos:
                if p["data"] == d_norm and abs(p["valor"] - val_num) < 0.01:
                    # Se tiver mesmo ticker (ex: ITUB3, FLRY3, KNRI11, HGRE11)
                    if ticker and p["ticker"] and ticker == p["ticker"]:
                        provento_duplicado = True
                        break
                    # Se um deles for sem ticker explícito mas da mesma categoria de provento
                    elif not ticker and (c_low in CATEGORIAS_PROVENTOS_SET and p["categoria"] in CATEGORIAS_PROVENTOS_SET):
                        provento_duplicado = True
                        break

        if provento_duplicado:
            statuses.append("⚠️ Duplicado")
            importar_flags.append(False)
            seen_in_batch.add(h)
        elif "transferência interna" in c_low or "transferencia interna" in c_low:
            statuses.append("🔄 Transf. Interna")
            importar_flags.append(False)
        elif any(k in d_low for k in ["pagamento fatura", "pgto fatura", "fatura cartao", "fatura cartão", "pagamento de cartao", "pagamento de cartão"]):
            statuses.append("📄 Pgto Fatura")
            importar_flags.append(False)
        elif any(k in d_low for k in ["paulo henrique", "goncalves rezende", "mesma titularidade", "entre contas"]):
            statuses.append("🔄 Transf. Interna")
            importar_flags.append(False)
        else:
            statuses.append("Novo")
            importar_flags.append(True)
            seen_in_batch.add(h)

    df["Status"] = statuses
    df["Importar"] = importar_flags
    return df
