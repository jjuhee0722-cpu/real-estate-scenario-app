from __future__ import annotations

import json
import os
import pandas as pd
import streamlit as st
import sys
from typing import Optional

from format_utils import format_amount, format_annual, format_gap, format_monthly, format_rate
from loan_logic import (
    NEWBORN_SPECIAL_LOAN, POLICY, assess_newborn_eligibility,
    government_loan_eligible, select_government_rate, select_newborn_special_rate,
)
from scenario_calculator import calculate_refinance, calculate_scenario


st.set_page_config(page_title="부동산 주거 시나리오 비교", page_icon="🏠", layout="wide")

BROWSER_STORAGE_PATH = "/mnt/real_estate_inputs.json"
IS_BROWSER_RUNTIME = sys.platform == "emscripten"


def load_saved_inputs() -> dict:
    """stlite 브라우저 저장소에서 이전 입력값을 읽는다."""
    if not IS_BROWSER_RUNTIME:
        return {}
    try:
        with open(BROWSER_STORAGE_PATH, "r", encoding="utf-8") as saved_file:
            data = json.load(saved_file)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


SAVED_INPUTS = load_saved_inputs()


def saved_value(key: str, default):
    return SAVED_INPUTS.get(key, default)


def saved_index(key: str, options: list, default_index: int) -> int:
    value = saved_value(key, options[default_index])
    try:
        return options.index(value)
    except ValueError:
        return default_index


def save_browser_inputs(values: dict) -> None:
    """공개 stlite 앱에서 입력값을 IndexedDB-backed 파일로 자동 저장한다."""
    if not IS_BROWSER_RUNTIME:
        return
    try:
        with open(BROWSER_STORAGE_PATH, "w", encoding="utf-8") as saved_file:
            json.dump(values, saved_file, ensure_ascii=False, indent=2)
    except OSError:
        # 저장소 접근이 차단돼도 계산 기능은 계속 동작해야 한다.
        pass


def reset_browser_inputs() -> None:
    if not IS_BROWSER_RUNTIME:
        return
    try:
        os.remove(BROWSER_STORAGE_PATH)
    except FileNotFoundError:
        pass
    st.session_state.clear()
    st.rerun()

