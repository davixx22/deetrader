from decimal import Decimal as D


def max_drawdown(values: list[D]) -> D:
    peak = values[0]
    drawdown = D("0")
    for value in values:
        peak = max(peak, value)
        drawdown = max(drawdown, peak - value)
    return drawdown


def test_max_drawdown():
    assert max_drawdown([D("500"), D("520"), D("490"), D("510")]) == D("30")
