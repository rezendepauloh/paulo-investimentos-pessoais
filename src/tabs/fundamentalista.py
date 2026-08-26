import streamlit as st
import pandas as pd
import db_manager
from data_loader import TERMOS_CONTABEIS, sync_fundamental_data_from_yfinance
from analytics import is_valid_yfinance_ticker
from src.utils.formatting import format_number

def render_tab_fundamentalista(df_holdings, df_dividendos):
    """
    Renderiza a aba de Análise Fundamentalista Histórica (Balanço, DRE, Fluxo de Caixa e FIIs).
    """
    st.subheader("🔍 Análise Fundamentalista Histórica")
    st.markdown("Consulte os demonstrativos financeiros históricos (Balanço Patrimonial, DRE e Fluxo de Caixa) das empresas que você possui em carteira.")
    
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

    col_f1, col_f2 = st.columns([1, 1])
    with col_f1:
        ativo_sel = st.selectbox("Escolha um Ativo da sua Carteira:", ativos_elegiveis)
    with col_f2:
        periodo_sel = st.radio("Período dos Demonstrativos:", ["Anual", "Trimestral"], horizontal=True)
        
    tipo_ativo_sel = df_holdings[df_holdings["ticker"] == ativo_sel]["tipo"].iloc[0]
    moeda_ativo_sel = df_holdings[df_holdings["ticker"] == ativo_sel]["moeda"].iloc[0]
    is_fii = (tipo_ativo_sel == "FIIs" or "FII" in str(ativo_sel).upper())
    
    col_btn_sync, _ = st.columns([1, 2])
    with col_btn_sync:
        if st.button("🔄 Atualizar Dados do Ativo", help="Busca os demonstrativos mais recentes do Yahoo Finance e atualiza o cache no SQLite."):
            with st.spinner("Atualizando dados..."):
                success = sync_fundamental_data_from_yfinance(ativo_sel)
                if success:
                    st.success("✅ Dados atualizados com sucesso!")
                    st.rerun()
                else:
                    st.error("❌ Falha ao atualizar dados.")
                    
    st.markdown("---")
    
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
        demo_sel = st.radio(
            "Demonstrativo para Análise:",
            ["Balanço Patrimonial", "DRE (Demonstrativo do Resultado)", "Fluxo de Caixa"],
            horizontal=True
        )
        
        demonstrativo_map = {
            "Balanço Patrimonial": "balanco",
            "DRE (Demonstrativo do Resultado)": "dre",
            "Fluxo de Caixa": "fluxo"
        }
        
        demo_key = demonstrativo_map[demo_sel]
        periodo_key = periodo_sel.lower()
        
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
