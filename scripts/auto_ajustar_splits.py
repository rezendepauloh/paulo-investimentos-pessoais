import os
import re
import pandas as pd
import datetime
from dotenv import load_dotenv

# Carrega configurações
load_dotenv(override=True)

from data_loader import clean_currency, clean_float, clean_int
from analytics import normalize_ticker, is_valid_yfinance_ticker
import yfinance as yf

print("=== INICIANDO AJUSTE AUTOMÁTICO DE SPLITS E BONIFICAÇÕES ===")

csv_path = "Planilha de Ordens - Ordens.csv"
output_path = "Planilha de Ordens - Ajustada.csv"

if not os.path.exists(csv_path):
    print(f"Erro: O arquivo '{csv_path}' não foi encontrado na raiz do projeto!")
    exit()

# 1. Carrega o CSV original do usuário
try:
    df_raw = pd.read_csv(csv_path)
    print(f"Arquivo original carregado com sucesso! Total de linhas: {len(df_raw)}")
except Exception as e:
    print(f"Erro ao ler o arquivo CSV: {e}")
    exit()

# Normaliza os cabeçalhos das colunas
df_raw.columns = [col.strip() for col in df_raw.columns]

# Garante conversão de datas para o cálculo interno
df_raw["Data_Calculo"] = pd.to_datetime(df_raw["Data envio"], dayfirst=True, errors="coerce")

# Remove linhas sem data válida
df_raw = df_raw.dropna(subset=["Data_Calculo"])

# 2. Separa ordens normais (Compras, Vendas, Subscrições) e remove desdobramentos/bonificações antigos imprecisos
df_splits_antigos = df_raw[df_raw["Compra/Venda"].str.upper().str.contains("DESDOBRAMENTO|BONIFICACAO|BONIFICAÇÃO")]
print(f"Removendo {len(df_splits_antigos)} lançamentos antigos de desdobramentos/bonificações para recálculo limpo.")

df_normal = df_raw[~df_raw["Compra/Venda"].str.upper().str.contains("DESDOBRAMENTO|BONIFICACAO|BONIFICAÇÃO")].copy()

# Converte colunas numéricas de forma limpa para cálculo
df_normal["Qtd_Calc"] = df_normal["Qtd Executada"].apply(clean_float)
df_normal["Total_Calc"] = df_normal["Total líquido"].apply(clean_currency)

# Identifica os ativos da carteira que são cotados no yfinance
ativos = df_normal["Papel"].dropna().unique()
print(f"Ativos únicos identificados na carteira: {list(ativos)}")

novas_linhas_splits = []

