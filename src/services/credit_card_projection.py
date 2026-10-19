# -*- coding: utf-8 -*-
"""
Serviço de Inteligência e Projeção de Parcelas de Cartão de Crédito.
Extrai compras parceladas (X/Y), consolida status da última parcela faturada
e projeta as parcelas futuras mês a mês, identificando datas de término e totais comprometidos.
"""
import re
import datetime
import pandas as pd
from typing import Dict, Any, List, Tuple, Optional
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

    # Validação contábil de parcela: atual <= total e total >= 1
    if cur_p < 1 or cur_p > tot_p or tot_p < 1:
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

    # Extrai parcelas e obrigações futuras
    records = []
    agora = pd.Timestamp.now().normalize()
    mes_atual_inicio = pd.Timestamp(agora.year, agora.month, 1)

    for _, row in df_cc.iterrows():
        desc = str(row.get("nome", ""))
        cur_p, tot_p, nome_base = extract_installment_info(desc)
        try:
            dt_val = pd.to_datetime(row.get("gasto_em"))
        except Exception:
            dt_val = pd.Timestamp.now()

        # Condição de inclusão:
        # 1. Parcelamento tradicional (tot_p > 1)
        # 2. Compromisso futuro extraordinário / Balão (tot_p == 1 com vencimento futuro >= mês atual)
        is_future_single = (tot_p == 1 and dt_val >= mes_atual_inicio)
        
        if tot_p > 1 or is_future_single:
            records.append({
                "dt": dt_val,
                "nome_original": desc,
                "nome_base": nome_base or desc,
                "cur_p": cur_p,
                "tot_p": tot_p,
                "valor_parcela": float(row.get("valor", 0.0)),
                "categoria": str(row.get("categoria", "Outros")),
                "conta_debitada": str(row.get("conta_debitada", "Cartão de crédito")),
                "is_future_single": is_future_single
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

        is_future_single = last_row.get("is_future_single", False)
        
        # Se a compra tinha parcelas restantes ou é um balão futuro ainda não vencido
        if is_future_single:
            status_real = "Ativa" if dt_ultima >= mes_atual_inicio else "Quitada"
            val_restante = val_parc if status_real == "Ativa" else 0.0
            faltam = 1 if status_real == "Ativa" else 0
            dt_termino = dt_ultima
            mes_termino_str = dt_termino.strftime("%m/%Y")
        else:
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
            "status": status_real,
            "is_future_single": is_future_single
        })

    df_consolidado = pd.DataFrame(latest_purchases)
    df_ativas = df_consolidado[df_consolidado["status"] == "Ativa"].copy()
    df_quitadas = df_consolidado[df_consolidado["status"] == "Quitada"].copy()

    # Gera projeção analítica mês a mês apenas para o mês corrente em diante
    futuras_list = []
    for _, row in df_ativas.iterrows():
        dt_base = row["data_ultima_fatura"]
        val_p = row["valor_parcela"]
        
        if row.get("is_future_single", False):
            # Compromisso futuro único (ex: Balão)
            fut_dt = dt_base
            if fut_dt >= mes_atual_inicio:
                futuras_list.append({
                    "ano_mes": fut_dt.strftime("%Y-%m"),
                    "mes_ano": fut_dt.strftime("%m/%Y"),
                    "data_estimada": fut_dt,
                    "nome_base": row["nome_base"],
                    "parcela": f"1/1 (Balão)",
                    "numero_parcela": 1,
                    "total_parcelas": 1,
                    "valor": val_p,
                    "categoria": row["categoria"],
                    "e_ultima_parcela": True
                })
        else:
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

