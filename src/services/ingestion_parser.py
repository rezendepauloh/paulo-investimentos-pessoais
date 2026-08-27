import os
import io
import re
import json
import datetime
import logging
import pandas as pd
from typing import List, Optional, Union, Any
from pydantic import BaseModel, Field
import google.generativeai as genai
from src.services.deduplication import generate_transaction_hash
from src.utils.logger import get_logger

logger = get_logger("services", "ingestion")


# Mapeamento e listas oficiais das Tabelas Nativas do Google Sheets
MAPA_CATEGORIAS_DESPESAS = {
    "educação": "Escola/Faculdade",
    "faculdade": "Escola/Faculdade",
    "unigran": "Escola/Faculdade",
    "escola": "Escola/Faculdade",
    "ensino": "Ensinos à Distância",
    "ead": "Ensinos à Distância",
    "curso": "Ensinos à Distância",
    "serviços": "Serviços / Manutenção",
    "servico": "Serviços / Manutenção",
    "manutenção": "Serviços / Manutenção",
    "manutencao": "Serviços / Manutenção",
    "seguro": "Serviços / Manutenção",
    "uber": "Táxi / Uber",
    "99app": "Táxi / Uber",
    "táxi": "Táxi / Uber",
    "taxi": "Táxi / Uber",
    "ifood": "Delivery comida",
    "delivery": "Delivery comida",
    "mercado": "Supermercado",
    "supermercado": "Supermercado",
    "farmácia": "Medicamentos",
    "farmacia": "Medicamentos",
    "drogaria": "Medicamentos",
    "remédio": "Medicamentos",
    "remedio": "Medicamentos",
    "posto": "Combustível",
    "gasolina": "Combustível",
    "combustivel": "Combustível",
    "combustível": "Combustível",
    "restaurante": "Restaurante",
    "lanchonete": "Lanches",
    "lanche": "Lanches",
    "luz": "Luz",
    "energia": "Luz",
    "água": "Água",
    "agua": "Água",
    "internet": "Internet",
    "streaming": "Streaming",
    "netflix": "Streaming",
    "spotify": "Streaming",
    "hotel": "Hotel",
    "médico": "Médicos e terapeutas",
    "medico": "Médicos e terapeutas",
    "consulta": "Médicos e terapeutas",
    "terapia": "Médicos e terapeutas",
    "beleza": "Salão de beleza",
    "cabelo": "Salão de beleza",
    "barbearia": "Salão de beleza",
    "roupa": "Vestuário",
    "vestuário": "Vestuário",
    "vestuario": "Vestuário",
    "presente": "Presentes",
    "jogo": "Games",
    "game": "Games",
    "steam": "Games",
    "condomínio": "Condomínio",
    "condominio": "Condomínio",
}

CATEGORIAS_VALIDAS_DESPESAS = [
    "Combustível", "Compras", "Condomínio", "Delivery comida", "Ensinos à Distância",
    "Escola/Faculdade", "Estacionamento", "Eventos", "Games", "Hotel", "Internet",
    "Lanches", "Luz", "Medicamentos", "Médicos e terapeutas", "Presentes", "Restaurante",
    "Salão de beleza", "Serviços / Manutenção", "Streaming", "Supermercado",
    "Telefonia", "Táxi / Uber", "Vestuário", "Água", "Outros"
]

CATEGORIAS_VALIDAS_RECEITAS = [
    "Salário",
    "Auxílio Saúde",
    "Auxílio Alimentação",
    "Auxílio Transporte",
    "Plantão",
    "Férias",
    "Líquidez investimento",
    "Esquema bancada",
    "Cashback",
    "Juros sobre Capital Próprio",
    "Dividendo EUA",
    "Aluguel Ações BR",
    "Rendimento FII",
    "Frações",
    "Rendimento Renda Fixa",
    "Dividendo BR",
    "Aluguel Ações EUA",
    "Outros"
]

def normalize_expense_category(text: str) -> str:
    """
    Normaliza a categoria de despesa garantindo correspondência com as opções da planilha.
    """
    t_clean = text.lower().strip()
    for key, cat in MAPA_CATEGORIAS_DESPESAS.items():
        if key in t_clean:
            return cat
    for cat in CATEGORIAS_VALIDAS_DESPESAS:
        if cat.lower() in t_clean:
            return cat
    return "Outros"

