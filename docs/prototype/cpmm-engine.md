# Protótipo do Motor Matemático de Precificação do AMM de Produto Constante (CPMM)

- **Issue de Origem:** [#4: Prototipar motor matemático de precificação do AMM de Produto Constante (CPMM)](https://github.com/ratopythonista/cota-certa/issues/4)
- **Branch do Protótipo:** `prototype/cpmm-engine`
- **Status:** Validado e Testado
- **Data:** 2026-09-05
- **Autor/Decisor:** @ratopythonista

---

## 1. Resumo Executivo & Resposta à Pergunta Central

A pergunta central formulada na Issue #4 é:
> *"Como implementar as fórmulas de compra, venda, probabilidade instantânea ($P_{yes} = \frac{y}{x+y}$) e slippage do AMM binário ($x \times y = k$) em um módulo puro Python com casos de teste cobrindo conservação de produto e liquidação final a R$ 1,00 / R$ 0,00?"*

### Resposta e Conclusões Principais:
1. **Mapeamento Canônico de Probabilidades:**  
   Em uma pool com reservas de cotas $x$ (Sim) e $y$ (Não) e produto constante $k = x \cdot y$:
   $$P_{sim} = \frac{y}{x + y}, \quad P_{nao} = \frac{x}{x + y}$$
   onde $P_{sim} + P_{nao} \equiv 1{,}00$ rigorosamente em qualquer instante.
2. **Modelo Arquitetural — Emissão de Conjuntos Completos (*Complete Set Minting*):**  
   Adotou-se o modelo padrão da indústria para mercados de predição binários (Gnosis CTF / Polymarket FPMM). A cada R$ 1,00 aportado pelo usuário, 1 par completo (1 Sim + 1 Não) é emitido contra o colateral em BRL mantido no cofre da plataforma.
3. **Mecânica Analítica Fechada de Venda ($O(1)$):**  
   Diferente de abordagens iterativas ou heurísticas, a extração de BRL através da venda de cotas recai em uma **equação quadrática analítica fechada**, executada em tempo estritamente constante $O(1)$.
4. **Solvência Contábil de 100% Garantida por Construção:**  
   A qualquer momento, o saldo de colateral em BRL no cofre é idêntico ao total de cotas em circulação ($Total_{sim} = Total_{nao} = Caixa_{brl}$). Na liquidação final pelo Oráculo, cada cota do desfecho vencedor é resgatada a **R$ 1,00**, as perdedoras a **R$ 0,00**, e o passivo total é liquidado sem resíduo ou risco de insolvência.
5. **Aritmética Financeira em `Decimal`:**  
   Para eliminar qualquer vazamento de centavos decorrente de imprecisão de ponto flutuante IEEE-754 e manter compatibilidade nativa de alta velocidade com o PostgreSQL (`NUMERIC(18, 4)` via SQLModel), o motor foi concebido em `decimal.Decimal` com precisão de 28 dígitos.

---

## 2. Formalização Matemática das Operações

### 2.1. Invariante da Pool
Sejam $x > 0$ a reserva de cotas Sim e $y > 0$ a reserva de cotas Não.  
A curva hiperbólica de produto constante exige:
$$k = x \cdot y$$

### 2.2. Compra de Cotas Sim com Aporte em Dinheiro ($\Delta b$ BRL)
Quando um usuário investe $\Delta b$ BRL para comprar Sim:
1. São emitidos $\Delta b$ pares (Sim e Não).
2. As $\Delta b$ cotas Não são adicionadas à pool:
   $$y' = y + \Delta b$$
3. Para conservar o produto $k$:
   $$x' = \frac{k}{y'} = \frac{k}{y + \Delta b}$$
4. A pool entrega ao comprador a diferença de cotas Sim:
   $$\Delta x_{pool} = x - x' = x - \frac{k}{y + \Delta b}$$
5. **Total de cotas Sim recebidas pelo usuário:**
   $$\text{Cotas}_{sim} = \Delta b + \Delta x_{pool} = \Delta b + x - \frac{k}{y + \Delta b}$$
6. **Preço médio de execução:**
   $$\bar{P}_{sim} = \frac{\Delta b}{\text{Cotas}_{sim}}$$
7. **Slippage relativo:**
   $$\text{Slippage} = \frac{\bar{P}_{sim} - P_{sim}^{antes}}{P_{sim}^{antes}}$$

*(A operação de compra de Não é perfeitamente simétrica invertendo os papéis de $x$ e $y$.)*

### 2.3. Venda Analítica de Cotas Sim ($S$ cotas por $\Delta b$ BRL)
Para resgatar Reais, o usuário entrega $S$ cotas Sim. O AMM desmembra essas cotas: entrega uma parte à pool em troca de cotas Não e funde as cotas Não obtidas com o restante das cotas Sim para resgatar $\Delta b$ Reais do cofre.

Equação da pool:
$$(x + S - \Delta b)(y - \Delta b) = k = x \cdot y$$

Expandindo a equação:
$$x y + S y - (x + y + S)\Delta b + \Delta b^2 = x y$$
$$\Delta b^2 - (x + y + S)\Delta b + S \cdot y = 0$$

