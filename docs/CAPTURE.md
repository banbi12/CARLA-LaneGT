# 顶视 RGB／语义／深度采集

重新采集才需要 CARLA、匹配 Python API、GPU 与 NVML。已有合法同步顶视数据可直接接入；本工具不从零生成 nuCarla 六相机数据集。

每地图配置需 map_profile、capture_config、cases、carla_root 与 carla_python。cases 指定完整代表帧及绝对相机位置，不能使用最近位姿替代。资源准备工具生成的 capture.json 是模板；按实际 ROI、地形和 K 检查覆盖后使用，默认高度 60m 并非所有场景都足够。

```bash
python run.py --paths config/paths.town03.local.json collect-plan \
  --limit 1 --output outputs/plan1
python run.py --paths config/paths.town03.local.json collect --limit 1 \
  --execute --output outputs/capture1
```

collect-plan 不启动 CARLA，不查询 NVML。collect --execute 拷贝独立采集代码、案例和地图配置，使用新建且自有的空 CARLA 服务；不会热切换占用中的服务器。实际地图名与 mp.to_opendrive 的 SHA256 必须精确匹配。

使用 Epic、三路同步、实际 image.transform、有限图像队列和 COMPLETE 文件摘要；当前典型尺寸 1152×2048、水平 FOV 36°。保留 Ground / Decals。已知 Town01 Props 卸载崩溃，模板保留该层；信号灯杆等可能残留。

显存每 100ms 采样，触发停止阈值为 7400MB（十进制）与物理显存 90% 的较小值。启动前要求余量；监视、清理仅作用于本次创建的进程。该机制不是硬显存上限，采样间隔内仍可能有峰值。一次只处理一个服务／地图。

输出为 `<output>/topdown_cases/<reference>/` 的 rgb.png、semantic_labels.png、depth_m.npy、metadata.json 和 COMPLETE.json。采集后将 topdown_root 指向该位置，再运行 check。不会自动改写输入配置。

坡度使用实测 XYZ。完全被上层结构遮挡的当前道路层无法由顶视观测恢复；原始 XODR 结构可以保留，自动连接须有同层可见证据。