def normalize_income_category(text: str) -> str:
    """
    Normaliza a categoria de receita garantindo correspondência com as opções da planilha,
    com suporte especializado a proventos de corretoras (Banco Inter, XP, B3).
    """
    t_clean = text.lower().strip()

    # 1. Reconhecimento de Proventos e B3 / Inter
    if "rendimento" in t_clean or re.search(r'\b[a-z]{4}11\b', t_clean):
        return "Rendimento FII"
    elif "aluguel" in t_clean or "nota de aluguel" in t_clean or "reembolso dividendo" in t_clean:
        if "eua" in t_clean or "usd" in t_clean or "adr" in t_clean:
            return "Aluguel Ações EUA"
        return "Aluguel Ações BR"
    elif "jcp" in t_clean or "juros sobre capital" in t_clean or "juros s/ capital" in t_clean:
        return "Juros sobre Capital Próprio"
    elif "dividendo" in t_clean or "provento" in t_clean:
        if "eua" in t_clean or "usd" in t_clean or "foreign" in t_clean:
            return "Dividendo EUA"
        return "Dividendo BR"
    elif "fracao" in t_clean or "frações" in t_clean or "fracion" in t_clean or "sobras" in t_clean:
        return "Frações"
    elif "renda fixa" in t_clean or "cdb" in t_clean or "lci" in t_clean or "lca" in t_clean or "tesouro" in t_clean or "cupom" in t_clean:
        return "Rendimento Renda Fixa"
    elif "cashback" in t_clean or "meliuz" in t_clean:
        return "Cashback"
    elif "saude" in t_clean or "saúde" in t_clean or "reembolso saude" in t_clean:
        return "Auxílio Saúde"
    elif "aliment" in t_clean or "refeic" in t_clean or "va" in t_clean or "vr" in t_clean:
        return "Auxílio Alimentação"
    elif "transp" in t_clean or "vt" in t_clean:
        return "Auxílio Transporte"
    elif "plant" in t_clean:
        return "Plantão"
    elif "ferias" in t_clean or "férias" in t_clean:
        return "Férias"
    elif "esquema" in t_clean or "bancada" in t_clean:
        return "Esquema bancada"
    elif "liquidez" in t_clean or "líquidez" in t_clean or "resgate" in t_clean:
        return "Líquidez investimento"

    for cat in CATEGORIAS_VALIDAS_RECEITAS:
        if cat.lower() in t_clean:
            return cat

    return "Salário"

REGRAS_CATEGORIAS = {
    # Fixos e Essenciais
    "Moradia": ("Fixo", "Essencial"),
    "Condomínio": ("Fixo", "Essencial"),
    "Luz": ("Fixo", "Essencial"),
    "Água": ("Fixo", "Essencial"),
    "Internet": ("Fixo", "Essencial"),
    "Telefonia": ("Fixo", "Essencial"),
    "Escola/Faculdade": ("Fixo", "Essencial"),
    "Ensinos à Distância": ("Fixo", "Essencial"),
    "Financiamento": ("Fixo", "Essencial"),
    "Salário": ("Fixo", "Essencial"),
    "Auxílio Saúde": ("Fixo", "Essencial"),
    "Auxílio Alimentação": ("Fixo", "Essencial"),
    "Auxílio Transporte": ("Fixo", "Essencial"),

    # Variáveis e Essenciais
    "Supermercado": ("Variável", "Essencial"),
    "Combustível": ("Variável", "Essencial"),
    "Medicamentos": ("Variável", "Essencial"),
    "Médicos e terapeutas": ("Variável", "Essencial"),
    "Serviços / Manutenção": ("Variável", "Essencial"),
    "Táxi / Uber": ("Variável", "Essencial"),
    "Pedágio viagem": ("Variável", "Essencial"),

    # Variáveis e Não Essenciais
    "Restaurante": ("Variável", "Não essencial"),
    "Delivery comida": ("Variável", "Não essencial"),
    "Lanches": ("Variável", "Não essencial"),
    "Compras": ("Variável", "Não essencial"),
    "Vestuário": ("Variável", "Não essencial"),
    "Games": ("Variável", "Não essencial"),
    "Streaming": ("Fixo", "Não essencial"),
    "Hotel": ("Variável", "Não essencial"),
    "Eventos": ("Variável", "Não essencial"),
    "Festas": ("Variável", "Não essencial"),
    "Presentes": ("Variável", "Não essencial"),
    "Salão de beleza": ("Variável", "Não essencial"),
    "Cabeleireiro": ("Variável", "Não essencial"),
    "Cashback": ("Variável", "Não essencial"),

    # Proventos / Investimentos
    "Rendimento FII": ("Variável", "Essencial"),
    "Dividendo BR": ("Variável", "Essencial"),
    "Dividendo EUA": ("Variável", "Essencial"),
    "Aluguel Ações BR": ("Variável", "Essencial"),
    "Aluguel Ações EUA": ("Variável", "Essencial"),
    "Juros sobre Capital Próprio": ("Variável", "Essencial"),
    "Rendimento Renda Fixa": ("Variável", "Essencial"),
    "Líquidez investimento": ("Variável", "Essencial"),
    "Esquema bancada": ("Variável", "Essencial"),
    "Plantão": ("Variável", "Essencial"),
    "Férias": ("Fixo", "Essencial"),
    "Frações": ("Variável", "Essencial"),
}

