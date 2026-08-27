import os
import streamlit as st
import pandas as pd
from datetime import datetime

from src.services.data_loader import (
    load_sheet_data,
    update_worksheet_from_dataframe,
    get_all_editable_spreadsheets,
    sync_google_sheets_to_sqlite,
    clean_currency,
)
from src.tabs.importar_gastos import (
    CATEGORIAS_RECEITAS,
    CATEGORIAS_DESPESAS,
    CONTAS_DEBITADAS_PADRAO,
    CONTAS_CREDITADAS_PADRAO,
    FIXO_VARIAVEL_OPCOES,
    ESSENCIAL_OPCOES,
)
from src.utils.formatting import format_number
from src.utils.logger import get_logger

logger = get_logger("tabs", "editor_planilhas")


def render_tab_editor_planilhas():
    """
    Renderiza a aba de Edição e Gestão Direta de Planilhas Google Sheets e SQLite.
    Permite visualizar, filtrar, alterar, adicionar e remover linhas diretamente com st.data_editor,
    gravando as modificações em tempo real tanto no Google Sheets quanto no SQLite local.
    """
    st.markdown('<div class="tab-header">📝 Editor de Dados das Planilhas</div>', unsafe_allow_html=True)
    st.caption("Edite registros existentes, adicione novos lançamentos ou corrija dados nas suas planilhas do Google Sheets com sincronização bidirecional em tempo real no SQLite local.")

    # 1. Mensagem Flash de Sucesso anterior se houver
    if "editor_flash_message" in st.session_state:
        st.success(st.session_state.pop("editor_flash_message"))

    # 2. Recupera lista de planilhas editáveis configuradas
    spreadsheets_list = get_all_editable_spreadsheets()

    if not spreadsheets_list:
        st.warning("⚠️ Nenhuma planilha configurada no arquivo `.env`. Configure `SPREADSHEET_BUDGET_ID_2026`, `SPREADSHEET_BUDGET_ID_2027` ou `SPREADSHEET_ORDERS_ID`.")
        return

    spreadsheet_titles = [s["title"] for s in spreadsheets_list]
    current_sheet_title = st.session_state.get("editor_selected_sheet", spreadsheet_titles[0])
    if current_sheet_title not in spreadsheet_titles:
        current_sheet_title = spreadsheet_titles[0]
        st.session_state.editor_selected_sheet = current_sheet_title

    active_sheet_meta = next((s for s in spreadsheets_list if s["title"] == current_sheet_title), spreadsheets_list[0])

    available_tabs = active_sheet_meta.get("tabs", ["Despesas"])
    current_tab_name = st.session_state.get("editor_selected_tab", available_tabs[0])
    if current_tab_name not in available_tabs:
        current_tab_name = available_tabs[0]
        st.session_state.editor_selected_tab = current_tab_name

    # 3. Banner Informativo Superior com Link e Instrução
    col_info, col_link = st.columns([8, 2], vertical_alignment="center")
    with col_info:
        st.markdown(
            f"📍 **Planilha Ativa:** `{active_sheet_meta['title']}` &nbsp;|&nbsp; "
            f"**Aba:** `{current_tab_name}` &nbsp;|&nbsp; "
            f"**Tipo:** `{active_sheet_meta.get('type', 'Geral').capitalize()}`"
        )
    with col_link:
        sheet_url = active_sheet_meta.get("url", "#")
        st.link_button("🔗 Abrir no Google Sheets", sheet_url, use_container_width=True)

    st.markdown("---")

    # 4. Carrega os dados da aba selecionada
    spreadsheet_id = active_sheet_meta["spreadsheet_id"]
    worksheet_name = current_tab_name

    with st.spinner(f"Carregando dados de '{worksheet_name}' ({active_sheet_meta['title']})..."):
        df_raw = load_sheet_data(spreadsheet_id, worksheet_name)

    if df_raw.empty:
        st.info(f"ℹ️ A aba '{worksheet_name}' está vazia ou aguardando primeiro preenchimento. Você pode adicionar novas linhas abaixo.")
        if worksheet_name == "Despesas":
            df_raw = pd.DataFrame(columns=[
                "Nome", "Valor", "Categoria", "Conta debitada",
                "Fixo vs. Variável", "Essencial vs. Não Essencial",
                "Gasto em", "Dias até", "Tipo de Cobrança"
            ])
        elif worksheet_name == "Receitas":
            df_raw = pd.DataFrame(columns=[
                "Nome", "Valor", "Categoria", "Conta creditada", "Recebido em", "Dias até"
            ])
        elif worksheet_name == "Ordens":
            df_raw = pd.DataFrame(columns=[
                "data envio", "Compra/Venda", "Papel", "Qtd Executada",
                "Preço médio", "Total líquido", "Moeda", "Tipo", "Total",
                "Corretagem", "Preço médio + corretagem", "Cód. Cliente",
                "Setor Econômico", "Indexador", "Taxa Indexador"
            ])

    # Converte tipos numéricos para float para permitir edição nativa
    df_to_edit = df_raw.copy()
    df_to_edit.index = list(range(len(df_to_edit)))
    for col in df_to_edit.columns:
        c_low = col.lower()
        if any(term in c_low for term in ["valor", "total", "preço", "preco", "corretagem", "qtd", "taxa"]):
            df_to_edit[col] = df_to_edit[col].apply(clean_currency)

    # 5. Aplicação dos Filtros da Barra Lateral
    mask = pd.Series(True, index=df_to_edit.index)

    # Filtro de Busca Textual
    search_term = st.session_state.get("editor_filter_search", "").strip().lower()
    if search_term:
        searchable_cols = [c for c in ["Nome", "Papel", "Categoria", "Conta debitada", "Conta creditada", "Tipo"] if c in df_to_edit.columns]
        if searchable_cols:
            search_mask = pd.Series(False, index=df_to_edit.index)
            for c in searchable_cols:
                search_mask |= df_to_edit[c].astype(str).str.lower().str.contains(search_term, na=False)
            mask &= search_mask

    # Filtro de Categorias
    selected_cats = st.session_state.get("editor_filter_categories", [])
    if selected_cats and "Categoria" in df_to_edit.columns:
        mask &= df_to_edit["Categoria"].astype(str).str.strip().isin(selected_cats)

    # Filtro de Contas (Débito / Crédito)
    selected_accs = st.session_state.get("editor_filter_accounts", [])
    if selected_accs:
        acc_col = "Conta debitada" if "Conta debitada" in df_to_edit.columns else ("Conta creditada" if "Conta creditada" in df_to_edit.columns else None)
        if acc_col:
            mask &= df_to_edit[acc_col].astype(str).str.strip().isin(selected_accs)

    # Filtro de Mês/Ano (Competência)
    selected_month = st.session_state.get("editor_filter_month", "Todos")
    date_col = next((c for c in ["Gasto em", "Recebido em", "data envio", "Data"] if c in df_to_edit.columns), None)
    if selected_month != "Todos" and date_col:
        dt_series = pd.to_datetime(df_to_edit[date_col], dayfirst=True, errors="coerce")
        mask &= (dt_series.dt.strftime("%m/%Y") == selected_month)

    # Filtro de Status (Dias até)
    selected_status = st.session_state.get("editor_filter_status", "Todos")
    if selected_status != "Todos" and "Dias até" in df_to_edit.columns:
        def categorize_status(val):
            val_str = str(val).strip().lower()
            if "creditado" in val_str or "debitado" in val_str or "já" in val_str:
                return "creditado_debitado"
            try:
                num = int(float(val_str))
                if num > 0:
                    return "a_vencer"
                elif num == 0:
                    return "hoje"
                else:
                    return "vencido"
            except Exception:
                return "outro"

        status_series = df_to_edit["Dias até"].apply(categorize_status)
        if selected_status == "Já creditado / Já debitado":
            mask &= (status_series == "creditado_debitado")
        elif selected_status == "A vencer (Futuro)":
            mask &= (status_series == "a_vencer")
        elif selected_status == "Hoje":
            mask &= (status_series == "hoje")
        elif selected_status == "Vencido / Atrasado":
            mask &= (status_series == "vencido")

    df_filtered = df_to_edit[mask].copy()

    # 6. Métricas Resumo da Planilha (Refletindo filtros ativos)
    mcol1, mcol2, mcol3, mcol4 = st.columns(4)
    total_linhas_total = len(df_to_edit)
    total_linhas_filtradas = len(df_filtered)
    
    with mcol1:
        if total_linhas_filtradas == total_linhas_total:
            st.metric("📋 Total de Registros", f"{total_linhas_total} linhas")
        else:
            st.metric("📋 Registros Filtrados", f"{total_linhas_filtradas} de {total_linhas_total} linhas")

    with mcol2:
        val_col = "Valor" if "Valor" in df_filtered.columns else ("Total líquido" if "Total líquido" in df_filtered.columns else None)
        if val_col:
            total_financeiro = df_filtered[val_col].sum()
            st.metric("💰 Volume Financeiro", format_number(total_financeiro, is_currency=True, currency="BRL"))
        else:
            st.metric("💰 Volume Financeiro", "N/D")

    with mcol3:
        if "Categoria" in df_filtered.columns:
            st.metric("🏷️ Categorias Visíveis", f"{df_filtered['Categoria'].nunique()}")
        elif "Papel" in df_filtered.columns:
            st.metric("📈 Ativos Visíveis", f"{df_filtered['Papel'].nunique()}")
        else:
            st.metric("📑 Colunas", f"{len(df_filtered.columns)}")

    with mcol4:
        if date_col and not df_filtered.empty:
            dates = pd.to_datetime(df_filtered[date_col], dayfirst=True, errors="coerce").dropna()
            if not dates.empty:
                st.metric("📅 Intervalo", f"{dates.min().strftime('%d/%m/%y')} - {dates.max().strftime('%d/%m/%y')}")
            else:
                st.metric("📅 Intervalo", "Variado")
        else:
            st.metric("📅 Período", f"{active_sheet_meta.get('year', 'Geral')}")

    # Badge informativo de filtros ativos
    active_filters_desc = []
    if search_term:
        active_filters_desc.append(f"Busca: '{search_term}'")
    if selected_cats:
        active_filters_desc.append(f"Categorias ({len(selected_cats)})")
    if selected_accs:
        active_filters_desc.append(f"Contas ({len(selected_accs)})")
    if selected_month != "Todos":
        active_filters_desc.append(f"Mês: {selected_month}")
    if selected_status != "Todos":
        active_filters_desc.append(f"Status: {selected_status}")

    if active_filters_desc:
        st.info(f"🔍 **Filtros ativos:** {' • '.join(active_filters_desc)} — Exibindo **{total_linhas_filtradas}** de **{total_linhas_total}** registros.")

    st.markdown("<br>", unsafe_allow_html=True)

    # 7. Configuração de Colunas Customizadas para o Data Editor
    column_config = {}

    if worksheet_name == "Despesas":
        column_config = {
            "Nome": st.column_config.TextColumn("Nome / Descrição", help="Descrição do gasto", required=True, width="medium"),
            "Valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f", min_value=0.0, step=0.01, required=True, width="small"),
            "Categoria": st.column_config.SelectboxColumn("Categoria", options=CATEGORIAS_DESPESAS, required=True, width="medium"),
            "Conta debitada": st.column_config.SelectboxColumn("Conta debitada", options=CONTAS_DEBITADAS_PADRAO, width="medium"),
            "Fixo vs. Variável": st.column_config.SelectboxColumn("Fixo vs. Variável", options=FIXO_VARIAVEL_OPCOES, width="small"),
            "Essencial vs. Não Essencial": st.column_config.SelectboxColumn("Essencial vs. Não Essencial", options=ESSENCIAL_OPCOES, width="medium"),
            "Gasto em": st.column_config.TextColumn("Gasto em (DD/MM/AAAA)", help="Data no formato DD/MM/AAAA", width="small"),
            "Dias até": st.column_config.TextColumn("Dias até", width="small"),
            "Tipo de Cobrança": st.column_config.TextColumn("Tipo de Cobrança", width="small"),
        }
    elif worksheet_name == "Receitas":
        column_config = {
            "Nome": st.column_config.TextColumn("Nome / Descrição", help="Descrição da receita ou dividendo", required=True, width="medium"),
            "Valor": st.column_config.NumberColumn("Valor (R$)", format="R$ %.2f", min_value=0.0, step=0.01, required=True, width="small"),
            "Categoria": st.column_config.SelectboxColumn("Categoria", options=CATEGORIAS_RECEITAS, required=True, width="medium"),
            "Conta creditada": st.column_config.SelectboxColumn("Conta creditada", options=CONTAS_CREDITADAS_PADRAO, width="medium"),
            "Recebido em": st.column_config.TextColumn("Recebido em (DD/MM/AAAA)", help="Data no formato DD/MM/AAAA", width="small"),
            "Dias até": st.column_config.TextColumn("Dias até", width="small"),
        }
    elif worksheet_name == "Ordens":
        column_config = {
            "data envio": st.column_config.TextColumn("Data de Envio", width="small"),
            "Compra/Venda": st.column_config.SelectboxColumn("Operação", options=["COMPRA", "VENDA", "DESDOBRAMENTO", "BONIFICACAO", "AMORTIZACAO"], width="small"),
            "Papel": st.column_config.TextColumn("Papel / Ticker", width="small"),
            "Qtd Executada": st.column_config.NumberColumn("Qtd Executada", format="%.4f", step=1.0, width="small"),
            "Preço médio": st.column_config.NumberColumn("Preço Médio", format="R$ %.4f", step=0.01, width="small"),
            "Total líquido": st.column_config.NumberColumn("Total Líquido", format="R$ %.2f", step=0.01, width="small"),
            "Moeda": st.column_config.SelectboxColumn("Moeda", options=["BRL", "USD"], width="small"),
            "Tipo": st.column_config.TextColumn("Tipo de Ativo", width="small"),
            "Total": st.column_config.NumberColumn("Total", format="R$ %.2f", width="small"),
            "Corretagem": st.column_config.NumberColumn("Corretagem", format="R$ %.2f", width="small"),
        }

    # 7. Aplicação da Ordenação Inteligente
    sort_column = st.session_state.get("editor_sort_column")
    ascending = st.session_state.get("editor_sort_ascending", False)

    if sort_column and sort_column in df_filtered.columns and not df_filtered.empty:
        col_lower = sort_column.lower()
        if any(d_term in col_lower for d_term in ["data", "gasto em", "recebido em"]):
            temp_dt = pd.to_datetime(df_filtered[sort_column], dayfirst=True, errors="coerce")
            df_filtered = df_filtered.assign(_sort_key=temp_dt).sort_values(by="_sort_key", ascending=ascending, na_position="last").drop(columns=["_sort_key"])
        elif pd.api.types.is_numeric_dtype(df_filtered[sort_column]):
            df_filtered = df_filtered.sort_values(by=sort_column, ascending=ascending, na_position="last")
        else:
            temp_str = df_filtered[sort_column].astype(str).str.lower()
            df_filtered = df_filtered.assign(_sort_key=temp_str).sort_values(by="_sort_key", ascending=ascending, na_position="last").drop(columns=["_sort_key"])

    # 8. Barra de Controle e Ordenação Rápida
    col_t_title, col_t_sort, col_t_dir = st.columns([5.5, 4, 2.5], vertical_alignment="center")
    with col_t_title:
        st.markdown(f"#### ✏️ **{active_sheet_meta['title']} ➔ `{worksheet_name}`**")
    with col_t_sort:
        colunas_disp = [c for c in df_filtered.columns if c not in ["_orig_idx"]] if not df_filtered.empty else []
        if colunas_disp:
            cur_s_col = st.session_state.get("editor_sort_column", colunas_disp[0])
            if cur_s_col not in colunas_disp:
                cur_s_col = colunas_disp[0]
            
            def on_quick_sort_change():
                st.session_state.editor_sort_column = st.session_state["editor_quick_sort_col"]
                
            st.selectbox(
                "↕️ Ordenar por:",
                options=colunas_disp,
                index=colunas_disp.index(cur_s_col),
                key="editor_quick_sort_col",
                on_change=on_quick_sort_change,
                label_visibility="collapsed"
            )
    with col_t_dir:
        cur_asc = st.session_state.get("editor_sort_ascending", False)
        dir_icon = "🔼 Crescente (ASC)" if cur_asc else "🔽 Decrescente (DESC)"
        if st.button(f"{dir_icon}", key="editor_btn_toggle_dir", use_container_width=True, help="Alternar ordenação entre Crescente (A-Z / Menor / Mais antigo) e Decrescente (Z-A / Maior / Mais recente)"):
            st.session_state.editor_sort_ascending = not cur_asc
            st.session_state.editor_sort_direction = "Crescente (A-Z / Mais antigo / Menor)" if not cur_asc else "Decrescente (Z-A / Mais recente / Maior)"
            st.rerun()

    st.caption("💡 Dica: Use os controles de ordenação acima ou no menu lateral para ordenar qualquer coluna. Clique duas vezes em qualquer célula para editar.")

    grid_key = f"editor_grid_{active_sheet_meta['id']}_{worksheet_name}"
    edited_df = st.data_editor(
        df_filtered,
        column_config=column_config,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key=grid_key
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # 9. Painel de Ações de Salvamento e Sincronização
    btn_col1, btn_col2, btn_spacer = st.columns([3.8, 2.2, 6])

    with btn_col1:
        if st.button("💾 Salvar Alterações na Planilha e no SQLite", type="primary", use_container_width=True):
            with st.spinner(f"Gravando alterações no Google Sheets ({active_sheet_meta['title']}) e sincronizando SQLite local..."):
                try:
                    logger.info(f"Editor de Planilhas: Preparando gravação de dados para a planilha {spreadsheet_id} (Aba: {worksheet_name})...")
                    
                    # Reconstrói o DataFrame completo mesclando as edições no subconjunto filtrado
                    df_to_save = df_to_edit.copy()
                    
                    # 1. Atualiza linhas existentes editadas
                    existing_indices = [idx for idx in edited_df.index if idx in df_to_save.index]
                    if existing_indices:
                        df_to_save.loc[existing_indices, :] = edited_df.loc[existing_indices, :]
                        
                    # 2. Adiciona novas linhas inseridas pelo usuário
                    new_indices = [idx for idx in edited_df.index if idx not in df_to_save.index]
                    if new_indices:
                        df_new_rows = edited_df.loc[new_indices, :]
                        df_to_save = pd.concat([df_to_save, df_new_rows], ignore_index=True)
                        
                    # 3. Trata linhas deletadas dentro do subconjunto filtrado
                    deleted_indices = [idx for idx in df_filtered.index if idx not in edited_df.index and idx in df_to_save.index]
                    if deleted_indices:
                        df_to_save = df_to_save.drop(index=deleted_indices)
                    
                    # 4. Grava no Google Sheets
                    update_worksheet_from_dataframe(spreadsheet_id, worksheet_name, df_to_save)
                    
                    # 5. Limpa cache e sincroniza SQLite local com paridade total
                    st.cache_data.clear()
                    st.cache_resource.clear()
                    sync_google_sheets_to_sqlite()
                    
                    now_str = datetime.now().strftime("%H:%M:%S")
                    success_msg = f"🎉 **Sucesso!** Planilha '{active_sheet_meta['title']}' (Aba '{worksheet_name}') e banco SQLite atualizados com êxito às **{now_str}** ({len(df_to_save)} registros totais)!"
                    st.session_state["editor_flash_message"] = success_msg
                    logger.info(f"Editor de Planilhas: Alterações salvas com sucesso em '{active_sheet_meta['title']}' - '{worksheet_name}' ({len(df_to_save)} registros).")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Erro ao salvar alterações: {e}")
                    logger.error(f"Erro ao salvar alterações no Google Sheets: {e}", exc_info=True)

    with btn_col2:
        if st.button("🔄 Recarregar Dados", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

