import os
import re
import json
import pandas as pd
import gspread
from gspread.utils import rowcol_to_a1
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
import streamlit as st
from src.database import db_manager
from src.utils.logger import get_logger

logger = get_logger("services", "data_loader")

def insert_into_native_table(spreadsheet, worksheet_name: str, rows_data: list) -> int:
    """
    Insere novas transações forçando a expansão do contêiner da Tabela Nativa do Google Sheets,
    preservando formatação contábil, validação de dados e chips coloridos.
    """
    if not rows_data or spreadsheet is None:
        return 0

    ws = spreadsheet.worksheet(worksheet_name)
    all_values = ws.get_all_values()
    current_last_row = len(all_values)

    if current_last_row <= 1:
        ws.insert_rows(rows_data, row=2, value_input_option="USER_ENTERED")
        return len(rows_data)

    # 1. Captura os dados da última linha que já pertence à tabela nativa
    old_last_row_values = ws.row_values(current_last_row)
    num_cols = max(len(old_last_row_values), len(rows_data[0]))
    num_new_rows = len(rows_data)

    # 2. Insere linhas em branco na posição da última linha (DENTRO do contêiner da tabela)
    # Isso força o Google Sheets a expandir o objeto da Tabela Nativa automaticamente
    blank_rows = [[""] * num_cols] * num_new_rows
    ws.insert_rows(blank_rows, row=current_last_row)

    # 3. Preenche o bloco expandido [current_last_row até current_last_row + num_new_rows]
    # Mantém a linha antiga na posição current_last_row e adiciona as novas linhas logo abaixo
    full_payload = [old_last_row_values] + rows_data
    
    start_cell = rowcol_to_a1(current_last_row, 1)
    end_cell = rowcol_to_a1(current_last_row + num_new_rows, num_cols)
    range_to_update = f"{start_cell}:{end_cell}"

    ws.update(
        range_name=range_to_update,
        values=full_payload,
        value_input_option="USER_ENTERED"
    )

    # 4. Replica validação e formatação para garantir consistência estética
    try:
        model_row_idx = current_last_row - 1
        new_last_row = current_last_row + num_new_rows
        batch_body = {
            "requests": [
                {
                    "copyPaste": {
                        "source": {
                            "sheetId": ws.id,
                            "startRowIndex": model_row_idx - 1,
                            "endRowIndex": model_row_idx,
                            "startColumnIndex": 0,
                            "endColumnIndex": num_cols
                        },
                        "destination": {
                            "sheetId": ws.id,
                            "startRowIndex": model_row_idx,
                            "endRowIndex": new_last_row,
                            "startColumnIndex": 0,
                            "endColumnIndex": num_cols
                        },
                        "pasteType": "PASTE_FORMAT"
                    }
                },
                {
                    "copyPaste": {
                        "source": {
                            "sheetId": ws.id,
                            "startRowIndex": model_row_idx - 1,
                            "endRowIndex": model_row_idx,
                            "startColumnIndex": 0,
                            "endColumnIndex": num_cols
                        },
                        "destination": {
                            "sheetId": ws.id,
                            "startRowIndex": model_row_idx,
                            "endRowIndex": new_last_row,
                            "startColumnIndex": 0,
                            "endColumnIndex": num_cols
                        },
                        "pasteType": "PASTE_DATA_VALIDATION"
                    }
                }
            ]
        }
        spreadsheet.batch_update(batch_body)
    except Exception as e_fmt:
        logger.warning(f"Aviso ao replicar estilos da tabela em {worksheet_name}: {e_fmt}")

    return num_new_rows


# Carrega variáveis de ambiente (override=True garante atualização dinâmica)
load_dotenv(override=True)

# Escopos do Google API
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def clean_currency(val):
    """
    Limpa strings de valores monetários no formato brasileiro (ex: R$ 1.234,56 ou -R$ 50,00)
    para o formato float do Python.
    """
    if pd.isna(val) or val == "":
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    
    val_str = str(val).strip()
    # Remove símbolos de moeda e espaços em branco
    val_str = re.sub(r"[R\$\s\xa0]", "", val_str)
    
    # Tratamento para pontuações no padrão BR (1.234,56 ou 1234,56)
    if "," in val_str:
        val_str = val_str.replace(".", "")  # remove separador de milhar
        val_str = val_str.replace(",", ".")  # substitui vírgula por ponto decimal
        
    try:
        return float(val_str)
    except ValueError:
        return 0.0

def clean_float(val):
    """
    Converte valores decimais de forma robusta, suportando formatos BR (1.234,56) e US (1,234.56).
    """
    if pd.isna(val) or val == "":
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    
    val_str = str(val).strip()
    # Remove símbolos monetários comuns e espaços
    val_str = re.sub(r"[R\$\s\xa0US]", "", val_str)
    
    if "," in val_str and "." in val_str:
        if val_str.find(",") > val_str.find("."):
            # Padrão BR: 1.234,56
            val_str = val_str.replace(".", "").replace(",", ".")
        else:
            # Padrão US: 1,234.56
            val_str = val_str.replace(",", "")
    elif "," in val_str:
        # Se tiver apenas vírgula, ex: 1,5 ou 1.500
        val_str = val_str.replace(",", ".")
        
    try:
        return float(val_str)
    except ValueError:
        return 0.0

def clean_int(val):
    """
    Converte valores inteiros de forma segura, preservando strings de status.
    """
    if pd.isna(val) or val == "":
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    
    val_str = str(val).strip()
    try:
        return int(val_str.replace(".", ""))
    except ValueError:
        try:
            return int(float(val_str.replace(".", "")))
        except ValueError:
            return val
 
def clean_percent_or_float(val):
    """
    Limpa e converte strings de percentuais ou decimais para float (ex: 105% -> 1.05, 5,85% -> 0.0585).
    """
    if pd.isna(val) or val == "":
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).strip()
    is_pct = False
    if "%" in val_str:
        val_str = val_str.replace("%", "").strip()
        is_pct = True
    if "," in val_str:
        val_str = val_str.replace(".", "").replace(",", ".")
    try:
        f = float(val_str)
        return f / 100.0 if is_pct else f
    except ValueError:
        return 0.0

@st.cache_resource
def get_gspread_client():
    """
    Inicializa e faz cache do cliente gspread usando a conta de serviço especificada.
    Suporta busca em data/credentials.json ou na raiz.
    """
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "data/credentials.json")
    if not os.path.exists(creds_path):
        # Fallback para raiz
        fallback_path = "credentials.json"
        if os.path.exists(fallback_path):
            creds_path = fallback_path
        else:
            raise FileNotFoundError(
                f"Arquivo de credenciais do Google Cloud '{creds_path}' não encontrado. "
                "Por favor, configure o arquivo em data/credentials.json ou ajuste o caminho no arquivo .env."
            )
    
    credentials = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    return gspread.authorize(credentials)

def get_budget_spreadsheet_id_for_year(ano: str | int) -> str | None:
    """
    Retorna o ID da planilha de orçamento do Google Sheets para o ano informado.
    Busca nas variáveis de ambiente na seguinte ordem de prioridade:
    1. SPREADSHEET_BUDGET_ID_{ANO} (ex: SPREADSHEET_BUDGET_ID_2027)
    2. SPREADSHEET_BUDGET_IDS (JSON ex: {"2026": "...", "2027": "..."})
    3. SPREADSHEET_BUDGET_ID (fallback geral)
    """
    ano_str = str(ano).strip()
    
    # 1. Variável de ambiente específica por ano
    env_ano_key = f"SPREADSHEET_BUDGET_ID_{ano_str}"
    val_ano = os.getenv(env_ano_key)
    if val_ano and val_ano.strip():
        return val_ano.strip()
        
    # 2. JSON de múltiplos anos
    json_ids = os.getenv("SPREADSHEET_BUDGET_IDS", "")
    if json_ids:
        try:
            parsed = json.loads(json_ids)
            if isinstance(parsed, dict) and ano_str in parsed and parsed[ano_str]:
                return str(parsed[ano_str]).strip()
        except Exception as e:
            logger.warning(f"Erro ao decodificar SPREADSHEET_BUDGET_IDS: {e}")
            
    # 3. Fallback para ID geral
    return os.getenv("SPREADSHEET_BUDGET_ID")

