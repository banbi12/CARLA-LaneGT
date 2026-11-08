# 中心线

`--centerline none` 不输出；`generate` 使用同地图 V4.2 XODR lane centers，无需 CARLA/GPU；`provided` 读取每帧中心线标签中的 classes.centerline。所有模式都保留完整 XYZ 和完整帧变换。

R3 在最终帧 targets 上进行同向重复／包含检查及唯一末端到起点合并，不反转点序以凑成连接，不把真实分出／汇入合为一条线。原 lane、source_refs、parent 和道路拓扑保留在世界资源与来源链中。原始世界拓扑文件没有被替换成新的 target 图。

显式模型采样时，centerline 使用类别 3，GT 保存实际 20 点；shift_v2 只有有效前向排列。长曲线的固定 20 点表示可能有更大的误差。完整曲线与采样图须一起查看。

provided 输入整理后若实例改变，centerline_exact_from_source 不再为 true；centerline_geometry_preserved 表示几何覆盖保持。页面人工工具对 centerline 仍只读。
