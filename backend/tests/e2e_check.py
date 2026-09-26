"""临时端到端验证：通过 TestClient 打真实 HTTP 接口，验证角色头、403、门禁与留痕。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from urllib.parse import quote

from fastapi.testclient import TestClient

from app.main import app
from app.store import store

store.reset()
client = TestClient(app)


def op(role: str, name: str) -> dict[str, str]:
    """与前端一致：中文角色名按 URL 百分号编码放进请求头。"""
    return {"X-Operator-Role": quote(role), "X-Operator-Name": quote(name)}


ADMIN = op("管理员", "张管理")
SALES = op("业务员", "李业务")
LAB = op("检测员", "赵检测")

fails = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        fails.append(name)


# 1. 健康检查与列表口径
r = client.get("/api/health")
check("health", r.status_code == 200 and r.json()["ok"])
r = client.get("/api/client")
items = r.json()["items"]
by_code = {i["单位编码"]: i for i in items}
check("expired shows 资质过期", by_code["CLIE-0002"]["单位状态"] == "资质过期", by_code["CLIE-0002"]["单位状态"])
check("valid shows 合作中", by_code["CLIE-0004"]["单位状态"] == "合作中")
check("list hides audit", "变更记录" not in by_code["CLIE-0002"])

# 2. 详情与列表同步 + 变更记录可见
r = client.get("/api/client/2")
check("detail sync status", r.json()["单位状态"] == "资质过期")
check("detail has audit list", r.json()["变更记录"] == [])
check("detail block reason", "2026-08-31" in r.json()["不可委托原因"])

# 3. 暂停单位新委托被拦（样品入口 + 结算入口）
body = {"values": {"样品编号": "SAMP-8001", "样品名称": "水样", "样品类别": "饮用水", "送检单位": "CLIE-0003"}}
r = client.post("/api/sample", json=body, headers=SALES)
check("suspended blocked sample", r.status_code == 200 and r.json()["ok"] is False and "已暂停" in r.json()["message"])
r = client.post("/api/settlement", json={"values": {"结算单号": "SETT-8001", "委托单位": "CLIE-0003", "结算周期": "2026-09"}}, headers=SALES)
check("suspended blocked settlement", r.json()["ok"] is False and "已暂停" in r.json()["message"])

# 4. 资质过期按到期口径拦下并说明原因
body = {"values": {"样品编号": "SAMP-8002", "样品名称": "水样", "样品类别": "饮用水", "送检单位": "CLIE-0002"}}
r = client.post("/api/sample", json=body, headers=SALES)
msg = r.json()["message"]
check("expired blocked with reason", r.json()["ok"] is False and "CNAS-L1002" in msg and "2026-08-31" in msg, msg)

# 5. 越权角色：403 且说明原因，不静默成功
r = client.post("/api/sample", json=body, headers=LAB)
check("lab role 403", r.status_code == 403 and "无权" in r.json()["detail"], r.json().get("detail"))
r = client.post("/api/client/4/actions", json={"values": {"action": "暂停合作"}}, headers=SALES)
check("sales suspend 403", r.status_code == 403 and "暂停合作" in r.json()["detail"])
r = client.post("/api/client", json={"values": {"单位编码": "CLIE-8001", "单位名称": "新公司", "单位类型": "企业单位"}}, headers=LAB)
check("lab create client 403", r.status_code == 403)
r = client.post("/api/sample", json=body)
check("no role 403", r.status_code == 403)

# 6. 正常流程：业务员登记 -> 审核员审核 -> 合作中可委托
r = client.post("/api/client", json={"values": {"单位编码": "CLIE-8001", "单位名称": "新客户", "单位类型": "企业单位", "资质编号": "CNAS-L8001", "资质有效期至": "2027-12-31"}}, headers=SALES)
check("sales registers client", r.json()["ok"] is True and r.json()["entry"]["status"] == "待审核")
new_id = r.json()["entry"]["id"]
r = client.post("/api/client", json={"values": {"单位编码": "CLIE-8001", "单位名称": "冒名", "单位类型": "企业单位"}}, headers=SALES)
check("duplicate code rejected", r.json()["ok"] is False and "重复" in r.json()["message"])
r = client.post(f"/api/client/{new_id}/actions", json={"values": {"action": "审核单位"}}, headers=op("审核员", "王审核"))
check("reviewer approves", r.json()["ok"] is True and r.json()["entry"]["status"] == "合作中")
r = client.post("/api/sample", json={"values": {"样品编号": "SAMP-8003", "样品名称": "土样", "样品类别": "环境", "送检单位": "CLIE-8001"}}, headers=SALES)
check("new client can commission", r.json()["ok"] is True, r.json().get("message"))

# 7. 档案修改留痕
r = client.put("/api/client/4", json={"values": {"资质编号": "CNAS-L1004-B", "结算方式": "季结"}}, headers=ADMIN)
check("admin updates profile", r.json()["ok"] is True, r.json().get("message"))
audits = [a for a in r.json()["entry"]["变更记录"] if a["动作"] == "修改档案"]
check("audit old/new", any(a["字段"] == "资质编号" and a["旧值"] == "CNAS-L1004" and a["新值"] == "CNAS-L1004-B" and a["操作人"] == "张管理" for a in audits))
r = client.put("/api/client/4", json={"values": {"单位编码": "CLIE-9999"}}, headers=ADMIN)
check("identity immutable", r.json()["ok"] is False and "不允许" in r.json()["message"])
r = client.put("/api/client/4", json={"values": {"结算方式": "现结"}}, headers=SALES)
check("sales update 403", r.status_code == 403)

# 8. 终止后：新委托被拦、档案冻结、历史记录不变
samples_before = client.get("/api/sample?size=200").json()["items"]
settlements_before = client.get("/api/settlement?size=200").json()["items"]
r = client.post("/api/client/4/actions", json={"values": {"action": "终止合作"}}, headers=ADMIN)
check("terminate ok", r.json()["ok"] is True)
r = client.post("/api/sample", json={"values": {"样品编号": "SAMP-8004", "样品名称": "气样", "样品类别": "环境", "送检单位": "CLIE-0004"}}, headers=SALES)
check("terminated blocked", r.json()["ok"] is False and "已终止" in r.json()["message"])
r = client.put("/api/client/4", json={"values": {"结算方式": "现结"}}, headers=ADMIN)
check("terminated frozen", r.json()["ok"] is False and "冻结" in r.json()["message"])
check("sample history untouched", client.get("/api/sample?size=200").json()["items"] == samples_before)
check("settlement history untouched", client.get("/api/settlement?size=200").json()["items"] == settlements_before)

# 9. 导出与状态过滤
r = client.get("/api/client/export")
check("export works", r.status_code == 200 and r.json()["module"] == "client")
r = client.get("/api/client?status=资质过期")
check("filter expired", all(i["单位状态"] == "资质过期" for i in r.json()["items"]) and r.json()["total"] >= 1)

print()
print("FAILED:", fails if fails else "none")
sys.exit(1 if fails else 0)
