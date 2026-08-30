"""Deterministic, auditable compliance pre-checks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ComplianceCheck:
    amount: float
    scope: str
    required_steps: list[str]
    risk_flags: list[str]
    basis: list[str]
    next_action: str


def check_procurement(amount: float, scope: str = "集团总部及所属全资、控股子公司") -> ComplianceCheck:
    """Evaluate the sample CG-2026-001 procurement approval thresholds."""
    if amount < 0:
        raise ValueError("amount must be non-negative")
    steps = ["预算确认", "需求论证"]
    basis = ["采购管理办法 CG-2026-001，V2.1，第1条"]
    if amount >= 1_000_000:
        steps.extend(["采购管理部组织公开招标", "采购评审委员会审议"])
        basis.append("采购管理办法 CG-2026-001，V2.1，第2条")
    else:
        steps.append("按内部授权矩阵完成采购审批")
    if amount >= 5_000_000:
        steps.append("总经理办公会审批")
    return ComplianceCheck(
        amount=amount,
        scope=scope,
        required_steps=steps,
        risk_flags=["不得拆分采购规避招标", "供应商利益关系必须如实披露"],
        basis=basis,
        next_action="补齐预算与需求论证材料后，提交采购管理部预审。",
    )