# 3. Para cada ativo, consulta a história oficial de splits e bonificações no Yahoo Finance
for ativo in ativos:
    t = str(ativo).strip().upper()
    if not is_valid_yfinance_ticker(t):
        continue
        
    norm_t = normalize_ticker(t)
    print(f"\nConsultando splits oficiais para {t} ({norm_t})...")
    
    # Menor data de compra deste ativo
    df_ativo = df_normal[df_normal["Papel"] == t].sort_values("Data_Calculo")
    min_date_ativo = df_ativo["Data_Calculo"].min()
    
    try:
        ticker_obj = yf.Ticker(norm_t)
        splits = ticker_obj.splits
        
        # Filtra apenas splits ocorridos após o primeiro aporte do usuário até hoje
        if not splits.empty:
            splits_filtrados = splits[splits.index.date >= min_date_ativo.date()]
            if not splits_filtrados.empty:
                print(f"Detectados {len(splits_filtrados)} splits/bonificações oficiais desde {min_date_ativo.date()}:")
                for date_split, fator in splits_filtrados.items():
                    # Converte data para comparação
                    split_date_only = date_split.date()
                    print(f" - Data: {split_date_only}, Fator: {fator}")
                    
                    # Filtra compras e vendas ocorridas ANTES do split
                    df_antes = df_normal[
                        (df_normal["Papel"] == t) & 
                        (df_normal["Data_Calculo"].dt.date < split_date_only)
                    ]
                    
                    # Calcula quantidade acumulada na véspera do split
                    qty_acumulada = 0.0
                    for _, row in df_antes.iterrows():
                        op = str(row["Compra/Venda"]).strip().upper()
                        q_exec = float(row["Qtd_Calc"])
                        if any(x in op for x in ["COMPRA", "C", "SUBSCRIÇÃO", "SUBSCRICAO"]):
                            qty_acumulada += q_exec
                        elif any(x in op for x in ["VENDA", "V"]):
                            qty_acumulada = max(0.0, qty_acumulada - q_exec)
                            
                    if qty_acumulada > 0.0001:
                        qty_adicional = qty_acumulada * (fator - 1.0)
                        if qty_adicional > 0.0001:
                            # Classifica como Bonificação ou Desdobramento baseado no fator
                            tipo_evento = "Desdobramento" if fator >= 1.5 else "Bonificação"
                            moeda_ativo = df_ativo.iloc[0]["Moeda"]
                            tipo_ativo = df_ativo.iloc[0]["Tipo"]
                            cod_cliente = df_ativo.iloc[0]["Cód. Cliente"]
                            
                            # Formata valores monetários zerados no padrão original da planilha
                            zero_monetario = "R$ 0,00" if moeda_ativo == "BRL" else "US$ 0,00"
                            
                            # Cria a nova ordem corporativa
                            nova_ordem = {
                                "Compra/Venda": tipo_evento,
                                "Tipo": tipo_ativo,
                                "Moeda": moeda_ativo,
                                "Papel": t,
                                "Qtd Executada": round(qty_adicional, 6),
                                "Preço médio": zero_monetario,
                                "Total": zero_monetario,
                                "Data envio": (datetime.datetime.combine(split_date_only, datetime.time(10, 0))).strftime("%d/%m/%Y %H:%M:%S"),
                                "Cód. Cliente": "B3 (Ajuste)",
                                "Corretagem": zero_monetario,
                                "Preço médio + corretagem": zero_monetario,
                                "Total líquido": zero_monetario,
                                "Data_Calculo": pd.Timestamp(split_date_only)
                            }
                            novas_linhas_splits.append(nova_ordem)
                            print(f"   => Adicionado: {tipo_evento} de +{qty_adicional:.4f} cotas de {t} em {split_date_only}")
            else:
                print(" Nenhum split oficial encontrado após a data da sua primeira compra.")
        else:
            print(" Nenhum split registrado para este ativo.")
    except Exception as e:
        print(f" Erro ao consultar splits de {norm_t}: {e}")

# 4. Junta tudo e gera o CSV ajustado final
if novas_linhas_splits:
    df_splits_novos = pd.DataFrame(novas_linhas_splits)
    df_final = pd.concat([df_normal, df_splits_novos], ignore_index=True)
    print(f"\nAdicionados {len(novas_linhas_splits)} desdobramentos/bonificações oficiais recalculados!")
else:
    df_final = df_normal
    print("\nNenhum novo desdobramento ou bonificação precisou ser adicionado.")

# Ordena cronologicamente por Data de Envio
df_final = df_final.sort_values("Data_Calculo").copy()

# Remove a coluna temporária de cálculo
df_final = df_final.drop(columns=["Data_Calculo", "Qtd_Calc", "Total_Calc"], errors="ignore")

# Função para formatar a quantidade executada com vírgula decimal (padrão PT-BR)
def format_float_br(val):
    if pd.isna(val) or val is None:
        return ""
    try:
        val_float = float(val)
        if val_float % 1 == 0:
            return str(int(val_float))
        # Formata com até 6 casas decimais, remove zeros à direita desnecessários
        formatted = f"{val_float:.6f}".rstrip('0').rstrip('.')
        return formatted.replace(".", ",")
    except Exception:
        return str(val)

# Formata as quantidades no padrão de localidade brasileiro
df_final["Qtd Executada"] = df_final["Qtd Executada"].apply(format_float_br)

# Salva o arquivo CSV final formatado perfeitamente
try:
    df_final.to_csv(output_path, index=False)
    print(f"\nSucesso absoluto! O arquivo ajustado foi salvo em: '{output_path}'")
    print("Agora você pode abrir esse arquivo e copiar as novas linhas para sua planilha do Google Sheets!")
except Exception as e:
    print(f"Erro ao salvar o arquivo final CSV: {e}")

print("=== CONCLUÍDO COM SUCESSO ===")
