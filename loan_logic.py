"""대출 계산과 정책 판정을 담당하는 순수 함수 모음.

모든 금액은 만원, 금리는 소수(4.5% == 0.045) 단위다.
정책값은 예시 시뮬레이션용이며 실제 신청 전 최신 기준 확인이 필요하다.
"""

from __future__ import annotations

from dataclasses import dataclass


POLICY = {
    "gov_income_limit_newlywed": 8_500,
    "gov_asset_limit": 51_100,
    "gov_house_price_limit": 60_000,
    "gov_max_loan_newlywed": 32_000,
    "gov_ltv": 0.70,
    "gov_dti": 0.60,
    "market_ltv_non_regulated": 0.70,
    "market_ltv_regulated": 0.40,
    "bank_dsr": 0.40,
    "stress_rate": 0.015,
    "market_mortgage_rate": 0.045,
    "market_refund_loan_rate": 0.050,
    "existing_debt_annual_burden_ratio": 0.10,
}

NEWBORN_SPECIAL_LOAN = {
    "name": "신생아 특례 디딤돌대출",
    "income_limit": 13_000,
    "income_limit_dual_income": 20_000,
    "asset_limit": 51_100,
    "house_price_limit": 90_000,
    "max_loan": 40_000,
    "ltv": 0.70,
    "dti": 0.60,
    "rate_min": 0.018,
    "rate_max": 0.045,
    "available_terms": [10, 15, 20, 30],
}


def monthly_payment(principal: float, annual_rate: float, years: float) -> float:
    """원리금균등 월 상환액. 기간이나 원금이 0이면 0을 반환한다."""
    if principal <= 0 or years <= 0:
        return 0.0
    months = max(int(round(years * 12)), 1)
    monthly_rate = max(annual_rate, 0.0) / 12
    if monthly_rate == 0:
        return principal / months
    factor = (1 + monthly_rate) ** months
    return principal * monthly_rate * factor / (factor - 1)


def principal_from_monthly_payment(payment: float, annual_rate: float, years: float) -> float:
    """월 상환 가능액에서 원리금균등 대출원금을 역산한다."""
    if payment <= 0 or years <= 0:
        return 0.0
    months = max(int(round(years * 12)), 1)
    monthly_rate = max(annual_rate, 0.0) / 12
    if monthly_rate == 0:
        return payment * months
    factor = (1 + monthly_rate) ** months
    return payment * (factor - 1) / (monthly_rate * factor)


def dsr_loan_limit(
    annual_income: float,
    dsr_ratio: float,
    annual_rate: float,
    years: float,
    existing_debt: float = 0,
    existing_debt_burden_ratio: float = POLICY["existing_debt_annual_burden_ratio"],
) -> float:
    allowed_annual_payment = max(annual_income, 0) * max(dsr_ratio, 0)
    existing_annual_burden = max(existing_debt, 0) * max(existing_debt_burden_ratio, 0)
    available_monthly = max(allowed_annual_payment - existing_annual_burden, 0) / 12
    return principal_from_monthly_payment(available_monthly, annual_rate, years)


def remaining_balance(principal: float, annual_rate: float, years: float, elapsed_years: float) -> float:
    """원리금균등 대출의 경과 시점 잔액."""
    if principal <= 0 or years <= 0 or elapsed_years >= years:
        return 0.0
    if elapsed_years <= 0:
        return max(principal, 0.0)
    total_months = max(int(round(years * 12)), 1)
    paid_months = min(max(int(round(elapsed_years * 12)), 0), total_months)
    rate = max(annual_rate, 0.0) / 12
    if rate == 0:
        return principal * (total_months - paid_months) / total_months
    payment = monthly_payment(principal, annual_rate, years)
    factor = (1 + rate) ** paid_months
    return max(principal * factor - payment * (factor - 1) / rate, 0.0)


def select_government_rate(combined_income: float) -> float:
    if combined_income <= 2_000:
        return 0.031
    if combined_income <= 4_000:
        return 0.0345
    if combined_income <= 7_000:
        return 0.038
    return 0.0415


def select_newborn_special_rate(combined_income: float) -> float:
    """실제 금리는 신청 시점·우대금리·자녀 수 등에 따라 달라질 수 있다."""
    if combined_income <= 4_000:
        return 0.023
    if combined_income <= 7_000:
        return 0.028
    if combined_income <= 13_000:
        return 0.033
    if combined_income <= 20_000:
        return 0.040
    return 0.045


def government_loan_eligible(
    marriage_planned: bool,
    user_home_count: int,
    independent_head_planned: bool,
    combined_income: float,
    combined_assets: float,
    house_price: float,
) -> tuple[bool, list[str]]:
    checks = {
        "혼인·신혼부부 조건": marriage_planned,
        "사용자 무주택": user_home_count == 0,
        "세대주 독립 예정": independent_head_planned,
        "합산소득 기준": combined_income <= POLICY["gov_income_limit_newlywed"],
        "합산 순자산 기준": combined_assets <= POLICY["gov_asset_limit"],
        "주택가격 기준": house_price <= POLICY["gov_house_price_limit"],
    }
    return all(checks.values()), [name for name, passed in checks.items() if not passed]


@dataclass(frozen=True)
class NewbornEligibility:
    eligible: bool
    failed_conditions: list[str]
    ltv_limit: float
    dti_limit: float
    final_limit: float


def assess_newborn_eligibility(
    combined_income: float,
    dual_income: bool,
    combined_assets: float,
    house_price: float,
    requested_principal: float,
    annual_income_for_dti: float,
    annual_rate: float,
    years: int,
    max_loan: float = NEWBORN_SPECIAL_LOAN["max_loan"],
) -> NewbornEligibility:
    income_limit = NEWBORN_SPECIAL_LOAN["income_limit_dual_income"] if dual_income else NEWBORN_SPECIAL_LOAN["income_limit"]
    ltv_limit = max(house_price, 0) * NEWBORN_SPECIAL_LOAN["ltv"]
    dti_limit = dsr_loan_limit(annual_income_for_dti, NEWBORN_SPECIAL_LOAN["dti"], annual_rate, years)
    final_limit = min(ltv_limit, dti_limit, max_loan)
    checks = {
        "합산소득 기준": combined_income <= income_limit,
        "합산 순자산 기준": combined_assets <= NEWBORN_SPECIAL_LOAN["asset_limit"],
        "주택가격 기준": house_price <= NEWBORN_SPECIAL_LOAN["house_price_limit"],
        "정책 최대한도": requested_principal <= max_loan,
        "LTV 70%": requested_principal <= ltv_limit,
        "DTI 60%": requested_principal <= dti_limit,
    }
    failed = [name for name, passed in checks.items() if not passed]
    return NewbornEligibility(not failed, failed, ltv_limit, dti_limit, final_limit)
