import streamlit as st
import pandas as pd
from src.database import db_manager
from src.services import (
    TERMOS_CONTABEIS,
    sync_fundamental_data_from_yfinance,
    is_valid_yfinance_ticker,
    calculate_fundamental_ratios,
    generate_fundamental_diagnosis,
)

from src.utils.formatting import format_number
from src.utils.logger import get_logger

logger = get_logger("tabs", "fundamentalista")

def render_tab_fundamentalista(df_holdings, df_dividendos):
    """
    Renderiza a aba de Análise Fundamentalista Histórica (Balanço, DRE, Fluxo de Caixa e FIIs).
    """
    if df_holdings.empty:
        st.info("Nenhum ativo em carteira para realizar a análise fundamentalista.")
        return

    ativos_elegiveis = []
    for ticker in sorted(df_holdings["ticker"].unique()):
        tipo_ativo = df_holdings[df_holdings["ticker"] == ticker]["tipo"].iloc[0]
        if is_valid_yfinance_ticker(ticker, tipo_ativo):
            ativos_elegiveis.append(ticker)
            
    if not ativos_elegiveis:
        st.info("Nenhum ativo elegível para análise fundamentalista em carteira.")
        return

    # Lê o ativo e periodicidade selecionados na sidebar
    ativo_sel = st.session_state.get("fund_ativo_sel", ativos_elegiveis[0])
    if ativo_sel not in ativos_elegiveis:
        ativo_sel = ativos_elegiveis[0]
        
    periodo_sel = st.session_state.get("fund_periodo_sel", "Anual")
        
    tipo_ativo_sel = df_holdings[df_holdings["ticker"] == ativo_sel]["tipo"].iloc[0]
    moeda_ativo_sel = df_holdings[df_holdings["ticker"] == ativo_sel]["moeda"].iloc[0]
    is_fii = (tipo_ativo_sel == "FIIs" or "FII" in str(ativo_sel).upper())
    
    if is_fii:

        st.markdown(f"### 🏢 Análise de FII: **{ativo_sel}**")
        st.info("FIIs (Fundos Imobiliários) não possuem demonstrativos contábeis convencionais (DRE e Balanço) públicos estruturados no padrão corporativo convencional. A análise de FIIs é voltada para a distribuição de proventos e indicadores patrimoniais.")
        
        total_recebido = 0.0
        if not df_dividendos.empty and "Ativo" in df_dividendos.columns:
            prov_fii = df_dividendos[df_dividendos["Ativo"] == ativo_sel]
            total_recebido = prov_fii["Valor"].sum() if not prov_fii.empty else 0.0
            
        col_met1, col_met2 = st.columns(2)
        with col_met1:
            st.metric("Total de Proventos Recebidos por Você", format_number(total_recebido, is_currency=True, currency="BRL"))
        with col_met2:
            posicao_fii = df_holdings[df_holdings["ticker"] == ativo_sel]
            if not posicao_fii.empty:
                qtd_fii = posicao_fii["quantidade"].iloc[0]
                st.metric("Sua Quantidade Atual", format_number(qtd_fii, decimals=0))
            else:
                st.metric("Sua Quantidade Atual", "0")
        
        if not df_dividendos.empty and "Ativo" in df_dividendos.columns:
            prov_fii = df_dividendos[df_dividendos["Ativo"] == ativo_sel]
            if not prov_fii.empty:
                st.markdown("#### 🪙 Histórico de Proventos Recebidos na Planilha")
                prov_fii_display = prov_fii.sort_values("Recebido em", ascending=False).copy()
                prov_fii_display["Valor"] = prov_fii_display["Valor"].apply(lambda v: format_number(v, is_currency=True, currency="BRL"))
                st.dataframe(
                    prov_fii_display[["Recebido em", "Valor"]].rename(columns={"Recebido em": "Data de Recebimento", "Valor": "Valor Pago"}),
                    width='stretch'
                )
    else:
        DEMO_SLUGS = {
            "analise": "📊 Análise Contábil & Diagnóstico",
            "balanco": "Balanço Patrimonial",
            "dre": "DRE (Demonstrativo do Resultado)",
            "fluxo": "Fluxo de Caixa"
        }
        SLUG_TO_LABEL_DEMO = DEMO_SLUGS
        LABEL_TO_SLUG_DEMO = {v: k for k, v in DEMO_SLUGS.items()}
        
        url_subtab = st.query_params.get("subtab", "analise")
        if url_subtab not in SLUG_TO_LABEL_DEMO:
            url_subtab = "analise"
            
        current_demo_label = SLUG_TO_LABEL_DEMO[url_subtab]
        demo_labels = list(DEMO_SLUGS.values())
        default_demo_idx = demo_labels.index(current_demo_label)

        demo_sel = st.radio(
            "Visão para Análise:",
            demo_labels,
            index=default_demo_idx,
            horizontal=True,
            key="fundamental_demo_radio"
        )
        
        selected_demo_slug = LABEL_TO_SLUG_DEMO[demo_sel]
        if st.query_params.get("subtab") != selected_demo_slug:
            st.query_params["subtab"] = selected_demo_slug
            logger.info(f"Sub-navegação Fundamentalista: {selected_demo_slug}")
            st.rerun()
        
        demo_key = selected_demo_slug
        periodo_key = periodo_sel.lower()

        if demo_key == "analise":
            # Busca Balanço, DRE e Fluxo para consolidar os índices de ADC
            df_b = db_manager.get_fundamental_data(ativo_sel, "balanco", periodo_key)
            df_d = db_manager.get_fundamental_data(ativo_sel, "dre", periodo_key)
            df_f = db_manager.get_fundamental_data(ativo_sel, "fluxo", periodo_key)

            if df_b.empty and df_d.empty:
                st.warning("⚠️ Nenhum dado contábil local encontrado para gerar o diagnóstico. Atualize os dados do ativo no menu lateral.")
            else:
                df_ratios = calculate_fundamental_ratios(df_b, df_d, df_f)
                diagnosticos = generate_fundamental_diagnosis(df_ratios, df_d)

                st.markdown(f"### 🎯 Diagnóstico Contábil & Tomada de Decisão: **{ativo_sel}**")
                st.caption(f"Periodicidade dos dados: **{periodo_sel}** | Metodologia baseada em Análise das Demonstrações Contábeis (ADC)")

                # Exibe Scorecards de Diagnóstico Rápido
                if diagnosticos:
                    st.markdown("#### 🔍 Pareceres do Diagnóstico:")
                    # Renderiza em 2 ou 3 colunas para boa leitura
                    cols_diag = st.columns(min(3, len(diagnosticos)))
                    for idx, diag in enumerate(diagnosticos):
                        with cols_diag[idx % len(cols_diag)]:
                            st.markdown(
                                f"""
                                <div style="border-radius: 8px; border: 1px solid #e0e0e0; padding: 12px; margin-bottom: 12px; background-color: rgba(255, 255, 255, 0.03);">
                                    <div style="font-size: 1.1rem; font-weight: 600;">{diag['icone']} {diag['titulo']}</div>
                                    <div style="font-size: 1.4rem; font-weight: bold; margin: 4px 0;">{diag['valor']}</div>
                                    <div style="font-size: 0.88rem; color: #888;">{diag['mensagem']}</div>
                                </div>
                                """,
                                unsafe_allow_html=True
                            )

                st.markdown("---")
                st.markdown("#### 📈 Matriz Histórica de Indicadores Contábeis")

                if not df_ratios.empty:
                    df_display_ratios = df_ratios.copy()
                    
                    # Formata as colunas de data (anos ou trimestre)
                    new_ratio_cols = []
                    for col_date in df_display_ratios.columns:
                        try:
                            yr, mo, _ = str(col_date).split("-")
                            if periodo_key == "anual":
                                new_ratio_cols.append(yr)
                            else:
                                new_ratio_cols.append(f"{mo}/{yr[2:]}")
                        except Exception:
                            new_ratio_cols.append(str(col_date))
                    df_display_ratios.columns = new_ratio_cols

                    # Formata valores para percentual ou número
                    def format_ratio_val(val, metric_name):
                        if val is None or pd.isna(val):
                            return "-"
                        if "Margem" in metric_name or "ROE" in metric_name or "ROIC" in metric_name or "(Passivo/Ativo)" in metric_name or "(CP/Total)" in metric_name:
                            return f"{val * 100:.2f}%"
                        elif "FCO" in metric_name or "FCL" in metric_name:
                            return format_number(val, is_currency=True, currency=moeda_ativo_sel, decimals=0)
                        else:
                            return f"{val:.2f}x"

                    df_formatted = pd.DataFrame(index=df_display_ratios.index, columns=df_display_ratios.columns)
                    for metric in df_display_ratios.index:
                        for col in df_display_ratios.columns:
                            df_formatted.loc[metric, col] = format_ratio_val(df_display_ratios.loc[metric, col], metric)

                    # Separação temática em Abas visuais
                    tab_liq, tab_endiv, tab_rent, tab_caixa = st.tabs([
                        "💧 Liquidez", 
                        "⚖️ Estrutura & Solvência", 
                        "💰 Rentabilidade & Margens", 
                        "💵 Fluxo de Caixa"
                    ])

                    with tab_liq:
                        sub_liq = ["Liquidez Corrente", "Liquidez Seca", "Liquidez Imediata"]
                        st.dataframe(df_formatted.loc[df_formatted.index.intersection(sub_liq)], width='stretch')
                        
                        with st.expander("📚 **Fórmulas e Fundamentos de Liquidez (ADC)**", expanded=False):
                            c1, c2, c3 = st.columns(3)
                            with c1:
                                st.markdown("##### 💧 Liquidez Corrente ($LC$)")
                                st.latex(r"LC = \frac{\text{Ativo Circulante}}{\text{Passivo Circulante}}")
                                st.caption("Mede a capacidade de pagamento de curto prazo para cada 1 real de dívida circulante. Idealmente superior a 1,00x.")
                            with c2:
                                st.markdown("##### 🏜️ Liquidez Seca ($LS$)")
                                st.latex(r"LS = \frac{\text{Ativo Circulante} - \text{Estoques}}{\text{Passivo Circulante}}")
                                st.caption("Capacidade de quitar obrigações imediatas sem depender da realização/venda dos estoques.")
                            with c3:
                                st.markdown("##### ⚡ Liquidez Imediata ($LI$)")
                                st.latex(r"LI = \frac{\text{Caixa e Equivalentes}}{\text{Passivo Circulante}}")
                                st.caption("Percentual das dívidas de curto prazo que a empresa pode liquidar instantaneamente com disponibilidades.")

                    with tab_endiv:
                        sub_endiv = ["Endividamento Geral (Passivo/Ativo)", "Composição do Endividamento (CP/Total)", "Dívida Líquida / EBITDA", "Imobilização do PL"]
                        st.dataframe(df_formatted.loc[df_formatted.index.intersection(sub_endiv)], width='stretch')
                        
                        with st.expander("📚 **Fórmulas e Fundamentos de Estrutura & Solvência (ADC)**", expanded=False):
                            c1, c2 = st.columns(2)
                            with c1:
                                st.markdown("##### ⚖️ Endividamento Geral ($EG$)")
                                st.latex(r"EG = \frac{\text{Passivo Exigível Total}}{\text{Ativo Total}} = \frac{PC + PNC}{\text{Ativo Total}}")
                                st.caption("Proporção do ativo financiada com capital de terceiros (recursos onerosos e operacionais).")

                                st.markdown("##### ⏳ Composição do Endividamento ($CE$)")
                                st.latex(r"CE = \frac{\text{Passivo Circulante (PC)}}{\text{Passivo Exigível Total (PC + PNC)}}")
                                st.caption("Mede a pressão de vencimento da dívida. Quanto menor o CE, mais alongado é o perfil das obrigações.")
                            with c2:
                                st.markdown("##### ⏳ Dívida Líquida / EBITDA")
                                st.latex(r"\frac{\text{Dívida Líquida}}{\text{EBITDA}} = \frac{\text{Dívida Bruta} - \text{Caixa}}{\text{EBITDA}}")
                                st.caption("Mede o tempo necessário (em anos) para quitar a dívida líquida com a geração operacional bruta de caixa. Idealmente abaixo de 2,5x ~ 3,0x.")

                                st.markdown("##### 🏢 Imobilização do PL ($IPL$)")
                                st.latex(r"IPL = \frac{\text{Ativo Não Circulante (ou Imobilizado)}}{\text{Patrimônio Líquido}}")
                                st.caption("Indica quanto do capital próprio está comprometido em ativos fixos/não circulantes.")

                    with tab_rent:
                        sub_rent = ["Margem Bruta", "Margem EBITDA", "Margem Líquida", "Giro do Ativo", "ROE (Retorno s/ Patrimônio Líquido)", "ROIC Estimado"]
                        st.dataframe(df_formatted.loc[df_formatted.index.intersection(sub_rent)], width='stretch')
                        
                        with st.expander("📚 **Fórmulas e Fundamentos de Rentabilidade & Margens (ADC)**", expanded=False):
                            c1, c2, c3 = st.columns(3)
                            with c1:
                                st.markdown("##### 📦 Margem Bruta ($MB$)")
                                st.latex(r"MB = \frac{\text{Lucro Bruto}}{\text{Receita Líquida}}")
                                st.caption("Rentabilidade após descontar os custos diretos de produção (CPV/CMV).")

                                st.markdown("##### ⚡ Margem EBITDA")
                                st.latex(r"\text{Margem EBITDA} = \frac{\text{EBITDA}}{\text{Receita Líquida}}")
                                st.caption("Eficiência operacional pura, desconsiderando efeitos financeiros, depreciação e impostos.")
                            with c2:
                                st.markdown("##### 💰 Margem Líquida ($ML$)")
                                st.latex(r"ML = \frac{\text{Lucro Líquido}}{\text{Receita Líquida}}")
                                st.caption("Percentual de cada 1 real faturado que efetivamente se converte em lucro aos acionistas.")

                                st.markdown("##### 🔄 Giro do Ativo ($GA$)")
                                st.latex(r"GA = \frac{\text{Receita Líquida}}{\text{Ativo Total}}")
                                st.caption("Eficiência com que os ativos totais da empresa geram vendas/receita operacional.")
                            with c3:
                                st.markdown("##### 💎 Return on Equity ($ROE$)")
                                st.latex(r"ROE = \frac{\text{Lucro Líquido}}{\text{Patrimônio Líquido}}")
                                st.caption("Taxa de remuneração do capital próprio investido pelos sócios/acionistas.")

                                st.markdown("##### 🎯 ROIC Estimado")
                                st.latex(r"ROIC = \frac{\text{NOPAT}}{\text{Capital Investido}} = \frac{\text{EBIT} \times (1 - t)}{PL + \text{Dívida Líquida}}")
                                st.caption("Retorno gerado sobre todo o capital produtivo alocado na empresa (próprio + terceiros).")

                    with tab_caixa:
                        sub_caixa = ["FCO (Geração de Caixa Operacional)", "FCL (Fluxo de Caixa Livre)"]
                        st.dataframe(df_formatted.loc[df_formatted.index.intersection(sub_caixa)], width='stretch')
                        
                        with st.expander("📚 **Fórmulas e Fundamentos de Fluxo de Caixa (ADC)**", expanded=False):
                            c1, c2 = st.columns(2)
                            with c1:
                                st.markdown("##### 🏭 Fluxo de Caixa Operacional ($FCO$)")
                                st.latex(r"FCO = \text{Lucro Líquido} + \text{D\&A} \pm \Delta \text{Capital de Giro}")
                                st.caption("Caixa efetivo gerado pelas atividades operacionais da empresa, depurado de receitas/despesas não caixa.")
                            with c2:
                                st.markdown("##### 🕊️ Fluxo de Caixa Livre ($FCL / FCF$)")
                                st.latex(r"FCL = FCO - CapEx")
                                st.caption("Caixa livre excedente após todos os investimentos de capital (CapEx), disponível para pagar dividendos ou amortizar dívidas.")
                else:
                    st.info("Dados insuficientes nos demonstrativos para gerar os indicadores da matriz contábil.")
        else:
            df_fundamental = db_manager.get_fundamental_data(ativo_sel, demo_key, periodo_key)
        
            if df_fundamental.empty:
                st.warning("⚠️ Nenhum dado contábil local encontrado para este ativo. Clique em **Atualizar Dados do Ativo** acima para carregar as informações históricas do Yahoo Finance.")
            else:
                df_translated = df_fundamental.copy()
                df_translated.index = [TERMOS_CONTABEIS.get(str(x), str(x)) for x in df_translated.index]
                df_translated = df_translated[~df_translated.index.duplicated(keep='first')]
                
                ORDEM_BALANCO = [
                    "Ativo Total", "Ativo Circulante", "Caixa e Equivalentes de Caixa", "Caixa, Equivalentes e Aplicações",
                    "Equivalentes de Caixa", "Caixa Financeiro", "Aplicações Financeiras CP", "Clientes / Contas a Receber",
                    "Contas a Receber", "Outros Contas a Receber", "Estoques", "Matéria-Prima", "Produtos Acabados",
                    "Despesas Antecipadas", "Outros Ativos Circulantes", "Ativo Não Circulante Total", "Ativo Não Circulante",
                    "Imobilizado Líquido", "Ativo Imobilizado Bruto", "Depreciação Acumulada", "Propriedades e Equipamentos",
                    "Terrenos e Benfeitorias", "Máquinas, Móveis e Equipamentos", "Arrendamentos / Leasing",
                    "Ágio e Intangíveis", "Ágio / Goodwill", "Ativos Intangíveis", "Investimentos e Adiantamentos",
                    "Investimentos em Coligadas/Joint Ventures", "Investimentos em Ativos Financeiros",
                    "Ativo Diferido (LP)", "Ativos Fiscais Diferidos (LP)", "Outros Ativos Não Circulantes",
                    "Passivo Total + PL", "Passivo Total", "Passivo Circulante", "Fornecedores / Contas a Pagar",
                    "Contas a Pagar e Despesas Apropriadas", "Outras Contas a Pagar LP", "Dívida de Curto Prazo (CP)",
                    "Empréstimos e Financiamentos CP", "Dívida de Curto Prazo", "Notas Comerciais",
                    "Outras Obrigações Financeiras CP", "Despesas Apropriadas a Pagar (CP)", "Passivo Diferido (CP)",
                    "Receita Diferida / Adiantamentos de Clientes", "Imposto de Renda a Pagar", "Total de Impostos a Pagar",
                    "Outros Passivos Circulantes", "Passivo Não Circulante", "Dívida de Longo Prazo",
                    "Empréstimos e Financiamentos LP", "Outros Passivos Não Circulantes", "Patrimônio Líquido (PL)",
                    "Patrimônio Líquido Ordinário", "Capital Social", "Ações Ordinárias (Capital)", "Lucros Acumulados",
                    "Ações em Tesouraria", "Outros Ajustes do Patrimônio Líquido", "Outros Itens do PL",
                    "Ajustes de Avaliação Patrimonial", "Patrimônio Líquido Total + Participação de Não Controladores"
                ]
                
                ORDEM_DRE = [
                    "Receita Líquida", "Receita Operacional", "Custo da Receita Reconciliado", "Custos dos Serviços/Produtos", "Lucro Bruto",
                    "Despesas Operacionais", "Despesas de Vendas, Gerais e Admin (SG&A)", "Despesas de Vendas, Gerais e Administrativas (SG&A)", "Despesas de Vendas e Marketing",
                    "Despesas Gerais e Administrativas", "Pesquisa e Desenvolvimento (P&D)", "Depreciação e Amortização (D&A)",
                    "Amortização", "Depreciação Reconciliada", "Resultado Operacional (EBIT)", "Resultado Operacional Reportado", "EBITDA", "EBITDA Normalizado", "EBIT", "Resultado Financeiro Líquido",
                    "Receitas Financeiras", "Despesas Financeiras", "Outras Receitas/Despesas Operacionais", "Outras Receitas/Despesas Não Operacionais", "Lucro Antes de Impostos (LAIR)", "Efeito Fiscal de Itens Extraordinários", "Alíquota de Imposto Efetiva", "Impostos e Provisões",
                    "Despesas Totais", "Lucro Líquido Incluindo Não Controladores", "Lucro Líquido", "Lucro Líquido aos Acionistas", "Lucro Líquido Diluído Disponível aos Acionistas", "Lucro Líquido Normalizado", "Lucro Líquido de Operações Continuadas (Controladores)", "Lucro Líquido de Operações Continuadas e Descontinuadas", "Lucro Líquido de Operações Continuadas",
                    "LPA Básico (Lucro por Ação)", "LPA Diluído (Lucro por Ação)", "Média de Ações Básicas", "Média de Ações Diluídas"
                ]
                
                ORDEM_FLUXO = [
                    "Lucro Líquido", "Depreciação, Amortização e Exaustão", "Remuneração Baseada em Ações", "Outros Ajustes Sem Efeito de Caixa", "Variação de Estoques",
                    "Variação de Contas a Receber", "Variação de Fornecedores / Contas a Pagar", "Variação de Contas a Pagar e Despesas Apropriadas", "Variação de Outros Ativos Circulantes", "Variação de Outros Passivos Circulantes",
                    "Variação de Capital de Giro", "Fluxo de Caixa Operacional (FCO)", "FCO - Atividades Operacionais", "Aquisição de Imobilizado (CapEx)", "Compra de Investimentos", "Venda de Investimentos",
                    "Compra e Venda Líquida de Investimentos", "Compra e Venda Líquida de Imobilizado (CapEx Líquido)", "Outras Variações Líquidas de Investimento", "Fluxo de Caixa de Investimentos (FCI)", "FCO - Atividades de Investimento",
                    "Emissão Líquida de Ações", "Pagamento de Ações Ordinárias / Redução de Capital", "Emissão de Dívida / Captação de Recursos", "Amortização de Dívidas", "Emissão de Dívida de Longo Prazo", "Pagamento de Dívida de Longo Prazo", "Pagamento de Dívida de Curto Prazo",
                    "Emissão/Amortização Líquida de Dívida LP", "Emissão/Amortização Líquida de Dívida CP", "Captação/Amortização Líquida de Dívida", "Dividendos em Dinheiro Pagos", "Outros Fluxos Líquidos de Financiamento", "Fluxo de Caixa de Financiamentos (FCF)", "FCO - Atividades de Financiamento",
                    "Imposto de Renda Pago (Dado Suplementar)", "Saldo de Caixa Inicial", "Variação Líquida de Caixa", "Saldo de Caixa Final"
                ]
                
                if demo_key == "balanco":
                    ordem_lista = ORDEM_BALANCO
                elif demo_key == "dre":
                    ordem_lista = ORDEM_DRE
                else:
                    ordem_lista = ORDEM_FLUXO
                    
                def get_sort_index(conta_traduzida):
                    try:
                        return ordem_lista.index(conta_traduzida)
                    except ValueError:
                        return 999
                        
                df_translated["sort_idx"] = [get_sort_index(idx) for idx in df_translated.index]
                df_translated = df_translated.sort_values("sort_idx").drop(columns=["sort_idx"])
                
                for col_date in df_translated.columns:
                    df_translated[col_date] = df_translated[col_date].apply(
                        lambda val: format_number(val, is_currency=True, currency=moeda_ativo_sel, decimals=0)
                    )
                    
                new_cols = []
                for col_date in df_translated.columns:
                    try:
                        yr, mo, _ = col_date.split("-")
                        if periodo_key == "anual":
                            new_cols.append(yr)
                        else:
                            new_cols.append(f"{mo}/{yr[2:]}")
                    except Exception:
                        new_cols.append(str(col_date))
                df_translated.columns = new_cols
                
                st.markdown(f"### 📑 {demo_sel} - {ativo_sel} ({periodo_sel})")
                
                if demo_key == "balanco":
                    contas_ativo = [
                        "Ativo Total", "Ativo Circulante", "Caixa e Equivalentes de Caixa", "Caixa, Equivalentes e Aplicações",
                        "Equivalentes de Caixa", "Caixa Financeiro", "Aplicações Financeiras CP", "Clientes / Contas a Receber",
                        "Contas a Receber", "Outros Contas a Receber", "Estoques", "Matéria-Prima", "Produtos Acabados",
                        "Despesas Antecipadas", "Outros Ativos Circulantes", "Ativo Não Circulante Total", "Ativo Não Circulante",
                        "Imobilizado Líquido", "Ativo Imobilizado Bruto", "Depreciação Acumulada", "Propriedades e Equipamentos",
                        "Terrenos e Benfeitorias", "Máquinas, Móveis e Equipamentos", "Arrendamentos / Leasing",
                        "Ágio e Intangíveis", "Ágio / Goodwill", "Ativos Intangíveis", "Investimentos e Adiantamentos",
                        "Investimentos em Coligadas/Joint Ventures", "Investimentos em Ativos Financeiros",
                        "Ativo Diferido (LP)", "Ativos Fiscais Diferidos (LP)", "Outros Ativos Não Circulantes"
                    ]
                    
                    df_ativos = df_translated[df_translated.index.isin(contas_ativo)]
                    df_passivos_pl = df_translated[~df_translated.index.isin(contas_ativo)]
                    
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.markdown("#### 🟢 Ativos (Liquidez Decrescente)")
                        st.dataframe(df_ativos, width='stretch')
                    with col_b:
                        st.markdown("#### 🔴 Passivo & PL (Exigibilidade Decrescente)")
                        st.dataframe(df_passivos_pl, width='stretch')
                else:
                    st.dataframe(df_translated, width='stretch')
