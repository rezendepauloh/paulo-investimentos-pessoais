import os
import google.generativeai as genai
import pandas as pd
import streamlit as st

def initialize_gemini():
    """
    Inicializa a API do Gemini de forma segura usando a chave de API fornecida no ambiente.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return False
        
    try:
        genai.configure(api_key=api_key)
        return True
    except Exception as e:
        st.error(f"Erro ao inicializar o Google Gemini: {e}")
        return False

def generate_allocation_tips(df_holdings, df_receitas, df_despesas, df_dividendos):
    """
    Cria uma análise automatizada e gera dicas personalizadas de alocação de carteira
    utilizando a inteligência artificial do Google Gemini.
    """
    if not initialize_gemini():
        return (
            "⚠️ **Chave do Gemini API não configurada ou inválida!**\n\n"
            "Para ativar as dicas de Inteligência Artificial baseadas em seus investimentos:\n"
            "1. Crie uma chave de API gratuita no [Google AI Studio](https://aistudio.google.com/).\n"
            "2. Insira a chave no campo do painel lateral ou configure a variável `GEMINI_API_KEY` no seu arquivo `.env` local."
        )
        
    # Prepara um resumo financeiro legível em texto para injetar no prompt
    
    # 1. Dados da Carteira
    portfolio_summary = ""
    total_market_val = 0.0
    total_invested = 0.0
    
    if not df_holdings.empty:
        total_market_val = df_holdings["valor_atual"].sum()
        total_invested = df_holdings["total_investido"].sum()
        
        # Agrupa por tipo
        by_type = df_holdings.groupby("tipo")["valor_atual"].sum()
        portfolio_summary += "### Distribuição da Carteira por Classe de Ativos:\n"
        for t, val in by_type.items():
            pct = (val / total_market_val) * 100.0
            portfolio_summary += f"- {t}: R$ {val:,.2f} ({pct:.2f}%)\n"
            
        portfolio_summary += "\n### Ativos Individuais na Carteira:\n"
        for _, row in df_holdings.iterrows():
            pct = (row['valor_atual'] / total_market_val) * 100.0
            portfolio_summary += (
                f"- Ativo: {row['ticker']} | Tipo: {row['tipo']} | "
                f"Qtd: {row['quantidade']} | Custo Médio: R$ {row['preco_medio']:,.2f} | "
                f"Preço Atual: R$ {row['preco_atual']:,.2f} | Valor Atual: R$ {row['valor_atual']:,.2f} ({pct:.2f}%) | "
                f"Rentabilidade: {row['retorno_percentual']:.2f}%\n"
            )
    else:
        portfolio_summary += "A carteira atual está sem ativos ativos no momento.\n"
        
    # 2. Dados de Orçamento
    budget_summary = "### Resumo Orçamentário Recente:\n"
    
    total_receitas = df_receitas["Valor"].sum() if not df_receitas.empty else 0.0
    total_despesas = df_despesas["Valor"].sum() if not df_despesas.empty else 0.0
    total_dividendos = df_dividendos["Valor"].sum() if not df_dividendos.empty else 0.0
    
    saving_rate = total_receitas - total_despesas
    saving_pct = (saving_rate / total_receitas * 100.0) if total_receitas > 0 else 0.0
    
    budget_summary += f"- Total de Receitas Ativas: R$ {total_receitas:,.2f}\n"
    budget_summary += f"- Total de Despesas/CUSTOS: R$ {total_despesas:,.2f}\n"
    budget_summary += f"- Dividendos Passivos Recebidos: R$ {total_dividendos:,.2f}\n"
    budget_summary += f"- Capacidade de Poupança (Receitas - Despesas): R$ {saving_rate:,.2f} ({saving_pct:.2f}% das receitas)\n"
    
    # Adiciona detalhes de dividendos recentes
    if not df_dividendos.empty:
        budget_summary += "\n### Dividendos Recebidos por Ativo:\n"
        divs_by_asset = df_dividendos.groupby("Ativo")["Valor"].sum()
        for asset, val in divs_by_asset.items():
            budget_summary += f"- {asset}: R$ {val:,.2f}\n"
            
    # Cria o prompt do analista financeiro
    prompt = f"""
Você é um consultor financeiro certificado (CNPI/CEA) e especialista em alocação de ativos e finanças pessoais de alto nível.
Sua tarefa é analisar os dados financeiros reais de um usuário, fornecer uma avaliação estruturada e dar recomendações inteligentes de onde alocar suas próximas economias.

Abaixo estão os dados reais do usuário obtidos de suas planilhas de controle pessoal:

---
DADOS DO USUÁRIO

## CARTEIRA DE INVESTIMENTOS ATUAL
- Patrimônio Total sob Custódia: R$ {total_market_val:,.2f}
- Capital Total Investido (Histórico): R$ {total_invested:,.2f}
- Lucro/Prejuízo Acumulado: R$ {total_market_val - total_invested:,.2f} ({( (total_market_val / total_invested - 1) * 100 if total_invested > 0 else 0):.2f}%)

{portfolio_summary}

{budget_summary}
---

Instruções para a geração de insights:
1. **Tom Profissional e Humilde:** Seja muito didático, use termos técnicos do mercado financeiro brasileiro de forma clara e objetiva (como Diversificação, Rebalanceamento, Renda Fixa Pós/Pré-fixada, FIIs, etc.).
2. **Diagnóstico da Carteira:** Identifique se há sobre-exposição a algum ativo ou classe, avalie o nível de diversificação e o perfil sugerido (conservador, moderado, arrojado) com base na alocação observada.
3. **Análise do Fluxo de Caixa:** Avalie a saúde financeira do orçamento (capacidade de poupança/taxa de poupança do usuário) e o papel dos dividendos passivos na aceleração do efeito bola de neve.
4. **Dicas Práticas de Alocação:** Sugira como alocar novos aportes (o dinheiro economizado mensalmente) de forma inteligente para reequilibrar a carteira em direção a uma alocação saudável. Use teorias renomadas de alocação de ativos (como a Teoria Moderna de Portfólios de Markowitz) de forma simplificada.
5. **Aviso Legal:** Insira de forma sutil no final um aviso legal lembrando que a IA fornece insights de apoio educacional e não representa recomendação formal de compra/venda de ativos.

Escreva a resposta de forma estruturada, com títulos elegantes em Markdown e listas pontuadas.
"""

    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"⚠️ **Erro ao gerar as recomendações da IA:** {e}\n\nPor favor, verifique se a sua chave de API do Gemini está ativa e configurada corretamente no arquivo `.env`."
