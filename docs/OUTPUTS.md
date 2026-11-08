# 输出契约

默认输出 `lanegt_geometry_v1`，单位米，BEV x 向右、y 向前、z 向上。每次提取写入新目录，不覆盖输入或历史结果。

```text
extraction/
  manifest.json
  boundary_world.json
  centerlines_world.json       # centerline generate 时
  geometry/<reference>/       # 候选与连接审计
  frames/<token>/
    gt.json.gz
    targets.json.gz
    input_binding.json
    sampling_diagnostics.json
    actual_sampler_targets.npz # 显式 --sampler maptr 时
```

`gt.classes` 包含 divider / boundary / ped_crossing / centerline；各实例有 id、parent_id、source、render_points（完整 XY）、render_xyz（完整 XYZ）和 points（未采样时 null）。counts 与实际 targets 对应。

`targets.json.gz` 的 full / full_xyz 是完整几何，fixed / worst / sampling_hd_m 仅在实际采样后出现。R3 归并来源在 source.input_target_ids、input_parent_ids 和 original_sources。直接提取的整理审计保存在 GT 的 linear_target_normalization；开发迁移工具可另存原始 targets 和审计文件。

真实采样 NPZ 包含 target_ids、labels、fixed20 `[N,20,2]`、shift_v2 `[N,19,20,2]`。labels 顺序 divider=0、ped_crossing=1、boundary=2、centerline=3；行顺序严格对应 targets。无效 shift 使用模型 padding，centerline 只有有效前向表示。

`sampling_backend` / `actual_sampler_applied` 表示是否调用真实适配器；未采样的完整折线不是缺少几何。MapTR 的 128 query 容量检查不会静默裁掉 GT，通用几何不受该模型限制。

图册含原图／GT 投影、顶视叠加、BEV、audit_data.js 和离线编辑资源。图册可能链接外部输入，不能当作自包含数据归档。

审核 JSON/CSV 记录结论，补线 JSON 记录几何操作，CAD 的 DXF 与 context.json 记录交换上下文，三者不可互换。人工应用生成新 GT；未执行采样时下载几何不代表已有模型点集。`human_approved` 与 `approved_for_training` 默认 false，分别记录审核与训练使用状态。
