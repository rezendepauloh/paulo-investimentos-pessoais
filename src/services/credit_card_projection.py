# -*- coding: utf-8 -*-
"""
Serviço de Inteligência e Projeção de Parcelas de Cartão de Crédito.
Extrai compras parceladas (X/Y), consolida status da última parcela faturada
e projeta as parcelas futuras mês a mês, identificando datas de término e totais comprometidos.
"""
import re
import datetime
import pandas as pd
from typing import Dict, Any, List, Tuple
from src.utils.logger import get_logger

logger = get_logger("services", "credit_card_projection")

REGEX_PARCELA = re.compile(r'(\d+)\s*/\s*(\d+)')

def extract_installment_info(descricao: str) -> Tuple[int, int, str]:
    """
    Identifica se a descrição possui notação de parcelamento X/Y.
    Retorna (parcela_atual, total_parcelas, nome_base_limpo).
    Exemplo:
        'AREZZO 2/6 (Compra: 04/07)' -> (2, 6, 'AREZZO')
        'SHOPEE *BUBUWEBSTORE 11/12' -> (11, 12, 'SHOPEE *BUBUWEBSTORE')
        'CASA LUGANO (Compra: 23/07)' -> (0, 0, 'CASA LUGANO')
    """
    if not descricao:
        return 0, 0, ""

    desc_str = str(descricao).strip()
    
    # 1. Remove tags de compra e datas (ex: '(Compra: 07/08)') antes de buscar parcelamento
    # para evitar falsos positivos de dias/meses como 07/08
    desc_sem_compra = re.sub(r'\(Compra:[^)]+\)', ' ', desc_str)

    m = REGEX_PARCELA.search(desc_sem_compra)
    if not m:
        return 0, 0, desc_str

    cur_p = int(m.group(1))
    tot_p = int(m.group(2))

    # Validação contábil de parcela: atual <= total e total > 1
    if cur_p < 1 or cur_p > tot_p or tot_p <= 1:
        return 0, 0, desc_str

    # Remove parcela e marcadores para gerar o nome base unificado
    nome_base = REGEX_PARCELA.sub(' ', desc_sem_compra)
    nome_base = re.sub(r'-\s*Parcela\s*', ' ', nome_base, flags=re.IGNORECASE)
    nome_base = re.sub(r'\s+', ' ', nome_base).strip()

    return cur_p, tot_p, nome_base

