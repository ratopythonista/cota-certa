"""
Comprehensive test suite for the CPMM Binary Prediction Market Pricing Engine.

Covers:
1. Product conservation invariant (x * y = k)
2. Implied probability sum (P_yes + P_no = 1.0)
3. Reversible round-trip symmetry (buy -> sell net 0 when fee = 0)
4. Collateral solvency in vault (100% backed)
5. Final resolution and liquidation at R$ 1.00 / R$ 0.00
6. Slippage scaling and asymmetric pool states
7. Boundary conditions and protocol fees
"""

from decimal import Decimal
import pytest

from prototype.cpmm import (
    Pool,
    create_pool,
    instant_probabilities,
    buy_yes,
    buy_no,
    sell_yes,
    sell_no,
    settle_market,
)


class TestPoolInitialization:
    def test_initial_reserves_and_probability(self):
        pool = create_pool(Decimal("5000.00"))
        assert pool.x == Decimal("5000.00")
        assert pool.y == Decimal("5000.00")
        assert pool.k == Decimal("25000000.00")
        assert pool.total_collateral == Decimal("5000.00")

        p_yes, p_no = instant_probabilities(pool)
        assert p_yes == Decimal("0.5")
        assert p_no == Decimal("0.5")
        assert p_yes + p_no == Decimal("1.0")

    def test_invalid_initial_liquidity(self):
        with pytest.raises(ValueError, match="Initial liquidity must be positive"):
            create_pool(Decimal("0.00"))

        with pytest.raises(ValueError, match="Initial liquidity must be positive"):
            create_pool(Decimal("-100.00"))


class TestProductConservation:
    @pytest.mark.parametrize("investment", [
        Decimal("1.00"),
        Decimal("10.00"),
        Decimal("100.00"),
        Decimal("1000.00"),
        Decimal("5000.00"),
    ])
    def test_buy_conserves_product_invariant(self, investment: Decimal):
        initial_pool = create_pool(Decimal("2000.00"))
        k_expected = initial_pool.k

        # Buy YES
        pool_after_yes, _ = buy_yes(initial_pool, investment)
        rel_diff_yes = abs(pool_after_yes.x * pool_after_yes.y - k_expected) / k_expected
        assert rel_diff_yes < Decimal("1e-20"), f"k changed after buy_yes: {pool_after_yes.x * pool_after_yes.y} != {k_expected}"

        # Buy NO
        pool_after_no, _ = buy_no(initial_pool, investment)
        rel_diff_no = abs(pool_after_no.x * pool_after_no.y - k_expected) / k_expected
        assert rel_diff_no < Decimal("1e-20"), f"k changed after buy_no: {pool_after_no.x * pool_after_no.y} != {k_expected}"

    @pytest.mark.parametrize("shares", [
        Decimal("1.00"),
        Decimal("25.00"),
        Decimal("150.00"),
        Decimal("500.00"),
    ])
    def test_sell_conserves_product_invariant(self, shares: Decimal):
        initial_pool = create_pool(Decimal("2000.00"))
        k_expected = initial_pool.k

        # First give the pool some asymmetry
        pool_primed, _ = buy_yes(initial_pool, Decimal("200.00"))

        # Sell YES
        pool_after_sell_yes, _ = sell_yes(pool_primed, shares)
        rel_diff = abs(pool_after_sell_yes.x * pool_after_sell_yes.y - k_expected) / k_expected
        assert rel_diff < Decimal("1e-20")

        # Sell NO
        pool_after_sell_no, _ = sell_no(pool_primed, shares)
        rel_diff_no = abs(pool_after_sell_no.x * pool_after_sell_no.y - k_expected) / k_expected
        assert rel_diff_no < Decimal("1e-20")


