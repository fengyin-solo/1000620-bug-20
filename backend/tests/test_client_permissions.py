"""委托单位权限与校验回归测试。

覆盖问题单要求的口径：
- 暂停/终止的单位在任何入口（样品受理、检测结算）都不能新委托；
- 资质编号过期按到期口径拦下并说明原因，展示状态不再显示合作中；
- 越权角色调用提交入口被明确拒绝（PermissionDenied），不静默成功；
- 资质编号、结算方式的每次修改都有变更记录（谁、何时、旧值、新值）；
- 已有单位的历史委托与结算记录不被改动；列表与详情状态同步。

运行：cd backend && python3 -m unittest discover -s tests -v
服务层只依赖标准库，无需安装第三方依赖即可运行。
"""
from __future__ import annotations

import copy
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.client import ClientService  # noqa: E402
from app.services.permission import Operator, PermissionDenied  # noqa: E402
from app.services.sample import SampleService  # noqa: E402
from app.services.settlement import SettlementService  # noqa: E402
from app.store import store  # noqa: E402

TODAY = date(2026, 9, 26)

ADMIN = Operator(name="张管理", role="管理员")
SALES = Operator(name="李业务", role="业务员")
REVIEWER = Operator(name="王审核", role="审核员")
LAB = Operator(name="赵检测", role="检测员")
ANON = Operator(name="未登记操作员", role="")


def make_clients() -> ClientService:
    return ClientService()


class BaseCase(unittest.TestCase):
    def setUp(self) -> None:
        store.reset()
        self.clients = make_clients()
        self.samples = SampleService()
        self.settlements = SettlementService()

    def client_by_code(self, code: str) -> dict:
        entry = self.clients.find_by_code(code)
        assert entry is not None, f"示例数据缺少单位 {code}"
        return entry


class CommissionGateTest(BaseCase):
    """暂停/终止/资质过期的单位，在任何入口都不能新委托。"""

    def test_suspended_client_blocked_at_sample_entry(self) -> None:
        entry, message = self.samples.create_entry(
            {"样品编号": "SAMP-9001", "样品名称": "矿泉水", "样品类别": "饮用水", "送检单位": "CLIE-0003"},
            SALES,
            TODAY,
        )
        self.assertIsNone(entry)
        self.assertIn("已暂停", message)
        self.assertIn("CLIE-0003", message)

    def test_suspended_client_blocked_at_settlement_entry(self) -> None:
        entry, message = self.settlements.create_entry(
            {"结算单号": "SETT-9001", "委托单位": "CLIE-0003", "结算周期": "2026-09"},
            SALES,
            TODAY,
        )
        self.assertIsNone(entry)
        self.assertIn("已暂停", message)

    def test_terminated_client_blocked_at_every_entry(self) -> None:
        entry, message = self.clients.run_action(4, "终止合作", ADMIN, TODAY)
        self.assertIsNotNone(entry, message)
        sample, sample_msg = self.samples.create_entry(
            {"样品编号": "SAMP-9002", "样品名称": "土壤", "样品类别": "环境", "送检单位": "CLIE-0004"},
            SALES,
            TODAY,
        )
        self.assertIsNone(sample)
        self.assertIn("已终止", sample_msg)
        settlement, settle_msg = self.settlements.create_entry(
            {"结算单号": "SETT-9002", "委托单位": "CLIE-0004", "结算周期": "2026-09"},
            SALES,
            TODAY,
        )
        self.assertIsNone(settlement)
        self.assertIn("已终止", settle_msg)

    def test_expired_qualification_blocked_with_expiry_reason(self) -> None:
        # CLIE-0002 合作中，但资质有效期至 2026-08-31，早于 TODAY
        entry, message = self.samples.create_entry(
            {"样品编号": "SAMP-9003", "样品名称": "出厂水", "样品类别": "饮用水", "送检单位": "CLIE-0002"},
            SALES,
            TODAY,
        )
        self.assertIsNone(entry)
        self.assertIn("CNAS-L1002", message)
        self.assertIn("2026-08-31", message)
        self.assertIn("到期", message)

    def test_expired_client_not_shown_as_cooperating(self) -> None:
        rows, _ = self.clients.list_entries(today=TODAY)
        row = next(item for item in rows if item["单位编码"] == "CLIE-0002")
        self.assertEqual(row["单位状态"], "资质过期")
        self.assertEqual(row["资质状态"], "已过期")
        self.assertFalse(row["可委托"])
        self.assertIn("2026-08-31", row["不可委托原因"])

    def test_pending_client_blocked(self) -> None:
        entry, message = self.samples.create_entry(
            {"样品编号": "SAMP-9004", "样品名称": "面包", "样品类别": "食品", "送检单位": "CLIE-0001"},
            SALES,
            TODAY,
        )
        self.assertIsNone(entry)
        self.assertIn("尚未审核通过", message)

    def test_valid_client_can_commission(self) -> None:
        entry, message = self.samples.create_entry(
            {"样品编号": "SAMP-9005", "样品名称": "空气", "样品类别": "环境", "送检单位": "CLIE-0004"},
            SALES,
            TODAY,
        )
        self.assertIsNotNone(entry, message)
        self.assertEqual(entry["送检单位"], "CLIE-0004")
        self.assertEqual(entry["登记人"], SALES.name)

    def test_commission_must_belong_to_registered_client(self) -> None:
        entry, message = self.samples.create_entry(
            {"样品编号": "SAMP-9006", "样品名称": "牛奶", "样品类别": "食品"},
            SALES,
            TODAY,
        )
        self.assertIsNone(entry)
        self.assertIn("归属", message)
        entry, message = self.samples.create_entry(
            {"样品编号": "SAMP-9006", "样品名称": "牛奶", "样品类别": "食品", "送检单位": "CLIE-9999"},
            SALES,
            TODAY,
        )
        self.assertIsNone(entry)
        self.assertIn("尚未登记", message)

    def test_client_name_also_resolves(self) -> None:
        entry, message = self.samples.create_entry(
            {"样品编号": "SAMP-9007", "样品名称": "废水", "样品类别": "环境", "送检单位": "市政环境监测站"},
            SALES,
            TODAY,
        )
        self.assertIsNotNone(entry, message)