def calculate_credit_card_health_indicators(
    df_despesas: pd.DataFrame,
    projections: Dict[str, Any],
    df_receitas: Optional[pd.DataFrame] = None
) -> Dict[str, Any]:
    """
    Calcula indicadores contábeis de alavancagem pessoal e solvência baseados no cartão de crédito:
    1. Comprometimento de Renda Mensal (Fatura projetada vs. Renda mensal média)
    2. Índice de Alavancagem em Parcelas (Saldo devedor total vs. Gasto mensal médio)
    3. Análise Vertical de Despesas em Cartão (Essencial vs. Não Essencial / Supérfluo)
    4. Concentração Top 3 Categorias de Gastos
    """
    resumo = projections.get("resumo", {})
    df_proj_mensal = projections.get("projecao_mensal", pd.DataFrame())
    df_ativas = projections.get("compras_ativas", pd.DataFrame())

    saldo_devedor_total = float(resumo.get("total_comprometido", 0.0))
    fatura_prox_mes = 0.0
    if not df_proj_mensal.empty and "total_mes" in df_proj_mensal.columns:
        fatura_prox_mes = float(df_proj_mensal.iloc[0]["total_mes"])

    # Estimativa de renda mensal
    renda_mensal = 0.0
    if df_receitas is not None and not df_receitas.empty and "Valor" in df_receitas.columns:
        # Se houver data de recebimento, calcula média mensal; caso contrário, usa a soma dos últimos lançamentos
        if "Recebido em" in df_receitas.columns:
            df_rec_valid = df_receitas.dropna(subset=["Recebido em", "Valor"]).copy()
            df_rec_valid["dt"] = pd.to_datetime(df_rec_valid["Recebido em"], format="%d/%m/%Y", errors="coerce")
            df_rec_valid = df_rec_valid.dropna(subset=["dt"])
            if not df_rec_valid.empty:
                df_rec_valid["mes_ano"] = df_rec_valid["dt"].dt.to_period("M")
                media_mes = df_rec_valid.groupby("mes_ano")["Valor"].sum().mean()
                renda_mensal = float(media_mes) if media_mes > 0 else 0.0
        if renda_mensal == 0.0:
            renda_mensal = float(df_receitas["Valor"].sum() / max(1, len(df_receitas.get("Recebido em", [1]))))

    # Estimativa de gastos mensais totais para cálculo de alavancagem (meses de renda/gastos comprometidos)
    gasto_mensal_medio = 0.0
    if df_despesas is not None and not df_despesas.empty and "Valor" in df_despesas.columns:
        if "Gasto em" in df_despesas.columns:
            df_desp_valid = df_despesas.dropna(subset=["Gasto em", "Valor"]).copy()
            df_desp_valid["dt"] = pd.to_datetime(df_desp_valid["Gasto em"], format="%d/%m/%Y", errors="coerce")
            df_desp_valid = df_desp_valid.dropna(subset=["dt"])
            if not df_desp_valid.empty:
                df_desp_valid["mes_ano"] = df_desp_valid["dt"].dt.to_period("M")
                media_gasto = df_desp_valid.groupby("mes_ano")["Valor"].sum().mean()
                gasto_mensal_medio = float(media_gasto) if media_gasto > 0 else 0.0

    # Taxa de comprometimento da renda com o cartão
    taxa_comprometimento = None
    if renda_mensal > 0 and fatura_prox_mes > 0:
        taxa_comprometimento = fatura_prox_mes / renda_mensal

    # Meses de gastos comprometidos no futuro
    meses_alavancagem = None
    ref_mensal = renda_mensal if renda_mensal > 0 else gasto_mensal_medio
    if ref_mensal > 0 and saldo_devedor_total > 0:
        meses_alavancagem = saldo_devedor_total / ref_mensal

    # Análise Vertical de Essencialidade nas Compras Parceladas Ativas
    pct_essencial = 0.0
    pct_nao_essencial = 0.0
    if not df_ativas.empty and "Essencial vs. Não Essencial" in df_ativas.columns:
        total_ativas_val = df_ativas["valor_restante"].sum()
        if total_ativas_val > 0:
            essencial_val = df_ativas[df_ativas["Essencial vs. Não Essencial"].str.lower().str.contains("essencial") & ~df_ativas["Essencial vs. Não Essencial"].str.lower().str.contains("não")]["valor_restante"].sum()
            pct_essencial = float(essencial_val / total_ativas_val)
    # Detecta se há compromisso de balão relevante entre as compras ativas
    balao_compromisso = None
    if not df_ativas.empty:
        df_bal = df_ativas[
            df_ativas["nome_base"].astype(str).str.contains(r'balão|apartamento.*balão|balao', case=False, na=False) |
            (df_ativas.get("is_future_single", False) & (df_ativas["valor_restante"] > 10000.0))
        ]
        if not df_bal.empty:
            row_b = df_bal.sort_values("valor_restante", ascending=False).iloc[0]
            balao_compromisso = {
                "nome": row_b["nome_base"],
                "valor": float(row_b["valor_restante"]),
                "mes_ano": row_b.get("mes_termino", "")
            }

    return {
        "fatura_proximo_mes": fatura_prox_mes,
        "saldo_devedor_total": saldo_devedor_total,
        "renda_mensal_estimada": renda_mensal,
        "gasto_mensal_medio": gasto_mensal_medio,
        "taxa_comprometimento_renda": taxa_comprometimento,
        "meses_alavancagem_futura": meses_alavancagem,
        "pct_essencial": pct_essencial,
        "pct_nao_essencial": pct_nao_essencial,
        "balao_compromisso": balao_compromisso,
    }


