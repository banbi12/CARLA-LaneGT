# 坐标、高程与 BEV

BEV 模型坐标为 x 向右、y 向前、z 向上，单位米。默认范围 `[-15,-30,15,30]`，大小 30×60m；默认 ego 局部高度范围 `[-2,2]m`。帧 transform 是完整 world→BEV 4×4 刚体变换，不可用平面 yaw 替代。

```bash
python run.py --paths config/paths.town03.local.json extract --limit 1 \
  --topdown-only --bev-range -15 -30 15 30 --output outputs/gt1
```

世界 XODR 几何含道路自身高程，按完整姿态进入当前帧后按 XYZ 裁剪。不同层道路不在 XY 并集；有坡度不等于顶视无效。但相机只能观察可见表面，桥面等上层结构可以遮挡下层；XODR 基础几何保留，缺少观测证据时不补连接。

顶视校验使用实测内外参、实际 ego 高程及完整 XYZ ROI 棱柱，默认保留 48px 安全边缘。高度并非固定相对世界 z=0；调整 ROI、FOV、分辨率或相机高度后，需重查覆盖与投影。非零横坡／超高尚不支持并明确拒绝。

模型 patch_size、GT 裁剪、六相机投影和人工编辑使用同一范围。修改范围后应生成新的提取和图册，旧人工补线不应强行复用。