def get_all_budget_spreadsheets() -> dict[str, str]:
    """
    Retorna um dicionário {ano: spreadsheet_id} de todas as planilhas de orçamento
    configuradas no ambiente (.env). Permite suporte escalável a 2026, 2027 e anos futuros.
    """
    planilhas = {}
    
    # 1. Varre variáveis no formato SPREADSHEET_BUDGET_ID_<ANO>
    pattern = re.compile(r"^SPREADSHEET_BUDGET_ID_(\d{4})$", re.IGNORECASE)
    for key, value in os.environ.items():
        match = pattern.match(key)
        if match and value and value.strip():
            ano = match.group(1)
            planilhas[ano] = value.strip()
            
    # 2. Varre JSON SPREADSHEET_BUDGET_IDS se configurado
    json_ids = os.getenv("SPREADSHEET_BUDGET_IDS", "")
    if json_ids:
        try:
            parsed = json.loads(json_ids)
            if isinstance(parsed, dict):
                for k, v in parsed.items():
                    if str(k).isdigit() and v and str(v).strip():
                        planilhas[str(k)] = str(v).strip()
        except Exception as e:
            logger.warning(f"Erro ao decodificar SPREADSHEET_BUDGET_IDS: {e}")

    # 3. Se nenhuma planilha por ano foi encontrada, utiliza o fallback SPREADSHEET_BUDGET_ID
    if not planilhas:
        default_id = os.getenv("SPREADSHEET_BUDGET_ID")
        if default_id and default_id.strip():
            planilhas["2026"] = default_id.strip()

    return dict(sorted(planilhas.items()))

import time

@st.cache_data(ttl=600)  # Cache de 10 minutos para não estourar cota do Sheets
def load_sheet_data(spreadsheet_id, sheet_name, max_retries=3):
    """
    Carrega os dados de uma aba específica de uma planilha como um DataFrame do Pandas.
    Inclui tentativas automáticas com backoff para resiliência a instabilidades do Google API (503 / 429).
    """
    for attempt in range(1, max_retries + 1):
        try:
            client = get_gspread_client()
            spreadsheet = client.open_by_key(spreadsheet_id)
            worksheet = spreadsheet.worksheet(sheet_name)
            records = worksheet.get_all_records(numericise_ignore=['all'])
            
            if not records:
                data = worksheet.get_all_values()
                if len(data) > 1:
                    headers = [h.strip() for h in data[0]]
                    rows = data[1:]
                    df = pd.DataFrame(rows, columns=headers)
                else:
                    return pd.DataFrame()
            else:
                df = pd.DataFrame(records)
                
            df.columns = [col.strip() for col in df.columns]
            return df
        except Exception as e:
            err_str = str(e)
            if ("503" in err_str or "429" in err_str or "unavailable" in err_str.lower()) and attempt < max_retries:
                logger.warning(f"Instabilidade temporária no Google Sheets ({err_str}). Tentativa {attempt}/{max_retries}. Aguardando...")
                time.sleep(1.5 * attempt)
                continue
            logger.error(f"Erro ao carregar a aba '{sheet_name}' da planilha '{spreadsheet_id}' (tentativa {attempt}/{max_retries}): {e}")
            if attempt == max_retries:
                return pd.DataFrame()
    return pd.DataFrame()

def update_worksheet_from_dataframe(spreadsheet_id: str, worksheet_name: str, df: pd.DataFrame) -> bool:
    """
    Substitui com segurança o conteúdo de uma aba específica no Google Sheets com o DataFrame fornecido,
    formatando datas, números e texto no padrão nativo compatível com fórmulas e tabelas do Google Sheets.
    """
    if not spreadsheet_id or not worksheet_name:
        raise ValueError("ID da planilha ou nome da aba inválido.")
        
    try:
        client = get_gspread_client()
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.worksheet(worksheet_name)
        
        df_export = df.copy()
        
        # Formata colunas de data para DD/MM/YYYY
        for col in df_export.columns:
            if pd.api.types.is_datetime64_any_dtype(df_export[col]):
                df_export[col] = df_export[col].dt.strftime("%d/%m/%Y").fillna("")
            elif "data" in col.lower() or "em" in col.lower():
                def format_date_cell(val):
                    if pd.isna(val) or str(val).strip() in ["", "NaT", "None"]:
                        return ""
                    val_str = str(val).strip()
                    try:
                        if "-" in val_str and len(val_str.split("-")[0]) == 4:
                            dt = pd.to_datetime(val_str, errors="coerce")
                            if not pd.isna(dt):
                                return dt.strftime("%d/%m/%Y")
                    except Exception:
                        pass
                    return val_str
                df_export[col] = df_export[col].apply(format_date_cell)
            elif df_export[col].dtype == object:
                df_export[col] = df_export[col].fillna("").astype(str).str.strip()
                
        df_export = df_export.fillna("")
        
        header = [str(c).strip() for c in df_export.columns.tolist()]
        data_values = df_export.values.tolist()
        
        clean_rows = []
        for row in data_values:
            clean_row = []
            for item in row:
                if pd.isna(item) or str(item) in ["nan", "None", "NaT"]:
                    clean_row.append("")
                elif isinstance(item, (int, float)):
                    clean_row.append(item)
                else:
                    clean_row.append(str(item))
            clean_rows.append(clean_row)
            
        all_rows = [header] + clean_rows
        
        worksheet.clear()
        try:
            worksheet.update(range_name="A1", values=all_rows, value_input_option="USER_ENTERED")
        except TypeError:
            try:
                worksheet.update("A1", all_rows, value_input_option="USER_ENTERED")
            except Exception:
                worksheet.update(all_rows, value_input_option="USER_ENTERED")

        # Limpa cache do carregador de planilhas
        try:
            load_sheet_data.clear()
        except Exception:
            pass

        logger.info(f"Aba '{worksheet_name}' da planilha '{spreadsheet_id}' atualizada com sucesso ({len(df)} registros).")
        return True
    except Exception as e:
        logger.error(f"Erro ao atualizar aba '{worksheet_name}' da planilha '{spreadsheet_id}': {e}")
        raise e

def get_all_editable_spreadsheets() -> list[dict]:
    """
    Retorna uma lista estruturada de todas as planilhas e abas editáveis disponíveis no sistema,
    incluindo planilhas de Orçamento anuais (2026, 2027, futuros anos) e Planilha de Ordens.
    """
    sheets_list = []
    
    # 1. Planilhas de Orçamento por ano
    budget_spreadsheets = get_all_budget_spreadsheets()
    for ano, b_id in budget_spreadsheets.items():
        if b_id:
            sheets_list.append({
                "id": f"budget_{ano}",
                "title": f"Planilha de Orçamento {ano}",
                "type": "budget",
                "year": ano,
                "spreadsheet_id": b_id,
                "tabs": ["Despesas", "Receitas"],
                "url": f"https://docs.google.com/spreadsheets/d/{b_id}/edit"
            })
            
    # 2. Planilha de Ordens
    orders_id = os.getenv("SPREADSHEET_ORDERS_ID")
    if orders_id:
        sheets_list.append({
            "id": "orders",
            "title": "Planilha de Ordens (Investimentos)",
            "type": "orders",
            "year": None,
            "spreadsheet_id": orders_id,
            "tabs": ["Ordens"],
            "url": f"https://docs.google.com/spreadsheets/d/{orders_id}/edit"
        })
        
    return sheets_list

