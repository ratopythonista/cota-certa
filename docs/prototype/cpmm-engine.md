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
collected 23 items

tests/test_cpmm.py::TestPoolInitialization::test_initial_reserves_and_probability PASSED [  4%]
tests/test_cpmm.py::TestPoolInitialization::test_invalid_initial_liquidity PASSED [  8%]
tests/test_cpmm.py::TestProductConservation::test_buy_conserves_product_invariant[investment0] PASSED [ 13%]
tests/test_cpmm.py::TestProductConservation::test_buy_conserves_product_invariant[investment1] PASSED [ 17%]
tests/test_cpmm.py::TestProductConservation::test_buy_conserves_product_invariant[investment2] PASSED [ 21%]
tests/test_cpmm.py::TestProductConservation::test_buy_conserves_product_invariant[investment3] PASSED [ 26%]
tests/test_cpmm.py::TestProductConservation::test_buy_conserves_product_invariant[investment4] PASSED [ 30%]
tests/test_cpmm.py::TestProductConservation::test_sell_conserves_product_invariant[shares0] PASSED [ 34%]
tests/test_cpmm.py::TestProductConservation::test_sell_conserves_product_invariant[shares1] PASSED [ 39%]
tests/test_cpmm.py::TestProductConservation::test_sell_conserves_product_invariant[shares2] PASSED [ 43%]
tests/test_cpmm.py::TestProductConservation::test_sell_conserves_product_invariant[shares3] PASSED [ 47%]
tests/test_cpmm.py::TestSymmetryAndReversibility::test_round_trip_recovers_exact_capital_without_fees[investment0] PASSED [ 52%]
tests/test_cpmm.py::TestSymmetryAndReversibility::test_round_trip_recovers_exact_capital_without_fees[investment1] PASSED [ 56%]
tests/test_cpmm.py::TestSymmetryAndReversibility::test_round_trip_recovers_exact_capital_without_fees[investment2] PASSED [ 60%]
tests/test_cpmm.py::TestSymmetryAndReversibility::test_round_trip_recovers_exact_capital_without_fees[investment3] PASSED [ 65%]
tests/test_cpmm.py::TestSymmetryAndReversibility::test_round_trip_no_shares PASSED [ 69%]
tests/test_cpmm.py::TestPriceAndSlippageMechanics::test_buying_yes_increases_yes_price_and_decreases_no_price PASSED [ 73%]
tests/test_cpmm.py::TestPriceAndSlippageMechanics::test_larger_trades_experience_higher_slippage PASSED [ 78%]
tests/test_cpmm.py::TestSolvencyAndLiquidation::test_liquidation_yes_resolves_to_one_reais PASSED [ 82%]
tests/test_cpmm.py::TestSolvencyAndLiquidation::test_liquidation_no_resolves_to_zero_for_yes_holders PASSED [ 86%]
tests/test_cpmm.py::TestSolvencyAndLiquidation::test_sequential_trading_and_final_solvency PASSED [ 91%]
tests/test_cpmm.py::TestSolvencyAndLiquidation::test_multi_user_lifecycle_with_partial_sell PASSED [ 95%]
tests/test_cpmm.py::TestProtocolFee::test_fee_deduction_on_buy_and_sell PASSED [100%]

