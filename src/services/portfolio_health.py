"""
Módulo de Diagnóstico Patrimonial & Saúde Financeira Pessoal.

Calcula:
1. Índice de Cobertura de Reserva de Emergência (meses de custo fixo / essencial cobertos por ativos de liquidez).
2. Taxa de Poupança e Capacidade de Aporte Médio.
3. Rentabilidade Real da Carteira (deduzida da inflação acumulada do IPCA).
4. Rebalanceamento e Alocação Orientada (desvios de metas patrimoniais).
"""

from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np


def calculate_portfolio_health_indicators(
    df_holdings: pd.DataFrame,
    df_despesas: pd.DataFrame,
    df_receitas: Optional[pd.DataFrame] = None,
    df_perf: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """
    Consolida métricas de saúde patrimonial:
    - Meses de Reserva de Emergência
    - Gasto Médio Essencial vs. Total
    - Rentabilidade Real vs. IPCA
    - Taxa Média de Poupança
    """
    total_patrimonio = float(df_holdings["valor_atual"].sum()) if not df_holdings.empty else 0.0

    # 1. Ativos de Alta Liquidez / Renda Fixa / Reserva
    # Filtra classes típicas de reserva: 'Renda Fixa', 'Tesouro Direto', 'Caixa' ou 'CDB'
    reserva_liquidez = 0.0
    if not df_holdings.empty and "tipo" in df_holdings.columns:
        tipos_reserva = ["RENDA FIXA", "TESOURO", "TESOURO DIRETO", "CAIXA", "CDB", "LCI", "LCA"]
        mask_reserva = df_holdings["tipo"].astype(str).str.upper().apply(
            lambda t: any(r in t for r in tipos_reserva)
        )
        reserva_liquidez = float(df_holdings[mask_reserva]["valor_atual"].sum())

    # Se não houver classe com esses nomes, considera a menor volatilidade ou 0
    # 2. Custo de Vida Mensal Médio (Total e Essencial)
    gasto_mensal_medio = 0.0
    gasto_essencial_mensal = 0.0

    if df_despesas is not None and not df_despesas.empty and "Valor" in df_despesas.columns:
        df_desp = df_despesas.dropna(subset=["Valor"]).copy()
        if "Gasto em" in df_desp.columns:
            df_desp["dt"] = pd.to_datetime(df_desp["Gasto em"], format="%d/%m/%Y", errors="coerce")
            df_desp = df_desp.dropna(subset=["dt"])
            if not df_desp.empty:
                df_desp["mes_ano"] = df_desp["dt"].dt.to_period("M")
                gasto_mensal_medio = float(df_desp.groupby("mes_ano")["Valor"].sum().mean())

                # Custo Essencial
                if "Essencial vs. Não Essencial" in df_desp.columns:
                    mask_ess = df_desp["Essencial vs. Não Essencial"].str.lower().str.contains("essencial") & \
                               ~df_desp["Essencial vs. Não Essencial"].str.lower().str.contains("não")
                    df_ess = df_desp[mask_ess]
                    if not df_ess.empty:
                        gasto_essencial_mensal = float(df_ess.groupby("mes_ano")["Valor"].sum().mean())

        if gasto_mensal_medio == 0.0:
            gasto_mensal_medio = float(df_despesas["Valor"].sum() / max(1, len(df_despesas.get("Gasto em", [1]))))
        if gasto_essencial_mensal == 0.0:
            gasto_essencial_mensal = gasto_mensal_medio * 0.7  # estimativa padrão de 70% essencial

    # Meses de Cobertura da Reserva
    meses_cobertura = None
    if gasto_essencial_mensal > 0 and reserva_liquidez > 0:
        meses_cobertura = reserva_liquidez / gasto_essencial_mensal
    elif gasto_mensal_medio > 0 and reserva_liquidez > 0:
        meses_cobertura = reserva_liquidez / gasto_mensal_medio

    # 3. Rentabilidade Real da Carteira (Acumulada)
    retorno_carteira_acum = 0.0
    ipca_acum = 0.0
    cdi_acum = 0.0
    retorno_real = None

    if df_perf is not None and not df_perf.empty:
        col_cart = "Retorno Carteira Acumulado (%)"
        col_ipca = "IPCA Acumulado (%)"
        col_cdi = "CDI Acumulado (%)"

        if col_cart in df_perf.columns:
            retorno_carteira_acum = float(df_perf[col_cart].iloc[-1])
        if col_ipca in df_perf.columns:
            ipca_acum = float(df_perf[col_ipca].iloc[-1])
        if col_cdi in df_perf.columns:
            cdi_acum = float(df_perf[col_cdi].iloc[-1])

        # Equação de Fisher: (1 + R_nominal) / (1 + IPCA) - 1
        retorno_real = ((1 + retorno_carteira_acum / 100.0) / (1 + ipca_acum / 100.0) - 1) * 100.0

    # 4. Detecção de Compromissos Extraordinários Futuros (ex: Balão do Apartamento)
    balao_info = None
    if df_despesas is not None and not df_despesas.empty:
        col_nome = "Nome" if "Nome" in df_despesas.columns else "nome"
        col_val = "Valor" if "Valor" in df_despesas.columns else "valor"
        col_gasto = "Gasto em" if "Gasto em" in df_despesas.columns else "gasto_em"

        df_balao = df_despesas[
            df_despesas[col_nome].astype(str).str.contains(r'balão|apartamento.*balão|balao', case=False, na=False) &
            (df_despesas[col_val] > 10000.0)
        ].copy()

        if not df_balao.empty:
            def parse_date_smart(val):
                s = str(val).strip()
                if "/" in s:
                    return pd.to_datetime(s, format="%d/%m/%Y", errors="coerce")
                return pd.to_datetime(s, errors="coerce")

            df_balao["dt"] = df_balao[col_gasto].apply(parse_date_smart)
            # Pega o maior ou mais próximo vencimento futuro
            df_balao_futuro = df_balao[df_balao["dt"] >= pd.Timestamp.now().normalize()]
            if not df_balao_futuro.empty:
                row_b = df_balao_futuro.sort_values("dt").iloc[0]
                valor_balao = float(row_b[col_val])
                dt_balao = row_b["dt"]
                nome_balao = str(row_b[col_nome])

                # Meses restantes
                hoje = pd.Timestamp.now()
                meses_restantes = max(1, (dt_balao.year - hoje.year) * 12 + (dt_balao.month - hoje.month))
                aporte_mensal_necessario = valor_balao / meses_restantes
                cobertura_patrimonio_pct = (total_patrimonio / valor_balao * 100.0) if valor_balao > 0 else 0.0
                cobertura_reserva_pct = (reserva_liquidez / valor_balao * 100.0) if valor_balao > 0 else 0.0

                balao_info = {
                    "nome": nome_balao,
                    "valor": valor_balao,
                    "data_vencimento": dt_balao,
                    "mes_ano_vencimento": dt_balao.strftime("%m/%Y"),
                    "meses_restantes": meses_restantes,
                    "aporte_mensal_necessario": aporte_mensal_necessario,
                    "cobertura_patrimonio_pct": cobertura_patrimonio_pct,
                    "cobertura_reserva_pct": cobertura_reserva_pct,
                }

    return {
        "total_patrimonio": total_patrimonio,
        "reserva_liquidez": reserva_liquidez,
        "gasto_mensal_medio": gasto_mensal_medio,
        "gasto_essencial_mensal": gasto_essencial_mensal,
        "meses_cobertura_reserva": meses_cobertura,
        "retorno_carteira_acum": retorno_carteira_acum,
        "ipca_acum": ipca_acum,
        "cdi_acum": cdi_acum,
        "retorno_real_acum": retorno_real,
        "balao_info": balao_info,
    }


def generate_portfolio_health_diagnosis(indicators: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Gera diagnósticos e recomendações de alocação para a Visão Geral do Patrimônio.
    """
    diagnosticos = []

    # 1. Cobertura da Reserva de Emergência
    meses_cob = indicators.get("meses_cobertura_reserva")
    reserva = indicators.get("reserva_liquidez", 0.0)
    if meses_cob is not None:
        if meses_cob >= 6.0:
            diagnosticos.append({
                "titulo": "Reserva de Emergência Sólida",
                "status": "bom",
                "icone": "🛡️",
                "valor": f"{meses_cob:.1f} meses",
                "mensagem": f"Você possui mais de 6 meses de custo essencial cobertos em renda fixa/liquidez (R$ {reserva:,.2f}). Permite investir em risco com tranquilidade.".replace(",", "X").replace(".", ",").replace("X", ".")
            })
        elif meses_cob >= 3.0:
            diagnosticos.append({
                "titulo": "Reserva em Construção",
                "status": "alerta",
                "icone": "🟡",
                "valor": f"{meses_cob:.1f} meses",
                "mensagem": "Cobertura entre 3 e 6 meses. Recomendável reforçar aportes em liquidez antes de aumentar exposição a renda variável."
            })
        else:
            diagnosticos.append({
                "titulo": "Reserva Vulnerável",
                "status": "critico",
                "icone": "🔴",
                "valor": f"{meses_cob:.1f} meses",
                "mensagem": "Menos de 3 meses de despesas cobertas em caixa. Alta sensibilidade a imprevistos que podem forçar resgates na baixa."
            })
    else:
        diagnosticos.append({
            "titulo": "Reserva de Emergência Não Identificada",
            "status": "alerta",
            "icone": "ℹ️",
            "valor": "0.0 meses",
            "mensagem": "Não foram encontrados ativos de renda fixa/liquidez imediata na carteira para constituir reserva."
        })

    # 2. Ganho Real Acima da Inflação
    ret_real = indicators.get("retorno_real_acum")
    ipca = indicators.get("ipca_acum", 0.0)
    if ret_real is not None:
        if ret_real > 2.0:
            diagnosticos.append({
                "titulo": "Poder de Compra Protegido",
                "status": "bom",
                "icone": "🚀",
                "valor": f"{ret_real:+.2f}% real",
                "mensagem": f"Sua carteira está crescendo em termos reais, batendo a inflação acumulada de {ipca:.1f}% pelo IPCA."
            })
        elif ret_real >= 0.0:
            diagnosticos.append({
                "titulo": "Poder de Compra Neutro",
                "status": "alerta",
                "icone": "🟡",
                "valor": f"{ret_real:+.2f}% real",
                "mensagem": "A valorização da carteira está empatando com a inflação acumulada. O patrimônio está sendo preservado, mas sem geração expressiva de riqueza real."
            })
        else:
            diagnosticos.append({
                "titulo": "Retorno Real Negativo",
                "status": "critico",
                "icone": "🔴",
                "valor": f"{ret_real:+.2f}% real",
                "mensagem": f"A rentabilidade acumulada está abaixo da inflação (IPCA {ipca:.1f}%). O patrimônio está perdendo poder de compra no período."
            })

    # 3. Superação do CDI (Custo de Oportunidade)
    ret_cart = indicators.get("retorno_carteira_acum")
    cdi = indicators.get("cdi_acum")
    if ret_cart is not None and cdi is not None and cdi > 0:
        pct_cdi = (ret_cart / cdi) * 100.0
        if pct_cdi >= 105.0:
            diagnosticos.append({
                "titulo": "Superando o CDI",
                "status": "bom",
                "icone": "📈",
                "valor": f"{pct_cdi:.0f}% do CDI",
                "mensagem": "A estratégia de alocação está gerando alfa positivo em relação à taxa básica livre de risco."
            })
        elif pct_cdi >= 90.0:
            diagnosticos.append({
                "titulo": "Alinhado ao CDI",
                "status": "alerta",
                "icone": "🟡",
                "valor": f"{pct_cdi:.0f}% do CDI",
                "mensagem": "Retorno próximo ao CDI. Verifique se o risco assumido em ativos voláteis está compensando o resultado obtido."
            })
        else:
            diagnosticos.append({
                "titulo": "Abaixo do CDI",
                "status": "critico",
                "icone": "🔴",
                "valor": f"{pct_cdi:.0f}% do CDI",
                "mensagem": "O retorno está inferior à renda fixa pós-fixada. Vale reavaliar a concentração em posições de baixo desempenho."
            })

    # 4. Alerta Estratégico de Passivo Futuro / Balão do Imóvel
    balao = indicators.get("balao_info")
    if balao:
        val_b = balao["valor"]
        meses_rest = balao["meses_restantes"]
        aporte_nec = balao["aporte_mensal_necessario"]
        cob_patr = balao["cobertura_patrimonio_pct"]
        cob_res = balao["cobertura_reserva_pct"]
        mes_ano_venc = balao["mes_ano_vencimento"]

        val_str = f"R$ {val_b:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        aporte_str = f"R$ {aporte_nec:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        if cob_patr >= 100.0:
            status_b = "alerta" if cob_res < 100.0 else "bom"
            icone_b = "🏢"
            msg_b = (
                f"Compromisso de {val_str} em {mes_ano_venc} ({meses_rest} meses restantes). "
                f"Seu patrimônio total cobre {cob_patr:.0f}% deste valor, mas apenas {cob_res:.0f}% está em liquidez/reserva. "
                f"Meta sugerida: poupar cerca de {aporte_str}/mês em renda fixa para quitação limpa sem liquidar ações/FIIs."
            )
        else:
            status_b = "critico"
            icone_b = "⚠️"
            msg_b = (
                f"Atenção alta: Balão de {val_str} em {mes_ano_venc} ({meses_rest} meses). "
                f"O valor supera o patrimônio líquido atual. Recomendado priorizar aporte de {aporte_str}/mês em caixa."
            )

        diagnosticos.append({
            "titulo": f"Compromisso: Balão Imobiliário ({mes_ano_venc})",
            "status": status_b,
            "icone": icone_b,
            "valor": val_str,
            "mensagem": msg_b
        })

    return diagnosticos


def calculate_portfolio_rebalancing(
    df_holdings: pd.DataFrame,
    target_weights: Optional[Dict[str, float]] = None
) -> pd.DataFrame:
    """
    Calcula desvios de alocação por classe de ativos e sugere o direcionamento de novos aportes.
    Target weights padrão:
    - Ações: 35%
    - FIIs: 30%
    - Renda Fixa: 25%
    - Cripto / Outros: 10%
    """
    if df_holdings.empty or "tipo" not in df_holdings.columns or "valor_atual" not in df_holdings.columns:
        return pd.DataFrame()

    total_val = float(df_holdings["valor_atual"].sum())
    if total_val <= 0:
        return pd.DataFrame()

    df_class = df_holdings.groupby("tipo")["valor_atual"].sum().reset_index()
    df_class["peso_atual"] = df_class["valor_atual"] / total_val

    # Metas padrão se não fornecidas
    default_targets = {
        "Ações": 0.35,
        "FIIs": 0.30,
        "Renda Fixa": 0.25,
        "Cripto": 0.05,
        "Internacional": 0.05
    }
    targets = target_weights or default_targets

    # Normaliza chaves
    res_rows = []
    for _, row in df_class.iterrows():
        classe = row["tipo"]
        val_atual = row["valor_atual"]
        peso_atual = row["peso_atual"]
        
        # Encontra target correspondente mais próximo
        meta_peso = 0.20 # fallback padrão
        for k, v in targets.items():
            if k.upper() in classe.upper() or classe.upper() in k.upper():
                meta_peso = v
                break

        desvio_pct = (peso_atual - meta_peso) * 100.0
        val_ideal = total_val * meta_peso
        diferenca_valor = val_ideal - val_atual

        if desvio_pct < -2.0:
            acao = "Aportar (Abaixo da Meta)"
            prioridade = "Alta"
        elif desvio_pct > 2.0:
            acao = "Aguardar (Acima da Meta)"
            prioridade = "Baixa"
        else:
            acao = "Equilibrado"
            prioridade = "Neutra"

        res_rows.append({
            "Classe": classe,
            "Valor Atual (R$)": val_atual,
            "Alocação Atual (%)": peso_atual * 100.0,
            "Alocação Meta (%)": meta_peso * 100.0,
            "Desvio (%)": desvio_pct,
            "Necessidade de Aporte (R$)": max(0.0, diferenca_valor),
            "Direcionamento": acao,
            "Prioridade": prioridade
        })

    return pd.DataFrame(res_rows).sort_values("Desvio (%)", ascending=True)