def append_transactions_to_sheets(df_transacoes: pd.DataFrame) -> dict:
    """
    Insere novas transações aprovadas nas abas 'Despesas' e 'Receitas' da planilha Google Sheets
    correspondente ao ano da transação ('Planilha de Orçamento {ANO}' ou via SPREADSHEET_BUDGET_ID)
    e atualiza diretamente o banco SQLite local em paridade imediata.
    
    Schema Despesas:
    ['Nome', 'Valor', 'Categoria', 'Conta debitada', 'Fixo vs. Variável', 'Essencial vs. Não Essencial', 'Gasto em', 'Dias até', 'Tipo de Cobrança']
    
    Schema Receitas:
    ['Nome', 'Valor', 'Categoria', 'Recebido em', 'Dias até']
    """
    if df_transacoes.empty:
        return {"despesas": 0, "receitas": 0}

    client = None
    try:
        client = get_gspread_client()
    except Exception as e:
        logger.error(f"Erro de autenticação com Google Sheets: {e}")
        st.error(f"⚠️ Erro ao conectar ao Google Sheets: {e}")

    inserted_counts = {"despesas": 0, "receitas": 0}
    df_despesas_local = []
    df_receitas_local = []

    # Agrupa transações por ano da data de lançamento
    transacoes_por_ano = {}
    for idx, row in df_transacoes.iterrows():
        data_raw = row.get("Data", row.get("Gasto em", row.get("Recebido em", "")))
        try:
            d_str = str(data_raw).strip()
            # Se já estiver em formato ISO YYYY-MM-DD (com traço no início)
            if "-" in d_str and len(d_str.split("-")[0]) == 4:
                dt_obj = pd.to_datetime(d_str, format="mixed", errors="coerce")
            else:
                dt_obj = pd.to_datetime(d_str, dayfirst=True, format="mixed", errors="coerce")
                
            if pd.isna(dt_obj) or dt_obj is pd.NaT:
                dt_obj = pd.Timestamp.now()
                
            ano = str(dt_obj.year)
            # Padrão nativo do Google Sheets brasileiro: DD/MM/YYYY
            data_br = dt_obj.strftime("%d/%m/%Y")
            data_sql = dt_obj.strftime("%Y-%m-%d 00:00:00")
        except Exception:
            ano = str(pd.Timestamp.now().year)
            data_br = str(data_raw)
            data_sql = str(data_raw)

        if ano not in transacoes_por_ano:
            transacoes_por_ano[ano] = []
        transacoes_por_ano[ano].append((row, data_br, data_sql))

    # Processa cada ano individualmente
    for ano, rows_ano in transacoes_por_ano.items():
        despesas_ano_sheet = []
        receitas_ano_sheet = []

        for row, data_br, data_sql in rows_ano:
            tipo = str(row.get("Tipo", "Despesa")).strip().capitalize()
            nome = str(row.get("Descricao", row.get("Nome", "Lançamento"))).strip()
            
            try:
                valor_num = float(row.get("Valor", 0.0))
            except (ValueError, TypeError):
                valor_num = 0.0

            categoria = str(row.get("Categoria", "Outros")).strip()

            if tipo == "Receita":
                # Schema Receitas: [Nome, Valor, Categoria, Conta creditada, Recebido em, Dias até]
                conta_cred = str(row.get("Conta creditada", row.get("Conta debitada", "Inter"))).strip()
                if not conta_cred or conta_cred == "None":
                    conta_cred = "Inter"

                dias_ate_rec = str(row.get("Dias até", "Já creditado")).strip() or "Já creditado"
                receitas_ano_sheet.append([
                    nome,
                    valor_num,
                    categoria,
                    conta_cred,
                    data_br,
                    dias_ate_rec
                ])
                df_receitas_local.append({
                    "Nome": nome,
                    "Valor": valor_num,
                    "Categoria": categoria,
                    "Conta creditada": conta_cred,
                    "Recebido em": data_sql,
                    "Dias até": 0
                })
            else:
                # Schema Despesas: [Nome, Valor, Categoria, Conta debitada, Fixo vs. Variável, Essencial vs. Não Essencial, Gasto em, Dias até, Tipo de Cobrança]
                conta_raw = str(row.get("Conta debitada", row.get("Forma_Pagamento", "Conta corrente"))).strip()
                conta = conta_raw if conta_raw and conta_raw != "None" else "Conta corrente"
                
                fixo_var_raw = str(row.get("Fixo vs. Variável", "Variável")).strip().capitalize()
                fixo_var = "Fixo" if fixo_var_raw == "Fixo" else "Variável"
                
                essencial_raw = str(row.get("Essencial vs. Não Essencial", "Essencial")).strip().capitalize()
                essencial = "Não essencial" if "não" in essencial_raw.lower() or "nao" in essencial_raw.lower() else "Essencial"
                
                dias_ate_desp = str(row.get("Dias até", "Já debitado")).strip() or "Já debitado"
                tipo_cobranca = str(row.get("Tipo de Cobrança", "À Vista")).strip() or "À Vista"

                despesas_ano_sheet.append([
                    nome,
                    valor_num,
                    categoria,
                    conta,
                    fixo_var,
                    essencial,
                    data_br,
                    dias_ate_desp,
                    tipo_cobranca
                ])
                df_despesas_local.append({
                    "Nome": nome,
                    "Valor": valor_num,
                    "Categoria": categoria,
                    "Conta debitada": conta,
                    "Gasto em": data_sql,
                    "Dias até": 0,
                    "Tipo de Cobrança": tipo_cobranca,
                    "Fixo vs. Variável": fixo_var,
                    "Essencial vs. Não Essencial": essencial
                })

        # Localiza planilha anual no Google Drive ou por ID específico do ano
        spreadsheet = None
        if client is not None:
            # 1. Tenta abrir pelo ID específico do ano configurado no .env (ex: SPREADSHEET_BUDGET_ID_2027)
            budget_id_ano = get_budget_spreadsheet_id_for_year(ano)
            if budget_id_ano:
                try:
                    spreadsheet = client.open_by_key(budget_id_ano)
                except Exception as e:
                    logger.warning(f"Não foi possível abrir planilha por ID para o ano {ano}: {e}")

            # 2. Se não abriu por ID, tenta abrir por título no Drive
            if spreadsheet is None:
                try:
                    sheet_title = f"Planilha de Orçamento {ano}"
                    spreadsheet = client.open(sheet_title)
                except Exception:
                    pass

            # 3. Fallback para SPREADSHEET_BUDGET_ID geral
            if spreadsheet is None:
                budget_id = os.getenv("SPREADSHEET_BUDGET_ID")
                if budget_id:
                    try:
                        spreadsheet = client.open_by_key(budget_id)
                    except Exception as e:
                        logger.error(f"Erro ao abrir planilha fallback: {e}")

            if spreadsheet is not None:
                if despesas_ano_sheet:
                    try:
                        n_desp = insert_into_native_table(spreadsheet, "Despesas", despesas_ano_sheet)
                        inserted_counts["despesas"] += n_desp
                        logger.info(f"{n_desp} despesas gravadas com sucesso na Tabela de {ano}.")
                    except Exception as e:
                        logger.error(f"Erro ao gravar Despesas: {e}")
                        st.error(f"Erro ao gravar Despesas na planilha do ano {ano}: {e}")

                if receitas_ano_sheet:
                    try:
                        n_rec = insert_into_native_table(spreadsheet, "Receitas", receitas_ano_sheet)
                        inserted_counts["receitas"] += n_rec
                        logger.info(f"{n_rec} receitas gravadas com sucesso na Tabela de {ano}.")
                    except Exception as e:
                        logger.error(f"Erro ao gravar Receitas: {e}")
                        st.error(f"Erro ao gravar Receitas na planilha do ano {ano}: {e}")
            else:
                inserted_counts["despesas"] += len(despesas_ano_sheet)
                inserted_counts["receitas"] += len(receitas_ano_sheet)

    if df_despesas_local:
        db_manager.save_dataframe_delta("despesas", pd.DataFrame(df_despesas_local), None)
    if df_receitas_local:
        db_manager.save_dataframe_delta("receitas", pd.DataFrame(df_receitas_local), None)

    return inserted_counts

