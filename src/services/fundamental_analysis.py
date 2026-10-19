"""
Módulo de Análise das Demonstrações Contábeis (ADC) e Indicadores Fundamentalistas.

Calcula índices clássicos de:
1. Liquidez (Corrente, Seca, Imediata)
2. Estrutura de Capital & Solvência (Endividamento Geral, Composição do Endividamento, Dívida Líquida / EBITDA, Imobilização do PL)
3. Rentabilidade & Eficiência (Margem Bruta, Margem EBITDA, Margem Líquida, ROE, ROIC aproximado, Giro do Ativo)
4. Diagnóstico e Checklist Prescritivo com pareceres qualitativos.
"""

from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np


def _safe_get(df: pd.DataFrame, possible_keys: List[str], col: Any) -> Optional[float]:
    """Busca com segurança o primeiro valor numérico válido entre uma lista de possíveis chaves contábeis."""
    if df is None or df.empty or col not in df.columns:
        return None
        
    for key in possible_keys:
        if key in df.index:
            val = df.loc[key, col]
            if pd.notna(val):
                try:
                    return float(val)
                except (ValueError, TypeError):
                    continue
    return None


def calculate_fundamental_ratios(
    df_balanco: pd.DataFrame,
    df_dre: pd.DataFrame,
    df_fluxo: Optional[pd.DataFrame] = None
) -> pd.DataFrame:
    """
    Calcula indicadores fundamentalistas e contábeis ano a ano (ou trimestre a trimestre)
    a partir dos demonstrativos financeiros em formato de DataFrame (contas como linhas, datas como colunas).
    
    Retorna DataFrame onde o índice são os indicadores e as colunas são as datas.
    """
    if df_balanco is None or df_balanco.empty:
        return pd.DataFrame()

    cols = list(df_balanco.columns)
    ratios_dict: Dict[str, Dict[str, Optional[float]]] = {}

    for c in cols:
        # --- Ativo ---
        ativo_total = _safe_get(df_balanco, ["Total Assets", "Ativo Total"], c)
        ativo_circulante = _safe_get(df_balanco, ["Current Assets", "Ativo Circulante"], c)
        estoques = _safe_get(df_balanco, ["Inventory", "Estoques"], c) or 0.0
        caixa = _safe_get(
            df_balanco, 
            [
                "Cash Cash Equivalents And Short Term Investments", 
                "Cash And Cash Equivalents", 
                "Cash Financial",
                "Caixa e Equivalentes de Caixa",
                "Caixa, Equivalentes e Aplicações"
            ], 
            c
        ) or 0.0
        ativo_nao_circulante = _safe_get(df_balanco, ["Total Non Current Assets", "Ativo Não Circulante Total", "Ativo Não Circulante"], c)

        # --- Passivo e PL ---
        passivo_circulante = _safe_get(df_balanco, ["Current Liabilities", "Passivo Circulante"], c)
        passivo_nao_circulante = _safe_get(df_balanco, ["Total Non Current Liabilities Net Minority Interest", "Passivo Não Circulante"], c)
        pl = _safe_get(df_balanco, ["Stockholders Equity", "Common Stock Equity", "Patrimônio Líquido (PL)", "Patrimônio Líquido Ordinário"], c)
        divida_cp = _safe_get(df_balanco, ["Current Debt", "Current Debt And Capital Lease Obligation", "Dívida de Curto Prazo (CP)"], c) or 0.0
        divida_lp = _safe_get(df_balanco, ["Long Term Debt", "Long Term Debt And Capital Lease Obligation", "Empréstimos e Financiamentos LP"], c) or 0.0
        divida_total = _safe_get(df_balanco, ["Total Debt", "Dívida Bruta"], c)
        if divida_total is None and (divida_cp > 0 or divida_lp > 0):
            divida_total = divida_cp + divida_lp

        # --- DRE ---
        receita_liquida = _safe_get(df_dre, ["Total Revenue", "Operating Revenue", "Receita Líquida", "Receita Operacional"], c)
        lucro_bruto = _safe_get(df_dre, ["Gross Profit", "Lucro Bruto"], c)
        ebit = _safe_get(df_dre, ["EBIT", "Operating Income", "Resultado Operacional (EBIT)"], c)
        ebitda = _safe_get(df_dre, ["EBITDA", "Normalized EBITDA"], c)
        lucro_liquido = _safe_get(
            df_dre, 
            ["Net Income Common Stockholders", "Net Income", "Lucro Líquido", "Lucro Líquido aos Acionistas"], 
            c
        )

        # --- Fluxo de Caixa (Opcional) ---
        fco = _safe_get(df_fluxo, ["Cash Flow From Continuing Operating Activities", "Operating Cash Flow", "Fluxo de Caixa Operacional (FCO)"], c)
        fcl = _safe_get(df_fluxo, ["Free Cash Flow", "Fluxo de Caixa Livre (FCL)"], c)

        # ========================================================
        # 1. ÍNDICES DE LIQUIDEZ (Capacidade de Pagamento)
        # ========================================================
        liq_corrente = None
        liq_seca = None
        liq_imediata = None
        if passivo_circulante and passivo_circulante > 0:
            if ativo_circulante is not None:
                liq_corrente = ativo_circulante / passivo_circulante
                liq_seca = (ativo_circulante - estoques) / passivo_circulante
            if caixa is not None:
                liq_imediata = caixa / passivo_circulante

        # ========================================================
        # 2. ESTRUTURA DE CAPITAL & SOLVÊNCIA
        # ========================================================
        endividamento_geral = None  # (Passivo Total / Ativo Total)
        comp_endividamento = None   # Passivo Circulante / Passivo Total Exigível
        divida_liq_ebitda = None
        imobilizacao_pl = None

        passivo_exigivel = None
        if passivo_circulante is not None:
            passivo_exigivel = passivo_circulante + (passivo_nao_circulante or 0.0)

        if passivo_exigivel is not None and ativo_total and ativo_total > 0:
            endividamento_geral = passivo_exigivel / ativo_total

        if passivo_exigivel and passivo_exigivel > 0 and passivo_circulante is not None:
            comp_endividamento = passivo_circulante / passivo_exigivel

        if divida_total is not None and ebitda and ebitda > 0:
            divida_liquida = divida_total - caixa
            divida_liq_ebitda = divida_liquida / ebitda

        if pl and pl > 0 and ativo_nao_circulante is not None:
            imobilizacao_pl = ativo_nao_circulante / pl

        # ========================================================
        # 3. RENTABILIDADE E MARGENS
        # ========================================================
        margem_bruta = None
        margem_ebitda = None
        margem_liquida = None
        giro_ativo = None
        roe = None
        roic = None

        if receita_liquida and receita_liquida > 0:
            if lucro_bruto is not None:
                margem_bruta = lucro_bruto / receita_liquida
            if ebitda is not None:
                margem_ebitda = ebitda / receita_liquida
            if lucro_liquido is not None:
                margem_liquida = lucro_liquido / receita_liquida
            if ativo_total and ativo_total > 0:
                giro_ativo = receita_liquida / ativo_total

        if pl and pl > 0 and lucro_liquido is not None:
            roe = lucro_liquido / pl

        # ROIC Aproximado: NOPAT / (PL + Dívida Total - Caixa)
        # NOPAT aproximado como EBIT * (1 - 0.34) para empresas no Brasil
        if ebit is not None and pl and pl > 0:
            capital_investido = pl + (divida_total or 0.0) - caixa
            if capital_investido > 0:
                nopat = ebit * 0.66
                roic = nopat / capital_investido

        ratios_dict[str(c)] = {
            "Liquidez Corrente": liq_corrente,
            "Liquidez Seca": liq_seca,
            "Liquidez Imediata": liq_imediata,
            "Endividamento Geral (Passivo/Ativo)": endividamento_geral,
            "Composição do Endividamento (CP/Total)": comp_endividamento,
            "Dívida Líquida / EBITDA": divida_liq_ebitda,
            "Imobilização do PL": imobilizacao_pl,
            "Margem Bruta": margem_bruta,
            "Margem EBITDA": margem_ebitda,
            "Margem Líquida": margem_liquida,
            "Giro do Ativo": giro_ativo,
            "ROE (Retorno s/ Patrimônio Líquido)": roe,
            "ROIC Estimado": roic,
            "FCO (Geração de Caixa Operacional)": fco,
            "FCL (Fluxo de Caixa Livre)": fcl,
        }

    return pd.DataFrame(ratios_dict)


