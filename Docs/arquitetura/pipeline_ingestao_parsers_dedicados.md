# Pipeline de Ingestão e Parsers Dedicados por Instituição

> **Objetivo:** Documentar a arquitetura dos parsers bancários (`src/services/parsers/`), ingestão multimodal via Gemini Vision e prevenção de duplicidades.

---

## 1. Padrão Strategy / Dispatcher por Banco

Para tratar as diferentes convenções de sinais (+/-), nomenclaturas de colunas e tags em arquivos bancários, a ingestão adota o padrão Strategy:

```mermaid
flowchart TD
    Arquivo["Upload de Arquivo (.OFX / .CSV / Imagem)"] --> Dispatcher["Dispatcher Central (parsers/__init__.py)"]
    Dispatcher -->|Sicredi| P_Sicredi["sicredi_parser.py"]
    Dispatcher -->|Inter| P_Inter["inter_parser.py"]
    Dispatcher -->|C6 Bank| P_C6["c6_parser.py"]
    Dispatcher -->|Nubank| P_Nubank["nubank_parser.py"]
    Dispatcher -->|99Pay| P_99["pay99_parser.py"]
    Dispatcher -->|Mercado Pago| P_MP["mercadopago_parser.py"]
    Dispatcher -->|XP / B3| P_B3["b3_parser.py / xp_parser.py"]
    Dispatcher -->|Cartões Loja (Vuon/Renner)| P_Cards["store_cards_parser.py / vuon_parser.py"]
    Dispatcher -->|Comprovante Imagem| OCR["Gemini Vision Multimodal OCR"]
    Dispatcher -->|Desconhecido| Generic["generic_parser.py (Heurística)"]

    P_Sicredi & P_Inter & P_C6 & P_Nubank & P_99 & P_MP & P_B3 & P_Cards & OCR & Generic --> Normalizador["DataFrame Padronizado<br/>(Data, Descrição, Valor, Categoria, Conta, Hash)"]
```

---

## 2. Prevenção de Duplicidades (Deduplicação SHA-256)

Para evitar lançamentos repetidos quando o usuário importa extratos com datas sobrepostas:
- O módulo `src/services/deduplication.py` calcula uma assinatura hash baseada em `(data, valor_normalizado, descricao_sanitizada, conta_origem)`.
- O editor interativo (`st.data_editor`) destaca visualmente transações já existentes no banco SQLite/Google Sheets, permitindo ao usuário desmarcar ou confirmar a inclusão.