def get_mock_data():
    """
    Gera dados simulados de alta qualidade para demonstração do aplicativo.
    """
    receitas_data = [
        {"Nome": "Salário Principal", "Valor": 8500.0, "Categoria": "Trabalho", "Recebido em": "05/05/2026", "Dias até": 0},
        {"Nome": "Projeto Freelance", "Valor": 2200.0, "Categoria": "Renda Extra", "Recebido em": "12/05/2026", "Dias até": 0},
    ]
    df_receitas = pd.DataFrame(receitas_data)
    df_receitas["Recebido em"] = pd.to_datetime(df_receitas["Recebido em"], format="%d/%m/%Y")
    df_receitas["Valor"] = df_receitas["Valor"].astype(float)
    df_receitas["Dias até"] = df_receitas["Dias até"].astype(int)

    despesas_data = [
        {"Nome": "Aluguel & Condomínio", "Valor": 2800.0, "Categoria": "Moradia", "Conta debitada": "Itaú", "Gasto em": "02/05/2026", "Dias até": 0, "Tipo de Cobrança": "Fixo", "Fixo vs. Variável": "Fixo", "Essencial vs. Não Essencial": "Essencial"},
        {"Nome": "Supermercado", "Valor": 1100.0, "Categoria": "Alimentação", "Conta debitada": "Nubank", "Gasto em": "10/05/2026", "Dias até": 0, "Tipo de Cobrança": "Variável", "Fixo vs. Variável": "Variável", "Essencial vs. Não Essencial": "Essencial"},
        {"Nome": "Combustível", "Valor": 450.0, "Categoria": "Transporte", "Conta debitada": "Nubank", "Gasto em": "15/05/2026", "Dias até": 0, "Tipo de Cobrança": "Variável", "Fixo vs. Variável": "Variável", "Essencial vs. Não Essencial": "Essencial"},
        {"Nome": "Academia", "Valor": 150.0, "Categoria": "Saúde", "Conta debitada": "Nubank", "Gasto em": "05/05/2026", "Dias até": 0, "Tipo de Cobrança": "Fixo", "Fixo vs. Variável": "Fixo", "Essencial vs. Não Essencial": "Não essencial"},
        {"Nome": "Streaming & Internet", "Valor": 180.0, "Categoria": "Lazer", "Conta debitada": "Itaú", "Gasto em": "08/05/2026", "Dias até": 0, "Tipo de Cobrança": "Fixo", "Fixo vs. Variável": "Fixo", "Essencial vs. Não Essencial": "Não essencial"},
        {"Nome": "Jantar Fora", "Valor": 350.0, "Categoria": "Lazer", "Conta debitada": "Nubank", "Gasto em": "20/05/2026", "Dias até": 0, "Tipo de Cobrança": "Variável", "Fixo vs. Variável": "Variável", "Essencial vs. Não Essencial": "Não essencial"},
    ]
    df_despesas = pd.DataFrame(despesas_data)
    df_despesas["Gasto em"] = pd.to_datetime(df_despesas["Gasto em"], format="%d/%m/%Y")
    df_despesas["Valor"] = df_despesas["Valor"].astype(float)
    df_despesas["Dias até"] = df_despesas["Dias até"].astype(int)

    dividendos_data = [
        {"Nome": "Rendimento HGLG11", "Valor": 110.0, "Ativo": "HGLG11", "Categoria": "FIIs", "Recebido em": "15/05/2026", "Dias até": 0},
        {"Nome": "Dividendos PETR4", "Valor": 320.0, "Ativo": "PETR4", "Categoria": "Ações", "Recebido em": "20/05/2026", "Dias até": 0},
        {"Nome": "Proventos WEGE3", "Valor": 45.0, "Ativo": "WEGE3", "Categoria": "Ações", "Recebido em": "22/05/2026", "Dias até": 0},
    ]
    df_dividendos = pd.DataFrame(dividendos_data)
    df_dividendos["Recebido em"] = pd.to_datetime(df_dividendos["Recebido em"], format="%d/%m/%Y")
    df_dividendos["Valor"] = df_dividendos["Valor"].astype(float)
    df_dividendos["Dias até"] = df_dividendos["Dias até"].astype(int)

    ordens_data = [
        {"Compra/Venda": "Compra", "Tipo": "Ações", "Moeda": "BRL", "Papel": "WEGE3", "Qtd Executada": 100, "Preço médio": 35.0, "Total": 3500.0, "data envio": "15/01/2025 10:30:00", "Cód. Cliente": "PAULO01", "Corretagem": 0.0, "Preço médio + corretagem": 35.0, "Total líquido": 3500.0, "Setor Econômico": "Bens Industriais / Máquinas"},
        {"Compra/Venda": "Compra", "Tipo": "Ações", "Moeda": "BRL", "Papel": "PETR4", "Qtd Executada": 150, "Preço médio": 28.0, "Total": 4200.0, "data envio": "18/01/2025 11:15:00", "Cód. Cliente": "PAULO01", "Corretagem": 0.0, "Preço médio + corretagem": 28.0, "Total líquido": 4200.0, "Setor Econômico": "Petróleo, Gás e Biocombustíveis"},
        {"Compra/Venda": "Compra", "Tipo": "FIIs", "Moeda": "BRL", "Papel": "HGLG11", "Qtd Executada": 50, "Preço médio": 155.0, "Total": 7750.0, "data envio": "20/01/2025 14:00:00", "Cód. Cliente": "PAULO01", "Corretagem": 0.0, "Preço médio + corretagem": 155.0, "Total líquido": 7750.0, "Setor Econômico": "Imobiliário"},
        {"Compra/Venda": "Compra", "Tipo": "Ações", "Moeda": "BRL", "Papel": "VALE3", "Qtd Executada": 50, "Preço médio": 62.0, "Total": 3100.0, "data envio": "10/07/2025 10:45:00", "Cód. Cliente": "PAULO01", "Corretagem": 0.0, "Preço médio + corretagem": 62.0, "Total líquido": 3100.0, "Setor Econômico": "Materiais Básicos / Mineração"},
        {"Compra/Venda": "Compra", "Tipo": "Ações", "Moeda": "BRL", "Papel": "WEGE3", "Qtd Executada": 50, "Preço médio": 38.5, "Total": 1925.0, "data envio": "12/07/2025 15:20:00", "Cód. Cliente": "PAULO01", "Corretagem": 0.0, "Preço médio + corretagem": 38.5, "Total líquido": 1925.0, "Setor Econômico": "Bens Industriais / Máquinas"},
        {"Compra/Venda": "Compra", "Tipo": "Internacional", "Moeda": "USD", "Papel": "IVV", "Qtd Executada": 10, "Preço médio": 480.0, "Total": 4800.0, "data envio": "05/01/2026 16:00:00", "Cód. Cliente": "PAULO01", "Corretagem": 0.0, "Preço médio + corretagem": 480.0, "Total líquido": 24000.0, "Setor Econômico": "Tecnologia"},
    ]
    df_ordens = pd.DataFrame(ordens_data)
    df_ordens["data envio"] = pd.to_datetime(df_ordens["data envio"], format="%d/%m/%Y %H:%M:%S")
    
    return df_receitas, df_despesas, df_dividendos, df_ordens