def infer_nature_and_essentiality(categoria: str, descricao: str = "") -> tuple[str, str]:
    """
    Infere automaticamente as classificações 'Fixo vs. Variável' e 'Essencial vs. Não Essencial'.
    """
    if categoria in REGRAS_CATEGORIAS:
        return REGRAS_CATEGORIAS[categoria]
        
    desc_low = descricao.lower()
    if any(k in desc_low for k in ["spotify", "netflix", "prime", "hbo", "disney", "youtube", "streaming", "assinatura"]):
        return ("Fixo", "Não essencial")
    elif any(k in desc_low for k in ["aluguel", "condom", "faculdade", "escola", "unigran", "energia", "energisa", "sanepar", "copel", "sabesp"]):
        return ("Fixo", "Essencial")
    elif any(k in desc_low for k in ["uber", "99", "posto", "combust", "farmacia", "droga", "mercado", "supermercado"]):
        return ("Variável", "Essencial")
    elif any(k in desc_low for k in ["ifood", "restaurante", "bar", "lanche", "steam", "game", "shopping"]):
        return ("Variável", "Não essencial")
        
    return ("Variável", "Essencial")

def detect_institution(filename: str = "", content_sample: str = "") -> str:
    """
    Infere a instituição financeira a partir do nome do arquivo ou conteúdo do extrato.
    """
    text_to_check = f"{filename} {content_sample}".lower()
    if "sicredi" in text_to_check:
        return "Sicredi"
    elif "inter" in text_to_check:
        return "Inter"
    elif "c6" in text_to_check:
        return "C6"
    elif "xp" in text_to_check or "xpi" in text_to_check:
        return "XP"
    elif "99pay" in text_to_check or "99 pay" in text_to_check or "99app" in text_to_check:
        return "99 Pay"
    elif "itau" in text_to_check or "itaú" in text_to_check:
        return "Itaú"
    elif "nubank" in text_to_check or "nu pagamentos" in text_to_check:
        return "Nubank"
    elif "bradesco" in text_to_check:
        return "Bradesco"
    elif "santander" in text_to_check:
        return "Santander"
    elif "caixa" in text_to_check:
        return "Caixa"
    elif "bb" in text_to_check or "banco do brasil" in text_to_check:
        return "Banco do Brasil"
    return "Conta corrente"

def sanitize_ofx_content(content_str: str) -> str:
    """Corrige anomalias comuns em cabeçalhos OFX de bancos brasileiros (ex: C6 Bank)."""
    # Corrige espaços em ENCODING: UTF - 8 -> ENCODING:UTF-8
    content_str = re.sub(r'ENCODING\s*:\s*UTF\s*-\s*8', 'ENCODING:UTF-8', content_str, flags=re.IGNORECASE)
    # Remove espaços entre chave e valor no cabeçalho OFX (ex: OFXHEADER: 100 -> OFXHEADER:100)
    lines = content_str.splitlines()
    sanitized_lines = []
    header_done = False
    for line in lines:
        if not header_done:
            if line.strip().startswith('<'):
                header_done = True
                sanitized_lines.append(line)
            else:
                parts = line.split(':', 1)
                if len(parts) == 2:
                    sanitized_lines.append(f"{parts[0].strip()}:{parts[1].strip()}")
                else:
                    sanitized_lines.append(line)
        else:
            sanitized_lines.append(line)
    return "\n".join(sanitized_lines)

