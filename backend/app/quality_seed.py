"""两轮质量审计的取样数据（10 个重叠实体 + 5 个新增实体）。

数据刻意构造成两种口径给出相反趋势：

* 第 1 轮（基线）只抽取 10 个重叠实体，错连明细 20 条 / 抽检关系 100 条；
* 第 2 轮扩大范围到 15 个实体，重叠样本改善到 10 条 / 100 条，
  但 5 个新增实体出现 40 条错连 / 50 条抽检关系。

因此——重叠样本口径错连率 20% → 10%（改善），全量口径 20% → 33.33%（恶化）。
这里的每个错连都带图谱版本和明细编号；少数新增样本错连没有落到明细，
用于演示「只有落到明细的错连才能进入整改」。
"""
from __future__ import annotations

from typing import Any

# (实体编号, 实体名称, 业务域)
OVERLAP_ENTITIES: list[tuple[str, str, str]] = [
    ("E01", "SKU-1001 商品主数据", "零售"),
    ("E02", "SUP-2001 供应商主数据", "供应链"),
    ("E03", "ORG-3001 机构主数据", "政务"),
    ("E04", "PRD-4001 产品主数据", "制造"),
    ("E05", "PER-5001 人员主数据", "人力"),
    ("E06", "LOC-6001 地点主数据", "地理"),
    ("E07", "DOC-7001 文档主数据", "内容"),
    ("E08", "EVT-8001 事件主数据", "风控"),
    ("E09", "AST-9001 资产主数据", "财务"),
    ("E10", "SVC-1101 服务主数据", "运营"),
]

NEW_ENTITIES: list[tuple[str, str, str]] = [
    ("E11", "SKU-1002 新品商品主数据", "零售"),
    ("E12", "SUP-2002 新增供应商主数据", "供应链"),
    ("E13", "ORG-3002 新增机构主数据", "政务"),
    ("E14", "PER-5002 新增人员主数据", "人力"),
    ("E15", "LOC-6002 新增地点主数据", "地理"),
]

# 每轮每个实体抽检 10 条关系；下列是其中判定为错连的条数。
MISLINK_COUNTS: dict[tuple[int, str], int] = {
    (1, "E01"): 3,
    (1, "E02"): 2,
    (1, "E03"): 2,
    (1, "E04"): 1,
    (1, "E05"): 2,
    (1, "E06"): 3,
    (1, "E07"): 2,
    (1, "E08"): 1,
    (1, "E09"): 2,
    (1, "E10"): 2,
    (2, "E01"): 1,
    (2, "E02"): 1,
    (2, "E03"): 2,
    (2, "E04"): 0,
    (2, "E05"): 1,
    (2, "E06"): 1,
    (2, "E07"): 2,
    (2, "E08"): 1,
    (2, "E09"): 1,
    (2, "E10"): 0,
    (2, "E11"): 9,
    (2, "E12"): 8,
    (2, "E13"): 8,
    (2, "E14"): 7,
    (2, "E15"): 8,
}

# 这些错连只留下聚合计数、没有落到明细记录，因此不能派发整改。
# 键为 (轮次, 实体编号, 从 0 开始的错连序号)。
NO_DETAIL_MISLINKS: set[tuple[int, str, int]] = {
    (2, "E14", 1),
    (2, "E14", 4),
    (2, "E15", 0),
}

CHECKED_LINKS_PER_ENTITY = 10
RELATIONS = ["同义实体", "别名", "上下位", "归属关系", "关联实体"]

ROUNDS: dict[int, dict[str, Any]] = {
    1: {
        "round": 1,
        "label": "第 1 轮（2026Q3 基线审计）",
        "short_label": "基线轮",
        "graph_version": "kg-2026Q3-v3",
        "audit_date": "2026-09-30",
        "scope_label": "重叠样本（10 个实体）",
        "sample_scope": "overlap",
    },
    2: {
        "round": 2,
        "label": "第 2 轮（2026Q4 扩围审计）",
        "short_label": "扩围轮",
        "graph_version": "kg-2026Q4-v4",
        "audit_date": "2026-11-18",
        "scope_label": "扩围样本（10 个重叠 + 5 个新增）",
        "sample_scope": "expanded",
    },
}


def _entities_for_round(round_no: int) -> list[tuple[str, str, str]]:
    if round_no == 1:
        return list(OVERLAP_ENTITIES)
    return list(OVERLAP_ENTITIES) + list(NEW_ENTITIES)


def _build_samples() -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for round_no, meta in ROUNDS.items():
        entities = _entities_for_round(round_no)
        for index, (entity_id, entity_name, domain) in enumerate(entities):
            stratum = "overlap" if entity_id in {item[0] for item in OVERLAP_ENTITIES} else "new"
            mislinks: list[dict[str, Any]] = []
            for order in range(MISLINK_COUNTS.get((round_no, entity_id), 0)):
                target_id, target_name, _ = entities[(index + order + 3) % len(entities)]
                ref_id = f"MIS-R{round_no}-{entity_id}-{order + 1:02d}"
                has_detail = (round_no, entity_id, order) not in NO_DETAIL_MISLINKS
                mislinks.append(
                    {
                        "ref_id": ref_id,
                        "detail_id": ref_id if has_detail else None,
                        "detail_available": has_detail,
                        "source_entity": f"{entity_id} {entity_name}",
                        "target_entity": f"{target_id} {target_name}",
                        "relation": RELATIONS[(index + order) % len(RELATIONS)],
                        "graph_version": meta["graph_version"],
                    }
                )
            samples.append(
                {
                    "sample_id": f"AUD-R{round_no}-{entity_id}",
                    "round": round_no,
                    "entity_id": entity_id,
                    "entity_name": entity_name,
                    "domain": domain,
                    "stratum": stratum,
                    "checked_links": CHECKED_LINKS_PER_ENTITY,
                    "graph_version": meta["graph_version"],
                    "mislinks": mislinks,
                }
            )
    return samples


SAMPLES: list[dict[str, Any]] = _build_samples()


def samples_for_round(round_no: int) -> list[dict[str, Any]]:
    return [sample for sample in SAMPLES if sample["round"] == round_no]


def round_meta(round_no: int) -> dict[str, Any]:
    return dict(ROUNDS[round_no])