def clean_and_normalize_orders(df_orders):
    """
    Limpa, normaliza colunas e valores, e aplica autocorreções no DataFrame de ordens.
    """
    if df_orders.empty:
        return df_orders
        
    col_mapping = {}
    for col in df_orders.columns:
        c_lower = str(col).lower().strip()
        if c_lower in ["data envio", "data de envio", "data_envio", "data", "data de envio de ordens"]:
            col_mapping[col] = "data envio"
        elif c_lower in ["compra/venda", "compra ou venda", "operação", "operacao", "c/v", "tipo de operacao", "tipo de operação"]:
            col_mapping[col] = "Compra/Venda"
        elif c_lower in ["tipo", "classe", "categoria"]:
            col_mapping[col] = "Tipo"
        elif c_lower in ["moeda"]:
            col_mapping[col] = "Moeda"
        elif c_lower in ["papel", "ativo", "ticker", "código", "codigo"]:
            col_mapping[col] = "Papel"
        elif c_lower in ["qtd executada", "quantidade", "qtd", "quantidade executada", "volume", "qtd execu", "qtd exec"]:
            col_mapping[col] = "Qtd Executada"
        elif c_lower in ["preço médio", "preco medio", "preço unitário", "preco unitario", "pm", "preço médi", "preco medi", "preço med"]:
            col_mapping[col] = "Preço médio"
        elif c_lower in ["total", "valor total", "valor"]:
            col_mapping[col] = "Total"
        elif c_lower in ["cód. cliente", "cod. cliente", "cliente", "cod cliente", "código cliente"]:
            col_mapping[col] = "Cód. Cliente"
        elif c_lower in ["corretagem", "taxas", "taxa", "custos", "corretag"]:
            col_mapping[col] = "Corretagem"
        elif c_lower in ["preço médio + corretagem", "preco medio + corretagem", "preço médio com corretagem", "pm+corretagem", "preço médio + c", "preco medio + c"]:
            col_mapping[col] = "Preço médio + corretagem"
        elif c_lower in ["total líquido", "total liquido", "valor líquido", "valor liquido", "total liquid"]:
            col_mapping[col] = "Total líquido"
        elif c_lower in ["setor econômico", "setor economico", "setor", "setor econômico"]:
            col_mapping[col] = "Setor Econômico"
        elif c_lower in ["indexador", "index", "tipo indexador"]:
            col_mapping[col] = "Indexador"
        elif c_lower in ["taxa indexador", "taxa index", "taxa", "taxaindexador", "taxaindex", "taxa inde:", "taxa inde"]:
            col_mapping[col] = "Taxa Indexador"
            
    if col_mapping:
        df_orders = df_orders.rename(columns=col_mapping)
        
    if "data envio" not in df_orders.columns:
        for col in df_orders.columns:
            if "data" in str(col).lower():
                df_orders = df_orders.rename(columns={col: "data envio"})
                break
        if "data envio" not in df_orders.columns:
            df_orders["data envio"] = pd.Timestamp.now()
            
    if "Papel" not in df_orders.columns:
        for col in df_orders.columns:
            if "ativo" in str(col).lower() or "papel" in str(col).lower() or "ticker" in str(col).lower():
                df_orders = df_orders.rename(columns={col: "Papel"})
                break
        if "Papel" not in df_orders.columns:
            df_orders["Papel"] = "AtivoIndefinido"
            
    if "Qtd Executada" not in df_orders.columns:
        for col in df_orders.columns:
            if "qtd" in str(col).lower() or "quant" in str(col).lower():
                df_orders = df_orders.rename(columns={col: "Qtd Executada"})
                break
                
    numeric_cols = ["Qtd Executada", "Preço médio", "Total", "Corretagem", "Preço médio + corretagem", "Total líquido"]
    for col in numeric_cols:
        if col in df_orders.columns:
            if col == "Qtd Executada":
                df_orders[col] = df_orders[col].apply(clean_float)
            else:
                df_orders[col] = df_orders[col].apply(clean_currency)
        else:
            df_orders[col] = 0.0
            
    if "Qtd Executada" in df_orders.columns and "Total" in df_orders.columns and "Preço médio" in df_orders.columns:
        import math
        for idx, row in df_orders.iterrows():
            try:
                qty = float(row["Qtd Executada"])
                tot = float(row["Total"])
                pm = float(row["Preço médio"])
                
                if qty > 0 and tot > 0 and pm > 0:
                    expected_qty = tot / pm
                    if qty > expected_qty * 3.0:
                        ratio = qty / expected_qty
                        power = round(math.log10(ratio))
                        if power > 0:
                            df_orders.at[idx, "Qtd Executada"] = qty / (10 ** power)
            except Exception:
                pass
                
    if "data envio" in df_orders.columns:
        raw_dates = df_orders["data envio"].copy()
        df_orders["data envio"] = pd.to_datetime(raw_dates, dayfirst=True, errors="coerce")
        
    string_cols = ["Compra/Venda", "Tipo", "Moeda", "Papel", "Setor Econômico", "Indexador"]
    for col in string_cols:
        if col in df_orders.columns:
            df_orders[col] = df_orders[col].astype(str).str.strip()
        else:
            df_orders[col] = ""
            
    if "Taxa Indexador" in df_orders.columns:
        df_orders["Taxa Indexador"] = df_orders["Taxa Indexador"].apply(clean_percent_or_float)
    else:
        df_orders["Taxa Indexador"] = 0.0
            
    # Autocorreção in-app de segurança contra distorções de milhar/localidade em bonificações
    for idx, row in df_orders.iterrows():
        try:
            op = str(row.get("Compra/Venda", "")).strip().upper()
            if "BONIFICAÇÃO" in op or "BONIFICACAO" in op or "DESDOBRAMENTO" in op:
                papel = str(row.get("Papel", "")).strip().upper()
                data_dt = row.get("data envio")
                if pd.isna(data_dt) or data_dt == "":
                    continue
                
                data_str = ""
                if hasattr(data_dt, "strftime"):
                    data_str = data_dt.strftime("%d/%m/%Y")
                else:
                    val_str = str(data_dt).strip()
                    match = re.search(r"(\d{2}/\d{2}/\d{4})", val_str)
                    if match:
                        data_str = match.group(1)
                    else:
                        match_us = re.search(r"(\d{4})-(\d{2})-(\d{2})", val_str)
                        if match_us:
                            data_str = f"{match_us.group(3)}/{match_us.group(2)}/{match_us.group(1)}"
                            
                if not data_str:
                    continue
                    
                chave = (papel, data_str)
                
                correcoes_conhecidas = {}
                correcoes_env = os.getenv("CORRECOES_CONHECIDAS", "{}")
                try:
                    correcoes_dict = json.loads(correcoes_env)
                    correcoes_conhecidas = {tuple(k.split("|")): float(v) for k, v in correcoes_dict.items()}
                except Exception as e:
                    logger.error(f"Erro ao carregar CORRECOES_CONHECIDAS do .env: {e}")
                
                if chave in correcoes_conhecidas:
                    old_val = df_orders.at[idx, "Qtd Executada"]
                    df_orders.at[idx, "Qtd Executada"] = correcoes_conhecidas[chave]
                    logger.info(f"Autocorreção de bonificação aplicada na memória: {papel} em {data_str} corrigido de {old_val} para {correcoes_conhecidas[chave]}")
        except Exception as e:
            logger.error(f"Erro ao processar autocorreção de bonificação na linha {idx}: {e}")
            
    return df_orders

CATEGORIAS_PROVENTOS = [
    "Dividendo BR",
    "Dividendo EUA",
    "Rendimento FII",
    "Aluguel Ações BR",
    "Aluguel Ações EUA",
    "Juros sobre Capital Próprio",
    "Rendimento Renda Fixa",
    "Frações"
]

def get_budget_data(use_mock=False, _is_retry=False):
    """
    Carrega os dados de Orçamento. Prioriza a leitura do banco de dados SQLite local,
    caindo de volta para o Google Sheets se o SQLite estiver vazio.
    Unifica todos os proventos na aba 'Receitas' e deriva df_dividendos dinamicamente.
    """
    load_dotenv(override=True)
    if use_mock:
        df_r, df_d, df_div, _ = get_mock_data()
        return df_r, df_d, df_div
        
    try:
        db_conn = db_manager.get_db_connection()
        c_receitas = pd.read_sql_query("SELECT count(*) as count FROM receitas", db_conn).iloc[0]["count"]
        c_despesas = pd.read_sql_query("SELECT count(*) as count FROM despesas", db_conn).iloc[0]["count"]
        
        if c_receitas > 0 or c_despesas > 0:
            logger.info("Carregando dados de Orçamento diretamente do SQLite local.")
            df_receitas = pd.read_sql_query("SELECT * FROM receitas", db_conn)
            df_despesas = pd.read_sql_query("SELECT * FROM despesas", db_conn)
            db_conn.close()
            
            map_rev = {
                "nome": "Nome", "valor": "Valor", "categoria": "Categoria",
                "recebido_em": "Recebido em", "dias_ate": "Dias até",
                "conta_creditada": "Conta creditada", "conta_debitada": "Conta debitada",
                "gasto_em": "Gasto em", "tipo_cobranca": "Tipo de Cobrança",
                "fixo_variavel": "Fixo vs. Variável", "essencial_nao_essencial": "Essencial vs. Não Essencial"
            }
            df_receitas = df_receitas.rename(columns=map_rev).drop(columns=["id"], errors="ignore")
            df_despesas = df_despesas.rename(columns=map_rev).drop(columns=["id"], errors="ignore")
            
            # Trata tipos de data
            if "Recebido em" in df_receitas.columns:
                df_receitas["Recebido em"] = pd.to_datetime(df_receitas["Recebido em"], errors="coerce")
            if "Gasto em" in df_despesas.columns:
                df_despesas["Gasto em"] = pd.to_datetime(df_despesas["Gasto em"], errors="coerce")
                
            # Deriva df_dividendos dinamicamente a partir das receitas categorizadas como proventos
            if not df_receitas.empty and "Categoria" in df_receitas.columns:
                df_dividendos = df_receitas[df_receitas["Categoria"].isin(CATEGORIAS_PROVENTOS)].copy()
                if "Ativo" not in df_dividendos.columns:
                    df_dividendos["Ativo"] = df_dividendos["Nome"]
            else:
                df_dividendos = pd.DataFrame(columns=["Nome", "Valor", "Ativo", "Categoria", "Recebido em", "Dias até"])
                
            return df_receitas, df_despesas, df_dividendos
        db_conn.close()
    except Exception as e:
        logger.error(f"Erro ao ler Orçamento do SQLite local: {e}. Caindo de volta para o Google Sheets.")
        
    if _is_retry:
        logger.warning("Banco SQLite permanece vazio após tentativa de sincronização com o Google Sheets.")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    # Fallback para o Sheets se o banco estiver vazio
    budget_spreadsheets = get_all_budget_spreadsheets()
    if not budget_spreadsheets:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        
    logger.info("Banco SQLite vazio. Disparando sincronização inicial automática do Orçamento...")
    sync_google_sheets_to_sqlite()
    return get_budget_data(use_mock=False, _is_retry=True)

