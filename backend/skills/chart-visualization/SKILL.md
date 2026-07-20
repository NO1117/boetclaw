---
name: chart-visualization
description: 钻井数据图表可视化技能，支持测井曲线、生产数据、井身结构图
---

# 图表可视化技能

## 适用场景

- 测井曲线对比图
- 钻井参数趋势图
- 生产数据柱状/折线图
- 井身结构示意图

## 图表类型

| 类型 | 用途 | 推荐工具 |
|------|------|----------|
| line | 参数趋势（WOB/RPM/ROP） | generate_chart |
| bar | 产量/进尺对比 | generate_chart |
| scatter | 参数相关性分析 | generate_chart |
| well_schematic | 井身结构 | generate_chart |

## 数据格式

输入 JSON 数组，每项包含 label 和 value 字段：

```json
[
  {"depth": 1000, "gr": 45.2, "resistivity": 12.5},
  {"depth": 1010, "gr": 48.1, "resistivity": 11.8}
]
```

## 配色建议

- 地质曲线：GR 绿色、电阻率红色
- 钻井参数：WOB 蓝色、RPM 橙色
- 背景：白色，网格浅灰