============================== 23 passed in 0.05s ==============================
```

---

## 5. Memorial de Cálculo Analítico: Simulação Multiusuário Passo a Passo

Simulação formal com 3 usuários ativos (Alice, Bob, Charlie) e o Provedor de Liquidez (LP) auditando a evolução exata de reservas, preços e cofre:

### 5.1. Estado Inicial (T0)
- **LP Aporta:** R$ 1.000,00 inicial criando a pool a 50%/50%.
- **Reservas:** $x_0 = 1.000{,}00$ (Sim), $y_0 = 1.000{,}00$ (Não), $k = 1.000.000{,}00$.
- **Probabilidades:** $P_{sim} = 50{,}00\%$, $P_{nao} = 50{,}00\%$.
- **Colateral no Cofre:** R$ 1.000,00.

### 5.2. Passo a Passo das Operações
1. **Alice compra Sim com R$ 200,00 ($\Delta b = 200$):**
   - $y_1 = 1.000 + 200 = 1.200{,}00$
   - $x_1 = \frac{1.000.000}{1.200} = 833{,}3333$
   - Cotas entregues: $\Delta b + (x_0 - x_1) = 200 + (1.000 - 833{,}3333) = 366{,}6667$ cotas Sim.
   - Preço médio: $\frac{200}{366{,}6667} = \text{R\$ } 0{,}5455$ (Slippage: $+9{,}09\%$).
   - Novo preço instantâneo: $P_{sim}^{(1)} = \frac{1.200}{833{,}3333 + 1.200} = 59{,}02\%$.
   - Cofre: R$ 1.200,00.
2. **Bob compra Não com R$ 300,00 ($\Delta b = 300$):**
   - $x_2 = 833{,}3333 + 300 = 1.133{,}3333$
   - $y_2 = \frac{1.000.000}{1.133{,}3333} = 882{,}3529$
   - Cotas entregues: $300 + (1.200 - 882{,}3529) = 617{,}6471$ cotas Não.
   - Preço médio: $\frac{300}{617{,}6471} = \text{R\$ } 0{,}4857$ (Slippage: $+18{,}51\%$).
   - Novo preço instantâneo: $P_{nao}^{(2)} = 56{,}23\%$, $P_{sim}^{(2)} = 43{,}77\%$.
   - Cofre: R$ 1.500,00.
3. **Charlie compra Sim com R$ 100,00 ($\Delta b = 100$):**
   - $y_3 = 882{,}3529 + 100 = 982{,}3529$
   - $x_3 = \frac{1.000.000}{982{,}3529} = 1.017{,}9641$
   - Cotas entregues: $100 + (1.133{,}3333 - 1.017{,}9641) = 215{,}3693$ cotas Sim.
   - Preço médio: $\frac{100}{215{,}3693} = \text{R\$ } 0{,}4643$ (Slippage: $+6{,}07\%$).
   - Novo preço instantâneo: $P_{sim}^{(3)} = 49{,}11\%$.
   - Cofre: R$ 1.600,00.
4. **Alice vende 50% de suas cotas Sim ($S = 183{,}3333$):**
   - $B = x_3 + y_3 + S = 1.017{,}9641 + 982{,}3529 + 183{,}3333 = 2.183{,}6504$
   - $C = S \cdot y_3 = 183{,}3333 \times 982{,}3529 = 180.098{,}0428$
   - $\Delta = B^2 - 4C = 4.047.937{,}02 \implies \sqrt{\Delta} = 2.011{,}9486$
   - Dinheiro resgatado: $\Delta b = \frac{B - \sqrt{\Delta}}{2} = \text{R\$ } 85{,}8509$
   - Novas reservas: $x_4 = 1.017{,}9641 + (183{,}3333 - 85{,}8509) = 1.115{,}4465$, $y_4 = 982{,}3529 - 85{,}8509 = 896{,}5020$.
   - Conservação de $k$: $1.115{,}4465 \times 896{,}5020 = 1.000.000{,}00$.
   - Cofre: R$ 1.600{,}00 - 85{,}8509 = \text{R\$ } 1.514{,}1491$.

### 5.3. Livro-Razão Consolidado Antes da Resolução

| Participante | Saldo BRL | Cotas Sim | Cotas Não | Custo Líquido Aportado |
| :--- | :--- | :--- | :--- | :--- |
| **Alice** | R$ 385,85 | 183,3333 | 0,0000 | R$ 114,15 |
| **Bob** | R$ 200,00 | 0,0000 | 617,6471 | R$ 300,00 |
| **Charlie** | R$ 400,00 | 215,3693 | 0,0000 | R$ 100,00 |
| **Pool LP** | R$ 0,00 | 1.115,4465 | 896,5020 | R$ 1.000,00 inicial |
| **TOTAL** | — | **1.514,1491** | **1.514,1491** | **Cofre: R$ 1.514,1491** |

### 5.4. Liquidação Final pelo Oráculo (Desfecho = SIM)
- **Alice**: 183,3333 cotas $\times$ R$ 1,00 = R$ 183,33 $\implies$ Saldo final R$ 569,18 (**Lucro: +R$ 69,18**)
- **Bob**: 617,6471 cotas $\times$ R$ 0,00 = R$ 0,00 $\implies$ Saldo final R$ 200,00 (**Prejuízo: -R$ 300,00**)
- **Charlie**: 215,3693 cotas $\times$ R$ 1,00 = R$ 215,37 $\implies$ Saldo final R$ 615,37 (**Lucro: +R$ 115,37**)
- **Pool LP**: 1.115,4465 cotas $\times$ R$ 1,00 = R$ 1.115,45 $\implies$ Variação de capital: **+R$ 115,45**
- **Auditoria do Cofre:**
  $$\text{Total Distribuído} = 183{,}33 + 0 + 215{,}37 + 1.115{,}45 = \text{R\$ } 1.514{,}1491$$
  $$\text{Saldo Residual} = \mathbf{\text{R\$ } 0{,}0000000000}$$