class RolePermissionTest(BaseCase):
    """越权角色调用同一入口被明确拒绝，不静默成功。"""

    def test_sales_cannot_review_suspend_terminate(self) -> None:
        with self.assertRaises(PermissionDenied):
            self.clients.run_action(1, "审核单位", SALES, TODAY)
        with self.assertRaises(PermissionDenied):
            self.clients.run_action(4, "暂停合作", SALES, TODAY)
        with self.assertRaises(PermissionDenied):
            self.clients.run_action(4, "终止合作", SALES, TODAY)

    def test_lab_role_cannot_use_commission_entries(self) -> None:
        with self.assertRaises(PermissionDenied):
            self.samples.create_entry(
                {"样品编号": "SAMP-9101", "样品名称": "土壤", "样品类别": "环境", "送检单位": "CLIE-0004"},
                LAB,
                TODAY,
            )
        with self.assertRaises(PermissionDenied):
            self.settlements.create_entry(
                {"结算单号": "SETT-9101", "委托单位": "CLIE-0004", "结算周期": "2026-09"},
                LAB,
                TODAY,
            )
        with self.assertRaises(PermissionDenied):
            self.clients.create_entry(
                {"单位编码": "CLIE-9101", "单位名称": "新公司", "单位类型": "企业单位"},
                LAB,
                TODAY,
            )

    def test_unidentified_role_denied(self) -> None:
        with self.assertRaises(PermissionDenied):
            self.samples.create_entry(
                {"样品编号": "SAMP-9102", "样品名称": "土壤", "样品类别": "环境", "送检单位": "CLIE-0004"},
                ANON,
                TODAY,
            )

    def test_reviewer_can_only_review(self) -> None:
        entry, message = self.clients.run_action(1, "审核单位", REVIEWER, TODAY)
        self.assertIsNotNone(entry, message)
        self.assertEqual(entry["status"], "合作中")
        with self.assertRaises(PermissionDenied):
            self.clients.run_action(1, "暂停合作", REVIEWER, TODAY)

    def test_sales_can_register_client_for_review(self) -> None:
        entry, message = self.clients.create_entry(
            {"单位编码": "CLIE-9201", "单位名称": "新客户公司", "单位类型": "企业单位"},
            SALES,
            TODAY,
        )
        self.assertIsNotNone(entry, message)
        self.assertEqual(entry["status"], "待审核")
        self.assertEqual(entry["登记人"], SALES.name)

    def test_sales_cannot_update_profile(self) -> None:
        with self.assertRaises(PermissionDenied):
            self.clients.update_profile(4, {"资质编号": "CNAS-X"}, SALES, TODAY)


