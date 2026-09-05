"""
CPMM Binary Prediction Market Pricing Engine Prototype.

Part of Issue #4 (Wayfinder Prototype).
Mathematics:
- Constant Product Invariant: x * y = k
- Instantaneous Probabilities: P(YES) = y / (x + y), P(NO) = x / (x + y)
- Complete Set Minting: 1 YES + 1 NO = R$ 1.00 (Collateralized)
- Closed-form Analytical Buying and Selling (O(1))
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN, getcontext
from typing import Literal

# Set decimal context precision (standard 28 digits, banker's rounding)
getcontext().prec = 28
getcontext().rounding = ROUND_HALF_EVEN


@dataclass(frozen=True)
class Pool:
    """State of an AMM CPMM Liquidity Pool."""
    x: Decimal  # Reserve of YES shares
    y: Decimal  # Reserve of NO shares
    k: Decimal  # Constant product invariant (x * y)
    total_collateral: Decimal  # Total BRL locked backing all shares
    fee_rate: Decimal = Decimal("0")  # Optional protocol fee (default 0%)

    def __post_init__(self) -> None:
        if self.x <= Decimal("0") or self.y <= Decimal("0"):
            raise ValueError("Pool reserves must be strictly positive.")
        if self.total_collateral < Decimal("0"):
            raise ValueError("Total collateral cannot be negative.")
        if not (Decimal("0") <= self.fee_rate < Decimal("1")):
            raise ValueError("Fee rate must be in range [0, 1).")


@dataclass(frozen=True)
class TradeResult:
    """Outcome of a buy or sell operation."""
    shares_delta: Decimal  # Shares bought or sold
    brl_amount: Decimal  # BRL invested (buy) or proceeds received (sell)
    effective_avg_price: Decimal  # brl_amount / shares_delta
    instant_price_before: Decimal  # Marginal price of the outcome before trade
    instant_price_after: Decimal  # Marginal price of the outcome after trade
    slippage: Decimal  # Relative difference between avg price and marginal before
    fee_paid: Decimal  # Protocol fee deducted in BRL
    outcome: Literal["YES", "NO"]
    action: Literal["BUY", "SELL"]


@dataclass(frozen=True)
class SettlementResult:
    """Outcome of final market resolution."""
    resolved_outcome: Literal["YES", "NO"]
    payout_per_yes: Decimal
    payout_per_no: Decimal
    user_payout: Decimal
    vault_solvency_verified: bool


def create_pool(
    initial_liquidity_brl: Decimal,
    fee_rate: Decimal = Decimal("0")
) -> Pool:
    """
    Initializes a new binary CPMM pool at 50% / 50% initial odds.

    Initial liquidity L (BRL) mints L YES shares and L NO shares.
    Pool holds: x = L, y = L, k = L * L, total_collateral = L.
    """
    if initial_liquidity_brl <= Decimal("0"):
        raise ValueError("Initial liquidity must be positive.")
    
    x = initial_liquidity_brl
    y = initial_liquidity_brl
    k = x * y
    return Pool(
        x=x,
        y=y,
        k=k,
        total_collateral=initial_liquidity_brl,
        fee_rate=fee_rate
    )


def instant_probabilities(pool: Pool) -> tuple[Decimal, Decimal]:
    """
    Computes instantaneous (marginal) probabilities:
    P(YES) = y / (x + y)
    P(NO) = x / (x + y)
    Guarantees P(YES) + P(NO) == 1.0.
    """
    total = pool.x + pool.y
    p_yes = pool.y / total
    p_no = pool.x / total
    return p_yes, p_no


def buy_yes(pool: Pool, investment_brl: Decimal) -> tuple[Pool, TradeResult]:
    """
    Buys YES shares with a given BRL investment.
    
    Mecânica:
    1. Deduz taxa de protocolo (se houver): net_inv = investment * (1 - fee_rate).
    2. Emissão de pares: net_inv YES e net_inv NO são gerados.
    3. As cotas NO entram na pool: y' = y + net_inv.
    4. Conservação de k: x' = k / y'.
    5. A pool libera (x - x') cotas YES adicionais ao usuário.
    6. Total de cotas YES do usuário = net_inv + (x - x').
    """
    if investment_brl <= Decimal("0"):
        raise ValueError("Investment amount must be positive.")

    p_yes_before, _ = instant_probabilities(pool)
    fee_paid = investment_brl * pool.fee_rate
    net_investment = investment_brl - fee_paid

    y_new = pool.y + net_investment
    x_new = pool.k / y_new
    shares_from_pool = pool.x - x_new
    total_shares = net_investment + shares_from_pool

    new_pool = Pool(
        x=x_new,
        y=y_new,
        k=pool.k,
        total_collateral=pool.total_collateral + net_investment,
        fee_rate=pool.fee_rate
    )

    p_yes_after, _ = instant_probabilities(new_pool)
    avg_price = investment_brl / total_shares
    slippage = (avg_price - p_yes_before) / p_yes_before

    trade_result = TradeResult(
        shares_delta=total_shares,
        brl_amount=investment_brl,
        effective_avg_price=avg_price,
        instant_price_before=p_yes_before,
        instant_price_after=p_yes_after,
        slippage=slippage,
        fee_paid=fee_paid,
        outcome="YES",
        action="BUY"
    )
    return new_pool, trade_result


def buy_no(pool: Pool, investment_brl: Decimal) -> tuple[Pool, TradeResult]:
    """
    Buys NO shares with a given BRL investment.
    
    Symmetric to buy_yes:
    x' = x + net_inv
    y' = k / x'
    Total NO shares = net_inv + (y - y')
    """
    if investment_brl <= Decimal("0"):
        raise ValueError("Investment amount must be positive.")

    _, p_no_before = instant_probabilities(pool)
    fee_paid = investment_brl * pool.fee_rate
    net_investment = investment_brl - fee_paid

    x_new = pool.x + net_investment
    y_new = pool.k / x_new
    shares_from_pool = pool.y - y_new
    total_shares = net_investment + shares_from_pool

    new_pool = Pool(
        x=x_new,
        y=y_new,
        k=pool.k,
        total_collateral=pool.total_collateral + net_investment,
        fee_rate=pool.fee_rate
    )

    _, p_no_after = instant_probabilities(new_pool)
    avg_price = investment_brl / total_shares
    slippage = (avg_price - p_no_before) / p_no_before

    trade_result = TradeResult(
        shares_delta=total_shares,
        brl_amount=investment_brl,
        effective_avg_price=avg_price,
        instant_price_before=p_no_before,
        instant_price_after=p_no_after,
        slippage=slippage,
        fee_paid=fee_paid,
        outcome="NO",
        action="BUY"
    )
    return new_pool, trade_result


def sell_yes(pool: Pool, shares_to_sell: Decimal) -> tuple[Pool, TradeResult]:
    """
    Sells S YES shares back to the AMM to redeem BRL cash.
    
    Mecânica analítica:
    (x + S - delta_b) * (y - delta_b) = k = x * y
    delta_b^2 - (x + y + S)*delta_b + S*y = 0
    delta_b = ((x + y + S) - sqrt((x + y + S)^2 - 4*S*y)) / 2
    """
    if shares_to_sell <= Decimal("0"):
        raise ValueError("Shares to sell must be positive.")

    p_yes_before, _ = instant_probabilities(pool)
    s = shares_to_sell
    b_term = pool.x + pool.y + s
    c_term = s * pool.y
    discriminant = b_term**2 - Decimal("4") * c_term
    if discriminant < Decimal("0"):
        raise ArithmeticError("Discriminant negative during sell_yes.")

    gross_delta_b = (b_term - discriminant.sqrt()) / Decimal("2")
    if gross_delta_b >= pool.y:
        raise ValueError("Sell order exceeds available pool depth.")

    fee_paid = gross_delta_b * pool.fee_rate
    net_proceeds = gross_delta_b - fee_paid

    x_new = pool.x + (s - gross_delta_b)
    y_new = pool.y - gross_delta_b

    new_pool = Pool(
        x=x_new,
        y=y_new,
        k=pool.k,
        total_collateral=pool.total_collateral - gross_delta_b,
        fee_rate=pool.fee_rate
    )

    p_yes_after, _ = instant_probabilities(new_pool)
    avg_price = net_proceeds / s
    slippage = (p_yes_before - avg_price) / p_yes_before

    trade_result = TradeResult(
        shares_delta=s,
        brl_amount=net_proceeds,
        effective_avg_price=avg_price,
        instant_price_before=p_yes_before,
        instant_price_after=p_yes_after,
        slippage=slippage,
        fee_paid=fee_paid,
        outcome="YES",
        action="SELL"
    )
    return new_pool, trade_result


def sell_no(pool: Pool, shares_to_sell: Decimal) -> tuple[Pool, TradeResult]:
    """
    Sells S NO shares back to the AMM to redeem BRL cash.
    
    Symmetric to sell_yes:
    (y + S - delta_b) * (x - delta_b) = k = x * y
    delta_b^2 - (x + y + S)*delta_b + S*x = 0
    delta_b = ((x + y + S) - sqrt((x + y + S)^2 - 4*S*x)) / 2
    """
    if shares_to_sell <= Decimal("0"):
        raise ValueError("Shares to sell must be positive.")

    _, p_no_before = instant_probabilities(pool)
    s = shares_to_sell
    b_term = pool.x + pool.y + s
    c_term = s * pool.x
    discriminant = b_term**2 - Decimal("4") * c_term
    if discriminant < Decimal("0"):
        raise ArithmeticError("Discriminant negative during sell_no.")

    gross_delta_b = (b_term - discriminant.sqrt()) / Decimal("2")
    if gross_delta_b >= pool.x:
        raise ValueError("Sell order exceeds available pool depth.")

    fee_paid = gross_delta_b * pool.fee_rate
    net_proceeds = gross_delta_b - fee_paid

    y_new = pool.y + (s - gross_delta_b)
    x_new = pool.x - gross_delta_b

    new_pool = Pool(
        x=x_new,
        y=y_new,
        k=pool.k,
        total_collateral=pool.total_collateral - gross_delta_b,
        fee_rate=pool.fee_rate
    )

    _, p_no_after = instant_probabilities(new_pool)
    avg_price = net_proceeds / s
    slippage = (p_no_before - avg_price) / p_no_before

    trade_result = TradeResult(
        shares_delta=s,
        brl_amount=net_proceeds,
        effective_avg_price=avg_price,
        instant_price_before=p_no_before,
        instant_price_after=p_no_after,
        slippage=slippage,
        fee_paid=fee_paid,
        outcome="NO",
        action="SELL"
    )
    return new_pool, trade_result


def settle_market(
    pool: Pool,
    outcome: Literal["YES", "NO"],
    user_yes_shares: Decimal = Decimal("0"),
    user_no_shares: Decimal = Decimal("0")
) -> SettlementResult:
    """
    Executes final settlement of a market:
    - If outcome is YES: 1 YES share = R$ 1.00; 1 NO share = R$ 0.00.
    - If outcome is NO:  1 YES share = R$ 0.00; 1 NO share = R$ 1.00.
    - Solvency check: confirms the vault collateral covers all outstanding winning shares.
    """
    if outcome == "YES":
        payout_per_yes = Decimal("1.00")
        payout_per_no = Decimal("0.00")
        user_payout = user_yes_shares * payout_per_yes
        # Pool's winning shares
        pool_payout = pool.x * payout_per_yes
    elif outcome == "NO":
        payout_per_yes = Decimal("0.00")
        payout_per_no = Decimal("1.00")
        user_payout = user_no_shares * payout_per_no
        pool_payout = pool.y * payout_per_no
    else:
        raise ValueError(f"Unknown resolution outcome: {outcome}")

    total_entitled = user_payout + pool_payout
    # Pool collateral must equal total entitled (within 1e-18 precision)
    diff = abs(pool.total_collateral - total_entitled)
    solvency_verified = diff < Decimal("1e-10")

    return SettlementResult(
        resolved_outcome=outcome,
        payout_per_yes=payout_per_yes,
        payout_per_no=payout_per_no,
        user_payout=user_payout,
        vault_solvency_verified=solvency_verified
    )


if __name__ == "__main__":
    print("=== CPMM ENGINE PROTOTYPE VALIDATION ===")
    p0 = create_pool(Decimal("1000.00"))
    p_yes, p_no = instant_probabilities(p0)
    print(f"Pool inicial: x={p0.x}, y={p0.y}, k={p0.k}, Colateral={p0.total_collateral}")
    print(f"Probabilidades: YES={p_yes:.4f} (R$ {p_yes:.2f}), NO={p_no:.4f} (R$ {p_no:.2f})")

    print("\n--- 1. Compra de R$ 100 em cotas Sim (YES) ---")
    p1, res_buy = buy_yes(p0, Decimal("100.00"))
    print(f"Cotas recebidas: {res_buy.shares_delta:.4f}")
    print(f"Preço médio pago: R$ {res_buy.effective_avg_price:.4f}")
    print(f"Preço instantâneo: antes={res_buy.instant_price_before:.4f} -> depois={res_buy.instant_price_after:.4f}")
    print(f"Slippage: {res_buy.slippage * 100:.2f}%")
    print(f"Pool após compra: x={p1.x:.4f}, y={p1.y:.4f}, k={p1.k:.4f}, k_conserved={p1.x * p1.y == p0.k}")

    print("\n--- 2. Venda imediata de 100% das cotas Sim adquiridas (Ida e Volta) ---")
    p2, res_sell = sell_yes(p1, res_buy.shares_delta)
    print(f"BRL recuperado na venda: R$ {res_sell.brl_amount:.4f}")
    print(f"Preço médio de venda: R$ {res_sell.effective_avg_price:.4f}")
    print(f"Pool após venda: x={p2.x:.4f}, y={p2.y:.4f}, k={p2.k:.4f}")
    print(f"Conservação exata de capital: BRL inicial={res_buy.brl_amount} vs final={res_sell.brl_amount:.4f}")

    print("\n--- 3. Liquidação Final a R$ 1,00 / R$ 0,00 ---")
    # Simula usuário mantendo as cotas e mercado resolvendo Sim
    settle_yes = settle_market(p1, "YES", user_yes_shares=res_buy.shares_delta, user_no_shares=Decimal("0"))
    print(f"Resolução Sim: Usuário recebe R$ {settle_yes.user_payout:.2f} (Lucro: R$ {settle_yes.user_payout - res_buy.brl_amount:.2f})")
    print(f"Solvência do cofre verificada: {settle_yes.vault_solvency_verified}")

    settle_no = settle_market(p1, "NO", user_yes_shares=res_buy.shares_delta, user_no_shares=Decimal("0"))
    print(f"Resolução Não: Usuário recebe R$ {settle_no.user_payout:.2f} (Perda: R$ {res_buy.brl_amount:.2f})")
    print(f"Solvência do cofre verificada: {settle_no.vault_solvency_verified}")