def generate_credit_card_diagnosis(indicators: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Gera diagnósticos e recomendações práticas para tomada de decisão no uso do cartão de crédito.
    """
    diagnosticos = []

    # 1. Comprometimento de Renda
    taxa = indicators.get("taxa_comprometimento_renda")
    fatura = indicators.get("fatura_proximo_mes", 0.0)
    if taxa is not None:
        if taxa <= 0.20:
            diagnosticos.append({
                "titulo": "Comprometimento Saudável",
                "status": "bom",
                "icone": "🟢",
                "valor": f"{taxa * 100:.1f}%",
                "mensagem": "A fatura futura consome até 20% da sua renda mensal. Nível confortável para manter a capacidade de poupança e investimentos."
            })
        elif taxa <= 0.35:
            diagnosticos.append({
                "titulo": "Comprometimento Moderado",
                "status": "alerta",
                "icone": "🟡",
                "valor": f"{taxa * 100:.1f}%",
                "mensagem": "A fatura consome entre 20% e 35% da renda estimada. Evite novas parcelas longas para não estrangular o orçamento."
            })
        else:
            diagnosticos.append({
                "titulo": "Comprometimento Elevado",
                "status": "critico",
                "icone": "🔴",
                "valor": f"{taxa * 100:.1f}%",
                "mensagem": "Mais de 35% da sua renda mensal já está comprometida com a próxima fatura. Recomendado pausar novas compras a prazo."
            })
    elif fatura > 0:
        diagnosticos.append({
            "titulo": "Próxima Fatura Prevista",
            "status": "neutro",
            "icone": "💳",
            "valor": f"R$ {fatura:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            "mensagem": "Valor estimado com base nas parcelas vincendas catalogadas."
        })

    # 2. Grau de Alavancagem em Parcelamentos Futuros
    meses_alav = indicators.get("meses_alavancagem_futura")
    saldo_total = indicators.get("saldo_devedor_total", 0.0)
    if meses_alav is not None:
        if meses_alav <= 1.0:
            diagnosticos.append({
                "titulo": "Alavancagem Curta / Baixa",
                "status": "bom",
                "icone": "🟢",
                "valor": f"{meses_alav:.1f} meses",
                "mensagem": "O saldo devedor de todas as parcelas futuras equivale a menos de 1 mês do seu orçamento. Dívida residual facilmente liquidável."
            })
        elif meses_alav <= 2.5:
            diagnosticos.append({
                "titulo": "Alavancagem Sob Controle",
                "status": "alerta",
                "icone": "🟡",
                "valor": f"{meses_alav:.1f} meses",
                "mensagem": "O saldo devedor futuro equivale a até 2,5 meses do seu fluxo. Priorize a quitação gradual antes de novas contratações."
            })
        else:
            diagnosticos.append({
                "titulo": "Alavancagem Futura Extensa",
                "status": "critico",
                "icone": "🔴",
                "valor": f"{meses_alav:.1f} meses",
                "mensagem": "Saldo devedor total supera 2,5 meses de gastos/renda. Há um acúmulo relevante de parcelamentos longos."
            })
    elif saldo_total > 0:
        diagnosticos.append({
            "titulo": "Dívida Futura Contratada",
            "status": "alerta",
            "icone": "ℹ️",
            "valor": f"R$ {saldo_total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            "mensagem": "Soma de todas as parcelas já contratadas a serem debitadas nos próximos meses."
        })

    # 3. Qualidade da Dívida (Essencial vs Supérfluo)
    pct_nao_essencial = indicators.get("pct_nao_essencial", 0.0)
    if pct_nao_essencial > 0:
        if pct_nao_essencial > 0.60:
            diagnosticos.append({
                "titulo": "Alto Peso em Não Essenciais",
                "status": "alerta",
                "icone": "🟡",
                "valor": f"{pct_nao_essencial * 100:.0f}%",
                "mensagem": "A maior parte das compras parceladas ativas corresponde a gastos não essenciais (lazer, compras discricionárias)."
            })
        else:
            diagnosticos.append({
                "titulo": "Parcelamento com Foco Estrutural",
                "status": "bom",
                "icone": "🟢",
                "valor": f"{(1 - pct_nao_essencial) * 100:.0f}% Essencial",
                "mensagem": "A maior fatia das parcelas ativas está alocada em necessidades essenciais ou investimentos materiais."
            })

    # 4. Alerta de Compromissos Extraordinários / Balão no Cartão
    balao_cartao = indicators.get("balao_compromisso")
    if balao_cartao:
        v_balao = balao_cartao["valor"]
        v_balao_str = f"R$ {v_balao:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        diagnosticos.append({
            "titulo": f"Compromisso Extraordinário (Balão)",
            "status": "critico",
            "icone": "🏢",
            "valor": v_balao_str,
            "mensagem": f"Identificado o compromisso '{balao_cartao['nome']}' com vencimento programado para {balao_cartao['mes_ano']}. Acompanhe a projeção na curva de decaimento."
        })

    return diagnosticos


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