def parse_ofx_fallback_regex(content_str: str, filename: str = "") -> pd.DataFrame:
    """Extrai transações via Regex em caso de falha do parser SGML estrito."""
    detected_inst = detect_institution(filename=filename, content_sample=content_str)
    records = []

    blocks = re.findall(r'<STMTTRN>(.*?)</STMTTRN>', content_str, re.DOTALL | re.IGNORECASE)
    for b in blocks:
        dtposted = re.search(r'<DTPOSTED>(.*?)(?:<|\n|\r)', b, re.IGNORECASE)
        trnamt = re.search(r'<TRNAMT>(.*?)(?:<|\n|\r)', b, re.IGNORECASE)
        memo = re.search(r'<MEMO>(.*?)(?:<|\n|\r)', b, re.IGNORECASE)
        name = re.search(r'<NAME>(.*?)(?:<|\n|\r)', b, re.IGNORECASE)

        # Parse Data (YYYYMMDD)
        raw_date = dtposted.group(1).strip() if dtposted else ""
        date_obj = None
        if len(raw_date) >= 8:
            try:
                date_obj = datetime.date(int(raw_date[:4]), int(raw_date[4:6]), int(raw_date[6:8]))
            except Exception:
                date_obj = datetime.date.today()
        else:
            date_obj = datetime.date.today()

        # Parse Valor e Tipo
        raw_val = trnamt.group(1).strip() if trnamt else "0"
        try:
            val_float = float(raw_val.replace(',', '.'))
        except ValueError:
            val_float = 0.0

        tipo = "Receita" if val_float > 0 else "Despesa"
        valor_abs = abs(val_float)

        descricao = memo.group(1).strip() if memo else (name.group(1).strip() if name else "Transação OFX")

        # Sugestão normalizada de Categoria baseada no tipo e texto da transação
        if tipo == "Receita":
            categoria = normalize_income_category(descricao)
        else:
            categoria = normalize_expense_category(descricao)

        desc_lower = descricao.lower()
        if "pix" in desc_lower:
            forma = "Pix"
        elif "cartao" in desc_lower or "fatura" in desc_lower:
            forma = "Cartão de crédito"
        elif "ted" in desc_lower or "doc" in desc_lower or "transf" in desc_lower:
            forma = "Transferência"
        elif "boleto" in desc_lower:
            forma = "Boleto"
        else:
            forma = "Conta corrente"

        fixo_var, essencial = infer_nature_and_essentiality(categoria, descricao)
        conta_creditada = detected_inst if tipo == "Receita" else ""
        conta_debitada = detected_inst if tipo == "Despesa" else ""

        records.append({
            "Data": date_obj,
            "Descricao": descricao,
            "Valor": valor_abs,
            "Categoria": categoria,
            "Tipo": tipo,
            "Conta creditada": conta_creditada,
            "Conta debitada": conta_debitada,
            "Fixo vs. Variável": fixo_var,
            "Essencial vs. Não Essencial": essencial,
            "Forma_Pagamento": forma
        })

    df = pd.DataFrame(records)
    if not df.empty:
        df["Hash"] = df.apply(lambda r: generate_transaction_hash(r["Data"], r["Valor"], r["Descricao"]), axis=1)
    else:
        df = pd.DataFrame(columns=['Data', 'Descricao', 'Valor', 'Categoria', 'Tipo', 'Conta creditada', 'Conta debitada', 'Fixo vs. Variável', 'Essencial vs. Não Essencial', 'Forma_Pagamento', 'Hash'])
    return df

