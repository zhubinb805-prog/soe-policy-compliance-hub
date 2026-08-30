import pytest

from services.compliance_rules import check_procurement


def test_procurement_below_tender_threshold():
    result = check_procurement(800_000)
    assert "公开招标" not in " ".join(result.required_steps)
    assert "内部授权矩阵" in " ".join(result.required_steps)


def test_procurement_requires_tender_and_committee_review():
    result = check_procurement(1_200_000)
    assert "采购管理部组织公开招标" in result.required_steps
    assert "采购评审委员会审议" in result.required_steps
    assert any("第2条" in item for item in result.basis)


def test_large_procurement_requires_management_meeting():
    result = check_procurement(5_000_000)
    assert "总经理办公会审批" in result.required_steps


def test_negative_amount_is_rejected():
    with pytest.raises(ValueError):
        check_procurement(-1)
