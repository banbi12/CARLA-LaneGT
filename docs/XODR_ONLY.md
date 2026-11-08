# XODR-only V4.2 基线

当前默认 semantic V4.5 R3 的 divider 来自冻结 V4.2 原生 roadMark 和 divider 连接。V4.2 保留道路局部完整 XYZ、不执行 V4.1 的表面筛选／被拒线恢复／几何抑制链；V4.1 源文件留作历史参考，不作为当前默认方案。

准备地图资源后，可只用 XODR 与位姿提取基线：

```bash
python run.py --paths config/paths.town03.local.json xodr-only --limit 1 \
  --topdown-only --centerline generate --output outputs/xodr1
```

run.py 从 map_profile 对应 pin 选择世界缓存，仍检查地图与 XODR 摘要。几何提取不读取 semantic 顶视图；图册另需匹配顶视 RGB／标定，六相机审核另需图像与元数据。

此入口忠实导出 V4.2 基线，不等同于最终 semantic R3：没有结构 boundary 的 semantic 连接，也没有最终 R3 统一 target 整理。用于比较基础几何、识别漏边或定位原始错线。已知参考线误当 boundary 的情况在基线中也会存在，交人工核对。

世界缓存通过 tools/prepare_map.py 从原始 XODR 构建。匹配缓存可以显式复用；不需要把模型环境升级为 Shapely 2。