def generate_fundamental_diagnosis(
    df_ratios: pd.DataFrame,
    df_dre: Optional[pd.DataFrame] = None
) -> List[Dict[str, Any]]:
    """
    Gera diagnósticos e pareceres para tomada de decisão com base nos indicadores mais recentes e tendências.
    Retorna uma lista de itens de checklist com status: 'bom', 'alerta', 'critico' ou 'neutro'.
    """
    if df_ratios is None or df_ratios.empty:
        return []

    # A coluna mais recente é a primeira (ordenadas decrescentemente)
    col_atual = df_ratios.columns[0]
    ratios_atuais = df_ratios[col_atual].to_dict()

    items = []

    # 1. Liquidez Corrente
    lc = ratios_atuais.get("Liquidez Corrente")
    if lc is not None:
        if lc >= 1.5:
            items.append({
                "titulo": "Liquidez Corrente Saudável",
                "status": "bom",
                "icone": "🟢",
                "valor": f"{lc:.2f}x",
                "mensagem": "A empresa tem folga confortável para cobrir suas obrigações de curto prazo (mais de R$ 1,50 para cada R$ 1,00 de dívida CP)."
            })
        elif lc >= 1.0:
            items.append({
                "titulo": "Liquidez Corrente Equilibrada",
                "status": "alerta",
                "icone": "🟡",
                "valor": f"{lc:.2f}x",
                "mensagem": "Capacidade de honrar compromissos no curto prazo é suficiente, mas sem ampla margem para choques inesperados."
            })
        else:
            items.append({
                "titulo": "Liquidez Corrente Pressionada",
                "status": "critico",
                "icone": "🔴",
                "valor": f"{lc:.2f}x",
                "mensagem": "O Passivo Circulante supera o Ativo Circulante. Risco de aperto de liquidez e necessidade de rolagem de dívidas."
            })

    # 2. Dívida Líquida / EBITDA
    dl_ebitda = ratios_atuais.get("Dívida Líquida / EBITDA")
    if dl_ebitda is not None:
        if dl_ebitda <= 0:
            items.append({
                "titulo": "Caixa Líquido Positivo",
                "status": "bom",
                "icone": "🟢",
                "valor": f"{dl_ebitda:.2f}x",
                "mensagem": "A empresa possui mais caixa e equivalentes do que dívida total bruta (estrutura de capital extremamente conservadora)."
            })
        elif dl_ebitda <= 2.5:
            items.append({
                "titulo": "Endividamento Sob Controle",
                "status": "bom",
                "icone": "🟢",
                "valor": f"{dl_ebitda:.2f}x",
                "mensagem": "Alavancagem saudável (abaixo de 2,5x EBITDA), condizente com a maioria dos setores de capital intensivo."
            })
        elif dl_ebitda <= 3.5:
            items.append({
                "titulo": "Alavancagem Moderada / Atenção",
                "status": "alerta",
                "icone": "🟡",
                "valor": f"{dl_ebitda:.2f}x",
                "mensagem": "Dívida em patamar elevado. Acompanhar a sensibilidade a altas de juros e a geração de caixa operacional."
            })
        else:
            items.append({
                "titulo": "Alavancagem Excessiva",
                "status": "critico",
                "icone": "🔴",
                "valor": f"{dl_ebitda:.2f}x",
                "mensagem": "Dívida Líquida superior a 3,5x EBITDA. Requer atenção redobrada; risco de estresse financeiro."
            })

    # 3. Rentabilidade (ROE)
    roe = ratios_atuais.get("ROE (Retorno s/ Patrimônio Líquido)")
    if roe is not None:
        if roe >= 0.18:
            items.append({
                "titulo": "ROE Excelente (Alta Rentabilidade)",
                "status": "bom",
                "icone": "🟢",
                "valor": f"{roe * 100:.1f}%",
                "mensagem": "Retorno sobre o patrimônio líquido muito atrativo, batendo com folga o custo de oportunidade (CDI)."
            })
        elif roe >= 0.10:
            items.append({
                "titulo": "ROE Moderado",
                "status": "alerta",
                "icone": "🟡",
                "valor": f"{roe * 100:.1f}%",
                "mensagem": "Rentabilidade aceitável, próxima às taxas de juros de mercado. Avaliar se o negócio possui diferenciais competitivos (moat)."
            })
        elif roe > 0:
            items.append({
                "titulo": "ROE Baixo",
                "status": "alerta",
                "icone": "🟡",
                "valor": f"{roe * 100:.1f}%",
                "mensagem": "A empresa é lucrativa, porém o retorno do capital dos acionistas está abaixo das taxas básicas de renda fixa."
            })
        else:
            items.append({
                "titulo": "Prejuízo no Período (ROE Negativo)",
                "status": "critico",
                "icone": "🔴",
                "valor": f"{roe * 100:.1f}%",
                "mensagem": "Resultado líquido negativo destruindo valor patrimonial no exercício recente."
            })

    # 4. Margem Líquida
    ml = ratios_atuais.get("Margem Líquida")
    if ml is not None:
        if ml >= 0.15:
            items.append({
                "titulo": "Margem Líquida Robusta",
                "status": "bom",
                "icone": "🟢",
                "valor": f"{ml * 100:.1f}%",
                "mensagem": "Forte poder de precificação e eficiência de custos (lucro líquido superior a 15% da receita)."
            })
        elif ml >= 0.05:
            items.append({
                "titulo": "Margem Líquida Estável",
                "status": "bom",
                "icone": "🟢",
                "valor": f"{ml * 100:.1f}%",
                "mensagem": "Margem operacional e líquida dentro da normalidade para setores industriais e comerciais."
            })
        elif ml > 0:
            items.append({
                "titulo": "Margem Líquida Apertada",
                "status": "alerta",
                "icone": "🟡",
                "valor": f"{ml * 100:.1f}%",
                "mensagem": "Margem abaixo de 5%. Qualquer aumento em insumos ou despesas financeiras pode levar o negócio ao prejuízo."
            })

    # 5. Consistência Histórica de Lucros (DRE multianual)
    if df_dre is not None and not df_dre.empty:
        lucro_keys = ["Net Income Common Stockholders", "Net Income", "Lucro Líquido", "Lucro Líquido aos Acionistas"]
        anos_lucrativos = 0
        total_anos = 0
        for c in df_dre.columns:
            nl = _safe_get(df_dre, lucro_keys, c)
            if nl is not None:
                total_anos += 1
                if nl > 0:
                    anos_lucrativos += 1
        
        if total_anos >= 3:
            if anos_lucrativos == total_anos:
                items.append({
                    "titulo": "Histórico de Lucros Consistente",
                    "status": "bom",
                    "icone": "🟢",
                    "valor": f"{anos_lucrativos}/{total_anos} anos",
                    "mensagem": "A empresa apresentou lucro líquido positivo em todos os anos analisados na base histórica."
                })
            elif anos_lucrativos / total_anos >= 0.7:
                items.append({
                    "titulo": "Lucros Recorrentes com Variações",
                    "status": "alerta",
                    "icone": "🟡",
                    "valor": f"{anos_lucrativos}/{total_anos} anos",
                    "mensagem": "Houve pelo menos um exercício com resultado deficitário nos períodos recentes."
                })
            else:
                items.append({
                    "titulo": "Instabilidade de Resultados",
                    "status": "critico",
                    "icone": "🔴",
                    "valor": f"{anos_lucrativos}/{total_anos} anos",
                    "mensagem": "Frequência recorrente de prejuízos. Empresa cíclica ou em processo de reestruturação/turnaround."
                })

    return items