def get_orders_data(use_mock=False, _is_retry=False):
    """
    Carrega dados de ordens de investimento. Prioriza o banco SQLite local, 
    caindo de volta para o Google Sheets se estiver vazio.
    """
    load_dotenv(override=True)
    if use_mock:
        _, _, _, df_o = get_mock_data()
        return df_o
        
    try:
        db_conn = db_manager.get_db_connection()
        c_ordens = pd.read_sql_query("SELECT count(*) as count FROM ordens", db_conn).iloc[0]["count"]
        
        if c_ordens > 0:
            logger.info("Carregando dados de Ordens diretamente do SQLite local.")
            df_orders = pd.read_sql_query("SELECT * FROM ordens", db_conn)
            db_conn.close()
            
            map_rev = {
                "data_envio": "data envio", "compra_venda": "Compra/Venda",
                "papel": "Papel", "qtd_executada": "Qtd Executada",
                "preco_medio": "Preço médio", "total_liquido": "Total líquido",
                "moeda": "Moeda", "tipo": "Tipo", "total": "Total",
                "corretagem": "Corretagem", "preco_medio_corretagem": "Preço médio + corretagem",
                "cod_cliente": "Cód. Cliente", "setor_economico": "Setor Econômico",
                "indexador": "Indexador", "taxa_indexador": "Taxa Indexador"
            }
            df_orders = df_orders.rename(columns=map_rev).drop(columns=["id"], errors="ignore")
            if "data envio" in df_orders.columns:
                df_orders["data envio"] = pd.to_datetime(df_orders["data envio"], errors="coerce")
            return df_orders
        db_conn.close()
    except Exception as e:
        logger.error(f"Erro ao ler Ordens do SQLite local: {e}. Caindo de volta para o Google Sheets.")
        
    if _is_retry:
        logger.warning("Banco SQLite de Ordens permanece vazio após tentativa de sincronização.")
        return pd.DataFrame()

    logger.info("Banco SQLite vazio. Disparando sincronização inicial automática das Ordens...")
    sync_google_sheets_to_sqlite()
    return get_orders_data(use_mock=False, _is_retry=True)

def sync_google_sheets_to_sqlite():
    """
    Sincroniza todas as planilhas do Google Sheets para o SQLite local de forma incremental/delta.
    Suporta múltiplos anos de planilhas de orçamento (2026, 2027, etc.) consolidando-os em tabelas unificadas.
    """
    logger.info("Iniciando sincronização incremental do Google Sheets para o SQLite local...")
    
    # 1. Sincroniza Ordens
    orders_id = os.getenv("SPREADSHEET_ORDERS_ID")
    if orders_id:
        try:
            logger.info("Buscando ordens novas do Google Sheets...")
            df_orders = load_sheet_data(orders_id, "Ordens")
            if df_orders.empty:
                client = get_gspread_client()
                spreadsheet = client.open_by_key(orders_id)
                first_worksheet = spreadsheet.get_worksheet(0)
                records = first_worksheet.get_all_records(numericise_ignore=['all'])
                if records:
                    df_orders = pd.DataFrame(records)
                    df_orders.columns = [col.strip() for col in df_orders.columns]
                else:
                    data = first_worksheet.get_all_values()
                    if len(data) > 1:
                        headers = [h.strip() for h in data[0]]
                        df_orders = pd.DataFrame(data[1:], columns=headers)
            
            if not df_orders.empty:
                df_orders = clean_and_normalize_orders(df_orders)
                db_manager.clear_table("ordens")
                db_manager.save_dataframe_delta("ordens", df_orders, None)
                logger.info(f"Ordens sincronizadas com sucesso: {len(df_orders)} registros.")
        except Exception as e:
            logger.error(f"Erro ao sincronizar aba Ordens: {e}")
            
    # 2. Sincroniza Orçamento (Receitas e Despesas) para todos os anos configurados
    budget_spreadsheets = get_all_budget_spreadsheets()
    if budget_spreadsheets:
        anos_configurados = list(budget_spreadsheets.keys())
        logger.info(f"Buscando lançamentos orçamentários dos anos configurados: {anos_configurados}...")
        
        all_receitas = []
        all_despesas = []
        
        for ano, b_id in budget_spreadsheets.items():
            if not b_id:
                continue
            try:
                logger.info(f"Sincronizando Orçamento do ano {ano} (Planilha: {b_id[:8]}...)...")
                
                # Receitas
                df_rec = load_sheet_data(b_id, "Receitas")
                if not df_rec.empty:
                    df_rec["Nome"] = df_rec["Nome"].astype(str).str.strip()
                    df_rec["Categoria"] = df_rec["Categoria"].astype(str).str.strip()
                    if "Conta creditada" in df_rec.columns:
                        df_rec["Conta creditada"] = df_rec["Conta creditada"].astype(str).str.strip()
                    df_rec["Valor"] = df_rec["Valor"].apply(clean_currency)
                    df_rec["Recebido em"] = pd.to_datetime(df_rec["Recebido em"], format="%d/%m/%Y", errors="coerce")
                    df_rec["Dias até"] = df_rec["Dias até"].apply(clean_int)
                    all_receitas.append(df_rec)
                    
                # Despesas
                df_desp = load_sheet_data(b_id, "Despesas")
                if not df_desp.empty:
                    df_desp["Nome"] = df_desp["Nome"].astype(str).str.strip()
                    df_desp["Categoria"] = df_desp["Categoria"].astype(str).str.strip()
                    if "Conta debitada" in df_desp.columns:
                        df_desp["Conta debitada"] = df_desp["Conta debitada"].astype(str).str.strip()
                    if "Tipo de Cobrança" in df_desp.columns:
                        df_desp["Tipo de Cobrança"] = df_desp["Tipo de Cobrança"].astype(str).str.strip()
                    
                    # Normaliza colunas Fixo/Variável e Essencial/Não Essencial
                    col_rename_despesas = {}
                    for col in df_desp.columns:
                        c_low = col.lower().strip()
                        if "fixo" in c_low and "vari" in c_low:
                            col_rename_despesas[col] = "Fixo vs. Variável"
                        elif "essencial" in c_low:
                            col_rename_despesas[col] = "Essencial vs. Não Essencial"
                    if col_rename_despesas:
                        df_desp = df_desp.rename(columns=col_rename_despesas)
                        
                    if "Fixo vs. Variável" in df_desp.columns:
                        df_desp["Fixo vs. Variável"] = df_desp["Fixo vs. Variável"].astype(str).str.strip()
                    if "Essencial vs. Não Essencial" in df_desp.columns:
                        df_desp["Essencial vs. Não Essencial"] = df_desp["Essencial vs. Não Essencial"].astype(str).str.strip()
                        
                    df_desp["Valor"] = df_desp["Valor"].apply(clean_currency)
                    df_desp["Gasto em"] = pd.to_datetime(df_desp["Gasto em"], format="%d/%m/%Y", errors="coerce")
                    df_desp["Dias até"] = df_desp["Dias até"].apply(clean_int)
                    all_despesas.append(df_desp)
            except Exception as e:
                logger.error(f"Erro ao sincronizar planilha de orçamento do ano {ano}: {e}")

        # Persiste consolidado no SQLite
        if all_receitas:
            df_receitas_total = pd.concat(all_receitas, ignore_index=True)
            db_manager.clear_table("receitas")
            db_manager.save_dataframe_delta("receitas", df_receitas_total, None)
            logger.info(f"Total de {len(df_receitas_total)} receitas consolidadas de {len(all_receitas)} ano(s) no SQLite.")
            
        if all_despesas:
            df_despesas_total = pd.concat(all_despesas, ignore_index=True)
            db_manager.clear_table("despesas")
            db_manager.save_dataframe_delta("despesas", df_despesas_total, None)
            logger.info(f"Total de {len(df_despesas_total)} despesas consolidadas de {len(all_despesas)} ano(s) no SQLite.")

    db_manager.set_last_sync_time()
    logger.info("Sincronização delta incremental concluída com sucesso.")

