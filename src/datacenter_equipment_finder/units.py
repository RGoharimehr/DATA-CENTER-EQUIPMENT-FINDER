from __future__ import annotations

MM_PER_INCH = 25.4
KW_PER_TON = 3.5168525
PSI_PER_BAR = 14.5037738
KV_PER_CV = 0.865


def mm_to_inch(mm: float) -> float:
    return mm / MM_PER_INCH


def inch_to_mm(inch: float) -> float:
    return inch * MM_PER_INCH


def tons_to_kw(tons: float) -> float:
    return tons * KW_PER_TON


def kw_to_tons(kw: float) -> float:
    return kw / KW_PER_TON


def bar_to_psi(bar: float) -> float:
    return bar * PSI_PER_BAR


def psi_to_bar(psi: float) -> float:
    return psi / PSI_PER_BAR


def cv_to_kv(cv: float) -> float:
    return cv * KV_PER_CV


def kv_to_cv(kv: float) -> float:
    return kv / KV_PER_CV