def calculate_credit_card_projections(df_despesas: pd.DataFrame) -> Dict[str, Any]:
    """
    Processa todas as despesas de cartão de crédito e gera:
    1. 'compras_ativas': DataFrame das compras que ainda possuem parcelas a vencer no período corrente/futuro.
    2. 'compras_finalizadas': DataFrame das compras parceladas que já foram quitadas.
    3. 'projecao_mensal': Projeção mês a mês dos valores das parcelas vincendas.
    4. 'detalhes_futuros': Lista de todas as parcelas projetadas para exibição analítica.
    5. 'resumo': Métricas consolidadas (Total a vencer, média mensal, compras ativas, etc.).
    """
    if df_despesas is None or df_despesas.empty:
        return _empty_projection_result()

    df = df_despesas.copy()

    # Normalização de nomes de colunas
    col_map = {
        "Nome": "nome", "Gasto em": "gasto_em", "Valor": "valor",
        "Categoria": "categoria", "Conta debitada": "conta_debitada"
    }
    for old_col, new_col in col_map.items():
        if old_col in df.columns and new_col not in df.columns:
            df[new_col] = df[old_col]

    # Filtra transações vinculadas a Cartão de crédito (ou com formato de parcelas)
    if "conta_debitada" in df.columns:
        df_cc = df[
            df["conta_debitada"].astype(str).str.contains("Cartão", case=False, na=False) |
            df["nome"].astype(str).str.contains(r'\d+/\d+', regex=True, na=False)
        ].copy()
    else:
        df_cc = df[df["nome"].astype(str).str.contains(r'\d+/\d+', regex=True, na=False)].copy()

    if df_cc.empty:
        return _empty_projection_result()

    # Extrai parcelas
    records = []
    for _, row in df_cc.iterrows():
        desc = str(row.get("nome", ""))
        cur_p, tot_p, nome_base = extract_installment_info(desc)
        if tot_p > 1:
            try:
                dt_val = pd.to_datetime(row.get("gasto_em"))
            except Exception:
                dt_val = pd.Timestamp.now()

            records.append({
                "dt": dt_val,
                "nome_original": desc,
                "nome_base": nome_base or desc,
                "cur_p": cur_p,
                "tot_p": tot_p,
                "valor_parcela": float(row.get("valor", 0.0)),
                "categoria": str(row.get("categoria", "Outros")),
                "conta_debitada": str(row.get("conta_debitada", "Cartão de crédito"))
            })

    if not records:
        return _empty_projection_result()

    df_parc = pd.DataFrame(records)
    # Ordena cronologicamente para identificar com precisão a última parcela lançada de cada compra
    df_parc = df_parc.sort_values(by=["dt", "cur_p"], ascending=[True, True])

    # Marco temporal: início do mês corrente
    agora = pd.Timestamp.now().normalize()
    mes_atual_inicio = pd.Timestamp(agora.year, agora.month, 1)

    # Agrupa por 'nome_base' para encontrar a última parcela conhecida
    latest_purchases = []
    for nome_base, group in df_parc.groupby("nome_base"):
        # Último registro deste item
        last_row = group.iloc[-1]
        cur_p = int(last_row["cur_p"])
        tot_p = int(last_row["tot_p"])
        faltam = max(0, tot_p - cur_p)
        dt_ultima = last_row["dt"]
        val_parc = float(last_row["valor_parcela"])

        # Data estimada de término
        dt_termino = dt_ultima + pd.DateOffset(months=faltam)
        mes_termino_str = dt_termino.strftime("%m/%Y")

        # Se a compra tinha parcelas restantes mas seu término teórico já passou há muito tempo
        # (ex: compra de 2025 que terminou antes do ano atual), ela já está concluída no mundo real
        status_real = "Ativa" if (faltam > 0 and dt_termino >= mes_atual_inicio) else "Quitada"
        val_restante = (faltam * val_parc) if status_real == "Ativa" else 0.0

        latest_purchases.append({
            "nome_base": nome_base,
            "ultima_descricao": last_row["nome_original"],
            "categoria": last_row["categoria"],
            "conta": last_row["conta_debitada"],
            "parcela_atual": cur_p,
            "total_parcelas": tot_p,
            "parcelas_restantes": faltam if status_real == "Ativa" else 0,
            "valor_parcela": val_parc,
            "valor_restante": val_restante,
            "data_ultima_fatura": dt_ultima,
            "data_termino": dt_termino,
            "mes_termino": mes_termino_str,
            "status": status_real
        })

    df_consolidado = pd.DataFrame(latest_purchases)
    df_ativas = df_consolidado[df_consolidado["status"] == "Ativa"].copy()
    df_quitadas = df_consolidado[df_consolidado["status"] == "Quitada"].copy()

    # Gera projeção analítica mês a mês apenas para o mês corrente em diante
    futuras_list = []
    for _, row in df_ativas.iterrows():
        dt_base = row["data_ultima_fatura"]
        val_p = row["valor_parcela"]
        for p_offset in range(1, row["total_parcelas"] - row["parcela_atual"] + 1):
            p_num = row["parcela_atual"] + p_offset
            fut_dt = dt_base + pd.DateOffset(months=p_offset)
            
            # Inclui apenas meses a partir do mês corrente
            if fut_dt >= mes_atual_inicio:
                futuras_list.append({
                    "ano_mes": fut_dt.strftime("%Y-%m"),
                    "mes_ano": fut_dt.strftime("%m/%Y"),
                    "data_estimada": fut_dt,
                    "nome_base": row["nome_base"],
                    "parcela": f"{p_num}/{row['total_parcelas']}",
                    "numero_parcela": p_num,
                    "total_parcelas": row["total_parcelas"],
                    "valor": val_p,
                    "categoria": row["categoria"],
                    "e_ultima_parcela": (p_num == row["total_parcelas"])
                })

    df_futuras = pd.DataFrame(futuras_list) if futuras_list else pd.DataFrame(
        columns=["ano_mes", "mes_ano", "data_estimada", "nome_base", "parcela", "numero_parcela", "total_parcelas", "valor", "categoria", "e_ultima_parcela"]
    )

    # Projeção consolidada por mês futuro
    if not df_futuras.empty:
        proj_mensal = df_futuras.groupby(["ano_mes", "mes_ano"]).agg(
            total_mes=("valor", "sum"),
            qtd_parcelas=("valor", "count"),
            compras_encerrando=("e_ultima_parcela", lambda x: int(sum(x)))
        ).reset_index().sort_values("ano_mes")
    else:
        proj_mensal = pd.DataFrame(columns=["ano_mes", "mes_ano", "total_mes", "qtd_parcelas", "compras_encerrando"])

    # Métricas consolidadas
    total_comprometido = float(df_ativas["valor_restante"].sum()) if not df_ativas.empty else 0.0
    media_mensal = float(proj_mensal["total_mes"].mean()) if not proj_mensal.empty else 0.0
    qtd_ativas = len(df_ativas)

    # Identificação do próximo mês de encerramento relevante
    # Dá preferência ao próximo mês da projeção (ou mês corrente caso existam finalizando nele)
    mes_atual_str = mes_atual_inicio.strftime("%m/%Y")
    prox_mes_inicio = mes_atual_inicio + pd.DateOffset(months=1)
    prox_mes_str = prox_mes_inicio.strftime("%m/%Y")

    compras_mes_atual = len(df_ativas[df_ativas["mes_termino"] == mes_atual_str])
    compras_prox_mes = len(df_ativas[df_ativas["mes_termino"] == prox_mes_str])

    if compras_prox_mes > 0:
        mes_destaque = prox_mes_str
        encerrando_destaque = compras_prox_mes
    elif compras_mes_atual > 0:
        mes_destaque = mes_atual_str
        encerrando_destaque = compras_mes_atual
    elif not proj_mensal.empty:
        mes_destaque = proj_mensal.iloc[0]["mes_ano"]
        encerrando_destaque = int(proj_mensal.iloc[0]["compras_encerrando"])
    else:
        mes_destaque = prox_mes_str
        encerrando_destaque = 0

    resumo = {
        "total_comprometido": total_comprometido,
        "media_mensal": media_mensal,
        "qtd_compras_ativas": qtd_ativas,
        "mes_atual": mes_atual_str,
        "proximo_mes": prox_mes_str,
        "mes_destaque_encerramento": mes_destaque,
        "encerrando_destaque": encerrando_destaque,
        "primeiro_mes_projetado": mes_destaque,
        "encerrando_proximo_mes": encerrando_destaque,
        "maior_mes_valor": float(proj_mensal["total_mes"].max()) if not proj_mensal.empty else 0.0
    }

    return {
        "compras_ativas": df_ativas.sort_values(by=["parcelas_restantes", "valor_restante"], ascending=[True, False]),
        "compras_quitadas": df_quitadas.sort_values(by="data_ultima_fatura", ascending=False),
        "projecao_mensal": proj_mensal,
        "detalhes_futuros": df_futuras,
        "resumo": resumo
    }

def _empty_projection_result() -> Dict[str, Any]:
    return {
        "compras_ativas": pd.DataFrame(),
        "compras_quitadas": pd.DataFrame(),
        "projecao_mensal": pd.DataFrame(),
        "detalhes_futuros": pd.DataFrame(),
        "resumo": {
            "total_comprometido": 0.0,
            "media_mensal": 0.0,
            "qtd_compras_ativas": 0,
            "primeiro_mes_projetado": "",
            "encerrando_proximo_mes": 0,
            "maior_mes_valor": 0.0
        }
    }
