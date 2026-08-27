import os
import datetime
import pandas as pd
import streamlit as st
from typing import Optional

from src.services.deduplication import identify_duplicates
from src.services.ingestion_parser import parse_ofx, parse_csv, parse_receipt_image
from src.services.pluggy_service import PluggyService
from src.services.data_loader import append_transactions_to_sheets
from src.utils.logger import get_logger

logger = get_logger("tabs", "importar_gastos")


CATEGORIAS_RECEITAS = [
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

CATEGORIAS_DESPESAS = [
    "Combustível",
    "Compras",
    "Condomínio",
    "Delivery comida",
    "Ensinos à Distância",
    "Escola/Faculdade",
    "Estacionamento",
    "Eventos",
    "Games",
    "Hotel",
    "Internet",
    "Lanches",
    "Luz",
    "Medicamentos",
    "Médicos e terapeutas",
    "Presentes",
    "Restaurante",
    "Salão de beleza",
    "Serviços / Manutenção",
    "Streaming",
    "Supermercado",
    "Telefonia",
    "Táxi / Uber",
    "Vestuário",
    "Água",
    "Outros"
]

# Lista unificada e ordenada sem duplicatas para o editor
CATEGORIAS_PADRAO = sorted(list(set(CATEGORIAS_RECEITAS + CATEGORIAS_DESPESAS)))

CONTAS_CREDITADAS_PADRAO = [
    "Inter",
    "Sicredi",
    "C6",
    "XP",
    "99 Pay",
    "Mercado Pago",
    "Conta corrente",
    "Cartão de crédito",
    "Nubank",
    "Outros",
    ""
]

CONTAS_DEBITADAS_PADRAO = [
    "Cartão de crédito",
    "Conta corrente",
    "99 Pay",
    "Mercado Pago",
    "Sicredi",
    "Inter",
    "C6",
    "XP",
    "Nubank",
    "Outros",
    ""
]

FIXO_VARIAVEL_OPCOES = ["Variável", "Fixo"]
ESSENCIAL_OPCOES = ["Essencial", "Não essencial"]

SUBTABS_IMPORTAR = {
    "comprovantes": "📸 1. Comprovantes e Prints (IA)",
    "arquivos": "📄 2. Arquivos Bancários (.OFX / .CSV)",
    "open_finance": "🏦 3. Open Finance (Pluggy)"
}
SLUG_TO_LABEL_IMPORTAR = SUBTABS_IMPORTAR
LABEL_TO_SLUG_IMPORTAR = {v: k for k, v in SUBTABS_IMPORTAR.items()}

def render_tab_importar_gastos(df_receitas_existentes: pd.DataFrame, df_despesas_existentes: pd.DataFrame):
    """
    Renderiza a aba de Ingestão Inteligente e Híbrida de Despesas/Receitas com 3 frentes de entrada,
    detecção em tempo real de duplicidades e conciliação interativa via st.data_editor.
    """
    st.markdown('<div class="tab-header">📥 Ingestão Inteligente e Conciliação de Gastos</div>', unsafe_allow_html=True)
    st.caption("Importe transações a partir de prints/comprovantes (OCR com IA), extratos bancários (.OFX / .CSV) ou via Open Finance (Pluggy).")

    # Inicializa estado da sessão para armazenar transações em análise/revisão
    if "df_staging_transactions" not in st.session_state:
        st.session_state.df_staging_transactions = pd.DataFrame(
            columns=[
                "Importar", "Status", "Data", "Descricao", "Valor", "Tipo",
                "Categoria", "Conta creditada", "Conta debitada", "Fixo vs. Variável", "Essencial vs. Não Essencial", "Hash"
            ]
        )

    # Consolida e normaliza base existente para checagem de duplicidade
    existentes_list = []
    if df_despesas_existentes is not None and not df_despesas_existentes.empty:
        df_d = df_despesas_existentes.copy()
        if "Gasto em" in df_d.columns:
            df_d = df_d.rename(columns={"Gasto em": "Data"})
        if "gasto_em" in df_d.columns:
            df_d = df_d.rename(columns={"gasto_em": "Data"})
        if "Nome" in df_d.columns:
            df_d = df_d.rename(columns={"Nome": "Descricao"})
        if "nome" in df_d.columns:
            df_d = df_d.rename(columns={"nome": "Descricao"})
        if "valor" in df_d.columns:
            df_d = df_d.rename(columns={"valor": "Valor"})
        df_d = df_d.dropna(subset=["Valor"])
        existentes_list.append(df_d)

    if df_receitas_existentes is not None and not df_receitas_existentes.empty:
        df_r = df_receitas_existentes.copy()
        if "Recebido em" in df_r.columns:
            df_r = df_r.rename(columns={"Recebido em": "Data"})
        if "recebido_em" in df_r.columns:
            df_r = df_r.rename(columns={"recebido_em": "Data"})
        if "Nome" in df_r.columns:
            df_r = df_r.rename(columns={"Nome": "Descricao"})
        if "nome" in df_r.columns:
            df_r = df_r.rename(columns={"nome": "Descricao"})
        if "valor" in df_r.columns:
            df_r = df_r.rename(columns={"valor": "Valor"})
        df_r = df_r.dropna(subset=["Valor"])
        existentes_list.append(df_r)

    df_existentes_total = pd.concat(existentes_list, ignore_index=True) if existentes_list else pd.DataFrame()

    # Sincroniza subtab com a URL (?subtab=slug)
    url_subtab = st.query_params.get("subtab", "comprovantes")
    if url_subtab not in SLUG_TO_LABEL_IMPORTAR:
        url_subtab = "comprovantes"
        
    current_label = SLUG_TO_LABEL_IMPORTAR[url_subtab]
    subtab_labels = list(SUBTABS_IMPORTAR.values())
    default_idx = subtab_labels.index(current_label)
    
    selected_label = st.radio(
        "Selecionar Método de Ingestão:",
        options=subtab_labels,
        index=default_idx,
        horizontal=True,
        label_visibility="collapsed",
        key="importar_subtab_radio"
    )
    
    selected_slug = LABEL_TO_SLUG_IMPORTAR[selected_label]
    if st.query_params.get("subtab") != selected_slug:
        st.query_params["subtab"] = selected_slug
        logger.info(f"Sub-navegação Importação: {selected_slug}")
        st.rerun()
    
    st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)


    # ==========================================
    # ABA 1: COMPROVANTES E PRINTS (GEMINI VISION)
    # ==========================================
    if selected_slug == "comprovantes":

        st.markdown("##### 📸 Leitura Inteligente de Prints e Comprovantes")
        st.write("Envie imagens de comprovantes Pix, faturas de cartão ou recibos. A IA extrairá automaticamente valores, datas e categorias.")

        uploaded_images = st.file_uploader(
            "Selecione um ou mais arquivos de imagem ou documento",
            type=["png", "jpg", "jpeg", "webp", "pdf"],
            accept_multiple_files=True,
            key="uploader_receipt_images"
        )

        col_proc_img, _ = st.columns([2.5, 7.5])
        with col_proc_img:
            btn_proc_images = st.button("✨ Processar Imagens com Gemini Vision", type="primary", use_container_width=True, disabled=(not uploaded_images))

        if btn_proc_images and uploaded_images:
            all_extracted = []
            with st.spinner("Analisando comprovantes e faturas com Gemini Vision..."):
                for uploaded_file in uploaded_images:
                    try:
                        bytes_data = uploaded_file.read()
                        mime_type = uploaded_file.type if uploaded_file.type else "image/png"
                        if "pdf" in uploaded_file.name.lower():
                            mime_type = "application/pdf"

                        df_parsed = parse_receipt_image(bytes_data, mime_type=mime_type)
                        if not df_parsed.empty:
                            all_extracted.append(df_parsed)
                    except Exception as e:
                        st.error(f"Erro ao processar `{uploaded_file.name}`: {e}")

            if all_extracted:
                df_novos = pd.concat(all_extracted, ignore_index=True)
                if "Conta debitada" not in df_novos.columns and "Forma_Pagamento" in df_novos.columns:
                    df_novos["Conta debitada"] = df_novos["Forma_Pagamento"]
                if "Fixo vs. Variável" not in df_novos.columns:
                    df_novos["Fixo vs. Variável"] = "Variável"
                if "Essencial vs. Não Essencial" not in df_novos.columns:
                    df_novos["Essencial vs. Não Essencial"] = "Essencial"

                df_novos = identify_duplicates(df_novos, df_existentes_total)
                st.session_state.df_staging_transactions = pd.concat(
                    [st.session_state.df_staging_transactions, df_novos], ignore_index=True
                ).drop_duplicates(subset=["Hash"], keep="last")
                st.success(f"🎉 {len(df_novos)} lançamentos extraídos dos comprovantes com sucesso!")
                st.rerun()

    # ==========================================
    # ABA 2: ARQUIVOS BANCÁRIOS (.OFX / .CSV)
    # ==========================================
    elif selected_slug == "arquivos":
        st.markdown("##### 📄 Importação de Extratos Bancários")
        st.write("Importe arquivos exportados do seu banco digital ou tradicional nos formatos `.ofx` ou `.csv` (Sicredi, Nubank, Itaú, etc.).")

        uploaded_bank_files = st.file_uploader(
            "Selecione arquivos .OFX ou .CSV",
            type=["ofx", "csv", "txt"],
            accept_multiple_files=True,
            key="uploader_bank_files"
        )

        col_proc_files, _ = st.columns([2.5, 7.5])
        with col_proc_files:
            btn_proc_files = st.button("📥 Processar Extratos Bancários", type="primary", use_container_width=True, disabled=(not uploaded_bank_files))

        if btn_proc_files and uploaded_bank_files:
            all_extracted_files = []
            with st.spinner("Decodificando extratos e normalizando dados..."):
                for b_file in uploaded_bank_files:
                    try:
                        bytes_data = b_file.read()
                        fname = b_file.name
                        if fname.lower().endswith(".ofx"):
                            df_parsed = parse_ofx(bytes_data, filename=fname)
                        else:
                            df_parsed = parse_csv(bytes_data, filename=fname)

                        if not df_parsed.empty:
                            all_extracted_files.append(df_parsed)
                    except Exception as e:
                        st.error(f"Erro ao processar `{b_file.name}`: {e}")

            if all_extracted_files:
                df_novos_files = pd.concat(all_extracted_files, ignore_index=True)
                if "Conta creditada" not in df_novos_files.columns:
                    df_novos_files["Conta creditada"] = df_novos_files.apply(
                        lambda r: r.get("Conta debitada", "") if r.get("Tipo") == "Receita" else "", axis=1
                    )
                if "Conta debitada" not in df_novos_files.columns and "Forma_Pagamento" in df_novos_files.columns:
                    df_novos_files["Conta debitada"] = df_novos_files["Forma_Pagamento"]
                if "Fixo vs. Variável" not in df_novos_files.columns:
                    df_novos_files["Fixo vs. Variável"] = "Variável"
                if "Essencial vs. Não Essencial" not in df_novos_files.columns:
                    df_novos_files["Essencial vs. Não Essencial"] = "Essencial"

                # Desmarca automaticamente por padrão pagamentos de fatura ou transferências internas para evitar duplicidade
                if "Importar" in df_novos_files.columns:
                    for idx, row in df_novos_files.iterrows():
                        d_low = str(row.get("Descricao", "")).lower()
                        if any(k in d_low for k in ["pagamento fatura", "pgto fatura", "fatura cartao", "fatura cartão", "pagamento de cartao", "pagamento de cartão"]):
                            df_novos_files.at[idx, "Importar"] = False

                df_novos_files = identify_duplicates(df_novos_files, df_existentes_total)
                st.session_state.df_staging_transactions = pd.concat(
                    [st.session_state.df_staging_transactions, df_novos_files], ignore_index=True
                ).drop_duplicates(subset=["Hash"], keep="last")
                st.success(f"🎉 {len(df_novos_files)} lançamentos importados dos extratos bancários!")
                st.rerun()

    # ==========================================
    # ABA 3: OPEN FINANCE (PLUGGY)
    # ==========================================
    elif selected_slug == "open_finance":
        st.markdown("##### 🏦 Conexão Open Finance via Pluggy")
        st.write("Sincronize transações diretamente da sua conta conectada via Open Finance.")


        col_p1, col_p2, col_p3 = st.columns([3, 3, 3])
        with col_p1:
            dt_inicio = st.date_input(
                "Data Inicial",
                value=datetime.date.today() - datetime.timedelta(days=15),
                key="pluggy_dt_inicio"
            )
        with col_p2:
            dt_fim = st.date_input(
                "Data Final",
                value=datetime.date.today(),
                key="pluggy_dt_fim"
            )
        with col_p3:
            st.write("")
            st.write("")
            btn_fetch_pluggy = st.button("🔄 Buscar Transações (Pluggy)", type="primary", use_container_width=True)

        if btn_fetch_pluggy:
            try:
                with st.spinner("Conectando à API da Pluggy e baixando transações..."):
                    pluggy = PluggyService()
                    df_pluggy = pluggy.fetch_transactions(
                        from_date=dt_inicio.strftime("%Y-%m-%d"),
                        to_date=dt_fim.strftime("%Y-%m-%d")
                    )

                    if not df_pluggy.empty:
                        if "Conta debitada" not in df_pluggy.columns and "Forma_Pagamento" in df_pluggy.columns:
                            df_pluggy["Conta debitada"] = df_pluggy["Forma_Pagamento"]
                        if "Fixo vs. Variável" not in df_pluggy.columns:
                            df_pluggy["Fixo vs. Variável"] = "Variável"
                        if "Essencial vs. Não Essencial" not in df_pluggy.columns:
                            df_pluggy["Essencial vs. Não Essencial"] = "Essencial"

                        df_pluggy = identify_duplicates(df_pluggy, df_existentes_total)
                        st.session_state.df_staging_transactions = pd.concat(
                            [st.session_state.df_staging_transactions, df_pluggy], ignore_index=True
                        ).drop_duplicates(subset=["Hash"], keep="last")
                        st.success(f"🎉 {len(df_pluggy)} transações obtidas da Pluggy com sucesso!")
                        st.rerun()
                    else:
                        st.info("Nenhuma transação retornada para o período informado ou contas não configuradas.")
            except Exception as e:
                st.error(f"Erro ao consultar Open Finance Pluggy: {e}")

    # ==========================================
    # ÁREA DE PRÉ-VISUALIZAÇÃO E CONCILIAÇÃO
    # ==========================================
    st.markdown("---")
    st.markdown("### 📋 Área de Revisão, Conciliação e Aprovação (Human-in-the-Loop)")
    st.caption("Revise, ajuste valores/categorias e selecione quais transações serão persistidas.")

    df_staging = st.session_state.df_staging_transactions

    if df_staging.empty:
        st.info("Nenhuma transação em fila para revisão. Utilize uma das 3 abas acima para carregar comprovantes, arquivos ou dados via Open Finance.")
        return

    # Garante colunas obrigatórias
    cols_order = [
        "Importar", "Status", "Data", "Descricao", "Valor", "Tipo",
        "Categoria", "Conta creditada", "Conta debitada", "Fixo vs. Variável", "Essencial vs. Não Essencial", "Hash"
    ]
    for c in cols_order:
        if c not in df_staging.columns:
            if c == "Importar":
                df_staging[c] = True
            elif c == "Status":
                df_staging[c] = "Novo"
            elif c == "Tipo":
                df_staging[c] = "Despesa"
            elif c == "Categoria":
                df_staging[c] = "Outros"
            elif c == "Conta creditada":
                df_staging[c] = ""
            elif c == "Conta debitada":
                df_staging[c] = "Conta corrente"
            elif c == "Fixo vs. Variável":
                df_staging[c] = "Variável"
            elif c == "Essencial vs. Não Essencial":
                df_staging[c] = "Essencial"
            else:
                df_staging[c] = ""

    df_staging = df_staging[cols_order].copy()

    # Sanitização e coerção estrita de tipos para o st.data_editor
    # 1. Converte 'Data' para objetos datetime.date para compatibilidade nativa com DateColumn
    df_staging["Data"] = pd.to_datetime(df_staging["Data"], dayfirst=True, errors="coerce").dt.date
    df_staging["Data"] = df_staging["Data"].fillna(datetime.date.today())
    
    # 2. Converte 'Valor' para float puro
    df_staging["Valor"] = pd.to_numeric(df_staging["Valor"], errors="coerce").fillna(0.0).astype(float)

    # 3. Converte 'Importar' para booleano puro
    df_staging["Importar"] = df_staging["Importar"].astype(bool)

    # 4. Strings limpas para colunas categóricas
    df_staging["Descricao"] = df_staging["Descricao"].astype(str)
    df_staging["Tipo"] = df_staging["Tipo"].astype(str)
    df_staging["Categoria"] = df_staging["Categoria"].astype(str)
    df_staging["Conta creditada"] = df_staging["Conta creditada"].astype(str)
    df_staging["Conta debitada"] = df_staging["Conta debitada"].astype(str)
    df_staging["Fixo vs. Variável"] = df_staging["Fixo vs. Variável"].astype(str)
    df_staging["Essencial vs. Não Essencial"] = df_staging["Essencial vs. Não Essencial"].astype(str)
    df_staging["Status"] = df_staging["Status"].astype(str)

    # Métricas discriminadas baseadas apenas nas linhas com 'Importar == True'
    df_selecionados = df_staging[df_staging["Importar"] == True]
    total_itens = len(df_staging)
    
    receitas_previstas = df_selecionados[df_selecionados["Tipo"] == "Receita"]["Valor"].sum()
    despesas_previstas = df_selecionados[df_selecionados["Tipo"] == "Despesa"]["Valor"].sum()
    saldo_liquido = receitas_previstas - despesas_previstas

    def format_currency_br(val: float) -> str:
        if val < 0:
            return f"-R$ {abs(val):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    # Formatação do delta para o st.metric
    if saldo_liquido > 0:
        delta_str = f"+R$ {saldo_liquido:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        delta_color = "normal"
    elif saldo_liquido < 0:
        delta_str = f"-R$ {abs(saldo_liquido):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        delta_color = "normal"
    else:
        delta_str = None
        delta_color = "off"

    mcol1, mcol2, mcol3, mcol4 = st.columns(4)
    mcol1.metric("Total na Fila", total_itens, help="Total de itens carregados para revisão.")
    mcol2.metric("🟢 Receitas Previstas", format_currency_br(receitas_previstas), help="Soma das receitas selecionadas para importação.")
    mcol3.metric("🔴 Despesas Previstas", format_currency_br(despesas_previstas), help="Soma das despesas selecionadas para importação.")
    
    # Exibição do Saldo Líquido com formatação correta de valor e delta
    mcol4.metric(
        "⚖️ Saldo Líquido",
        format_currency_br(saldo_liquido),
        delta=delta_str,
        delta_color=delta_color,
        help="Receitas Previstas menos Despesas Previstas dos itens selecionados."
    )

    # Editor Interativo de Dados com Tipagem Compatível e Todas as Colunas de Schema
    edited_df = st.data_editor(
        df_staging,
        key="staging_data_editor",
        width="stretch",
        height=600,
        hide_index=True,
        column_config={
            "Importar": st.column_config.CheckboxColumn("Importar", default=True),
            "Status": st.column_config.TextColumn("Status", disabled=True),
            "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY", required=True),
            "Descricao": st.column_config.TextColumn("Nome / Descrição", required=True),
            "Valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f", min_value=0.01, required=True),
            "Tipo": st.column_config.SelectboxColumn(
                "Tipo",
                options=["Despesa", "Receita"],
                required=True
            ),
            "Categoria": st.column_config.SelectboxColumn(
                "Categoria",
                options=CATEGORIAS_PADRAO,
                required=True
            ),
            "Conta creditada": st.column_config.SelectboxColumn(
                "Conta creditada",
                options=CONTAS_CREDITADAS_PADRAO,
                required=False
            ),
            "Conta debitada": st.column_config.SelectboxColumn(
                "Conta debitada",
                options=CONTAS_DEBITADAS_PADRAO,
                required=False
            ),
            "Fixo vs. Variável": st.column_config.SelectboxColumn(
                "Fixo vs. Variável",
                options=FIXO_VARIAVEL_OPCOES,
                required=True
            ),
            "Essencial vs. Não Essencial": st.column_config.SelectboxColumn(
                "Essencial vs. Não Essencial",
                options=ESSENCIAL_OPCOES,
                required=True
            ),
            "Hash": None,  # Oculta da tabela visual preservando para deduplicação interna
        }
    )

    # Ações de gravação e limpeza
    btn_col1, btn_col2, _ = st.columns([3, 2, 5])
    
    with btn_col1:
        if st.button("💾 Gravar Lançamentos na Planilha", type="primary", use_container_width=True):
            df_to_save = edited_df[edited_df["Importar"] == True].copy()
            if df_to_save.empty:
                st.warning("Nenhuma linha selecionada para importação (marque o checkbox 'Importar').")
            else:
                with st.spinner("Gravando no Google Sheets e sincronizando SQLite local..."):
                    try:
                        # Converte 'Data' para string YYYY-MM-DD
                        df_to_save["Data"] = df_to_save["Data"].astype(str)
                        res = append_transactions_to_sheets(df_to_save)
                        st.cache_data.clear()
                        
                        # Remove os itens salvos do staging
                        saved_hashes = set(df_to_save["Hash"].tolist())
                        st.session_state.df_staging_transactions = edited_df[~edited_df["Hash"].isin(saved_hashes)]
                        
                        st.success(
                            f"🎉 Sucesso! Gravados com êxito: {res.get('despesas', 0)} despesas e {res.get('receitas', 0)} receitas."
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar lançamentos: {e}")

    with btn_col2:
        if st.button("🗑️ Limpar Fila de Revisão", use_container_width=True):
            st.session_state.df_staging_transactions = pd.DataFrame(
                columns=[
                    "Importar", "Status", "Data", "Descricao", "Valor", "Tipo",
                    "Categoria", "Conta debitada", "Fixo vs. Variável", "Essencial vs. Não Essencial", "Hash"
                ]
            )
            st.rerun()
