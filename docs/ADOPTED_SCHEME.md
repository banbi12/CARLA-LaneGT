# 默认提取方案

MultiTown 默认使用 **semantic V4.5 R3**。软件版本为 1.0.0。

| 类别 | 来源与处理 |
| --- | --- |
| divider | XODR-only V4.2，关闭 semantic 补线；采用 R2 target 整理 |
| boundary | V4.2 结构为主，semantic／depth 提供端点连接；R3 保留有意分段 |
| centerline | 同地图 XODR，使用有向 R3 target 整理 |
| ped_crossing | 同地图 XODR crosswalk 对象 |

部分断线、漏线、误线及歧义连接可通过[人工后处理](POSTPROCESSING.md)修订。算法与实例组织见[算法说明](ALGORITHM.md)，地图接入见[跨地图说明](MULTITOWN.md)。
