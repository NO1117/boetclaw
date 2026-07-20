---
name: code-generation
description: 钻井数据分析与自动化代码生成技能
---

# 代码生成技能

## 适用场景

- 测井数据解析脚本
- 钻井参数统计分析
- WITS/WITSML 数据对接
- 报表自动化生成

## 技术栈偏好

- Python：pandas, numpy, matplotlib, lasio
- JavaScript/TypeScript：Node.js 数据处理
- SQL：PostgreSQL/MySQL 查询

## 代码规范

1. 添加类型注解（Python）或 TypeScript 类型
2. 包含 docstring 说明用途
3. 提供使用示例
4. 错误处理完善
5. 遵循 PEP 8 / ESLint 规范

## 常见模式

### LAS 文件读取

```python
import lasio
las = lasio.read("well.las")
df = las.df()
```

### 钻井参数统计

```python
import pandas as pd
stats = df.groupby("formation").agg({"rop": "mean", "wob": "max"})
```
