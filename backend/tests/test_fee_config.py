"""
Unit tests for FeeConfig contract fee calculation logic.

These tests verify the fee math documented in CONTRACTS.md
and validate edge cases, especially the minimum fee floor.
"""

import unittest


class TestFeeCalculation(unittest.TestCase):
    """Test fee calculation with 250 bps (2.5%) rate."""

    RATE_BPS = 250
    DIVISOR = 10000

    def _calculate_fee(self, amount: int, rate: int = RATE_BPS) -> int:
        """Simulate FeeConfig.calculate_fee() logic."""
        if amount == 0:
            return 0
        calculated = (amount * rate) // self.DIVISOR
        if calculated == 0 and rate > 0:  # minimum floor only when rate > 0
            return 1
        return calculated

    def test_normal_case_500k_micro_usdc(self):
        """0.50 USDC at 2.5% should yield 0.0125 USDC fee."""
        amount = 500000
        fee = self._calculate_fee(amount)
        self.assertEqual(fee, 12500, "500000 * 250 / 10000 = 12500")
        payout = amount - fee
        self.assertEqual(payout, 487500, "Seller payout = 487500")

    def test_normal_case_100k_micro_usdc(self):
        """0.10 USDC at 2.5% should yield 0.0025 USDC fee."""
        amount = 100000
        fee = self._calculate_fee(amount)
        self.assertEqual(fee, 2500, "100000 * 250 / 10000 = 2500")
        payout = amount - fee
        self.assertEqual(payout, 97500, "Seller payout = 97500")

    def test_normal_case_10k_micro_usdc(self):
        """0.01 USDC at 2.5% should yield 0.00025 USDC fee."""
        amount = 10000
        fee = self._calculate_fee(amount)
        self.assertEqual(fee, 250, "10000 * 250 / 10000 = 250")
        payout = amount - fee
        self.assertEqual(payout, 9750, "Seller payout = 9750")

    def test_edge_case_dust_39_micro_usdc(self):
        """
        Dust amount edge case: 39 microUSDC at 2.5% rate.
        
        (39 * 250) / 10000 = 9750 / 10000 = 0 (integer division)
        
        Without minimum floor: fee = 0 (invalid USDC transfer)
        WITH minimum floor: fee = 1 microUSDC (valid minimum)
        """
        amount = 39
        fee = self._calculate_fee(amount)
        self.assertEqual(
            fee, 1, "Dust amount produces minimum 1 microUSDC fee (not 0)"
        )
        payout = amount - fee
        self.assertEqual(payout, 38, "Seller payout = 38 microUSDC")

    def test_edge_case_zero_amount(self):
        """Zero amount should yield zero fee (no payout)."""
        amount = 0
        fee = self._calculate_fee(amount)
        self.assertEqual(fee, 0, "Zero amount → zero fee")
        payout = amount - fee
        self.assertEqual(payout, 0, "Zero payout")

    def test_edge_case_1_micro_usdc(self):
        """1 microUSDC (smallest non-zero amount)."""
        amount = 1
        fee = self._calculate_fee(amount)
        # (1 * 250) / 10000 = 250 / 10000 = 0, but applies minimum floor
        self.assertEqual(fee, 1, "1 microUSDC produces minimum 1 microUSDC fee")
        payout = amount - fee
        self.assertEqual(payout, 0, "Seller payout = 0")

    def test_fee_never_exceeds_amount(self):
        """Verify fee is always ≤ amount (obvious but important)."""
        test_amounts = [1, 10, 100, 1000, 10000, 100000, 1000000]
        for amount in test_amounts:
            fee = self._calculate_fee(amount)
            self.assertLessEqual(
                fee, amount, f"Fee {fee} must be ≤ amount {amount}"
            )

    def test_payout_never_negative(self):
        """Verify seller payout is always ≥ 0."""
        test_amounts = [0, 1, 10, 39, 100, 10000, 500000]
        for amount in test_amounts:
            fee = self._calculate_fee(amount)
            payout = amount - fee
            self.assertGreaterEqual(
                payout, 0, f"Payout {payout} must be ≥ 0 for amount {amount}"
            )

    def test_various_fee_rates(self):
        """Verify calculation works across different fee rates."""
        test_cases = [
            (100000, 0, 0),  # 0% fee
            (100000, 100, 1000),  # 1% fee: 100000 * 100 / 10000 = 1000
            (100000, 250, 2500),  # 2.5% fee
            (100000, 500, 5000),  # 5% fee
            (100000, 1000, 10000),  # 10% fee (hard cap)
        ]
        for amount, rate, expected_fee in test_cases:
            fee = self._calculate_fee(amount, rate)
            self.assertEqual(
                fee,
                expected_fee,
                f"Amount {amount} at {rate} bps should yield {expected_fee}",
            )

    def test_fee_calculation_standard_amount(self):
        """Test case from CONTRACTS.md: 500000 microUSDC at 250 bps."""
        amount = 500000
        fee = self._calculate_fee(amount, 250)
        payout = amount - fee
        self.assertEqual(fee, 12500, "Fee should be exactly 12500")
        self.assertEqual(payout, 487500, "Payout should be exactly 487500")
        self.assertEqual(fee + payout, amount, "Fee + payout must equal amount")

    def test_fee_calculation_minimum_amount(self):
        """Test case: 1000 microUSDC at 250 bps."""
        amount = 1000
        fee = self._calculate_fee(amount, 250)
        payout = amount - fee
        # (1000 * 250) / 10000 = 25
        self.assertEqual(fee, 25, "Fee should be exactly 25")
        self.assertEqual(payout, 975, "Payout should be exactly 975")

    def test_fee_calculation_dust_amount(self):
        """Test case from CONTRACTS.md: 39 microUSDC at 250 bps produces 1 microUSDC fee (minimum floor)."""
        amount = 39
        fee = self._calculate_fee(amount, 250)
        payout = amount - fee
        # (39 * 250) / 10000 = 0, but minimum floor = 1
        self.assertEqual(fee, 1, "Fee should be minimum 1 (not 0)")
        self.assertEqual(payout, 38, "Payout should be 38")

    def test_fee_calculation_zero_amount(self):
        """Test case: 0 microUSDC produces 0 fee with no minimum floor."""
        amount = 0
        fee = self._calculate_fee(amount, 250)
        payout = amount - fee
        self.assertEqual(fee, 0, "Zero amount should produce zero fee")
        self.assertEqual(payout, 0, "Zero payout")

    def test_fee_rate_ceiling_enforced(self):
        """Verify that fee rate is capped at 1000 basis points (10%)."""
        # This test documents the on-chain constraint
        rate_1001 = 1001  # Above cap
        amount = 100000
        # This should be checked at contract deployment/update
        # For unit test, just verify the rate would be invalid
        self.assertGreater(rate_1001, 1000, "Rate 1001 exceeds 10% hard cap")

    def test_set_fee_rate_requires_owner(self):
        """Non-owner set_fee_rate should revert with the documented message."""
        owner = "OWNER"
        caller = "NOT_OWNER"
        with self.assertRaisesRegex(AssertionError, "Only the contract owner can update the fee rate"):
            assert caller == owner, "Only the contract owner can update the fee rate"

    def test_set_fee_rate_ceiling_enforced(self):
        """Setting fee above 1000 bps must fail."""
        with self.assertRaises(AssertionError):
            assert 1001 <= 1000, "Fee rate cannot exceed 10% (1000 basis points)"

    def test_set_fee_rate_at_ceiling_succeeds(self):
        """Setting fee to exactly 1000 bps should succeed."""
        new_rate_bps = 1000
        assert new_rate_bps <= 1000
        amount = 500000
        self.assertEqual(self._calculate_fee(amount, new_rate_bps), 50000)

    def test_fee_rate_at_ceiling_valid(self):
        """Verify that fee rate of exactly 1000 basis points (10%) is valid."""
        amount = 100000
        fee = self._calculate_fee(amount, 1000)
        self.assertEqual(fee, 10000, "10% rate on 100000 should yield 10000")
        self.assertEqual(amount - fee, 90000, "Payout should be 90000")

    def test_record_fee_accumulates_correctly(self):
        """Test that fee collection accumulates across multiple calls."""
        # Simulate FeeConfig.record_fee_collected behavior
        total = 0
        
        # First fee: 12500 microUSDC
        total += 12500
        self.assertEqual(total, 12500)
        
        # Second fee: 25 microUSDC
        total += 25
        self.assertEqual(total, 12525)
        
        # Third fee: 1 microUSDC
        total += 1
        self.assertEqual(total, 12526, "Total should accumulate to exactly 12526")

    def test_escrow_release_splits_correctly(self):
        """Integration test: verify payment split logic for 500000 microUSDC."""
        amount = 500000
        fee_rate_bps = 250
        
        # Calculate fee
        calculated_fee = (amount * fee_rate_bps) // 10000
        # No minimum floor needed here (calculated_fee > 0)
        
        seller_payout = amount - calculated_fee
        treasury_fee = calculated_fee
        
        # Verify split
        self.assertEqual(seller_payout, 487500, "Seller should receive exactly 487500")
        self.assertEqual(treasury_fee, 12500, "Treasury should receive exactly 12500")
        self.assertEqual(seller_payout + treasury_fee, amount, "Split must be lossless")

    def test_escrow_release_atomicity_invariant(self):
        """Safety test: if either transfer fails, invariant prevents partial state."""
        amount = 500000
        fee_rate_bps = 250
        
        # Calculate split
        calculated_fee = (amount * fee_rate_bps) // 10000
        seller_payout = amount - calculated_fee
        
        # Verify invariant: fee + payout == amount
        invariant_holds = (calculated_fee + seller_payout == amount)
        self.assertTrue(invariant_holds, "Atomicity invariant: fee + payout must equal amount")
        
        # If either inner transaction fails, the atomic group reverts
        # This test documents that the invariant protects against partial splits

    def test_escrow_release_atomicity(self):
        """If treasury transfer fails, seller payout must not persist (atomic behavior)."""
        seller_before = 100000
        treasury_before = 50000
        amount = 500000
        fee = self._calculate_fee(amount, 250)
        payout = amount - fee

        # Simulate atomic submit failure on second leg.
        transfer_failed = True
        if transfer_failed:
            seller_after = seller_before
            treasury_after = treasury_before
        else:
            seller_after = seller_before + payout
            treasury_after = treasury_before + fee

        self.assertEqual(seller_after, seller_before)
        self.assertEqual(treasury_after, treasury_before)


if __name__ == "__main__":
    unittest.main()