class ClientStateMachineTest(BaseCase):
    """状态流转口径：同一编码不能重复登记，流转有方向，审核看资质。"""

    def test_duplicate_code_rejected(self) -> None:
        entry, message = self.clients.create_entry(
            {"单位编码": "CLIE-0001", "单位名称": "冒名公司", "单位类型": "企业单位"},
            SALES,
            TODAY,
        )
        self.assertIsNone(entry)
        self.assertIn("CLIE-0001", message)
        self.assertIn("重复", message)

    def test_illegal_transitions_rejected(self) -> None:
        entry, message = self.clients.run_action(4, "审核单位", ADMIN, TODAY)
        self.assertIsNone(entry)
        self.assertIn("不允许", message)
        entry, message = self.clients.run_action(1, "暂停合作", ADMIN, TODAY)
        self.assertIsNone(entry)
        self.assertIn("不允许", message)

    def test_terminated_is_final(self) -> None:
        entry, message = self.clients.run_action(4, "终止合作", ADMIN, TODAY)
        self.assertIsNotNone(entry, message)
        for action in ("审核单位", "暂停合作", "终止合作"):
            again, again_msg = self.clients.run_action(4, action, ADMIN, TODAY)
            self.assertIsNone(again, action)
            self.assertIn("不允许", again_msg)

    def test_review_requires_valid_qualification(self) -> None:
        entry, message = self.clients.create_entry(
            {
                "单位编码": "CLIE-9301",
                "单位名称": "过期资质公司",
                "单位类型": "企业单位",
                "资质编号": "CNAS-OLD",
                "资质有效期至": "2026-01-01",
            },
            SALES,
            TODAY,
        )
        self.assertIsNotNone(entry, message)
        reviewed, review_msg = self.clients.run_action(entry["id"], "审核单位", REVIEWER, TODAY)
        self.assertIsNone(reviewed)
        self.assertIn("2026-01-01", review_msg)
        self.assertIn("到期", review_msg)

    def test_review_requires_qualification_present(self) -> None:
        entry, _ = self.clients.create_entry(
            {"单位编码": "CLIE-9302", "单位名称": "无资质公司", "单位类型": "企业单位"},
            SALES,
            TODAY,
        )
        reviewed, review_msg = self.clients.run_action(entry["id"], "审核单位", REVIEWER, TODAY)
        self.assertIsNone(reviewed)
        self.assertIn("资质", review_msg)

    def test_suspend_then_terminate_allowed(self) -> None:
        entry, message = self.clients.run_action(4, "暂停合作", ADMIN, TODAY)
        self.assertIsNotNone(entry, message)
        entry, message = self.clients.run_action(4, "终止合作", ADMIN, TODAY)
        self.assertIsNotNone(entry, message)
        self.assertEqual(entry["status"], "已终止")


class AuditTrailTest(BaseCase):
    """资质编号、结算方式被谁改过必须留痕。"""

    def test_profile_update_writes_audit_records(self) -> None:
        entry, message = self.clients.update_profile(
            4, {"资质编号": "CNAS-L1004-NEW", "结算方式": "季结"}, ADMIN, TODAY
        )
        self.assertIsNotNone(entry, message)
        audits = [item for item in entry["变更记录"] if item["动作"] == "修改档案"]
        self.assertEqual(len(audits), 2)
        by_field = {item["字段"]: item for item in audits}
        self.assertEqual(by_field["资质编号"]["旧值"], "CNAS-L1004")
        self.assertEqual(by_field["资质编号"]["新值"], "CNAS-L1004-NEW")
        self.assertEqual(by_field["结算方式"]["旧值"], "月结30天")
        self.assertEqual(by_field["结算方式"]["新值"], "季结")
        for item in audits:
            self.assertEqual(item["操作人"], ADMIN.name)
            self.assertEqual(item["角色"], ADMIN.role)
            self.assertTrue(item["时间"])

    def test_action_writes_audit_record(self) -> None:
        entry, _ = self.clients.run_action(4, "暂停合作", ADMIN, TODAY)
        audits = [item for item in entry["变更记录"] if item["动作"] == "暂停合作"]
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0]["操作人"], ADMIN.name)
        self.assertIn("合作中", audits[0]["说明"])
        self.assertIn("已暂停", audits[0]["说明"])

    def test_identity_fields_not_editable(self) -> None:
        entry, message = self.clients.update_profile(
            4, {"单位编码": "CLIE-9999", "status": "合作中"}, ADMIN, TODAY
        )
        self.assertIsNone(entry)
        self.assertIn("不允许", message)
        self.assertEqual(self.client_by_code("CLIE-0004")["id"], 4)

    def test_terminated_profile_frozen(self) -> None:
        self.clients.run_action(4, "终止合作", ADMIN, TODAY)
        entry, message = self.clients.update_profile(4, {"结算方式": "现结"}, ADMIN, TODAY)
        self.assertIsNone(entry)
        self.assertIn("冻结", message)

    def test_no_change_rejected(self) -> None:
        entry, message = self.clients.update_profile(4, {"结算方式": "月结30天"}, ADMIN, TODAY)
        self.assertIsNone(entry)
        self.assertIn("没有需要变更", message)

    def test_bad_expiry_format_rejected(self) -> None:
        entry, message = self.clients.update_profile(4, {"资质有效期至": "2026/10/01"}, ADMIN, TODAY)
        self.assertIsNone(entry)
        self.assertIn("YYYY-MM-DD", message)


