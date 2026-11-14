# Guia de Conciliação e Ingestão de Gastos

> **Objetivo:** Instruções operacionais para importar extratos, conciliar faturas de cartão e processar comprovantes na interface do Streamlit.

---

## 1. Acesso à Aba de Importação

Acesse diretamente pelo navegador através da URL:
```text
http://localhost:8502/?tab=importar_gastos
```

A aba é dividida em três submenus:
1. **📸 Comprovantes (OCR com Gemini Vision):** Upload de capturas de tela e fotos de comprovantes Pix, boletos ou recibos. O Gemini Vision extrai data, valor, favorecido e sugere categoria.
2. **📁 Arquivos de Extrato (.OFX / .CSV):** Upload de arquivos bancários estruturados.
3. **🌐 Open Finance (Pluggy):** Sincronização direta de transações bancárias.

---

## 2. Fluxo de Importação por Extrato Bancário

1. Selecione a **Instituição Financeira** (ex: *Sicredi, Inter, C6, Nubank, 99 Pay, Cartões de Loja*).
2. Faça o upload do arquivo `.ofx` ou `.csv`.
3. O parser dedicado processa os sinais e nomes das colunas, exibindo a tabela na grade interativa (`st.data_editor`).
4. **Verificação de Duplicatas:** Transações que já constam no banco de dados local ou na planilha são sinalizadas automaticamente para evitar lançamentos duplicados.
5. Revise categorias, contas e clique em **Confirmar e Gravar Lançamentos**.