class TestSymmetryAndReversibility:
    @pytest.mark.parametrize("investment", [
        Decimal("10.00"),
        Decimal("50.00"),
        Decimal("200.00"),
        Decimal("500.00"),
    ])
    def test_round_trip_recovers_exact_capital_without_fees(self, investment: Decimal):
        pool = create_pool(Decimal("1000.00"))
        
        # 1. Buy YES
        pool1, buy_res = buy_yes(pool, investment)
        assert buy_res.shares_delta > investment  # Receives more shares than BRL (price < 1.00)
        
        # 2. Sell back exact same shares
        pool2, sell_res = sell_yes(pool1, buy_res.shares_delta)
        
        # Net BRL must equal original investment
        diff_brl = abs(sell_res.brl_amount - investment)
        assert diff_brl < Decimal("1e-12")

        # Reserves must return to original
        assert abs(pool2.x - pool.x) < Decimal("1e-12")
        assert abs(pool2.y - pool.y) < Decimal("1e-12")
        assert abs(pool2.total_collateral - pool.total_collateral) < Decimal("1e-12")

    def test_round_trip_no_shares(self):
        pool = create_pool(Decimal("1000.00"))
        pool1, buy_res = buy_no(pool, Decimal("100.00"))
        pool2, sell_res = sell_no(pool1, buy_res.shares_delta)

        assert abs(sell_res.brl_amount - Decimal("100.00")) < Decimal("1e-12")
        assert abs(pool2.x - pool.x) < Decimal("1e-12")
        assert abs(pool2.y - pool.y) < Decimal("1e-12")


class TestPriceAndSlippageMechanics:
    def test_buying_yes_increases_yes_price_and_decreases_no_price(self):
        pool = create_pool(Decimal("1000.00"))
        p_yes_0, p_no_0 = instant_probabilities(pool)
        assert p_yes_0 == Decimal("0.5")

        pool1, _ = buy_yes(pool, Decimal("100.00"))
        p_yes_1, p_no_1 = instant_probabilities(pool1)

        assert p_yes_1 > p_yes_0
        assert p_no_1 < p_no_0
        assert p_yes_1 + p_no_1 == Decimal("1.0")

    def test_larger_trades_experience_higher_slippage(self):
        pool = create_pool(Decimal("1000.00"))

        _, small_trade = buy_yes(pool, Decimal("10.00"))
        _, large_trade = buy_yes(pool, Decimal("300.00"))

        assert large_trade.slippage > small_trade.slippage
        assert large_trade.effective_avg_price > small_trade.effective_avg_price


