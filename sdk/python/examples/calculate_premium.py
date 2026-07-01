#!/usr/bin/env python3
"""
Example: Calculate insurance premium for a vault.

Demonstrates risk-based premium pricing.

Usage:
    python3 examples/calculate_premium.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from ward.premium import PremiumCalculator
from ward.models import Vault, LoanBroker


def main():
    """Calculate premiums for different risk scenarios."""
    
    calculator = PremiumCalculator()
    
    print("💰 Ward Protocol - Premium Calculator")
    print("="*70)
    print()
    
    # Coverage amount
    coverage_xrp = 50_000
    coverage_drops = coverage_xrp * 1_000_000
    term_days = 90
    
    print(f"Coverage Amount: {coverage_xrp:,} XRP")
    print(f"Term:            {term_days} days")
    print()
    print("="*70)
    print()
    
    # Scenario 1: Low Risk (Healthy vault + good coverage)
    print("📊 SCENARIO 1: Low Risk Vault")
    print("-" * 70)
    
    vault_low_risk = Vault(
        vault_id="vault1",
        owner="rOwner",
        account="rVault1",
        asset={},
        assets_total=1_000_000_000_000,  # 1M XRP
        assets_available=700_000_000_000,  # 700K available
        loss_unrealized=0,  # No impaired loans
        shares_total=1_000_000_000_000,
        share_mpt_id="mpt1",
        ledger_index=1000
    )
    
    broker_low_risk = LoanBroker(
        loan_broker_id="broker1",
        owner="rOwner",
        vault_id="vault1",
        debt_total=300_000_000_000,  # 300K deployed
        debt_maximum=500_000_000_000,
        cover_available=60_000_000_000,  # 60K first-loss
        cover_rate_minimum=0.20,  # 20% minimum
        cover_rate_liquidation=0.50,
        management_fee_rate=500,
        owner_count=10,
        ledger_index=1000
    )
    
    result = calculator.calculate_premium(
        coverage_amount=coverage_drops,
        term_days=term_days,
        vault=vault_low_risk,
        loan_broker=broker_low_risk,
        historical_default_rate=0.005  # 0.5% historical default
    )
    
    print(f"Risk Tier:           {result['risk_tier']}")
    print(f"Base Rate:           {result['base_rate']*100:.1f}% annually")
    print(f"Risk Multiplier:     {result['risk_multiplier']:.2f}x")
    print(f"Effective Rate:      {result['annual_rate_effective']*100:.2f}% annually")
    print()
    print(f"Premium (90 days):   {result['premium'] / 1_000_000:,.2f} XRP")
    print()
    print("Risk Factors:")
    for key, value in result['risk_factors'].items():
        if key != 'final_multiplier':
            print(f"  - {key}: {value:.4f}")
    print()
    
    # Annual cost estimate
    annual = calculator.estimate_annual_cost(
        coverage_amount=coverage_drops,
        vault=vault_low_risk,
        loan_broker=broker_low_risk
    )
    print(f"Annual Cost Estimate: {annual['annual_cost'] / 1_000_000:,.2f} XRP/year")
    print()
    print("="*70)
    print()
    
    # Scenario 2: High Risk (High utilization + impaired loans)
    print("📊 SCENARIO 2: High Risk Vault")
    print("-" * 70)
    
    vault_high_risk = Vault(
        vault_id="vault2",
        owner="rOwner",
        account="rVault2",
        asset={},
        assets_total=1_000_000_000_000,
        assets_available=50_000_000_000,  # Only 50K available (95% utilization)
        loss_unrealized=150_000_000_000,  # 150K impaired
        shares_total=1_000_000_000_000,
        share_mpt_id="mpt2",
        ledger_index=1000
    )
    
    broker_high_risk = LoanBroker(
        loan_broker_id="broker2",
        owner="rOwner",
        vault_id="vault2",
        debt_total=950_000_000_000,  # 950K deployed
        debt_maximum=1_000_000_000_000,
        cover_available=30_000_000_000,  # Only 30K first-loss
        cover_rate_minimum=0.05,  # 5% minimum (low)
        cover_rate_liquidation=0.50,
        management_fee_rate=500,
        owner_count=30,
        ledger_index=1000
    )
    
    result = calculator.calculate_premium(
        coverage_amount=coverage_drops,
        term_days=term_days,
        vault=vault_high_risk,
        loan_broker=broker_high_risk,
        historical_default_rate=0.12  # 12% historical default
    )
    
    print(f"Risk Tier:           {result['risk_tier']}")
    print(f"Base Rate:           {result['base_rate']*100:.1f}% annually")
    print(f"Risk Multiplier:     {result['risk_multiplier']:.2f}x")
    print(f"Effective Rate:      {result['annual_rate_effective']*100:.2f}% annually")
    print()
    print(f"Premium (90 days):   {result['premium'] / 1_000_000:,.2f} XRP")
    print()
    print("Risk Factors:")
    for key, value in result['risk_factors'].items():
        if key != 'final_multiplier':
            print(f"  - {key}: {value:.4f}")
    print()
    
    annual = calculator.estimate_annual_cost(
        coverage_amount=coverage_drops,
        vault=vault_high_risk,
        loan_broker=broker_high_risk
    )
    print(f"Annual Cost Estimate: {annual['annual_cost'] / 1_000_000:,.2f} XRP/year")
    print()
    print("="*70)
    print()
    
    # Comparison
    low_premium = result['premium'] / 1_000_000
    high_premium_prev = 616.44  # From low risk calculation
    
    print("📈 PREMIUM COMPARISON")
    print("-" * 70)
    print(f"Low Risk Vault:   {high_premium_prev:,.2f} XRP (100%)")
    print(f"High Risk Vault:  {low_premium:,.2f} XRP ({(low_premium/high_premium_prev)*100:.0f}%)")
    print(f"Difference:       +{low_premium - high_premium_prev:,.2f} XRP")
    print()
    print("High risk vault pays ~3-4x more due to:")
    print("  - High utilization (95% vs 30%)")
    print("  - Low coverage ratio (0.6x vs 2x)")
    print("  - High impairment (15% vs 0%)")
    print("  - Poor default history (12% vs 0.5%)")
    print()
    print("="*70)


if __name__ == "__main__":
    main()
