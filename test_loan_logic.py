"""loan_logic.py의 핵심 금융 계산 단위 테스트."""

import math

import pytest

from loan_logic import dsr_loan_limit, monthly_payment, remaining_balance


def reference_monthly_payment(principal: float, annual_rate: float, years: int) -> float:
    """검증용 표준 원리금균등상환 공식."""
    months = years * 12
    if principal <= 0 or months <= 0:
        return 0.0
    monthly_rate = annual_rate / 12
    if monthly_rate == 0:
        return principal / months
    return principal * monthly_rate / (1 - (1 + monthly_rate) ** -months)


def test_monthly_payment_matches_standard_annuity_formula() -> None:
    expected = reference_monthly_payment(45_000, 0.045, 30)
    assert monthly_payment(45_000, 0.045, 30) == pytest.approx(expected)


def test_monthly_payment_with_zero_interest() -> None:
    assert monthly_payment(12_000, 0.0, 10) == pytest.approx(100.0)


def test_monthly_payment_with_zero_principal() -> None:
    assert monthly_payment(0, 0.045, 30) == 0.0


def test_remaining_balance_matches_amortization_formula() -> None:
    principal = 30_000
    annual_rate = 0.045
    years = 30
    elapsed_years = 3
    monthly_rate = annual_rate / 12
    paid_months = elapsed_years * 12
    payment = reference_monthly_payment(principal, annual_rate, years)
    expected = (
        principal * (1 + monthly_rate) ** paid_months
        - payment * ((1 + monthly_rate) ** paid_months - 1) / monthly_rate
    )
    assert remaining_balance(principal, annual_rate, years, elapsed_years) == pytest.approx(expected)


def test_remaining_balance_with_zero_interest() -> None:
    # 10년 중 4년을 갚았다면 원금의 60%가 남는다.
    assert remaining_balance(12_000, 0.0, 10, 4) == pytest.approx(7_200.0)


def test_remaining_balance_after_loan_term_is_zero() -> None:
    assert remaining_balance(10_000, 0.045, 10, 15) == 0.0


def test_remaining_balance_with_zero_principal() -> None:
    assert remaining_balance(0, 0.045, 30, 3) == 0.0


def test_dsr_limit_uses_income_allowance_and_existing_debt_burden() -> None:
    annual_income = 6_000
    dsr_ratio = 0.40
    existing_debt = 10_000
    debt_burden_ratio = 0.10
    test_rate = 0.06
    years = 30

    available_annual_payment = annual_income * dsr_ratio - existing_debt * debt_burden_ratio
    limit = dsr_loan_limit(
        annual_income,
        dsr_ratio,
        test_rate,
        years,
        existing_debt,
        debt_burden_ratio,
    )

    # 역산한 한도의 월 상환액이 DSR상 허용 월 상환액과 같아야 한다.
    assert monthly_payment(limit, test_rate, years) == pytest.approx(
        available_annual_payment / 12
    )


def test_dsr_limit_with_zero_interest() -> None:
    # 연소득 3,000만원 × DSR 40% = 연 1,200만원, 10년간 원금 1.2억원.
    assert dsr_loan_limit(3_000, 0.40, 0.0, 10) == pytest.approx(12_000.0)


def test_dsr_limit_with_zero_income() -> None:
    assert dsr_loan_limit(0, 0.40, 0.06, 30) == 0.0

