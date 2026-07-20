---
name: las-parser
description: LAS 测井文件解析与数据质量检查技能
languages: zh, en
---

# LAS 文件解析技能

## 适用场景

- 读取 LAS（Log ASCII Standard）测井文件
- 曲线数据提取与质量检查
- 缺失值/异常值检测

## 解析流程

1. 读取 LAS 头段（Version/Well/Curve/Parameter）
2. 提取曲线数据到 DataFrame
3. 质量检查：空值率、深度连续性、异常值范围

## 代码模式

```python
import lasio
las = lasio.read("well.las")
df = las.df()
# 质检
null_rate = df.isnull().mean()
depth_step = df.index.to_series().diff().dropna()
```

## 输出规范

- 曲线清单 + 深度范围 + 采样间隔
- 质检报告：每条曲线空值率、异常段落