st.markdown(
    """
    <style>
    .block-container {padding-top: 2rem; padding-bottom: 3rem; max-width: 1400px;}
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {line-height: 1.45;}
    [data-testid="stMetric"] {
        background: linear-gradient(145deg, #ffffff 0%, #f7f9fc 100%);
        border: 1px solid #e5e9f0;
        border-radius: 14px;
        padding: 1rem 1.1rem;
        box-shadow: 0 4px 14px rgba(15, 23, 42, 0.04);
    }
    [data-testid="stMetricLabel"] {font-weight: 650; color: #475569;}
    [data-testid="stMetricValue"] {font-weight: 750; color: #0f172a;}
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 16px;
        border-color: #e2e8f0;
        background: #ffffff;
        box-shadow: 0 6px 18px rgba(15, 23, 42, 0.04);
    }
    .app-kicker {color: #2563eb; font-weight: 700; margin-bottom: .2rem;}
    .app-description {color: #475569; font-size: 1.02rem; margin-top: -.35rem;}
    .section-note {color: #64748b; font-size: .92rem;}
    @media (max-width: 700px) {
        .block-container {padding-top: 1rem; padding-left: 1rem; padding-right: 1rem;}
        h1 {font-size: 1.75rem !important;}
        [data-testid="stMetric"] {padding: .8rem .9rem;}
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def money_input(
    label: str,
    value: int,
    key: str,
    help_text: Optional[str] = None,
    container=None,
) -> float:
    """만원 단위 입력. 기본 위치는 Sidebar이며 다른 컨테이너도 받을 수 있다."""
    target = container if container is not None else st.sidebar
    initial_value = int(round(float(saved_value(key, value))))
    return float(target.number_input(label, min_value=0, value=initial_value, step=100, key=key, help=help_text))


def scenario_inputs(container, prefix: str, defaults: tuple[int, ...]) -> dict[str, float]:
    labels = ["총 필요자금", "내 현금 액수", "남자친구 현금 액수", "필요 대출금", "부대비용", "기타비용"]
    keys = ["total_need", "my_cash", "boyfriend_cash", "loan_needed", "extra_cost", "other_cost"]
    return {
        key: money_input(f"{label} (만원)", default, f"{prefix}_{key}", container=container)
        for label, key, default in zip(labels, keys, defaults)
    }


def chart_data(a, b, fields: list[tuple[str, str]]) -> pd.DataFrame:
    rows = []
    for label, field in fields:
        rows.extend([
            {"구분": label, "시나리오": "시나리오 A", "금액(만원)": getattr(a, field)},
            {"구분": label, "시나리오": "시나리오 B", "금액(만원)": getattr(b, field)},
        ])
    return pd.DataFrame(rows)


st.sidebar.title("🏠 입력 조건")
st.sidebar.caption("모든 금액의 입력 단위는 만원입니다.")
if IS_BROWSER_RUNTIME:
    st.sidebar.caption("💾 입력값은 현재 브라우저에 자동 저장됩니다.")

basic_section = st.sidebar.expander("1. 기본 조건", expanded=True)
marriage_planned = basic_section.checkbox("혼인신고 예정", value=bool(saved_value("marriage_planned", True)), key="marriage_planned")
independent_head = basic_section.checkbox("향후 세대주 독립 예정", value=bool(saved_value("independent_head", True)), key="independent_head")
home_options = [0, 1, 2]
user_home_count = basic_section.selectbox(
    "사용자 현재 주택 소유", home_options, index=saved_index("user_home_count", home_options, 0),
    format_func=lambda x: "무주택" if x == 0 else f"{x}주택", key="user_home_count",
)
boyfriend_home_count = basic_section.selectbox(
    "남자친구 현재 주택 소유", home_options, index=saved_index("boyfriend_home_count", home_options, 1),
    format_func=lambda x: "무주택" if x == 0 else f"{x}주택", key="boyfriend_home_count",
)
combined_assets = money_input("합산 순자산 (만원)", 20_000, "combined_assets", container=basic_section)
user_income = money_input("사용자 연봉 (만원)", 4_400, "user_income", container=basic_section)
boyfriend_income = money_input("남자친구 연봉 (만원)", 4_400, "boyfriend_income", container=basic_section)
user_debt = money_input("사용자 기존 대출 잔액 (만원)", 0, "user_debt", container=basic_section)
boyfriend_debt = money_input("남자친구 기존 부채 잔액 (만원)", 0, "boyfriend_debt", container=basic_section)
loan_year_options = [10, 15, 20, 30, 35, 40]
loan_years = basic_section.selectbox(
    "대출기간", loan_year_options, index=saved_index("loan_years", loan_year_options, 3),
    format_func=lambda x: f"{x}년", key="loan_years",
)
regulated = basic_section.checkbox("규제지역", value=bool(saved_value("regulated", False)), key="regulated")
stress_dsr = basic_section.checkbox("스트레스 DSR 적용", value=bool(saved_value("stress_dsr", True)), key="stress_dsr")

a_section = st.sidebar.expander("2. 시나리오 A 입력", expanded=True)
a_section.caption("화정동 아파트 사용자 명의 단독 매수")
a_input = scenario_inputs(a_section, "a", (60_000, 15_000, 0, 45_000, 1_500, 0))

b_section = st.sidebar.expander("3. 시나리오 B 입력", expanded=False)
b_section.caption("남자친구 집 전세금 반환 후 입주")
b_input = scenario_inputs(b_section, "b", (32_000, 15_000, 0, 17_000, 300, 0))

refinance_section = st.sidebar.expander("4. 신생아 특례대출 대환", expanded=False)
refinance_enabled = refinance_section.checkbox(
    "신생아 특례대출 대환 적용", value=bool(saved_value("refinance_enabled", False)), key="refinance_enabled"
)
elapsed_years = float(refinance_section.number_input(
    "대환 예상 시점 (년)", min_value=0.0, value=float(saved_value("elapsed_years", 3.0)), step=0.5, key="elapsed_years"
))
newborn_terms = NEWBORN_SPECIAL_LOAN["available_terms"]
newborn_years = refinance_section.selectbox(
    "신생아 특례대출 기간", newborn_terms, index=saved_index("newborn_years", newborn_terms, 3),
    format_func=lambda x: f"{x}년", key="newborn_years",
)
apply_fee = refinance_section.checkbox(
    "중도상환수수료 반영", value=bool(saved_value("apply_fee", False)), key="apply_fee"
)
refinance_other_cost = money_input("대환 관련 기타비용 (만원)", 0, "refinance_other_cost", container=refinance_section)

combined_income = user_income + boyfriend_income
auto_gov_rate = select_government_rate(combined_income)
auto_newborn_rate = select_newborn_special_rate(combined_income)

advanced = st.sidebar.expander("5. 고급 설정", expanded=False)
with advanced:
    override_gov = advanced.checkbox(
        "정부지원 금리 수동 조정", value=bool(saved_value("override_gov", False)), key="override_gov"
    )
    gov_rate_input = advanced.number_input(
        "정부지원 대출 금리 (%)", 0.0, 20.0, float(saved_value("gov_rate_pct", auto_gov_rate * 100)), 0.05,
        key="gov_rate_pct",
    ) / 100
    market_rate = advanced.number_input(
        "시중 주담대 금리 (%)", 0.0, 20.0, float(saved_value("market_rate_pct", POLICY["market_mortgage_rate"] * 100)), 0.05,
        key="market_rate_pct",
    ) / 100
    refund_rate = advanced.number_input(
        "전세금 반환 대출 금리 (%)", 0.0, 20.0, float(saved_value("refund_rate_pct", POLICY["market_refund_loan_rate"] * 100)), 0.05,
        key="refund_rate_pct",
    ) / 100
    override_newborn = advanced.checkbox(
        "신생아 특례 금리 수동 조정", value=bool(saved_value("override_newborn", False)), key="override_newborn"
    )
    newborn_rate_input = advanced.number_input(
        "신생아 특례대출 금리 (%)", 0.0, 20.0, float(saved_value("newborn_rate_pct", auto_newborn_rate * 100)), 0.05,
        key="newborn_rate_pct",
    ) / 100
    dsr_ratio = advanced.number_input(
        "DSR 비율 (%)", 0.0, 100.0, float(saved_value("dsr_ratio_pct", POLICY["bank_dsr"] * 100)), 1.0,
        key="dsr_ratio_pct",
    ) / 100
    stress_rate = advanced.number_input(
        "스트레스 금리 (%p)", 0.0, 20.0, float(saved_value("stress_rate_pct", POLICY["stress_rate"] * 100)), 0.1,
        key="stress_rate_pct",
    ) / 100
    market_ltv_default = POLICY["market_ltv_regulated"] if regulated else POLICY["market_ltv_non_regulated"]
    market_ltv = advanced.number_input(
        "일반대출 LTV (%)", 0.0, 100.0, float(saved_value("market_ltv_pct", market_ltv_default * 100)), 1.0,
        key="market_ltv_pct",
    ) / 100
    newborn_max_loan = money_input(
        "신생아 특례 최대한도 (만원)",
        int(NEWBORN_SPECIAL_LOAN["max_loan"]),
        "newborn_max",
        container=advanced,
    )
    fee_rate_input = advanced.number_input(
        "중도상환수수료율 (%)", 0.0, 10.0, float(saved_value("fee_rate_pct", 0.0)), 0.05,
        key="fee_rate_pct",
    ) / 100

browser_inputs = {
    "marriage_planned": marriage_planned,
    "independent_head": independent_head,
    "user_home_count": user_home_count,
    "boyfriend_home_count": boyfriend_home_count,
    "combined_assets": combined_assets,
    "user_income": user_income,
    "boyfriend_income": boyfriend_income,
    "user_debt": user_debt,
    "boyfriend_debt": boyfriend_debt,
    "loan_years": loan_years,
    "regulated": regulated,
    "stress_dsr": stress_dsr,
    **{f"a_{key}": value for key, value in a_input.items()},
    **{f"b_{key}": value for key, value in b_input.items()},
    "refinance_enabled": refinance_enabled,
    "elapsed_years": elapsed_years,
    "newborn_years": newborn_years,
    "apply_fee": apply_fee,
    "refinance_other_cost": refinance_other_cost,
    "override_gov": override_gov,
    "gov_rate_pct": gov_rate_input * 100,
    "market_rate_pct": market_rate * 100,
    "refund_rate_pct": refund_rate * 100,
    "override_newborn": override_newborn,
    "newborn_rate_pct": newborn_rate_input * 100,
    "dsr_ratio_pct": dsr_ratio * 100,
    "stress_rate_pct": stress_rate * 100,
    "market_ltv_pct": market_ltv * 100,
    "newborn_max": newborn_max_loan,
    "fee_rate_pct": fee_rate_input * 100,
}
save_browser_inputs(browser_inputs)

if IS_BROWSER_RUNTIME:
    if st.sidebar.button("저장값 초기화", key="reset_saved_inputs", width="stretch"):
        reset_browser_inputs()

gov_rate = gov_rate_input if override_gov else auto_gov_rate
newborn_rate = newborn_rate_input if override_newborn else auto_newborn_rate
fee_rate = fee_rate_input if apply_fee else 0.0

gov_eligible, gov_failed = government_loan_eligible(
    marriage_planned, user_home_count, independent_head, combined_income,
    combined_assets, a_input["total_need"],
)
if gov_eligible:
    a_type, a_rate, a_ltv, a_policy_max = "정부지원 대출 가능", gov_rate, POLICY["gov_ltv"], POLICY["gov_max_loan_newlywed"]
else:
    a_type, a_rate, a_ltv, a_policy_max = "일반 은행 주택담보대출", market_rate, market_ltv, None

a = calculate_scenario(
    scenario_name="시나리오 A", **a_input, annual_rate=a_rate,
    dsr_test_rate=a_rate + stress_rate if stress_dsr else a_rate,
    loan_years=loan_years, ltv=a_ltv, max_policy_loan=a_policy_max,
    income_for_dsr=user_income, existing_debt=user_debt, dsr_ratio=dsr_ratio,
    loan_type=a_type, existing_debt_burden_ratio=POLICY["existing_debt_annual_burden_ratio"],
)
b = calculate_scenario(
    scenario_name="시나리오 B", **b_input, annual_rate=refund_rate,
    dsr_test_rate=refund_rate + stress_rate if stress_dsr else refund_rate,
    loan_years=loan_years, ltv=market_ltv, max_policy_loan=None,
    income_for_dsr=boyfriend_income, existing_debt=boyfriend_debt, dsr_ratio=dsr_ratio,
    loan_type="전세금 반환 또는 일반 담보대출", existing_debt_burden_ratio=POLICY["existing_debt_annual_burden_ratio"],
)

formatters = {"money": lambda v: format_amount(v, 1), "rate": format_rate, "gap": format_gap,
              "monthly": format_monthly, "annual": format_annual, "text": str}


def render_comparison_table(rows: list[tuple[str, str, str]]) -> None:
    table = {"항목": [], "시나리오 A": [], "시나리오 B": []}
    for label, field, kind in rows:
        table["항목"].append(label)
        table["시나리오 A"].append(formatters[kind](getattr(a, field)))
        table["시나리오 B"].append(formatters[kind](getattr(b, field)))
    st.dataframe(pd.DataFrame(table).set_index("항목"), width="stretch")


def show_funding_status(result) -> None:
    if result.funding_gap > 0:
        st.warning(f"부족자금 {format_amount(result.funding_gap, 1)}이 발생합니다.")
    elif result.funding_gap < 0:
        st.success(f"여유자금 {format_amount(abs(result.funding_gap), 1)}이 남습니다.")
    else:
        st.success("입력한 자금계획이 정확히 일치합니다.")


st.markdown('<div class="app-kicker">HOUSING FINANCE PLANNER</div>', unsafe_allow_html=True)
st.title("부동산 주거 시나리오 비교")
st.markdown(
    '<div class="app-description">직접 입력한 자금계획을 바탕으로 두 주거 시나리오의 현금 부담, 대출한도와 월 상환액을 한눈에 비교합니다.</div>',
    unsafe_allow_html=True,
)
st.caption("금액 단위는 만원이며, 주요 결과에는 억 원 환산값을 함께 표시합니다.")
st.info("본 계산기는 의사결정 보조용입니다. 실제 대출 가능 여부와 금리는 은행 심사 및 최신 정책 기준에 따라 달라질 수 있습니다.")

st.subheader("핵심 결과")
top_metrics = st.columns(3)
top_metrics[0].metric("시나리오 A 월 상환액", format_monthly(a.monthly_payment))
top_metrics[1].metric("시나리오 B 월 상환액", format_monthly(b.monthly_payment))
top_metrics[2].metric("월 상환액 차이", format_amount(abs(a.monthly_payment - b.monthly_payment), 1))
funding_metrics = st.columns(2)
funding_metrics[0].metric("시나리오 A 부족·여유자금", format_gap(a.funding_gap))
funding_metrics[1].metric("시나리오 B 부족·여유자금", format_gap(b.funding_gap))

st.subheader("시나리오별 결과")
card_a, card_b = st.columns(2)
with card_a:
    with st.container(border=True):
        st.markdown("### 🏢 시나리오 A")
        st.caption("화정동 아파트 사용자 명의 단독 매수")
        a_card_metrics = st.columns(2)
        a_card_metrics[0].metric("실제 총 필요자금", format_amount(a.actual_total_need, 1))
        a_card_metrics[1].metric("총 현금 투입액", format_amount(a.total_cash, 1))
        st.metric("필요 대출금", format_amount(a.loan_needed, 1))
        st.markdown(f"**적용 대출**  ·  {a.loan_type}  ·  {format_rate(a.annual_rate)}")
        st.markdown(f"**최종 가능 한도**  ·  {format_amount(a.final_loan_limit, 1)}")
        show_funding_status(a)

with card_b:
    with st.container(border=True):
        st.markdown("### 🏠 시나리오 B")
        st.caption("남자친구 집 전세금 반환 후 입주")
        b_card_metrics = st.columns(2)
        b_card_metrics[0].metric("실제 총 필요자금", format_amount(b.actual_total_need, 1))
        b_card_metrics[1].metric("총 현금 투입액", format_amount(b.total_cash, 1))
        st.metric("필요 대출금", format_amount(b.loan_needed, 1))
        st.markdown(f"**적용 대출**  ·  {b.loan_type}  ·  {format_rate(b.annual_rate)}")
        st.markdown(f"**최종 가능 한도**  ·  {format_amount(b.final_loan_limit, 1)}")
        show_funding_status(b)

st.subheader("상세 비교")
st.markdown("#### ① 자금 구성")
render_comparison_table([
    ("총 필요자금", "total_need", "money"),
    ("부대비용", "extra_cost", "money"),
    ("기타비용", "other_cost", "money"),
    ("실제 총 필요자금", "actual_total_need", "money"),
    ("총 현금 투입액", "total_cash", "money"),
    ("필요 대출금", "loan_needed", "money"),
    ("부족자금 또는 여유자금", "funding_gap", "gap"),
])
st.divider()
st.markdown("#### ② 대출 조건과 한도")
render_comparison_table([
    ("적용 대출유형", "loan_type", "text"),
    ("적용 금리", "annual_rate", "rate"),
    ("DSR 심사용 금리", "dsr_test_rate", "rate"),
    ("LTV 기준 대출한도", "ltv_limit", "money"),
    ("DSR 기준 대출한도", "dsr_limit", "money"),
    ("최종 가능 대출한도", "final_loan_limit", "money"),
    ("대출한도 초과액", "loan_limit_excess", "money"),
])
st.divider()
st.markdown("#### ③ 상환 부담")
render_comparison_table([
    ("예상 월 원리금 상환액", "monthly_payment", "monthly"),
    ("예상 연간 상환액", "annual_payment", "annual"),
])

st.subheader("비교 차트")
left, right = st.columns(2)
with left:
    st.subheader("자금 구성 비교")
    st.bar_chart(chart_data(a, b, [("실제 총 필요자금", "actual_total_need"), ("현금 투입액", "total_cash"), ("필요 대출금", "loan_needed")]), x="구분", y="금액(만원)", color="시나리오")
with right:
    st.subheader("월 상환액 비교")
    st.bar_chart(pd.DataFrame({"시나리오": ["시나리오 A", "시나리오 B"], "월 상환액(만원)": [a.monthly_payment, b.monthly_payment]}).set_index("시나리오"))

st.subheader("부족·여유자금 비교")
st.bar_chart(pd.DataFrame({"시나리오": ["시나리오 A", "시나리오 B"], "부족(+)/여유(-), 만원": [a.funding_gap, b.funding_gap]}).set_index("시나리오"))

refi = None
if refinance_enabled:
    refi_panel = st.expander("👶 신생아 특례대출 대환 결과", expanded=True)
    refi = calculate_refinance(
        principal=a.loan_needed, original_rate=a.annual_rate, original_years=loan_years,
        elapsed_years=elapsed_years, new_rate=newborn_rate, new_years=newborn_years,
        prepayment_fee_rate=fee_rate, other_cost=refinance_other_cost, max_new_loan=newborn_max_loan,
    )
    newborn_check = assess_newborn_eligibility(
        combined_income, user_income > 0 and boyfriend_income > 0, combined_assets,
        a.total_need, refi["desired_new_principal"], combined_income, newborn_rate,
        newborn_years, newborn_max_loan,
    )
    if newborn_check.eligible:
        refi_panel.success("입력값 기준 신생아 특례대출 대환 조건을 충족하는 것으로 시뮬레이션됩니다.")
    else:
        refi_panel.warning("입력값 기준 신생아 특례대출 대환 조건을 만족하지 못할 수 있습니다. 단순 금리 비교 결과를 표시합니다. 미충족: " + ", ".join(newborn_check.failed_conditions))
    if refi["uncovered"] > 0:
        refi_panel.warning(f"대환 필요금이 설정한 최대한도를 초과해 {format_amount(refi['uncovered'], 1)}의 별도 자금이 필요합니다.")
    refi_metrics_top = refi_panel.columns(2)
    refi_metrics_top[0].metric("대환 시점 남은 원금", format_amount(refi["balance"], 1))
    refi_metrics_top[1].metric("대환 후 월 상환액", format_monthly(refi["new_monthly"]))
    refi_metrics_bottom = refi_panel.columns(2)
    refi_metrics_bottom[0].metric("월 절감액", format_amount(refi["monthly_saving"], 1))
    refi_metrics_bottom[1].metric("연 절감액", format_amount(refi["annual_saving"], 1))
    refi_panel.metric("총 이자 절감액", format_amount(refi["interest_saving"], 1))
    refi_panel.divider()
    refi_panel.markdown("#### 시나리오 A 대환 후 vs 시나리오 B")
    refi_panel.caption("시나리오 B에는 신생아 특례대출을 적용하지 않고, 입력된 기존 대출 조건을 그대로 사용합니다.")
    a_refi_vs_b_difference = refi["new_monthly"] - b.monthly_payment
    comparison_metrics = refi_panel.columns(2)
    comparison_metrics[0].metric("A 대환 후 월 상환액", format_monthly(refi["new_monthly"]))
    comparison_metrics[1].metric("B 월 상환액 (특례 미적용)", format_monthly(b.monthly_payment))
    if a_refi_vs_b_difference > 0:
        refi_panel.info(
            f"시나리오 B의 월 상환액이 A의 신생아 특례 대환 후보다 "
            f"{format_amount(a_refi_vs_b_difference, 1)} 낮습니다."
        )
    elif a_refi_vs_b_difference < 0:
        refi_panel.success(
            f"시나리오 A의 신생아 특례 대환 후 월 상환액이 B보다 "
            f"{format_amount(abs(a_refi_vs_b_difference), 1)} 낮습니다."
        )
    else:
        refi_panel.info("시나리오 A의 신생아 특례 대환 후와 시나리오 B의 월 상환액이 같습니다.")

    three_way_comparison = pd.DataFrame(
        {
            "항목": ["대출 구분", "적용 금리", "대출기간", "월 상환액", "연 상환액", "초기 현금 투입액", "대환 추가 필요현금"],
            "A 기존대출 유지": [
                a.loan_type,
                format_rate(a.annual_rate),
                f"잔여 {max(loan_years - elapsed_years, 0):g}년",
                format_monthly(refi["old_monthly"]),
                format_annual(refi["old_monthly"] * 12),
                format_amount(a.total_cash, 1),
                format_amount(0, 1),
            ],
            "A 신생아 특례 대환": [
                NEWBORN_SPECIAL_LOAN["name"],
                format_rate(newborn_rate),
                f"{newborn_years}년",
                format_monthly(refi["new_monthly"]),
                format_annual(refi["new_monthly"] * 12),
                format_amount(a.total_cash, 1),
                format_amount(refi["uncovered"], 1),
            ],
            "B 현재 조건 (특례 미적용)": [
                b.loan_type,
                format_rate(b.annual_rate),
                f"{loan_years}년",
                format_monthly(b.monthly_payment),
                format_annual(b.annual_payment),
                format_amount(b.total_cash, 1),
                "해당 없음",
            ],
        }
    ).set_index("항목")
    refi_panel.dataframe(three_way_comparison, width="stretch")
    refi_table = {
        "기존 시나리오 A 대출금": format_amount(a.loan_needed), "기존 대출금리": format_rate(a.annual_rate),
        "기존 대출기간": f"{loan_years}년", "대환 예상 시점": f"{elapsed_years:g}년",
        "대환 시점 남은 원금": format_amount(refi["balance"], 1), "중도상환수수료": format_amount(refi["prepayment_fee"], 1),
        "대환 관련 기타비용": format_amount(refi["other_cost"], 1), "신생아 특례대출 원금": format_amount(refi["new_principal"], 1),
        "신생아 특례대출 금리": format_rate(newborn_rate), "신생아 특례대출 기간": f"{newborn_years}년",
        "대환 전 월 상환액": format_monthly(refi["old_monthly"]), "대환 후 월 상환액": format_monthly(refi["new_monthly"]),
        "월 절감액": format_amount(refi["monthly_saving"], 1), "연 절감액": format_amount(refi["annual_saving"], 1),
        "기존 대출 유지 시 잔여 총상환액": format_amount(refi["old_remaining_total"], 1),
        "대환 후 총상환액": format_amount(refi["new_total"], 1),
        "기존 대출 유지 시 잔여 이자": format_amount(refi["old_remaining_interest"], 1),
        "대환 후 총 이자": format_amount(refi["new_interest"], 1),
        "예상 총 이자 절감액": format_amount(refi["interest_saving"], 1),
        "현금 보충 포함 총상환 차이": format_amount(refi["total_outflow_saving"], 1),
    }
    refi_panel.dataframe(pd.DataFrame.from_dict(refi_table, orient="index", columns=["계산 결과"]), width="stretch")
    refi_panel.bar_chart(
        pd.DataFrame(
            {
                "구분": ["A 기존대출 유지", "A 신생아 특례 대환", "B 현재 조건"],
                "월 상환액(만원)": [refi["old_monthly"], refi["new_monthly"], b.monthly_payment],
            }
        ).set_index("구분")
    )

st.subheader("자동 판단 코멘트")
monthly_low = "A" if a.monthly_payment < b.monthly_payment else "B"
cash_low = "A" if a.total_cash < b.total_cash else "B"
st.info(f"현재 입력값 기준 시나리오 {monthly_low}의 월 상환 부담이 더 낮고, 시나리오 {cash_low}의 초기 현금 투입액이 더 낮습니다.")
if not gov_eligible:
    st.info("시나리오 A 정부지원 대출 조건 미충족 항목: " + ", ".join(gov_failed))
else:
    st.success("시나리오 A는 입력값 기준 정부지원 대출 가능 조건을 충족합니다.")
for result in (a, b):
    if result.loan_limit_excess > 0:
        st.warning(f"{result.name}의 필요 대출금이 자동 산출 한도를 {format_amount(result.loan_limit_excess, 1)} 초과합니다.")
    if result.funding_gap > 0:
        st.warning(f"{result.name}에 {format_amount(result.funding_gap, 1)}의 부족자금이 있습니다. 추가 현금 확보 또는 자금계획 조정이 필요합니다.")
st.info("시나리오 B는 남자친구 명의의 기존 주택, 임대차계약 종료·보증금 반환 일정, 담보대출 심사 구조를 별도로 확인해야 합니다.")
if refi:
    direction = "감소" if refi["monthly_saving"] >= 0 else "증가"
    st.info(f"신생아 특례대출 대환 시 월 상환액은 약 {format_amount(abs(refi['monthly_saving']), 1)} {direction}하는 것으로 계산됩니다. 실제 적용 가능성은 출산 시점·소득·자산·주택가격·대환 요건에 따라 달라집니다.")
    refi_vs_b = refi["new_monthly"] - b.monthly_payment
    if refi_vs_b == 0:
        st.info("신생아 특례는 A에만 적용해 비교했으며, A 대환 후와 B의 월 부담이 같습니다.")
    else:
        lower_label = "시나리오 B" if refi_vs_b > 0 else "시나리오 A 대환 후"
        st.info(f"신생아 특례는 A에만 적용해 비교했으며, 월 부담은 {lower_label}가 {format_amount(abs(refi_vs_b), 1)} 낮습니다.")

with st.expander("계산 가정과 꼭 확인할 점"):
    st.markdown("""
    - 모든 금액은 **만원**, 상환 방식은 **원리금균등상환**입니다.
    - 시나리오 A의 DSR은 사용자 소득·부채, 시나리오 B는 남자친구 소득·부채를 사용합니다.
    - 기존 부채의 연간 부담은 잔액의 10%로 단순 가정합니다.
    - 대환 비교의 ‘총 이자 절감액’은 대환 시점 이후 이자끼리 비교한 값입니다. ‘현금 보충 포함 총상환 차이’에는 대환 한도 초과로 별도 투입하는 현금도 반영합니다.
    - 정책값은 예시 기본값입니다. 실제 신청 전 주택도시기금과 취급은행의 최신 기준을 반드시 확인하세요.
    """)