def parse_ofx(file_input: Any, filename: str = "") -> pd.DataFrame:
    """
    Parser principal de OFX com sanitização prévia de cabeçalhos não-padrão
    (suporte a bancos como C6, Sicredi, Inter, Nubank) e fallback automático via Regex.
    Aceita bytes, str ou objetos file-like.
    """
    if isinstance(file_input, str):
        content_str = file_input
    elif isinstance(file_input, bytes):
        content_str = ""
        for enc in ['utf-8', 'latin1', 'cp1252']:
            try:
                content_str = file_input.decode(enc)
                break
            except Exception:
                continue
    elif hasattr(file_input, "read"):
        raw = file_input.read()
        if isinstance(raw, str):
            content_str = raw
        else:
            content_str = ""
            for enc in ['utf-8', 'latin1', 'cp1252']:
                try:
                    content_str = raw.decode(enc)
                    break
                except Exception:
                    continue
    else:
        content_str = str(file_input)

    if not content_str or not content_str.strip():
        return pd.DataFrame(columns=['Data', 'Descricao', 'Valor', 'Categoria', 'Tipo', 'Conta creditada', 'Conta debitada', 'Fixo vs. Variável', 'Essencial vs. Não Essencial', 'Forma_Pagamento', 'Hash'])

    detected_inst = detect_institution(filename=filename, content_sample=content_str)
    sanitized = sanitize_ofx_content(content_str)

    try:
        from ofxtools.Parser import OFXTree
        parser = OFXTree()
        parser.parse(io.StringIO(sanitized))
        ofx = parser.convert()

        records = []
        statements = []
        if hasattr(ofx, 'statements'):
            statements.extend(ofx.statements)
        if hasattr(ofx, 'bankStatements'):
            statements.extend(ofx.bankStatements)
        if hasattr(ofx, 'creditCardStatements'):
            statements.extend(ofx.creditCardStatements)

        for stmt in statements:
            if hasattr(stmt, 'transactions'):
                for stmt_trx in stmt.transactions:
                    dt = stmt_trx.dtposted
                    memo = str(getattr(stmt_trx, 'memo', '') or getattr(stmt_trx, 'name', '') or '').strip()
                    trnamt = float(stmt_trx.trnamt)

                    tipo = "Receita" if trnamt > 0 else "Despesa"
                    valor = abs(trnamt)

                    forma = "Conta corrente"
                    if "pix" in memo.lower():
                        forma = "Pix"
                    elif "cartao" in memo.lower() or "compra" in memo.lower():
                        forma = "Cartão de crédito" if hasattr(ofx, 'creditCardStatements') and stmt in ofx.creditCardStatements else "Débito"
                    elif "ted" in memo.lower() or "doc" in memo.lower() or "transf" in memo.lower():
                        forma = "Transferência"
                    elif "boleto" in memo.lower():
                        forma = "Boleto"

                    if tipo == "Receita":
                        categoria = normalize_income_category(memo)
                    else:
                        categoria = normalize_expense_category(memo)

                    fixo_var, essencial = infer_nature_and_essentiality(categoria, memo)
                    conta_creditada = detected_inst if tipo == "Receita" else ""
                    conta_debitada = detected_inst if tipo == "Despesa" else ""

                    records.append({
                        "Data": dt.date() if hasattr(dt, 'date') else pd.to_datetime(dt).date(),
                        "Descricao": memo if memo else "Transação OFX",
                        "Valor": valor,
                        "Categoria": categoria,
                        "Tipo": tipo,
                        "Conta creditada": conta_creditada,
                        "Conta debitada": conta_debitada,
                        "Fixo vs. Variável": fixo_var,
                        "Essencial vs. Não Essencial": essencial,
                        "Forma_Pagamento": forma
                    })

        if records:
            df = pd.DataFrame(records)
            df["Hash"] = df.apply(lambda r: generate_transaction_hash(r["Data"], r["Valor"], r["Descricao"]), axis=1)
            return df
        else:
            return parse_ofx_fallback_regex(sanitized, filename)

    except Exception as e:
        logger.warning(f"Parser OFX padrão falhou ({e}). Acionando parser fallback via Regex.")
        return parse_ofx_fallback_regex(sanitized, filename)

