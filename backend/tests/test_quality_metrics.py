"""可复核质量指标的回归测试：口径、改善率保护、明细派发与受理回执。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import quality_metrics as qm
from app.store import store


@pytest.fixture()
def client():
    qm.ledger.reset()
    store._tables["quality_audit"] = [
        row for row in store.rows("quality_audit")
        if not str(row.get("报告编号", "")).startswith("QUAL-MET-")
    ]
    yield TestClient(app)
    qm.ledger.reset()


def _rates(payload: dict) -> dict[str, float]:
    return {item["stratum"]: item["error_rate_pct"] for item in payload["strata"]}


def test_stratified_metrics_have_numerator_denominator_and_version(client):
    payload = client.get("/api/quality/metrics?round=2").json()
    rates = _rates(payload)
    assert rates == {"overlap": 10.0, "new": 80.0, "all": 33.33}
    total = payload["total"]
    assert (total["numerator"], total["denominator"]) == (50, 150)
    assert total["graph_versions"] == ["kg-2026Q4-v4"]
    assert len(total["sample_ids"]) == 15
    overlap = payload["strata"][0]
    assert len(overlap["entity_ids"]) == 10


def test_two_scopes_produce_opposite_trends_and_conflict_is_explicit(client):
    comparison = client.get("/api/quality/compare").json()
    assert comparison["status"] == "ok"
    assert comparison["matched_same_scope"]["baseline_error_rate_pct"] == 20.0
    assert comparison["matched_same_scope"]["current_error_rate_pct"] == 10.0
    assert comparison["improvement_rate"] == 50.0
    assert comparison["direction"] == "改善"
    expanded = comparison["expanded_scope"]
    assert expanded["status"] == "not_comparable"
    assert expanded["improvement_rate_pct"] is None
    assert expanded["delta_pp"] == 13.33
    assert comparison["conflict"]["detected"] is True
    assert comparison["conflict"]["overlap_direction"] == "改善"
    assert comparison["conflict"]["full_scope_direction"] == "恶化"


def test_missing_baseline_never_becomes_improvement_rate(client):
    client.post(
        "/api/quality/samples/availability",
        json={"action": "标记不可取得", "remark": "1"},
    )
    comparison = client.get("/api/quality/compare").json()
    assert comparison["status"] == "baseline_missing"
    assert comparison["improvement_rate"] is None
    assert comparison["improvement_pp"] is None
    assert comparison["guarded_fallback"]["allowed"] is False
    # 本期全量指标仍然可看，数值与改善率无关
    current = comparison["current_scope_metrics"]["total"]
    assert (current["numerator"], current["denominator"]) == (50, 150)
    assert current["error_rate_pct"] == 33.33


def test_only_detail_backed_mislinks_are_dispatched(client):
    plan = client.get("/api/quality/remediation?round=2").json()
    assert plan["counts"]["dispatchable"] == 47
    assert plan["counts"]["skipped_missing_detail"] == 3
    assert all(item["detail_id"] for item in plan["items"])
    assert all(not item["detail_available"] for item in plan["skipped"])
    assert {item["graph_version"] for item in plan["items"]} == {"kg-2026Q4-v4"}


def test_sync_creates_receipt_and_legacy_scope_stays_checkable(client):
    new_scope = client.post("/api/quality/remediation/sync?round=2&scope=expanded").json()
    assert new_scope["ok"] is True
    assert new_scope["receipt"]["scope"] == "expanded"
    assert new_scope["audit_report"]["报告编号"] == "QUAL-MET-R2-EXPANDED"

    legacy_scope = client.post("/api/quality/remediation/sync?round=2&scope=overlap").json()
    assert legacy_scope["counts"]["dispatchable"] == 10

    for receipt_id, numerator, denominator in (
        ("RCPT-R2-expanded", 50, 150),
        ("RCPT-R2-overlap", 10, 100),
    ):
        verified = client.get(f"/api/quality/receipts/{receipt_id}").json()
        assert verified["status"] == "可核对"
        assert verified["snapshot"]["numerator"] == numerator
        assert verified["snapshot"]["denominator"] == denominator
        assert verified["improvement_claim"] is None

    receipts = client.get("/api/quality/receipts").json()
    assert receipts["total"] == 2


def test_receipt_reports_missing_sample_instead_of_claiming_improvement(client):
    client.post("/api/quality/remediation/sync?round=2&scope=expanded")
    client.post(
        "/api/quality/samples/availability",
        json={"action": "标记不可取得", "remark": "2"},
    )
    verified = client.get("/api/quality/receipts/RCPT-R2-expanded").json()
    assert verified["available"] is False
    assert verified["status"] == "原样本不可取得"
    assert verified["improvement_claim"] is None


def test_receipt_with_one_lost_sample_stops_recomputing(client):
    client.post("/api/quality/remediation/sync?round=2&scope=expanded")
    client.post(
        "/api/quality/samples/availability",
        json={"action": "失效样本", "remark": "AUD-R2-E05"},
    )
    verified = client.get("/api/quality/receipts/RCPT-R2-expanded").json()
    assert verified["available"] is False
    assert verified["status"] == "原样本不可取得"
    assert verified["missing_sample_ids"] == ["AUD-R2-E05"]
    assert verified["recomputed"] is None
    # 快照保持受理时的分子分母，不被缩小的重算结果替换
    assert verified["snapshot"]["denominator"] == 150


def test_evidence_traces_each_mislink_to_graph_version(client):
    evidence = client.get("/api/quality/evidence?round=2&stratum=new").json()
    assert evidence["count"] == 40
    record = evidence["records"][0]
    assert record["sample_id"].startswith("AUD-R2-E1")
    assert record["graph_version"] == "kg-2026Q4-v4"
    assert record["detail_available"] is True


def test_partial_baseline_loss_shrinks_same_scope_instead_of_substituting(client):
    client.post(
        "/api/quality/samples/availability",
        json={"action": "失效样本", "remark": "AUD-R1-E05"},
    )
    comparison = client.get("/api/quality/compare").json()
    assert comparison["status"] == "ok"
    matched = comparison["matched_same_scope"]
    # 缺失的实体在基线与本期同时剔除，口径仍对齐，但不再覆盖 10 个实体
    assert len(matched["entity_ids"]) == 9
    assert "E05" not in matched["entity_ids"]
    assert (matched["baseline"]["denominator"], matched["current"]["denominator"]) == (90, 90)
    assert comparison["expanded_scope"]["status"] == "not_comparable"
    assert "无法取得" in comparison["expanded_scope"]["reason"]
    baseline_metrics = comparison["baseline_scope_metrics"]
    assert baseline_metrics["missing_sample_ids"] == ["AUD-R1-E05"]


def test_sync_refuses_when_scope_samples_unavailable_and_keeps_receipt(client):
    client.post("/api/quality/remediation/sync?round=2&scope=expanded")
    client.post(
        "/api/quality/samples/availability",
        json={"action": "标记不可取得", "remark": "2"},
    )
    refused = client.post("/api/quality/remediation/sync?round=2&scope=expanded").json()
    assert refused["ok"] is False
    assert refused["receipt"] is None
    receipts = client.get("/api/quality/receipts").json()
    assert [item["receipt_id"] for item in receipts["items"]] == ["RCPT-R2-expanded"]
    verified = client.get("/api/quality/receipts/RCPT-R2-expanded").json()
    assert verified["available"] is False
