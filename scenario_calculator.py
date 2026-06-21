"""시나리오 및 대환 비교 계산."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional

from loan_logic import dsr_loan_limit, monthly_payment, remaining_balance


@dataclass
class ScenarioResult:
    name: str
    total_need: float
    my_cash: float
    boyfriend_cash: float
    loan_needed: float
    extra_cost: float
    other_cost: float
    loan_type: str
    annual_rate: float
    dsr_test_rate: float
    loan_years: int
    ltv: float
    total_cash: float
    actual_total_need: float
    funding_gap: float
    monthly_payment: float
    annual_payment: float
    ltv_limit: float
    dsr_limit: float
    final_loan_limit: float
    loan_limit_excess: float

    def to_dict(self) -> dict:
        return asdict(self)


def calculate_scenario(
    *, scenario_name: str, total_need: float, my_cash: float, boyfriend_cash: float,
    loan_needed: float, extra_cost: float, other_cost: float, annual_rate: float,
    dsr_test_rate: float, loan_years: int, ltv: float, max_policy_loan: Optional[float],
    income_for_dsr: float, existing_debt: float, dsr_ratio: float, loan_type: str,
    existing_debt_burden_ratio: float,
) -> ScenarioResult:
    total_cash = my_cash + boyfriend_cash
    actual_total_need = total_need + extra_cost + other_cost
    funding_gap = actual_total_need - total_cash - loan_needed
    ltv_limit = max(total_need, 0) * max(ltv, 0)
    dsr_limit = dsr_loan_limit(
        income_for_dsr, dsr_ratio, dsr_test_rate, loan_years,
        existing_debt, existing_debt_burden_ratio,
    )
    limits = [ltv_limit, dsr_limit]
    if max_policy_loan is not None:
        limits.append(max_policy_loan)
    final_limit = min(limits)
    payment = monthly_payment(loan_needed, annual_rate, loan_years)
    return ScenarioResult(
        scenario_name, total_need, my_cash, boyfriend_cash, loan_needed, extra_cost,
        other_cost, loan_type, annual_rate, dsr_test_rate, loan_years, ltv,
        total_cash, actual_total_need, funding_gap, payment, payment * 12,
        ltv_limit, dsr_limit, final_limit, max(loan_needed - final_limit, 0),
    )


def calculate_refinance(
    *, principal: float, original_rate: float, original_years: int,
    elapsed_years: float, new_rate: float, new_years: int,
    prepayment_fee_rate: float, other_cost: float, max_new_loan: float,
) -> dict[str, float]:
    balance = remaining_balance(principal, original_rate, original_years, elapsed_years)
    fee = balance * max(prepayment_fee_rate, 0)
    desired_new_principal = balance + fee + max(other_cost, 0)
    new_principal = min(desired_new_principal, max(max_new_loan, 0))
    uncovered = max(desired_new_principal - new_principal, 0)
    remaining_months = max(int(round((original_years - elapsed_years) * 12)), 0)
    old_monthly = monthly_payment(principal, original_rate, original_years) if remaining_months else 0.0
    old_remaining_total = old_monthly * remaining_months
    new_monthly = monthly_payment(new_principal, new_rate, new_years)
    new_total = new_monthly * new_years * 12
    old_remaining_interest = max(old_remaining_total - balance, 0.0)
    new_interest = max(new_total - new_principal, 0.0)
    interest_saving = old_remaining_interest - new_interest
    # 한도 초과분은 대환 시 현금으로 보충한다고 보고 전체 현금유출 비교에 포함한다.
    total_outflow_saving = old_remaining_total - new_total - uncovered
    return {
        "balance": balance, "prepayment_fee": fee, "other_cost": other_cost,
        "desired_new_principal": desired_new_principal, "new_principal": new_principal,
        "uncovered": uncovered, "old_monthly": old_monthly, "new_monthly": new_monthly,
        "monthly_saving": old_monthly - new_monthly,
        "annual_saving": (old_monthly - new_monthly) * 12,
        "old_remaining_total": old_remaining_total, "new_total": new_total,
        "old_remaining_interest": old_remaining_interest, "new_interest": new_interest,
        "interest_saving": interest_saving, "total_outflow_saving": total_outflow_saving,
    }


def cumulative_loan_payments(
    principal: float,
    annual_rate: float,
    years: float,
    elapsed_years: float,
) -> float:
    """대출 시작 후 경과 시점까지 납부한 누적 원리금."""
    if principal <= 0 or years <= 0 or elapsed_years <= 0:
        return 0.0
    total_months = max(int(round(years * 12)), 0)
    elapsed_months = max(int(round(elapsed_years * 12)), 0)
    paid_months = min(elapsed_months, total_months)
    return monthly_payment(principal, annual_rate, years) * paid_months


def cumulative_refinance_payments(
    *,
    original_monthly: float,
    original_years: float,
    refinance_after_years: float,
    new_monthly: float,
    new_years: float,
    elapsed_years: float,
) -> float:
    """대환 전·후 납부액을 연결한 경과 시점 누적 원리금."""
    if elapsed_years <= 0:
        return 0.0
    target_months = max(int(round(elapsed_years * 12)), 0)
    original_total_months = max(int(round(original_years * 12)), 0)
    requested_refinance_month = max(int(round(refinance_after_years * 12)), 0)
    if requested_refinance_month >= original_total_months:
        return max(original_monthly, 0) * min(target_months, original_total_months)
    refinance_month = min(
        requested_refinance_month,
        original_total_months,
    )
    old_paid_months = min(target_months, refinance_month)
    new_total_months = max(int(round(new_years * 12)), 0)
    new_paid_months = min(max(target_months - refinance_month, 0), new_total_months)
    return max(original_monthly, 0) * old_paid_months + max(new_monthly, 0) * new_paid_months