# Dicionário de Tradução Contábil Inglês -> Português (PT-BR)
TERMOS_CONTABEIS = {
    # Income Statement (DRE)
    "Total Revenue": "Receita Líquida",
    "Operating Revenue": "Receita Operacional",
    "Cost Of Revenue": "Custos dos Serviços/Produtos",
    "Gross Profit": "Lucro Bruto",
    "Operating Expense": "Despesas Operacionais",
    "Research And Development": "Pesquisa e Desenvolvimento (P&D)",
    "Selling General And Administrative": "Despesas de Vendas, Gerais e Admin (SG&A)",
    "Selling General And Administration": "Despesas de Vendas, Gerais e Administrativas (SG&A)",
    "Selling And Marketing Expense": "Despesas de Vendas e Marketing",
    "General And Administrative Expense": "Despesas Gerais e Administrativas",
    "Amortization": "Amortização",
    "Depreciation And Amortization": "Depreciação e Amortização (D&A)",
    "Operating Income": "Resultado Operacional (EBIT)",
    "Net Non Operating Interest Income Expense": "Resultado Financeiro Líquido",
    "Interest Income": "Receitas Financeiras",
    "Interest Expense": "Despesas Financeiras",
    "Normalized Income": "Lucro Líquido Normalizado",
    "Pretax Income": "Lucro Antes de Impostos (LAIR)",
    "Tax Provision": "Impostos e Provisões",
    "Net Income": "Lucro Líquido",
    "Net Income Common Stockholders": "Lucro Líquido aos Acionistas",
    "EBITDA": "EBITDA",
    "EBIT": "EBIT",
    "Diluted Average Shares": "Média de Ações Diluídas",
    "Diluted EPS": "LPA Diluído (Lucro por Ação)",
    "Normalized EBITDA": "EBITDA Normalizado",
    "Net Income Including Noncontrolling Interests": "Lucro Líquido Incluindo Não Controladores",
    "Net Income From Continuing Operation Net Minority Interest": "Lucro Líquido de Operações Continuadas (Controladores)",
    "Net Income From Continuing And Discontinued Operation": "Lucro Líquido de Operações Continuadas e Descontinuadas",
    "Net Income Continuous Operations": "Lucro Líquido de Operações Continuadas",
    "Basic EPS": "LPA Básico (Lucro por Ação)",
    "Diluted NI Availto Com Stockholders": "Lucro Líquido Diluído Disponível aos Acionistas",
    "Other Income Expense": "Outras Receitas/Despesas Operacionais",
    "Reconciled Cost Of Revenue": "Custo da Receita Reconciliado",
    "Other Non Operating Income Expenses": "Outras Receitas/Despesas Não Operacionais",
    "Reconciled Depreciation": "Depreciação Reconciliada",
    "Tax Effect Of Unusual Items": "Efeito Fiscal de Itens Extraordinários",
    "Tax Rate For Calcs": "Alíquota de Imposto Efetiva",
    "Total Expenses": "Despesas Totais",
    "Basic Average Shares": "Média de Ações Básicas",
    "Total Operating Income As Reported": "Resultado Operacional Reportado",
    
    # Balance Sheet (Balanço Patrimonial)
    "Total Assets": "Ativo Total",
    "Current Assets": "Ativo Circulante",
    "Cash And Cash Equivalents": "Caixa e Equivalentes de Caixa",
    "Cash Cash Equivalents And Short Term Investments": "Caixa, Equivalentes e Aplicações",
    "Cash Equivalents": "Equivalentes de Caixa",
    "Cash Financial": "Caixa Financeiro",
    "Other Short Term Investments": "Aplicações Financeiras CP",
    "Receivables": "Contas a Receber",
    "Accounts Receivable": "Clientes / Contas a Receber",
    "Other Receivables": "Outros Contas a Receber",
    "Inventory": "Estoques",
    "Raw Materials": "Matéria-Prima",
    "Finished Goods": "Produtos Acabados",
    "Prepaid Assets": "Despesas Antecipadas",
    "Other Current Assets": "Outros Ativos Circulantes",
    "Non Current Assets": "Ativo Não Circulante",
    "Net PPE": "Imobilizado Líquido",
    "Gross PPE": "Ativo Imobilizado Bruto",
    "Accumulated Depreciation": "Depreciação Acumulada",
    "Properties": "Propriedades e Equipamentos",
    "Land And Improvements": "Terrenos e Benfeitorias",
    "Machinery Furniture Equipment": "Máquinas, Móveis e Equipamentos",
    "Leases": "Arrendamentos / Leasing",
    "Goodwill And Other Intangible Assets": "Ágio e Intangíveis",
    "Goodwill": "Ágio / Goodwill",
    "Intangible Assets": "Ativos Intangíveis",
    "Investments And Advances": "Investimentos e Adiantamentos",
    "Investmentsin Associatesand Jointventures": "Investimentos em Coligadas/Joint Ventures",
    "Investmentin Financial Assets": "Investimentos em Ativos Financeiros",
    "Non Current Deferred Assets": "Ativo Diferido (LP)",
    "Non Current Deferred Taxes Assets": "Ativos Fiscais Diferidos (LP)",
    "Other Non Current Assets": "Outros Ativos Não Circulantes",
    "Total Non Current Assets": "Ativo Não Circulante Total",
    
    "Total Liabilities Net Minority Interest": "Passivo Total + PL",
    "Total Liabilities": "Passivo Total",
    "Current Liabilities": "Passivo Circulante",
    "Payables": "Contas a Pagar",
    "Accounts Payable": "Fornecedores / Contas a Pagar",
    "Payables And Accrued Expenses": "Contas a Pagar e Despesas Apropriadas",
    "Tradeand Other Payables Non Current": "Outras Contas a Pagar LP",
    "Short Term Debt": "Empréstimos e Financiamentos CP",
    "Current Debt And Capital Lease Obligation": "Dívida de Curto Prazo",
    "Current Debt": "Dívida de Curto Prazo (CP)",
    "Commercial Paper": "Notas Comerciais",
    "Other Current Borrowings": "Outras Obrigações Financeiras CP",
    "Current Accrued Expenses": "Despesas Apropriadas a Pagar (CP)",
    "Current Deferred Liabilities": "Passivo Diferido (CP)",
    "Current Deferred Revenue": "Receita Diferida / Adiantamentos de Clientes",
    "Income Tax Payable": "Imposto de Renda a Pagar",
    "Total Tax Payable": "Total de Impostos a Pagar",
    "Other Current Liabilities": "Outros Passivos Circulantes",
    "Non Current Liabilities": "Passivo Não Circulante",
    "Long Term Debt": "Empréstimos e Financiamentos LP",
    "Long Term Debt And Capital Lease Obligation": "Dívida de Longo Prazo",
    "Other Non Current Liabilities": "Outros Passivos Não Circulantes",
    "Total Non Current Liabilities Net Minority Interest": "Passivo Não Circulante Total",
    
    "Stockholders Equity": "Patrimônio Líquido (PL)",
    "Common Stock Equity": "Patrimônio Líquido Ordinário",
    "Capital Stock": "Capital Social",
    "Common Stock": "Ações Ordinárias (Capital)",
    "Retained Earnings": "Lucros Acumulados",
    "Treasury Stock": "Ações em Tesouraria",
    "Other Equity Adjustments": "Outros Ajustes do Patrimônio Líquido",
    "Other Equity Interest": "Outros Itens do PL",
    "Gains Losses Not Affecting Retained Earnings": "Ajustes de Avaliação Patrimonial",
    "Total Equity Gross Minority Interest": "Patrimônio Líquido Total + Participação de Não Controladores",
    "Net Debt": "Dívida Líquida",
    "Total Debt": "Dívida Bruta",
    "Ordinary Shares Number": "Quantidade de Ações Ordinárias",
    "Share Issued": "Ações Emitidas",
    "Tangible Book Value": "Valor Patrimonial Tangível",
    "Net Tangible Assets": "Ativos Tangíveis Líquidos",
    "Invested Capital": "Capital Investido",
    "Total Capitalization": "Capitalização Total",
    "Working Capital": "Capital de Giro",
    "Available For Sale Securities": "Títulos Disponíveis para Venda",
    
    # Cash Flow (Fluxo de Caixa)
    "Operating Cash Flow": "Fluxo de Caixa Operacional (FCO)",
    "Investing Cash Flow": "Fluxo de Caixa de Investimentos (FCI)",
    "Capital Expenditure": "Investimento em Ativos (CapEx)",
    "Financing Cash Flow": "Fluxo de Caixa de Financiamentos (FCF)",
    "Net Income From Continuing Operations": "Lucro Líquido Operações Continuadas",
    "Free Cash Flow": "Fluxo de Caixa Livre (FCL)",
    "End Cash Position": "Saldo de Caixa Final",
    "Beginning Cash Position": "Saldo de Caixa Inicial",
    "Changes In Cash": "Variação Líquida de Caixa",
    "Repurchase Of Capital Stock": "Recompra de Ações",
    "Common Stock Dividend Paid": "Dividendos Pagos",
    "Change In Inventory": "Variação de Estoques",
    "Change In Other Current Assets": "Variação de Outros Ativos Circulantes",
    "Cash Flow From Continuing Investing Activities": "FCO - Atividades de Investimento",
    "Cash Flow From Continuing Operating Activities": "FCO - Atividades Operacionais",
    "Change In Payable": "Variação de Fornecedores / Contas a Pagar",
    "Cash Dividends Paid": "Dividendos em Dinheiro Pagos",
    "Changes In Account Receivables": "Variação de Contas a Receber",
    "Change In Working Capital": "Variação de Capital de Giro",
    "Change In Receivables": "Variação de Contas a Receber",
    "Change In Payables And Accrued Expense": "Variação de Contas a Pagar e Despesas Apropriadas",
    "Change In Other Current Liabilities": "Variação de Outros Passivos Circulantes",
    "Common Stock Payments": "Pagamento de Ações Ordinárias / Redução de Capital",
    "Depreciation Amortization Depletion": "Depreciação, Amortização e Exaustão",
    "Income Tax Paid Supplemental Data": "Imposto de Renda Pago (Dado Suplementar)",
    "Issuance Of Debt": "Emissão de Dívida / Captação de Recursos",
    "Long Term Debt Issuance": "Emissão de Dívida de Longo Prazo",
    "Long Term Debt Payments": "Pagamento de Dívida de Longo Prazo",
    "Net Common Stock Issuance": "Emissão Líquida de Ações",
    "Change In Account Payable": "Variação de Fornecedores / Contas a Pagar",
    "Cash Flow From Continuing Financing Activities": "FCO - Atividades de Financiamento",
    "Net Issuance Payments Of Debt": "Captação/Amortização Líquida de Dívida",
    "Net Investment Purchase And Sale": "Compra e Venda Líquida de Investimentos",
    "Net Other Investing Changes": "Outras Variações Líquidas de Investimento",
    "Net Long Term Debt Issuance": "Emissão/Amortização Líquida de Dívida LP",
    "Net PPE Purchase And Sale": "Compra e Venda Líquida de Imobilizado (CapEx Líquido)",
    "Net Short Term Debt Issuance": "Emissão/Amortização Líquida de Dívida CP",
    "Other Non Cash Items": "Outros Ajustes Sem Efeito de Caixa",
    "Net Other Financing Charges": "Outros Fluxos Líquidos de Financiamento",
    "Purchase Of Investment": "Compra de Investimentos",
    "Purchase Of PPE": "Aquisição de Imobilizado (CapEx)",
    "Repayment Of Debt": "Amortização de Dívidas",
    "Sale Of Investment": "Venda de Investimentos",
    "Short Term Debt Payments": "Pagamento de Dívida de Curto Prazo",
    "Stock Based Compensation": "Remuneração Baseada em Ações",
}