Como o discriminante $\Delta = (x + y + S)^2 - 4 S y$ é estritamente positivo para todo $x, y, S > 0$, a **solução analítica exata** é:
$$\Delta b = \frac{(x + y + S) - \sqrt{(x + y + S)^2 - 4 \cdot S \cdot y}}{2}$$

Novas reservas:
$$x' = x + S - \Delta b, \quad y' = y - \Delta b, \quad x' \cdot y' \equiv k$$

---

## 3. Estrutura dos Artefatos do Protótipo

Os arquivos criados na branch `prototype/cpmm-engine` incluem:

1. **`prototype/cpmm.py`**:
   - Módulo puro em Python contendo as dataclasses `Pool`, `TradeResult` e `SettlementResult`.
   - Funções puras: `create_pool`, `instant_probabilities`, `buy_yes`, `buy_no`, `sell_yes`, `sell_no` e `settle_market`.
   - Suporte a `fee_rate: Decimal` configurável (padrão 0%).
2. **`tests/test_cpmm.py`**:
   - Suíte de 22 testes unitários em `pytest` cobrindo:
     - Conservação estrita de $k$ em ordens de diferentes magnitudes;
     - Simetria de ida e volta (comprar e vender a mesma quantidade recupera exatamente os fundos);
     - Progressão de slippage em função do tamanho da ordem;
     - Verificação de solvência do cofre após sequências de compras e vendas;
     - Liquidação final a R$ 1,00 / R$ 0,00 no desfecho Sim e Não;
     - Dedução e impacto de taxas de protocolo.
3. **`prototype/cpmm_demo.html`**:
   - Demonstrador interativo independente (HTML/CSS/JS puro, sem servidor ou dependências de CDN).
   - Painel de estado em tempo real com barra de probabilidade instantânea.
   - Controles livres (*free-play*) e 4 cenários guiados com passo a passo para validação comportamental.

---

## 4. Evidência de Execução dos Testes

Execução realizada via `uv run pytest tests/test_cpmm.py -v`:

```
============================= test session starts ==============================
platform darwin -- Python 3.12.4, pytest-9.1.1, pluggy-1.6.0
collected 22 items

tests/test_cpmm.py::TestPoolInitialization::test_initial_reserves_and_probability PASSED [  4%]
tests/test_cpmm.py::TestPoolInitialization::test_invalid_initial_liquidity PASSED [  9%]
tests/test_cpmm.py::TestProductConservation::test_buy_conserves_product_invariant[investment0] PASSED [ 13%]
tests/test_cpmm.py::TestProductConservation::test_buy_conserves_product_invariant[investment1] PASSED [ 18%]
tests/test_cpmm.py::TestProductConservation::test_buy_conserves_product_invariant[investment2] PASSED [ 22%]
tests/test_cpmm.py::TestProductConservation::test_buy_conserves_product_invariant[investment3] PASSED [ 27%]
tests/test_cpmm.py::TestProductConservation::test_buy_conserves_product_invariant[investment4] PASSED [ 31%]
tests/test_cpmm.py::TestProductConservation::test_sell_conserves_product_invariant[shares0] PASSED [ 36%]
tests/test_cpmm.py::TestProductConservation::test_sell_conserves_product_invariant[shares1] PASSED [ 40%]
tests/test_cpmm.py::TestProductConservation::test_sell_conserves_product_invariant[shares2] PASSED [ 45%]
tests/test_cpmm.py::TestProductConservation::test_sell_conserves_product_invariant[shares3] PASSED [ 50%]
tests/test_cpmm.py::TestSymmetryAndReversibility::test_round_trip_recovers_exact_capital_without_fees[investment0] PASSED [ 54%]
tests/test_cpmm.py::TestSymmetryAndReversibility::test_round_trip_recovers_exact_capital_without_fees[investment1] PASSED [ 59%]
tests/test_cpmm.py::TestSymmetryAndReversibility::test_round_trip_recovers_exact_capital_without_fees[investment2] PASSED [ 63%]
tests/test_cpmm.py::TestSymmetryAndReversibility::test_round_trip_recovers_exact_capital_without_fees[investment3] PASSED [ 68%]
tests/test_cpmm.py::TestSymmetryAndReversibility::test_round_trip_no_shares PASSED [ 72%]
tests/test_cpmm.py::TestPriceAndSlippageMechanics::test_buying_yes_increases_yes_price_and_decreases_no_price PASSED [ 77%]
tests/test_cpmm.py::TestPriceAndSlippageMechanics::test_larger_trades_experience_higher_slippage PASSED [ 81%]
tests/test_cpmm.py::TestSolvencyAndLiquidation::test_liquidation_yes_resolves_to_one_reais PASSED [ 86%]
tests/test_cpmm.py::TestSolvencyAndLiquidation::test_liquidation_no_resolves_to_zero_for_yes_holders PASSED [ 90%]
tests/test_cpmm.py::TestSolvencyAndLiquidation::test_sequential_trading_and_final_solvency PASSED [ 95%]
tests/test_cpmm.py::TestProtocolFee::test_fee_deduction_on_buy_and_sell PASSED [100%]

============================== 22 passed in 0.02s ==============================
```