class TestSolvencyAndLiquidation:
    def test_liquidation_yes_resolves_to_one_reais(self):
        pool = create_pool(Decimal("1000.00"))
        pool1, trade = buy_yes(pool, Decimal("200.00"))

        settlement = settle_market(
            pool1,
            outcome="YES",
            user_yes_shares=trade.shares_delta,
            user_no_shares=Decimal("0")
        )

        assert settlement.payout_per_yes == Decimal("1.00")
        assert settlement.payout_per_no == Decimal("0.00")
        assert settlement.user_payout == trade.shares_delta * Decimal("1.00")
        assert settlement.user_payout > trade.brl_amount  # Profitable because YES won
        assert settlement.vault_solvency_verified is True

    def test_liquidation_no_resolves_to_zero_for_yes_holders(self):
        pool = create_pool(Decimal("1000.00"))
        pool1, trade = buy_yes(pool, Decimal("200.00"))

        settlement = settle_market(
            pool1,
            outcome="NO",
            user_yes_shares=trade.shares_delta,
            user_no_shares=Decimal("0")
        )

        assert settlement.payout_per_yes == Decimal("0.00")
        assert settlement.payout_per_no == Decimal("1.00")
        assert settlement.user_payout == Decimal("0.00")
        assert settlement.vault_solvency_verified is True

    def test_sequential_trading_and_final_solvency(self):
        """
        Multiple users buy and sell across both sides; vault must remain 100% solvent.
        """
        pool = create_pool(Decimal("2000.00"))

        # User A buys YES with 150 BRL
        pool, trade_a = buy_yes(pool, Decimal("150.00"))
        # User B buys NO with 250 BRL
        pool, trade_b = buy_no(pool, Decimal("250.00"))
        # User C buys YES with 80 BRL
        pool, trade_c = buy_yes(pool, Decimal("80.00"))
        # User A sells half of their YES shares
        pool, trade_a_sell = sell_yes(pool, trade_a.shares_delta / Decimal("2"))

        user_a_yes = trade_a.shares_delta / Decimal("2")
        user_b_no = trade_b.shares_delta
        user_c_yes = trade_c.shares_delta

        # Check total YES in existence vs total NO in existence
        total_yes = user_a_yes + user_c_yes + pool.x
        total_no = user_b_no + pool.y
        # Both must match pool total collateral
        assert abs(total_yes - pool.total_collateral) < Decimal("1e-12")
        assert abs(total_no - pool.total_collateral) < Decimal("1e-12")

        # Settlement on YES
        settle_yes = settle_market(pool, "YES", user_yes_shares=(user_a_yes + user_c_yes))
        assert settle_yes.vault_solvency_verified is True

        # Settlement on NO
        settle_no = settle_market(pool, "NO", user_no_shares=user_b_no)
        assert settle_no.vault_solvency_verified is True

    def test_multi_user_lifecycle_with_partial_sell(self):
        """
        Multi-user realistic scenario:
        - Pool initialized with 1000 BRL
        - Alice buys YES (200 BRL)
        - Bob buys NO (300 BRL)
        - Charlie buys YES (100 BRL)
        - Alice sells 50% of her YES shares
        - Verify exact product conservation and 100% solvency under YES and NO resolutions.
        """
        pool = create_pool(Decimal("1000.00"))
        alice_brl = Decimal("500.00")
        bob_brl = Decimal("500.00")
        charlie_brl = Decimal("500.00")

        # 1. Alice buys YES (200 BRL)
        alice_brl -= Decimal("200.00")
        pool, trade_alice_buy = buy_yes(pool, Decimal("200.00"))
        alice_yes = trade_alice_buy.shares_delta
        alice_no = Decimal("0")

        # 2. Bob buys NO (300 BRL)
        bob_brl -= Decimal("300.00")
        pool, trade_bob_buy = buy_no(pool, Decimal("300.00"))
        bob_yes = Decimal("0")
        bob_no = trade_bob_buy.shares_delta

        # 3. Charlie buys YES (100 BRL)
        charlie_brl -= Decimal("100.00")
        pool, trade_charlie_buy = buy_yes(pool, Decimal("100.00"))
        charlie_yes = trade_charlie_buy.shares_delta
        charlie_no = Decimal("0")

        # 4. Alice sells 50% of her YES shares
        alice_shares_to_sell = alice_yes / Decimal("2")
        alice_yes -= alice_shares_to_sell
        pool, trade_alice_sell = sell_yes(pool, alice_shares_to_sell)
        alice_brl += trade_alice_sell.brl_amount

        # Invariant checks
        k_expected = Decimal("1000000.00")
        assert abs(pool.x * pool.y - k_expected) / k_expected < Decimal("1e-20")

        total_yes = alice_yes + bob_yes + charlie_yes + pool.x
        total_no = alice_no + bob_no + charlie_no + pool.y
        assert abs(total_yes - pool.total_collateral) < Decimal("1e-12")
        assert abs(total_no - pool.total_collateral) < Decimal("1e-12")

        # Resolution YES
        payout_alice_yes = alice_yes * Decimal("1.00")
        payout_bob_yes = bob_yes * Decimal("1.00")
        payout_charlie_yes = charlie_yes * Decimal("1.00")
        payout_lp_yes = pool.x * Decimal("1.00")
        total_paid_yes = payout_alice_yes + payout_bob_yes + payout_charlie_yes + payout_lp_yes
        assert abs(total_paid_yes - pool.total_collateral) < Decimal("1e-12")
        assert (alice_brl + payout_alice_yes) > Decimal("500.00")  # Alice profitable
        assert (charlie_brl + payout_charlie_yes) > Decimal("500.00")  # Charlie profitable
        assert (bob_brl + payout_bob_yes) == Decimal("200.00")  # Bob lost 300

        # Resolution NO
        payout_alice_no = alice_no * Decimal("1.00")
        payout_bob_no = bob_no * Decimal("1.00")
        payout_charlie_no = charlie_no * Decimal("1.00")
        payout_lp_no = pool.y * Decimal("1.00")
        total_paid_no = payout_alice_no + payout_bob_no + payout_charlie_no + payout_lp_no
        assert abs(total_paid_no - pool.total_collateral) < Decimal("1e-12")
        assert (bob_brl + payout_bob_no) > Decimal("500.00")  # Bob profitable


class TestProtocolFee:
    def test_fee_deduction_on_buy_and_sell(self):
        fee_rate = Decimal("0.02")  # 2% fee
        pool = create_pool(Decimal("1000.00"), fee_rate=fee_rate)

        # Buy with fee
        pool1, buy_res = buy_yes(pool, Decimal("100.00"))
        assert buy_res.fee_paid == Decimal("2.00")

        # Sell with fee
        _, sell_res = sell_yes(pool1, Decimal("50.00"))
        assert sell_res.fee_paid > Decimal("0.00")
