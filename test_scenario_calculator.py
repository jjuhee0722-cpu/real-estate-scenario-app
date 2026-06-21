"""scenario_calculator.py의 시나리오 및 대환 계산 단위 테스트."""

import pytest

from scenario_calculator import calculate_refinance, calculate_scenario


def make_scenario(**overrides):
    inputs = {
        "scenario_name": "테스트 시나리오",
        "total_need": 60_000,
        "my_cash": 15_000,
        "boyfriend_cash": 0,
        "loan_needed": 45_000,
        "extra_cost": 1_500,
        "other_cost": 0,
        "annual_rate": 0.045,
        "dsr_test_rate": 0.060,
        "loan_years": 30,
        "ltv": 0.70,
        "max_policy_loan": None,
        "income_for_dsr": 4_400,
        "existing_debt": 0,
        "dsr_ratio": 0.40,
        "loan_type": "일반 은행 주택담보대출",
        "existing_debt_burden_ratio": 0.10,
    }
    inputs.update(overrides)
    return calculate_scenario(**inputs)


def reference_payment(principal: float, annual_rate: float, years: int) -> float:
    if principal <= 0 or years <= 0:
        return 0.0
    months = years * 12
    monthly_rate = annual_rate / 12
    if monthly_rate == 0:
        return principal / months
    return principal * monthly_rate / (1 - (1 + monthly_rate) ** -months)


def reference_balance(principal: float, annual_rate: float, years: int, elapsed_years: int) -> float:
    if elapsed_years >= years:
        return 0.0
    months_paid = elapsed_years * 12
    monthly_rate = annual_rate / 12
    if monthly_rate == 0:
        return principal * (years - elapsed_years) / years
    payment = reference_payment(principal, annual_rate, years)
    factor = (1 + monthly_rate) ** months_paid
    return principal * factor - payment * (factor - 1) / monthly_rate


def test_scenario_funding_gap() -> None:
    result = make_scenario()
    # 60,000 + 1,500 - 15,000 - 45,000 = 1,500만원 부족.
    assert result.actual_total_need == 61_500
    assert result.total_cash == 15_000
    assert result.funding_gap == 1_500


def test_scenario_cash_surplus_is_negative_funding_gap() -> None:
    result = make_scenario(
        total_need=10_000,
        my_cash=12_000,
        loan_needed=0,
        extra_cost=0,
        annual_rate=0.0,
        dsr_test_rate=0.0,
        income_for_dsr=0,
    )
    assert result.funding_gap == -2_000
    assert result.monthly_payment == 0.0
    assert result.dsr_limit == 0.0


def test_scenario_final_limit_uses_most_conservative_limit() -> None:
    result = make_scenario(
        income_for_dsr=8_500,
        max_policy_loan=32_000,
    )
    assert result.ltv_limit == 42_000
    assert result.dsr_limit > 32_000
    assert result.final_loan_limit == 32_000


def test_refinance_calculation() -> None:
    principal = 30_000
    original_rate = 0.045
    original_years = 30
    elapsed_years = 3
    new_rate = 0.033
    new_years = 30
    fee_rate = 0.01
    other_cost = 100

    result = calculate_refinance(
        principal=principal,
        original_rate=original_rate,
        original_years=original_years,
        elapsed_years=elapsed_years,
        new_rate=new_rate,
        new_years=new_years,
        prepayment_fee_rate=fee_rate,
        other_cost=other_cost,
        max_new_loan=40_000,
    )

    expected_balance = reference_balance(principal, original_rate, original_years, elapsed_years)
    expected_fee = expected_balance * fee_rate
    expected_new_principal = expected_balance + expected_fee + other_cost
    expected_old_monthly = reference_payment(principal, original_rate, original_years)
    expected_new_monthly = reference_payment(expected_new_principal, new_rate, new_years)

    assert result["balance"] == pytest.approx(expected_balance)
    assert result["prepayment_fee"] == pytest.approx(expected_fee)
    assert result["new_principal"] == pytest.approx(expected_new_principal)
    assert result["old_monthly"] == pytest.approx(expected_old_monthly)
    assert result["new_monthly"] == pytest.approx(expected_new_monthly)
    assert result["monthly_saving"] == pytest.approx(expected_old_monthly - expected_new_monthly)
    assert result["annual_saving"] == pytest.approx(
        (expected_old_monthly - expected_new_monthly) * 12
    )


def test_refinance_with_zero_interest() -> None:
    result = calculate_refinance(
        principal=12_000,
        original_rate=0.0,
        original_years=10,
        elapsed_years=4,
        new_rate=0.0,
        new_years=6,
        prepayment_fee_rate=0.0,
        other_cost=0,
        max_new_loan=40_000,
    )
    assert result["balance"] == pytest.approx(7_200.0)
    assert result["old_monthly"] == pytest.approx(100.0)
    assert result["new_monthly"] == pytest.approx(100.0)
    assert result["monthly_saving"] == pytest.approx(0.0)


def test_refinance_with_zero_principal() -> None:
    result = calculate_refinance(
        principal=0,
        original_rate=0.045,
        original_years=30,
        elapsed_years=3,
        new_rate=0.033,
        new_years=30,
        prepayment_fee_rate=0.0,
        other_cost=0,
        max_new_loan=40_000,
    )
    assert result["balance"] == 0.0
    assert result["old_monthly"] == 0.0
    assert result["new_principal"] == 0.0
    assert result["new_monthly"] == 0.0


def test_refinance_after_original_term_has_no_balance() -> None:
    result = calculate_refinance(
        principal=10_000,
        original_rate=0.045,
        original_years=10,
        elapsed_years=15,
        new_rate=0.030,
        new_years=10,
        prepayment_fee_rate=0.0,
        other_cost=0,
        max_new_loan=40_000,
    )
    assert result["balance"] == 0.0
    assert result["old_monthly"] == 0.0
    assert result["new_principal"] == 0.0
    assert result["new_monthly"] == 0.0

