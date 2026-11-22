"""可复核质量指标接口：看板取数、两轮比较、明细回查、整改清单与受理回执。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query

from app.schemas import ActionPayload, ActionResult
from app.services import quality_metrics as qm

router = APIRouter(prefix="/api/quality", tags=["可复核质量指标"])


@router.get("/dashboard")
def dashboard(round: int = Query(default=2), baseline: int = Query(default=1)) -> dict[str, Any]:
    _ensure_round(round)
    _ensure_round(baseline)
    return qm.dashboard_payload(round, baseline)


@router.get("/metrics")
def metrics(
    round: int = Query(default=2),
    scope: str = Query(default="expanded"),
) -> dict[str, Any]:
    _ensure_round(round)
    _ensure_scope(scope)
    return qm.metrics_for_round(round, scope)


@router.get("/compare")
def compare(
    baseline: int = Query(default=1),
    current: int = Query(default=2),
) -> dict[str, Any]:
    _ensure_round(baseline)
    _ensure_round(current)
    return qm.compare_rounds(baseline, current)


@router.get("/samples")
def samples(round: int = Query(default=2)) -> dict[str, Any]:
    _ensure_round(round)
    return qm.samples_payload(round)


@router.get("/evidence")
def evidence(
    round: int = Query(default=2),
    stratum: str = Query(default="all"),
) -> dict[str, Any]:
    _ensure_round(round)
    if stratum not in ("all", "overlap", "new"):
        raise HTTPException(status_code=400, detail=f"未知分层：{stratum}")
    return qm.evidence(round, stratum)


@router.get("/remediation")
def remediation(
    round: int = Query(default=2),
    scope: str = Query(default="expanded"),
) -> dict[str, Any]:
    _ensure_round(round)
    _ensure_scope(scope)
    return qm.build_remediation(round, scope)


@router.post("/remediation/sync")
def sync_remediation(
    payload: dict[str, Any] | None = Body(default=None),
    round: int = Query(default=2),
    scope: str = Query(default="expanded"),
    operator: str = Query(default="治理看板"),
) -> dict[str, Any]:
    _ensure_round(round)
    _ensure_scope(scope)
    remark = str((payload or {}).get("remark") or "").strip()
    return qm.sync_remediation(round, scope, operator=remark or operator)


@router.get("/receipts")
def receipts() -> dict[str, Any]:
    return {"items": qm.list_receipts(), "total": len(qm.ledger.receipts)}


@router.get("/receipts/{receipt_id}")
def receipt(receipt_id: str) -> dict[str, Any]:
    result = qm.verify_receipt(receipt_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"受理回执 {receipt_id} 不存在")
    return result


@router.post("/samples/availability")
def set_availability(payload: ActionPayload) -> ActionResult:
    """模拟原样本不可取得 / 恢复，用于核对指标口径的降级行为。"""
    action = payload.action.strip()
    round_no = 1
    if payload.remark:
        try:
            round_no = int(payload.remark)
        except ValueError:
            round_no = 1
    _ensure_round(round_no)
    if action in ("标记不可取得", "mark_unavailable"):
        qm.ledger.mark_round_unavailable(round_no, "用户标记：原样本无法取得")
    elif action in ("恢复样本", "restore"):
        qm.ledger.restore_round(round_no)
    elif action in ("失效样本", "mark_sample_missing"):
        sample_id = (payload.remark or "").strip()
        if not qm.ledger.mark_sample_missing(sample_id):
            raise HTTPException(status_code=400, detail=f"未知样本编号：{sample_id}")
        return ActionResult(ok=True, message=f"样本 {sample_id} 已标记为无法取得")
    elif action in ("重置", "reset"):
        qm.ledger.reset()
    else:
        raise HTTPException(status_code=400, detail=f"未知动作：{action}")
    return ActionResult(ok=True, message=f"第 {round_no} 轮样本可用性已更新：{action}")


def _ensure_round(round_no: int) -> None:
    if round_no not in qm.ROUNDS:
        raise HTTPException(status_code=400, detail=f"未知审计轮次：{round_no}")


def _ensure_scope(scope: str) -> None:
    if scope not in qm.SCOPE_LABELS:
        raise HTTPException(status_code=400, detail=f"未知指标口径：{scope}")
