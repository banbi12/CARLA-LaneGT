# 完整几何与可选 MapTRv2 采样

默认提取不需要模型仓库或权重。完整 XY／XYZ 折线是基础标注，固定点是模型表示。`--sampler none`（默认）保留完整几何、GT points=null；`--sampler maptr` 显式调用外部 MapTRv2 的 `LiDARInstanceLines`。

配置独立 `model_root` 与 `maptr_python` 后：

```bash
python run.py --paths config/paths.town03.local.json extract --limit 1 \
  --topdown-only --centerline generate --sampler maptr --output outputs/gt_sampled1
# 或从已有完整几何生成独立采样结果：
python run.py --paths config/paths.town03.local.json export-maptr \
  --source outputs/gt1 --output outputs/gt_sampled2
```

采样在 target 组织之后执行。保留 target ID、完整几何和 source，按相同顺序保存 fixed20、shift_v2、labels；centerline 的方向与前向有效排列不能丢失。GT 中的 points 为真实 fixed20，centerline 亦然。

采样在 CPU 执行，不加载权重、不推理、不训练。最大 Hausdorff 偏差描述固定点表示与完整折线的差异，不是模型预测误差；合并长曲线后可能增大。图册可分别检查 FULL、fixed20、shift_v2 worst。

导出目录是新结果，生成图册时使用与源相同的每地图 paths 配置。Dataset 适配源码位于 src/adapters，真正的训练配置和训练过程属于外部模型项目。
