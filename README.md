# 星恒BMS一线通协议 Saleae HLA解析工具
适配星恒智能BMS一线通协议A1.3.3版本的Saleae Logic高电平分析仪（HLA），实现协议帧的自动解析、参数提取与可视化展示。

## 一、工具简介
### 1.1 核心功能
- 解析一线通协议完整帧结构：同步信号→主报文→停止信号；
- 支持公有报文（ID=0x01）全字段解析（协议版本、电池参数、故障码等）；
- 支持私有报文（0x3B/0x3C/自定义）基础解析与校验；
- 分层展示解析结果（物理层/帧解析层/应用层/业务层）；
- 自动标注异常（时序错误、校验失败、长度不匹配等）。

### 1.2 协议适配
- 协议版本：星恒一线通A1.3.3；
- 帧时序：严格遵循T1/T2脉宽、2ms位周期规则；
- 数值转换：按协议表A.2/A.5/A.6/A.7的精度和偏移量计算物理值。

## 二、环境要求
### 2.1 软件环境
- Saleae Logic 2.x及以上版本（支持Python HLA API）；
- Python 3.8+（Saleae内置，无需额外安装）。

### 2.2 硬件环境
- Saleae Logic 8/16逻辑分析仪；
- 一线通总线接线：BMS COM线 → 逻辑分析仪数字通道，共地连接。

## 三、快速使用
### 3.1 安装HLA
1. 下载文件：
   - `xh_onewire_bms.py`：核心解析代码；
   - `xh_onewire_bms_config.json`：配置文件（可选，用于参数调整）；
2. 打开Saleae Logic，点击`Analyzer` → `Add High-Level Analyzer` → `Load Custom Analyzer`；
3. 选择`xh_onewire_bms.py`加载，解析器名称显示为`XHOneWireHLA`；
4. 选择一线通总线对应的数字通道作为输入。

### 3.2 配置参数
| 参数名              | 默认值 | 说明                     |
|---------------------|--------|--------------------------|
| 采样率(MHz)         | 1.0    | 建议≥0.5MHz，匹配2ms位周期 |
| 高低电平阈值(V)     | 2.0    | 适配3.3V/5V总线，可按需调整 |

### 3.3 采样配置
- 采样时长：≥10s（覆盖多帧报文）；
- 触发条件：上升沿触发（定位同步信号起始）；
- 采样深度：≥1M样本（避免数据丢失）。

### 3.4 查看结果
Saleae右侧`Analyzer Results`分层展示：
- **physical**：原始位信号时序解析；
- **frame**：帧边界与同步/停止信号校验；
- **app**：报文ID与类型识别；
- **business**：电池参数物理值与状态解析；
- **error**：异常标注（红色）。

## 四、配置文件说明
`xh_onewire_bms_config.json`用于存储核心参数，无需修改代码即可适配：
- `saleae_config`：Saleae采样与触发配置；
- `protocol_constants`：协议时序与报文常量；
- `error_tolerance`：时序校验误差容忍度；
- `value_conversion`：物理值转换精度与偏移量。

## 五、常见问题排查
| 错误类型                | 排查方案                                                                 |
|-------------------------|--------------------------------------------------------------------------|
| 同步信号T1脉宽异常      | 检查采样率≥0.5MHz、总线接地良好、无电磁干扰                             |
| 位周期异常              | 确认总线电平稳定、逻辑分析仪与BMS共地、采样率匹配                       |
| 校验码失败              | 总线丢包/干扰，检查屏蔽线接地、远离高压电源线                           |
| 公有报文长度异常        | 确认BMS协议版本为A1.3.3，原厂BMS（第三方可能修改报文格式）|

## 六、扩展开发
### 6.1 私有报文解析
补充`_parse_private_msg`方法，示例：
```python
def _parse_private_msg(self, data):
    """解析单串电压私有报文（ID=0x3B）"""
    if self.msg_id == ProtocolConst.SINGLE_VOLT_ID.value:
        # 按协议表A.6解析单串电压
        cell_count = data[1]  # 电芯数量
        voltages = []
        for i in range(2, len(data)-1, 2):
            volt = struct.unpack('<H', data[i:i+2])[0]
            voltages.append(f'{self._calc_physical_value(volt, 0.001, 0)}V')
        return f'单串电压: 共{cell_count}串 | {" | ".join(voltages)}'