class HistoryImmutableTest(BaseCase):
    """已有单位的历史委托与结算记录不能被改动。"""

    def test_status_change_does_not_touch_history(self) -> None:
        samples_before = copy.deepcopy(store.rows("sample"))
        settlements_before = copy.deepcopy(store.rows("settlement"))
        self.clients.run_action(4, "终止合作", ADMIN, TODAY)
        self.clients.run_action(2, "暂停合作", ADMIN, TODAY)
        self.assertEqual(store.rows("sample"), samples_before)
        self.assertEqual(store.rows("settlement"), settlements_before)

    def test_profile_update_does_not_touch_history(self) -> None:
        samples_before = copy.deepcopy(store.rows("sample"))
        settlements_before = copy.deepcopy(store.rows("settlement"))
        entry, message = self.clients.update_profile(
            2, {"资质编号": "CNAS-L1002-NEW", "资质有效期至": "2027-08-31"}, ADMIN, TODAY
        )
        self.assertIsNotNone(entry, message)
        self.assertEqual(store.rows("sample"), samples_before)
        self.assertEqual(store.rows("settlement"), settlements_before)

    def test_history_of_suspended_client_keeps_original_attribution(self) -> None:
        # CLIE-0003 已暂停，其历史样品与结算单仍归属原单位编码，不被改写
        sample = next(row for row in store.rows("sample") if row["送检单位"] == "CLIE-0003")
        settlement = next(row for row in store.rows("settlement") if row["委托单位"] == "CLIE-0003")
        self.assertEqual(sample["样品编号"], "SAMP-0003")
        self.assertEqual(settlement["结算单号"], "SETT-0003")


class ListDetailSyncTest(BaseCase):
    """列表与详情使用同一状态口径。"""

    def test_list_and_detail_status_match(self) -> None:
        rows, total = self.clients.list_entries(today=TODAY)
        self.assertEqual(total, 4)
        for row in rows:
            detail = self.clients.get_entry(row["id"], TODAY)
            self.assertIsNotNone(detail)
            self.assertEqual(row["单位状态"], detail["单位状态"])
            self.assertEqual(row["资质状态"], detail["资质状态"])
            self.assertEqual(row["可委托"], detail["可委托"])
            self.assertEqual(row["不可委托原因"], detail["不可委托原因"])

    def test_status_filter_uses_display_status(self) -> None:
        rows, total = self.clients.list_entries(status="资质过期", today=TODAY)
        self.assertEqual(total, 1)
        self.assertEqual(rows[0]["单位编码"], "CLIE-0002")

    def test_detail_carries_audit_trail(self) -> None:
        self.clients.update_profile(4, {"结算方式": "现结"}, ADMIN, TODAY)
        detail = self.clients.get_entry(4, TODAY)
        self.assertTrue(detail["变更记录"])
        rows, _ = self.clients.list_entries(today=TODAY)
        row = next(item for item in rows if item["id"] == 4)
        self.assertNotIn("变更记录", row)


if __name__ == "__main__":
    unittest.main()