def sync_fundamental_data_from_yfinance(ticker_orig=None):
    """
    Busca os demonstrativos financeiros do yfinance e salva no SQLite local.
    Se ticker_orig for None, sincroniza todos os tickers elegíveis presentes na carteira.
    """
    import yfinance as yf
    from .analytics import normalize_ticker, is_valid_yfinance_ticker
    
    if ticker_orig is None:
        # Busca todas as ordens para descobrir todos os tickers únicos
        try:
            df_ord = db_manager.get_table_data("ordens")
            if df_ord.empty:
                logger.warning("Nenhuma ordem encontrada no SQLite para sincronização global.")
                return False
            tickers_carteira = df_ord["Papel"].dropna().unique().tolist()
            sucessos = 0
            for t in tickers_carteira:
                if is_valid_yfinance_ticker(t):
                    if sync_fundamental_data_from_yfinance(t):
                        sucessos += 1
            return sucessos > 0
        except Exception as e:
            logger.error(f"Erro ao sincronizar dados fundamentalistas globais: {e}")
            return False
            
    ticker_norm = normalize_ticker(ticker_orig)
    if not is_valid_yfinance_ticker(ticker_orig):
        logger.warning(f"Ticker {ticker_orig} não é elegível para dados fundamentalistas.")
        return False
        
    logger.info(f"Iniciando sincronização de dados fundamentalistas para {ticker_norm}...")
    try:
        ticker_obj = yf.Ticker(ticker_norm)
        
        # Demonstrativos Anuais
        try:
            db_manager.save_fundamental_data(ticker_orig, "balanco", "anual", ticker_obj.balance_sheet)
        except Exception as e:
            logger.error(f"Erro ao salvar balanco anual para {ticker_orig}: {e}")
            
        try:
            db_manager.save_fundamental_data(ticker_orig, "dre", "anual", ticker_obj.income_stmt)
        except Exception as e:
            logger.error(f"Erro ao salvar dre anual para {ticker_orig}: {e}")
            
        try:
            db_manager.save_fundamental_data(ticker_orig, "fluxo", "anual", ticker_obj.cashflow)
        except Exception as e:
            logger.error(f"Erro ao salvar fluxo anual para {ticker_orig}: {e}")
            
        # Demonstrativos Trimestrais
        try:
            db_manager.save_fundamental_data(ticker_orig, "balanco", "trimestral", ticker_obj.quarterly_balance_sheet)
        except Exception as e:
            logger.error(f"Erro ao salvar balanco trimestral para {ticker_orig}: {e}")
            
        try:
            db_manager.save_fundamental_data(ticker_orig, "dre", "trimestral", ticker_obj.quarterly_income_stmt)
        except Exception as e:
            logger.error(f"Erro ao salvar dre trimestral para {ticker_orig}: {e}")
            
        try:
            db_manager.save_fundamental_data(ticker_orig, "fluxo", "trimestral", ticker_obj.quarterly_cashflow)
        except Exception as e:
            logger.error(f"Erro ao salvar fluxo trimestral para {ticker_orig}: {e}")
            
        return True
    except Exception as e:
        logger.error(f"Erro ao baixar dados fundamentalistas do yfinance para {ticker_orig}: {e}")
        return False
