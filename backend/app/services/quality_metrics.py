"""可复核质量指标：两轮审计样本的分层聚合、同口径比较与整改清单生成。

指标口径约定（全部可回查）：

* 分子 = 判定为错连的关系条数，分母 = 该范围抽检的关系总条数；
* 每个指标都携带抽取样本编号、实体清单与图谱版本；
* 只有带明细编号（detail_id）的错连才能派发整改，未落明细的只计入分子并单独列出；
* 比较改善率时只允许使用两轮都实际取得的同一批实体样本。基线样本无法取得时，
  改善率返回不可计算，绝不把全量错连率的变化折算成改善率。

本轮数据刻意让两种口径给出相反趋势：重叠样本 20% → 10%（改善），
扩围全量 20% → 33.33%（恶化）。看板必须同时展示两者并说明不可互相替代。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from app.quality_seed import (
    CHECKED_LINKS_PER_ENTITY,
    NEW_ENTITIES,
    OVERLAP_ENTITIES,
    ROUNDS,
    SAMPLES,
    round_meta,
    samples_for_round,
)

OVERLAP_IDS = {item[0] for item in OVERLAP_ENTITIES}
NEW_IDS = {item[0] for item in NEW_ENTITIES}

STRATUM_LABELS = {
    "overlap": "重叠样本",
    "new": "新增样本",
    "all": "全量样本",
}

SCOPE_LABELS = {
    "expanded": "扩围口径（当轮全部样本）",
    "overlap": "旧口径（仅重叠样本）",
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _round_pct(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


class QualityLedger:
    """保存取样可用性、整改清单与已受理范围回执（进程内，可重置）。"""

    def __init__(self) -> None:
        self.unavailable_rounds: dict[int, str] = {}
        self.missing_sample_ids: set[str] = set()
        self.remediation: dict[str, dict[str, Any]] = {}
        self.receipts: dict[str, dict[str, Any]] = {}

    def reset(self) -> None:
        self.unavailable_rounds.clear()
        self.missing_sample_ids.clear()
        self.remediation.clear()
        self.receipts.clear()

    # ---- 样本可用性 ----
    def mark_round_unavailable(self, round_no: int, reason: str) -> None:
        self.unavailable_rounds[round_no] = reason or "原样本无法取得"

    def restore_round(self, round_no: int) -> None:
        self.unavailable_rounds.pop(round_no, None)
        self.missing_sample_ids = {
            sample_id for sample_id in self.missing_sample_ids
            if not sample_id.startswith(f"AUD-R{round_no}-")
        }

    def mark_sample_missing(self, sample_id: str) -> bool:
        known = {sample["sample_id"] for sample in SAMPLES}
        if sample_id not in known:
            return False
        self.missing_sample_ids.add(sample_id)
        return True

    def round_unavailable_reason(self, round_no: int) -> str | None:
        if round_no in self.unavailable_rounds:
            return self.unavailable_rounds[round_no]
        if not self.visible_samples(round_no):
            return "该轮取样样本全部缺失，原样本无法取得"
        return None

    def visible_samples(self, round_no: int) -> list[dict[str, Any]]:
        if round_no in self.unavailable_rounds:
            return []
        return [
            sample for sample in samples_for_round(round_no)
            if sample["sample_id"] not in self.missing_sample_ids
        ]


ledger = QualityLedger()


# ---------------------------------------------------------------------------
# 分层聚合
# ---------------------------------------------------------------------------
def _aggregate(samples: Iterable[dict[str, Any]], stratum: str) -> dict[str, Any]:
    sample_list = list(samples)
    numerator = sum(len(sample["mislinks"]) for sample in sample_list)
    denominator = sum(int(sample["checked_links"]) for sample in sample_list)
    detail_refs: list[str] = []
    missing_detail_refs: list[str] = []
    for sample in sample_list:
        for mislink in sample["mislinks"]:
            if mislink.get("detail_available") and mislink.get("detail_id"):
                detail_refs.append(mislink["detail_id"])
            else:
                missing_detail_refs.append(mislink["ref_id"])
    rate = (numerator / denominator * 100) if denominator else None
    detail_coverage = (len(detail_refs) / numerator * 100) if numerator else 100.0
    return {
        "stratum": stratum,
        "label": STRATUM_LABELS.get(stratum, stratum),
        "entity_count": len(sample_list),
        "sample_count": len(sample_list),
        "entity_ids": [sample["entity_id"] for sample in sample_list],
        "sample_ids": [sample["sample_id"] for sample in sample_list],
        "numerator": numerator,
        "denominator": denominator,
        "error_rate_pct": _round_pct(rate),
        "numerator_detail_backed": len(detail_refs),
        "numerator_without_detail": len(missing_detail_refs),
        "detail_coverage_pct": _round_pct(detail_coverage),
        "detail_refs": detail_refs,
        "missing_detail_refs": missing_detail_refs,
        "graph_versions": sorted({sample["graph_version"] for sample in sample_list}),
    }


def _stratum_samples(samples: list[dict[str, Any]], stratum: str) -> list[dict[str, Any]]:
    if stratum == "all":
        return samples
    return [sample for sample in samples if sample["stratum"] == stratum]


def metrics_for_round(round_no: int, scope: str = "expanded") -> dict[str, Any]:
    """返回某一轮在指定口径下的可复核指标（含分子、分母、版本、样本编号）。"""
    meta = round_meta(round_no)
    unavailable_reason = ledger.round_unavailable_reason(round_no)
    samples = ledger.visible_samples(round_no)
    if scope == "overlap":
        samples = [sample for sample in samples if sample["entity_id"] in OVERLAP_IDS]

    strata = []
    if scope == "expanded" and any(sample["stratum"] == "new" for sample in samples):
        strata.extend([
            _aggregate(_stratum_samples(samples, "overlap"), "overlap"),
            _aggregate(_stratum_samples(samples, "new"), "new"),
        ])
    strata.append(_aggregate(samples, "all" if scope == "expanded" else "overlap"))

    return {
        "round": round_no,
        "round_label": meta["label"],
        "graph_version": meta["graph_version"],
        "audit_date": meta["audit_date"],
        "scope": scope,
        "scope_label": SCOPE_LABELS.get(scope, scope),
        "available": unavailable_reason is None,
        "unavailable_reason": unavailable_reason,
        "missing_sample_ids": sorted(
            sample["sample_id"] for sample in samples_for_round(round_no)
            if sample["sample_id"] in ledger.missing_sample_ids
        ),
        "strata": strata,
        "total": strata[-1],
        "generated_at": _now(),
    }


# ---------------------------------------------------------------------------
# 同口径比较
# ---------------------------------------------------------------------------
def _same_scope_aggregate(
    samples: list[dict[str, Any]], entity_ids: set[str], stratum: str
) -> dict[str, Any]:
    return _aggregate(
        [sample for sample in samples if sample["entity_id"] in entity_ids], stratum
    )


def _trend(improvement_pp: float | None) -> str:
    if improvement_pp is None:
        return "不可比"
    if improvement_pp > 0:
        return "改善"
    if improvement_pp < 0:
        return "恶化"
    return "持平"


def compare_rounds(baseline_round: int = 1, current_round: int = 2) -> dict[str, Any]:
    """比较两轮审计：同口径（共同实体）给改善率，扩围全量只给展示值且不当作改善率。"""
    baseline_meta = round_meta(baseline_round)
    current_meta = round_meta(current_round)
    baseline_reason = ledger.round_unavailable_reason(baseline_round)
    current_reason = ledger.round_unavailable_reason(current_round)
    baseline_samples = ledger.visible_samples(baseline_round)
    current_samples = ledger.visible_samples(current_round)

    baseline_ids = {sample["entity_id"] for sample in baseline_samples}
    current_ids = {sample["entity_id"] for sample in current_samples}
    common_ids = baseline_ids & current_ids

    result: dict[str, Any] = {
        "baseline": {
            "round": baseline_round,
            "label": baseline_meta["label"],
            "graph_version": baseline_meta["graph_version"],
            "available": baseline_reason is None,
            "unavailable_reason": baseline_reason,
            "entity_ids": sorted(baseline_ids),
            "sample_ids": [sample["sample_id"] for sample in baseline_samples],
        },
        "current": {
            "round": current_round,
            "label": current_meta["label"],
            "graph_version": current_meta["graph_version"],
            "available": current_reason is None,
            "unavailable_reason": current_reason,
            "entity_ids": sorted(current_ids),
            "sample_ids": [sample["sample_id"] for sample in current_samples],
        },
        "current_scope_metrics": metrics_for_round(current_round, "expanded"),
        "baseline_scope_metrics": (
            metrics_for_round(baseline_round, "expanded") if baseline_reason is None else None
        ),
        "generated_at": _now(),
    }

    # 基线样本缺失：改善率必须不可计算，不能拿全量错连率变化顶上。
    if baseline_reason is not None or not baseline_samples:
        result.update({
            "status": "baseline_missing",
            "improvement_rate": None,
            "improvement_pp": None,
            "direction": "不可计算",
            "matched_same_scope": None,
            "reason": (
                f"基线轮（第{baseline_round}轮）原样本无法取得：{baseline_reason or '无可用样本'}；"
                "按口径规则不得把全量错连率的变化算作改善率"
            ),
            "guarded_fallback": {
                "attempted": "全量错连率直接相减",
                "allowed": False,
                "reason": "基线没有可对齐的实体级样本，分子与分母不可比",
            },
        })
        return result

    # 同口径：只取两轮都实际抽到的共同实体。
    baseline_matched = _same_scope_aggregate(baseline_samples, common_ids, "overlap")
    current_matched = _same_scope_aggregate(current_samples, common_ids, "overlap")
    if not common_ids or not baseline_matched["denominator"] or not current_matched["denominator"]:
        result.update({
            "status": "no_common_sample",
            "improvement_rate": None,
            "improvement_pp": None,
            "direction": "不可计算",
            "matched_same_scope": None,
            "reason": "两轮没有共同实体样本，无法建立同口径改善率",
        })
        return result

    base_rate = baseline_matched["error_rate_pct"] or 0.0
    cur_rate = current_matched["error_rate_pct"] or 0.0
    improvement_pp = round(base_rate - cur_rate, 2)
    relative = round(improvement_pp / base_rate * 100, 2) if base_rate else None
    matched = {
        "status": "comparable",
        "entity_ids": sorted(common_ids),
        "baseline": baseline_matched,
        "current": current_matched,
        "baseline_error_rate_pct": base_rate,
        "current_error_rate_pct": cur_rate,
        "improvement_pp": improvement_pp,
        # 改善率（相对下降）只在基线错连率 > 0 时有定义
        "improvement_rate_pct": relative,
        "direction": _trend(improvement_pp),
    }

    # 扩围全量：仅做展示，明确标记口径不同、不得当作改善率。
    baseline_all = _aggregate(baseline_samples, "all")
    current_all = _aggregate(current_samples, "all")
    same_entity_scope = baseline_ids == current_ids
    baseline_rate = baseline_all["error_rate_pct"]
    current_rate = current_all["error_rate_pct"]
    display_delta = (
        round((current_rate or 0.0) - (baseline_rate or 0.0), 2)
        if baseline_rate is not None and current_rate is not None else None
    )
    if same_entity_scope:
        expanded = {
            "status": "comparable",
            "reason": "两轮抽检实体完全一致，全量口径可以直接比较",
            "baseline": baseline_all,
            "current": current_all,
            "delta_pp": display_delta,
            "improvement_rate_pct": (
                round(-display_delta / baseline_rate * 100, 2)
                if display_delta is not None and baseline_rate else None
            ),
            "direction": _trend(
                round((baseline_rate or 0.0) - (current_rate or 0.0), 2)
            ),
        }
    else:
        if ledger.missing_sample_ids & {s["sample_id"] for s in samples_for_round(baseline_round)}:
            expanded_reason = (
                "基线轮有样本已无法取得，全量口径的分子分母缺项且与本期构成不同，"
                "其变化不能作为改善率"
            )
        else:
            expanded_reason = (
                "基线轮只覆盖重叠实体，本期扩围新增实体；全量口径的分子分母构成不同，"
                "其变化不能作为改善率"
            )
        expanded = {
            "status": "not_comparable",
            "reason": expanded_reason,
            "baseline": baseline_all,
            "current": current_all,
            "delta_pp": display_delta,
            "improvement_rate_pct": None,
            "direction": "口径不可比",
            "display_only": True,
        }

    result.update({
        "status": "ok",
        "improvement_rate": relative,
        "improvement_pp": improvement_pp,
        "direction": matched["direction"],
        "matched_same_scope": matched,
        "expanded_scope": expanded,
        "conflict": _conflict(matched, expanded),
        "remediation_basis": "matched_same_scope",
    })
    return result


def _conflict(matched: dict[str, Any], expanded: dict[str, Any]) -> dict[str, Any]:
    expanded_trend = expanded.get("direction")
    overlap_trend = matched.get("direction")
    if expanded.get("status") == "not_comparable" and expanded_trend == "口径不可比":
        full_trend = _full_scope_raw_trend(expanded)
    else:
        full_trend = expanded_trend
    detected = bool(
        overlap_trend in ("改善", "恶化")
        and full_trend in ("改善", "恶化")
        and full_trend != overlap_trend
    )
    return {
        "detected": detected,
        "overlap_direction": overlap_trend,
        "full_scope_direction": full_trend,
        "full_scope_claimable": expanded.get("status") == "comparable",
        "note": (
            "重叠样本改善、扩围全量恶化：两种口径的样本构成不同，不能互相替代；"
            "下一批整改以落到明细的错连为准，不能用单一趋势代表整体质量"
            if detected else
            "两种口径未出现相反趋势；仍需分别标注样本范围与图谱版本"
        ),
    }


def _full_scope_raw_trend(expanded: dict[str, Any]) -> str:
    baseline_rate = expanded["baseline"].get("error_rate_pct")
    current_rate = expanded["current"].get("error_rate_pct")
    if baseline_rate is None or current_rate is None:
        return "不可比"
    return "恶化" if current_rate > baseline_rate else ("改善" if current_rate < baseline_rate else "持平")


# ---------------------------------------------------------------------------
# 整改清单：只有落到明细的错连才能派发
# ---------------------------------------------------------------------------
def build_remediation(round_no: int = 2, scope: str = "expanded") -> dict[str, Any]:
    """按指定口径生成可派发的整改对象；未落明细的错连只登记、不派发。"""
    unavailable_reason = ledger.round_unavailable_reason(round_no)
    samples = ledger.visible_samples(round_no)
    if scope == "overlap":
        samples = [sample for sample in samples if sample["entity_id"] in OVERLAP_IDS]
    samples = sorted(samples, key=lambda sample: sample["entity_id"])

    items: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for sample in samples:
        for mislink in sample["mislinks"]:
            if mislink.get("detail_available") and mislink.get("detail_id"):
                items.append({
                    "ref_id": mislink["ref_id"],
                    "detail_id": mislink["detail_id"],
                    "round": round_no,
                    "sample_id": sample["sample_id"],
                    "entity_id": sample["entity_id"],
                    "entity_name": sample["entity_name"],
                    "stratum": sample["stratum"],
                    "source_entity": mislink["source_entity"],
                    "target_entity": mislink["target_entity"],
                    "relation": mislink["relation"],
                    "graph_version": mislink["graph_version"],
                    "scope": scope,
                    "status": "待整改",
                })
            else:
                skipped.append({
                    "ref_id": mislink["ref_id"],
                    "detail_id": mislink.get("detail_id"),
                    "detail_available": False,
                    "round": round_no,
                    "sample_id": sample["sample_id"],
                    "entity_id": sample["entity_id"],
                    "stratum": sample["stratum"],
                    "graph_version": mislink["graph_version"],
                    "reason": "错连未落到明细记录，缺少可回查的明细编号，不能派发整改",
                })

    metrics = metrics_for_round(round_no, scope)
    by_stratum: dict[str, int] = {}
    for item in items:
        by_stratum[item["stratum"]] = by_stratum.get(item["stratum"], 0) + 1
    return {
        "round": round_no,
        "scope": scope,
        "graph_version": ROUNDS[round_no]["graph_version"],
        "available": unavailable_reason is None,
        "unavailable_reason": unavailable_reason,
        "entity_ids": sorted(sample["entity_id"] for sample in samples),
        "sample_ids": sorted(sample["sample_id"] for sample in samples),
        "sampled_checked_links": sum(int(sample["checked_links"]) for sample in samples),
        "items": items,
        "skipped": skipped,
        "counts": {
            "dispatchable": len(items),
            "skipped_missing_detail": len(skipped),
            "by_stratum": by_stratum,
            "numerator": metrics["total"]["numerator"],
            "denominator": metrics["total"]["denominator"],
        },
        "generated_at": _now(),
    }


def sync_remediation(
    round_no: int = 2,
    scope: str = "expanded",
    operator: str = "治理看板",
) -> dict[str, Any]:
    """把取样结果同步进整改清单，并为本次受理范围留存可核对回执。"""
    plan = build_remediation(round_no, scope)
    if not plan["available"]:
        return {
            "ok": False,
            "message": (
                f"第 {round_no} 轮{SCOPE_LABELS.get(scope, scope)}的原样本不可取得"
                f"（{plan['unavailable_reason']}），不能同步整改清单，也不覆盖既有受理回执"
            ),
            "receipt": None,
            "items": [],
            "skipped": [],
            "counts": plan["counts"],
            "audit_report": None,
        }
    accepted_at = _now()
    for item in plan["items"]:
        existing = ledger.remediation.get(item["ref_id"])
        if existing is None:
            ledger.remediation[item["ref_id"]] = {
                **item,
                "accepted_scope": f"{round_no}:{scope}",
                "accepted_at": accepted_at,
                "operator": operator,
                "last_synced_at": accepted_at,
            }
        else:
            existing["last_synced_at"] = accepted_at
            existing["status"] = existing.get("status", "待整改")

    receipt_id = f"RCPT-R{round_no}-{scope}"
    previous = ledger.receipts.get(receipt_id)
    # 同一轮同一口径重复同步不新增受理范围，保留首次受理时间。
    receipt = {
        "receipt_id": receipt_id,
        "round": round_no,
        "scope": scope,
        "scope_label": SCOPE_LABELS.get(scope, scope),
        "graph_version": plan["graph_version"],
        "entity_ids": plan["entity_ids"],
        "sample_ids": plan["sample_ids"],
        "snapshot": {
            "numerator": plan["counts"]["numerator"],
            "denominator": plan["counts"]["denominator"],
            "error_rate_pct": (
                round(plan["counts"]["numerator"] / plan["counts"]["denominator"] * 100, 2)
                if plan["counts"]["denominator"] else None
            ),
            "dispatchable": plan["counts"]["dispatchable"],
            "skipped_missing_detail": plan["counts"]["skipped_missing_detail"],
            "graph_version": plan["graph_version"],
        },
        "status": "已受理",
        "accepted_at": previous["accepted_at"] if previous else accepted_at,
        "last_synced_at": accepted_at,
        "operator": operator,
    }
    ledger.receipts[receipt_id] = receipt

    return {
        "ok": True,
        "message": (
            f"已按{SCOPE_LABELS.get(scope, scope)}同步 {plan['counts']['dispatchable']} 条明细错连到整改清单"
            + (f"，{plan['counts']['skipped_missing_detail']} 条未落明细未派发"
               if plan["counts"]["skipped_missing_detail"] else "")
        ),
        "receipt": receipt,
        "items": plan["items"],
        "skipped": plan["skipped"],
        "counts": plan["counts"],
        "audit_report": _upsert_audit_report(receipt),
    }


def _upsert_audit_report(receipt: dict[str, Any]) -> dict[str, Any]:
    """把本轮取样的汇总快照写成质量审计报告，进入既有「指派整改」流程。"""
    from app.store import store

    report_no = f"QUAL-MET-R{receipt['round']}-{receipt['scope'].upper()}"
    rows = store.rows("quality_audit")
    snapshot = receipt["snapshot"]
    rate = snapshot["error_rate_pct"]
    accuracy = f"{round(100 - rate, 2)}%" if rate is not None else "不可计算"
    values = {
        "报告编号": report_no,
        "审计范围": (
            f"可复核质量指标 R{receipt['round']} "
            f"{SCOPE_LABELS.get(receipt['scope'], receipt['scope'])} "
            f"{receipt['graph_version']}"
        ),
        "实体准确率": accuracy,
        "关系完整率": (
            f"错连 {snapshot['numerator']}/{snapshot['denominator']}"
        ),
        "冗余度": f"{snapshot['skipped_missing_detail']} 条未落明细",
        "更新时效": receipt["last_synced_at"],
        "合规结论": "需整改",
        "审计时间": receipt["last_synced_at"],
    }
    for row in rows:
        if row.get("报告编号") == report_no:
            row.update(values)
            row["status"] = "需整改"
            row["pending"] = True
            return row
    rows.append({
        "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
        "status": "需整改",
        "pending": True,
        "abnormal": False,
        **values,
    })
    return rows[-1]


def list_receipts() -> list[dict[str, Any]]:
    return sorted(ledger.receipts.values(), key=lambda item: item["receipt_id"])


def verify_receipt(receipt_id: str) -> dict[str, Any] | None:
    """回查已受理范围：受理时的样本全部可取得才重算，缺任何一条都不得给出新结论。"""
    receipt = ledger.receipts.get(receipt_id)
    if receipt is None:
        return None
    round_no = receipt["round"]
    entity_ids = set(receipt["entity_ids"])
    reason = ledger.round_unavailable_reason(round_no)
    missing = sorted(
        sample_id for sample_id in receipt["sample_ids"]
        if sample_id in ledger.missing_sample_ids
    )
    if reason is None and missing:
        reason = f"受理时的取样样本缺失：{'、'.join(missing)}"
    if reason is not None:
        return {
            "receipt_id": receipt_id,
            "status": "原样本不可取得",
            "available": False,
            "reason": reason,
            "missing_sample_ids": missing,
            "snapshot": receipt["snapshot"],
            "recomputed": None,
            "drift": None,
            "improvement_claim": None,
        }
    recomputed = _same_scope_aggregate(ledger.visible_samples(round_no), entity_ids, "all")
    snapshot = receipt["snapshot"]
    drift = {
        "numerator": recomputed["numerator"] - snapshot["numerator"],
        "denominator": recomputed["denominator"] - snapshot["denominator"],
        "dispatchable": len([
            mislink for sample in ledger.visible_samples(round_no)
            if sample["entity_id"] in entity_ids
            for mislink in sample["mislinks"] if mislink.get("detail_available")
        ]) - snapshot["dispatchable"],
    }
    return {
        "receipt_id": receipt_id,
        "status": "可核对" if not any(drift.values()) else "存在漂移",
        "available": True,
        "graph_version": receipt["graph_version"],
        "snapshot": snapshot,
        "recomputed": {
            "numerator": recomputed["numerator"],
            "denominator": recomputed["denominator"],
            "error_rate_pct": recomputed["error_rate_pct"],
            "graph_version": recomputed["graph_versions"],
            "sample_ids": recomputed["sample_ids"],
        },
        "drift": drift,
        "improvement_claim": None,
    }


def evidence(round_no: int, stratum: str = "all") -> dict[str, Any]:
    """明细回查：列出该口径下每个错连的取样、明细与图谱版本。"""
    samples = ledger.visible_samples(round_no)
    if stratum != "all":
        samples = [sample for sample in samples if sample["stratum"] == stratum]
    records: list[dict[str, Any]] = []
    for sample in samples:
        for mislink in sample["mislinks"]:
            records.append({
                "sample_id": sample["sample_id"],
                "entity_id": sample["entity_id"],
                "entity_name": sample["entity_name"],
                "stratum": sample["stratum"],
                "checked_links": sample["checked_links"],
                "ref_id": mislink["ref_id"],
                "detail_id": mislink.get("detail_id"),
                "detail_available": bool(mislink.get("detail_available")),
                "source_entity": mislink["source_entity"],
                "target_entity": mislink["target_entity"],
                "relation": mislink["relation"],
                "graph_version": mislink["graph_version"],
            })
    return {
        "round": round_no,
        "stratum": stratum,
        "records": records,
        "count": len(records),
        "graph_version": ROUNDS[round_no]["graph_version"],
    }


def samples_payload(round_no: int) -> dict[str, Any]:
    return {
        "round": round_no,
        "round_label": ROUNDS[round_no]["label"],
        "graph_version": ROUNDS[round_no]["graph_version"],
        "available": ledger.round_unavailable_reason(round_no) is None,
        "unavailable_reason": ledger.round_unavailable_reason(round_no),
        "samples": ledger.visible_samples(round_no),
    }


def dashboard_payload(round_no: int = 2, baseline_round: int = 1) -> dict[str, Any]:
    """治理看板一次性取数：新口径指标、旧口径指标、两轮比较、整改清单预览。"""
    return {
        "round": round_no,
        "baseline_round": baseline_round,
        "metrics": metrics_for_round(round_no, "expanded"),
        "legacy_scope_metrics": metrics_for_round(round_no, "overlap"),
        "baseline_metrics": (
            metrics_for_round(baseline_round, "expanded")
            if ledger.round_unavailable_reason(baseline_round) is None else None
        ),
        "comparison": compare_rounds(baseline_round, round_no),
        "remediation_preview": {
            "expanded": build_remediation(round_no, "expanded")["counts"],
            "overlap": build_remediation(round_no, "overlap")["counts"],
        },
        "receipts": list_receipts(),
        "generated_at": _now(),
    }
