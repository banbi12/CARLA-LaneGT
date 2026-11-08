# 跨地图范围与接入

管线通过每地图 profile、原始 XODR 摘要、独立 V4.2 缓存和捕获位姿绑定隔离地图，不能仅把 Town10 的名称改成其他地图。

已在 CARLA 0.9.16 的 Town01–Town07、Town10（Town10HD/Opt）进行跨 Town 测试，整体流程基本可行。部分断线、漏线及误线可用页面补线、两线圆角和 CAD 人工修订。

## 地图资源

从实际服务器导出或取得匹配 XODR，调用 `tools/prepare_map.py`，生成独立 `.local` profile。`map_id` 使用 `Town03`、`Town05` 等两位数形式；reference 对非 Town05 使用 `<Town>_` 前缀。新地图或版本需重新检查可用服务名、XODR 几何类型、laneSection、crosswalk、道路层和实际投影。

Town01、Town02 的已测 XODR 没有 crosswalk 对象，因此 `ped_crossing` 明确为空，不能等同于视觉上没有横道，也不能凭空生成目标。

## 高程与分层

每条道路使用自身的 XYZ / elevation profile；帧变换保留 roll、pitch、yaw 和平移。不全局压到 z=0，也不把不同层道路在 XY 上并集。非零 superelevation／crossfall 仍拒绝，不能宣称已支持所有横坡。

相机覆盖按实测 K、外参、ego 高度与完整 ROI 棱柱校验。桥面挡住下层时，观测不能补充下层连接；不能通过放宽高度阈值强行接通。

## 采集差异

Town01_Opt 曾在卸载 Props 时触发 CARLA 原生崩溃，当前生成模板保留该层。其他地图的层配置由独立 capture_config 记录，不能假定所有 Props 或信号灯杆均可移除。显存限制是定时采样触发停止，不是显存分配硬上限。

人工修订方式见[页面后处理](POSTPROCESSING.md)。
