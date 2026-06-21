"""한국어 금액·비율 표시 유틸리티."""


def format_amount(value: float, decimals: int = 0) -> str:
    value = float(value)
    man = f"{value:,.{decimals}f}만 원"
    if abs(value) >= 10_000:
        return f"{man} ({value / 10_000:.2f}억 원)"
    return man


def format_monthly(value: float) -> str:
    return f"월 {value:,.1f}만 원"


def format_annual(value: float) -> str:
    return f"연 {value:,.1f}만 원"


def format_rate(value: float) -> str:
    return f"{value * 100:.2f}%"


def format_gap(value: float) -> str:
    if value > 0:
        return f"부족 {format_amount(value, 1)}"
    if value < 0:
        return f"여유 {format_amount(abs(value), 1)}"
    return "부족·여유 없음"
