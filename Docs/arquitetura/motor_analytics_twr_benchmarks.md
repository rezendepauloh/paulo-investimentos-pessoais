# Motor de Analytics: TWR, Benchmarks e Custódia

> **Objetivo:** Documentar as fórmulas, bibliotecas financeiras e metodologias de cálculo de desempenho patrimonial aplicadas em `src/services/analytics.py`.

---

## 1. Time-Weighted Rate of Return (TWR)

Para avaliar a real performance da carteira sem distorções causadas por grandes aportes ou retiradas de capital, o sistema emprega a metodologia **TWR (Cálculo por Cotas)**:

$$R_{TWR} = \prod_{t=1}^{n} (1 + R_t) - 1$$

Onde:
- $R_t = \frac{V_t - (V_{t-1} + C_t)}{V_{t-1} + C_t}$
- $V_t$: Valor da carteira no fechamento do dia $t$.
- $C_t$: Fluxo de caixa líquido (aportes menos retiradas) no dia $t$.

Isso garante que a rentabilidade reflita estritamente as decisões de alocação de ativos e variações de mercado.

---

## 2. Ajuste Oficial de Splits e Grupamentos

O motor reconcilia desdobramentos (*splits*) e grupamentos de ações e fundos imobiliários:
- Cotações históricas são ajustadas via `yfinance`.
- O script auxiliar `scripts/auto_ajustar_splits.py` valida e reconcilia o volume de cotas em carteira para evitar distorções de preço médio e rentabilidade acumulada.

---

## 3. Integração com Benchmarks de Mercado

O painel compara a curva da carteira contra 4 referências oficiais:
1. **CDI Acumulado:** Coletado via API do Banco Central do Brasil (SGS - Sistema Gerenciador de Séries Temporais).
2. **IPCA & IPCA + 6% a.a.:** Inflação oficial para aferição de ganho real de capital.
3. **Ibovespa (`^BVSP`):** Principal índice acionário brasileiro.
4. **S&P 500 (`^GSPC`):** Principal benchmark do mercado global e ações americanas.

