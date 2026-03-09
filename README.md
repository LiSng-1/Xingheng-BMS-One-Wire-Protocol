这是一个标准的 README.md 文件，用于说明该 Saleae 拓展插件的功能、安装方法、协议依据以及使用指南。请将其保存为 README.md 并放在与 extension.json 和 Python 脚本相同的文件夹中。

Saleae Logic Extension: Xingheng BMS One-Wire Protocol

此插件是专为 Saleae Logic Analyzer (Logic 2 / Logic Pro) 开发的软件扩展，用于解码 星恒电源 (Xingheng Power) BMS 的 一线通 (One-Wire) 通信协议。

它能够将物理层的时序信号自动转换为应用层数据，包括电池电压、电流、SOC、温度及故障码，并自动进行校验和验证。

📋 协议依据

本插件严格基于以下文档开发：
文档名称: 《星恒BMS一线通协议说明》
版本号: A1.3.3 (正式版)
关键特性:
    同步头: Low ≥ 10ms, High = 1ms
    逻辑定义: 
        1: Low 0.5ms / High 1.5ms
        0: Low 1.5ms / High 0.5ms
    停止位: Low ≥ 5ms, High ≥ 50ms
    数据格式: LSB First (低位先发), Little-Endian (小端模式)
    校验算法: SUM (ID + Ver + Data) & 0xFF

✨ 功能特点

自动帧识别: 智能检测同步头和停止位，自动分割数据帧。
多报文支持:
    公有报文 (0x01): 解析额定电压、SOC、工作电压/电流、温度、故障码等。
    私有报文 (0x3A/0x3B/0x3C): 解析实时数据、单体电压及唯一码。
物理量转换: 自动将原始 Hex 数据转换为工程单位 (V, A, %, ℃)。
校验检查: 实时计算 SUM 校验值，错误帧会自动标记为 CRC Error。
可视化结果: 在 Saleae 软件的 "Results" 面板中直接显示可读数据。

📦 安装步骤

下载文件: 确保您拥有以下三个文件，并将它们放在同一个文件夹内：
    extension.json
    xingheng_analyzer.py (或您命名的 Python 脚本)
    README.md
打开 Saleae Software: 启动 Saleae Logic 2 或 Logic Pro 软件。
添加分析器:
    点击右侧面板的 + 按钮。
    搜索或找到 Software Extension 并添加。
加载插件:
    点击新添加的 "Software Extension" 旁边的 齿轮图标 (⚙️) 进入设置。
    点击 Select Extension Folder。
    选择包含上述文件的整个文件夹 (不要只选单个文件)。
完成: 如果加载成功，设置界面将显示 "Xingheng BMS One-Wire Protocol" 及配置选项。

⚙️ 配置说明

加载插件后，您将看到以下配置项：
参数名   说明   推荐设置
Input Channel   连接 BMS 一线通信号的逻辑分析仪通道号。   根据实际接线选择 (如 Ch 0)

Timing Tolerance   脉宽识别的容差范围 (ms)。用于适应信号噪声或晶振偏差。   默认 0.4 (即 ±0.4ms)

硬件连接建议
信号线: 将 Saleae 探针连接到 BMS 的 COM (或 TX) 引脚。
地线: 务必连接 GND。
上拉电阻: 一线通总线通常需要上拉电阻。如果 BMS 内部未集成或 ECU 未连接，您可能需要在探针处外接一个 4.7kΩ - 10kΩ 的上拉电阻至系统电压 (通常为 5V 或 12V)，以确保高电平稳定。

📊 如何查看结果

设置采样率：建议设置为 1 MS/s 或更高，以精确捕捉 0.5ms 的脉冲。
设置触发：建议设置触发条件为 Channel X Low > 8ms，以便捕获完整的帧起始。
点击 Start 开始采集。
采集结束后，查看软件底部的 Results 表格。
    每一行代表一帧数据。
    内容包括：帧类型, SOC, 电压, 电流, 校验状态。
    双击某一行，波形视图会自动跳转到该帧的位置。

示例输出
Time: 0.012s | Public (0x01) | SOC: 95.0% | V: 58.4V | I: 2.5A | Status: OK
Time: 0.067s | Private (0x3A)| SOC: 94.5% | V: 58.3V | I: 2.4A | Status: OK
Time: 0.120s | Public (0x01) | SOC: 94.0% | V: 58.2V | I: 2.3A | Status: CRC Error

🛠️ 故障排除

无法加载插件:
    检查 extension.json 中的 "python_script" 文件名是否与实际 Python 文件完全一致。
    确保所有文件在同一文件夹内。
    查看 Saleae 的 View -> Developer -> Show Console 获取详细的 Python 报错信息。
解析结果为空:
    确认波形上是否存在明显的 10ms 低电平 (同步头)。
    检查采样率是否过低 (低于 200 KS/s 可能导致误判)。
    检查信号是否有严重的噪声干扰，尝试调整 Timing Tolerance。
大量 CRC Error:
    检查接地是否良好。
    确认是否需要外接上拉电阻。
    确认协议版本是否匹配 (本插件基于 A1.3.3)。

📄 许可证

本项目采用 MIT License。您可以自由使用、修改和分发此代码。

🤝 贡献与支持

如果您发现协议解析有误或有新的报文类型需要支持，欢迎提交 Issue 或 Pull Request。
Generated based on Xingheng BMS Protocol Spec A1.3.3