def parse_csv(file_bytes: bytes, filename: str = "") -> pd.DataFrame:
    """
    Realiza o parse e padronização de extratos bancários em formato CSV (.csv).
    Suporta múltiplos encodings (utf-8-sig, utf-8, latin1), detecta separadores (; ou ,)
    e possui suporte nativo à inferência de instituições financeiras (Sicredi, Inter, C6, XP, etc.).
    """
    try:
        # Tenta múltiplos encodings para decodificar e ler o CSV
        df_raw = None
        content_sample = ""
        for enc in ["utf-8-sig", "utf-8", "latin1"]:
            try:
                sample = file_bytes[:4096].decode(enc, errors="ignore")
                content_sample = sample
                sep = ";" if sample.count(";") > sample.count(",") else ","
                temp_df = pd.read_csv(io.BytesIO(file_bytes), sep=sep, encoding=enc, dtype=str)
                if temp_df.shape[1] >= 2 and not temp_df.empty:
                    df_raw = temp_df
                    break
            except Exception:
                continue

        if df_raw is None or df_raw.empty:
            return pd.DataFrame(columns=['Data', 'Descricao', 'Valor', 'Categoria', 'Tipo', 'Conta creditada', 'Conta debitada', 'Fixo vs. Variável', 'Essencial vs. Não Essencial', 'Forma_Pagamento', 'Hash'])

        detected_inst = detect_institution(filename=filename, content_sample=content_sample)

        # Normaliza nomes de colunas
        cols_map = {str(col).strip(): str(col).lower().strip() for col in df_raw.columns}
        
        date_col = None
        desc_col = None
        val_col = None
        tipo_col = None

        for orig, low in cols_map.items():
            if not date_col and any(k in low for k in ["data", "date", "dia", "dt"]):
                date_col = orig
            elif not desc_col and any(k in low for k in ["descricao", "descrição", "historico", "histórico", "memo", "title", "lançamento", "lancamento", "nome"]):
                desc_col = orig
            elif not val_col and any(k in low for k in ["valor", "amount", "value", "total", "quantia"]) and "saldo" not in low:
                val_col = orig
            elif not tipo_col and low in ["tipo", "tipo transacao", "tipo transação", "c/d"]:
                tipo_col = orig

        if not val_col:
            for c in df_raw.columns:
                sample_series = df_raw[c].dropna().astype(str).head(10)
                if any(re.search(r'\d+[,.]\d{2}', s) for s in sample_series):
                    val_col = c
                    break

        if not desc_col:
            for c in df_raw.columns:
                if c not in [date_col, val_col, tipo_col] and df_raw[c].dtype == object:
                    desc_col = c
                    break

        if not date_col:
            for c in df_raw.columns:
                if c not in [val_col, desc_col, tipo_col]:
                    sample_series = df_raw[c].dropna().astype(str).head(5)
                    if any(re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', s) for s in sample_series):
                        date_col = c
                        break

        records = []
        for _, row in df_raw.iterrows():
            d_val = str(row[date_col]).strip() if date_col and pd.notna(row[date_col]) else ""
            desc_val = str(row[desc_col]).strip() if desc_col and pd.notna(row[desc_col]) else "Lançamento CSV"
            v_raw = str(row[val_col]).strip() if val_col and pd.notna(row[val_col]) else "0"
            t_raw = str(row[tipo_col]).strip().upper() if tipo_col and pd.notna(row[tipo_col]) else ""

            if not d_val or not v_raw or v_raw == "0":
                continue

            # Parsing e normalização de Data
            dt_obj = pd.to_datetime(d_val, dayfirst=True, errors="coerce")
            if pd.isna(dt_obj):
                continue
            data_date = dt_obj.date()

            # Parsing de Valores Numéricos
            is_negative = "-" in v_raw or "DEBITO" in t_raw or "DÉBITO" in t_raw or "DEB" in t_raw
            is_credit = "+" in v_raw or "CREDITO" in t_raw or "CRÉDITO" in t_raw or "CRED" in t_raw

            v_clean = re.sub(r"[R\$\s\xa0\+\-]", "", v_raw).strip()

            if "," in v_clean and "." in v_clean:
                if v_clean.find(",") > v_clean.find("."):
                    v_clean = v_clean.replace(".", "").replace(",", ".")
                else:
                    v_clean = v_clean.replace(",", "")
            elif "," in v_clean:
                v_clean = v_clean.replace(",", ".")

            try:
                val_float = float(v_clean)
            except ValueError:
                continue

            # Determina Tipo
            if is_negative:
                tipo = "Despesa"
            elif is_credit:
                tipo = "Receita"
            elif "deb" in desc_val.lower():
                tipo = "Despesa"
            elif "cred" in desc_val.lower() or "recebimento" in desc_val.lower() or "salario" in desc_val.lower() or "salário" in desc_val.lower():
                tipo = "Receita"
            else:
                tipo = "Despesa"

            # Sugestão inteligente de Forma de Pagamento
            desc_lower = desc_val.lower()
            if "pix" in desc_lower:
                forma_pagto = "Pix"
            elif "debito" in desc_lower or "débito" in desc_lower:
                forma_pagto = "Débito"
            elif "credito" in desc_lower or "crédito" in desc_lower or "fatura" in desc_lower:
                forma_pagto = "Crédito"
            elif "boleto" in desc_lower:
                forma_pagto = "Boleto"
            else:
                forma_pagto = "Conta corrente"

            # Sugestão normalizada de Categoria baseada no tipo e texto da transação
            if tipo == "Receita":
                categoria = normalize_income_category(desc_val)
            else:
                categoria = normalize_expense_category(desc_val)

            fixo_var, essencial = infer_nature_and_essentiality(categoria, desc_val)
            conta_creditada = detected_inst if tipo == "Receita" else ""
            conta_debitada = detected_inst if tipo == "Despesa" else ""

            records.append({
                "Data": data_date,
                "Descricao": desc_val,
                "Valor": abs(val_float),
                "Categoria": categoria,
                "Tipo": tipo,
                "Conta creditada": conta_creditada,
                "Conta debitada": conta_debitada,
                "Fixo vs. Variável": fixo_var,
                "Essencial vs. Não Essencial": essencial,
                "Forma_Pagamento": forma_pagto
            })

        df = pd.DataFrame(records)
        if not df.empty:
            df["Hash"] = df.apply(lambda r: generate_transaction_hash(r["Data"], r["Valor"], r["Descricao"]), axis=1)
        else:
            df = pd.DataFrame(columns=['Data', 'Descricao', 'Valor', 'Categoria', 'Tipo', 'Conta creditada', 'Conta debitada', 'Fixo vs. Variável', 'Essencial vs. Não Essencial', 'Forma_Pagamento', 'Hash'])
        return df

    except Exception as e:
        logger.error(f"Erro ao processar arquivo CSV: {e}")
        return pd.DataFrame(columns=['Data', 'Descricao', 'Valor', 'Categoria', 'Tipo', 'Conta creditada', 'Conta debitada', 'Fixo vs. Variável', 'Essencial vs. Não Essencial', 'Forma_Pagamento', 'Hash'])

def parse_receipt_image(image_bytes: bytes, mime_type: str = "image/png") -> pd.DataFrame:
    """
    Processa comprovantes de Pix, faturas de cartão, recibos e extratos fotográficos utilizando o Gemini Multimodal.
    Retorna DataFrame padronizado com Schema Pydantic estruturado.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Chave GEMINI_API_KEY não configurada no ambiente ou no painel lateral.")
        
    genai.configure(api_key=api_key)
    
    prompt = """
Você é um auditor financeiro especialista em OCR e conciliação bancária.
Analise detalhadamente a imagem/documento anexo (que pode ser um comprovante de Pix, fatura de cartão de crédito, extrato bancário ou cupom fiscal).
Extraia todas as transações financeiras individuais visíveis.

Para cada transação, extraia:
1. data: Data do pagamento/lançamento no formato YYYY-MM-DD. Se o ano não for informado, assuma o ano corrente.
2. descricao: Nome da loja, estabelecimento, beneficiário ou descrição clara da transação.
3. valor: Valor numérico positivo em reais (float).
4. tipo: 'Despesa' para pagamentos/saídas/compras e 'Receita' para transferências recebidas/estornos.
5. categoria: Categoria sugerida de gasto (ex: Alimentação, Supermercado, Transporte, Moradia, Saúde, Lazer, Vestuário, Educação, Serviços, Renda Extra, Outros).
6. forma_pagamento: 'Pix', 'Cartão de Crédito', 'Cartão de Débito', 'Boleto', 'Transferência' ou 'Outros'.

Seja rigoroso e preciso com os valores e datas. Retorne estritamente o JSON estruturado conforme o schema.
"""

    try:
        # Tenta modelos na ordem de preferência (2.5-flash, 1.5-flash)
        model_name = "gemini-1.5-flash"
        
        model = genai.GenerativeModel(
            model_name=model_name,
            generation_config={
                "response_mime_type": "application/json",
                "response_schema": RegistroFinanceiroLote
            }
        )
        
        image_part = {
            "mime_type": mime_type,
            "data": image_bytes
        }
        
        response = model.generate_content([image_part, prompt])
        res_json = json.loads(response.text)
        
        transacoes = res_json.get("transacoes", [])
        if not transacoes and isinstance(res_json, list):
            transacoes = res_json
            
        records = []
        for item in transacoes:
            raw_d = item.get("data", "")
            try:
                dt_obj = pd.to_datetime(raw_d, dayfirst=True).date()
            except Exception:
                dt_obj = pd.Timestamp.now().date()

            desc = item.get("descricao", "Comprovante").strip()
            cat_sug = item.get("categoria", "Outros").strip()
            tipo = item.get("tipo", "Despesa").strip().capitalize()
            if tipo == "Receita":
                cat = normalize_income_category(f"{cat_sug} {desc}")
            else:
                cat = normalize_expense_category(f"{cat_sug} {desc}")

            fixo_var, essencial = infer_nature_and_essentiality(cat, desc)
            forma_pagto = item.get("forma_pagamento", "Pix").strip()

            records.append({
                "Data": dt_obj,
                "Descricao": desc,
                "Valor": float(item.get("valor", 0.0)),
                "Categoria": cat,
                "Tipo": tipo,
                "Conta creditada": "Conta corrente" if tipo == "Receita" else "",
                "Conta debitada": forma_pagto if tipo == "Despesa" else "",
                "Fixo vs. Variável": fixo_var,
                "Essencial vs. Não Essencial": essencial,
                "Forma_Pagamento": forma_pagto
            })
            
        df = pd.DataFrame(records)
        if not df.empty:
            df["Hash"] = df.apply(lambda r: generate_transaction_hash(r["Data"], r["Valor"], r["Descricao"]), axis=1)
        else:
            df = pd.DataFrame(columns=['Data', 'Descricao', 'Valor', 'Categoria', 'Tipo', 'Conta creditada', 'Conta debitada', 'Fixo vs. Variável', 'Essencial vs. Não Essencial', 'Forma_Pagamento', 'Hash'])
        return df

    except Exception as e:
        logger.error(f"Erro ao processar imagem com Gemini Vision: {e}")
        # Fallback sem response_schema caso a versão do SDK ou modelo tenha restrição
        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            image_part = {"mime_type": mime_type, "data": image_bytes}
            prompt_fallback = prompt + "\nResponda em formato JSON puro: {\"transacoes\": [{\"data\": \"YYYY-MM-DD\", \"descricao\": \"...\", \"valor\": 0.00, \"tipo\": \"Despesa\", \"categoria\": \"...\", \"forma_pagamento\": \"...\"}]}"
            response = model.generate_content([image_part, prompt_fallback])
            
            raw_text = response.text
            match = re.search(r"\{.*\}|\[.*\]", raw_text, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                items = data.get("transacoes", data) if isinstance(data, dict) else data
                records = []
                for it in items:
                    d_str = it.get("data", pd.Timestamp.now().strftime("%Y-%m-%d"))
                    try:
                        d_obj = pd.to_datetime(d_str).date()
                    except Exception:
                        d_obj = pd.Timestamp.now().date()
                    
                    desc = it.get("descricao", "Lançamento")
                    cat_sug = it.get("categoria", "Outros")
                    tipo = it.get("tipo", "Despesa").capitalize()
                    cat = normalize_income_category(f"{cat_sug} {desc}") if tipo == "Receita" else normalize_expense_category(f"{cat_sug} {desc}")
                    fixo_var, essencial = infer_nature_and_essentiality(cat, desc)
                    forma_pagto = it.get("forma_pagamento", "Outros")

                    records.append({
                        "Data": d_obj,
                        "Descricao": desc,
                        "Valor": float(it.get("valor", 0.0)),
                        "Categoria": cat,
                        "Tipo": tipo,
                        "Conta creditada": "Conta corrente" if tipo == "Receita" else "",
                        "Conta debitada": forma_pagto if tipo == "Despesa" else "",
                        "Fixo vs. Variável": fixo_var,
                        "Essencial vs. Não Essencial": essencial,
                        "Forma_Pagamento": forma_pagto
                    })
                df = pd.DataFrame(records)
                if not df.empty:
                    df["Hash"] = df.apply(lambda r: generate_transaction_hash(r["Data"], r["Valor"], r["Descricao"]), axis=1)
                    return df
            return pd.DataFrame(columns=['Data', 'Descricao', 'Valor', 'Categoria', 'Tipo', 'Conta creditada', 'Conta debitada', 'Fixo vs. Variável', 'Essencial vs. Não Essencial', 'Forma_Pagamento', 'Hash'])
        except Exception as e2:
            logger.error(f"Erro no fallback do Gemini Vision: {e2}")
            raise RuntimeError(f"Falha na extração de dados via Gemini Vision: {e}")
