from saleae.analyzers import HighLevelAnalyzer, AnalyzerFrame, StringSetting, NumberSetting
import struct
from enum import Enum

# 协议核心常量定义（星恒一线通A1.3.3）
class ProtocolConst(Enum):
    # 帧时序参数(ms)
    SYNC_T1_MIN = 10.0    # 同步信号T1最小脉宽
    SYNC_T2 = 1.0         # 同步信号T2固定脉宽
    BIT_PERIOD = 2.0      # 逻辑0/1周期
    BIT1_T1 = 0.5         # 逻辑1 T1脉宽
    BIT1_T2 = 1.5         # 逻辑1 T2脉宽
    BIT0_T1 = 1.5         # 逻辑0 T1脉宽
    BIT0_T2 = 0.5         # 逻辑0 T2脉宽
    STOP_T1 = 5.0         # 停止信号T1脉宽
    STOP_T2_MIN = 50.0    # 停止信号T2最小脉宽
    # 报文参数
    PUBLIC_ID = 0x01      # 公有报文ID
    PUBLIC_LEN = 20       # 公有报文固定长度(字节)
    SINGLE_VOLT_ID = 0x3B # 单串电压私有报文ID
    UNIQUE_CODE_ID = 0x3C # 电池唯一码私有报文ID
    # 校验码掩码
    CHECKSUM_MASK = 0xFF  # 低8位校验

# 解析状态机定义
class ParseState(Enum):
    IDLE = 0       # 空闲
    SYNC = 1       # 解析同步信号
    DATA = 2       # 解析主报文
    STOP = 3       # 解析停止信号
    CHECK = 4      # 校验与转换

# 电芯材料映射（表A.3）
CELL_MATERIAL = {
    0x00: '默认保留', 0x01: '磷酸铁锂', 0x02: '锰酸锂', 0x03: '三元锂',
    0x04: '钴酸锂', 0x05: '聚合锂', 0x06: '钛酸锂', 0x07: '铅酸',
    0x08: '镍氢', 0x09: '钠', 0x0A: '保留', 0x0B: '保留',
    0x0C: '保留', 0x0D: '保留', 0x0E: '保留', 0x0F: '保留'
}

# 电池工作状态映射（表A.2/A.5）
BATTERY_STATUS = {
    0x00: '电池单独放电', 0x01: '电池单独充电', 0x02: '电池单独回馈',
    0x03: '预留', 0x04: '预留', 0x05: '预留', 0x06: '预留',
    0x07: '预留', 0x08: '预留', 0x09: '预留', 0x0A: '预留',
    0x0B: '预留', 0x0C: '预留', 0x0D: '预留', 0x0E: '预留', 0x0F: '预留'
}

# 故障码/预警/报警映射（表A.4）
FAULT_CODE = {
    0x00: '无故障', 0x01: 'DOC2P 放电过流二级保护', 0x02: 'DOC1P 放电过流一级保护▲',
    0x03: 'CUTP 低温充电保护', 0x04: 'COTP 充电高温保护★', 0x05: 'DOTP 放电高温保护★',
    0x06: 'UVP 欠压保护', 0x07: 'OVP 过压保护▲', 0x08: 'COCP 充电过流保护',
    0x09: 'DUTP 放电低温保护', 0x0A: 'CMOSP 充电MOS故障', 0x0B: 'DMOSP 放电MOS故障'
}
ALARM_CODE = {0x10: '预留', 0x14: '充电高温异常报警★', 0x15: '放电高温异常报警★'}
WARNING_CODE = {
    0x20: '预留', 0x22: '放电过流一级预警▲', 0x23: '低温充电预警', 0x24: '充电高温预警▲',
    0x25: '放电高温预警▲', 0x26: '欠压预警', 0x27: '过压预警▲', 0x28: '充电过流预警',
    0x29: '放电低温预警'
}

# 充电状态映射（表A.5）
CHARGE_STATUS = {
    0x00: '默认保留', 0x01: '满充停止', 0x02: '非法充电', 0x03: '电池保护(可续充)',
    0x04: '正在充电', 0xFF: '无效值'
}

# BMS当前状态位定义（表A.5）
BMS_STATUS_BIT = {
    0: '预留', 1: '预留', 2: '充电器连接状态(0=未连,1=已连)',
    3: '整车是否合法(0=合法,1=不合法)',4: '预留',5: '预放电MOS状态(0=关,1=开)',
    6: '放电MOS状态(0=关,1=开)',7: '充电MOS状态(0=关,1=开)'
}

class XHOneWireHLA(HighLevelAnalyzer):
    # Saleae 配置项（界面可配置）
    sample_rate = NumberSetting(label='采样率(MHz)', default_value=1, min_value=0.1, max_value=10)
    voltage_threshold = NumberSetting(label='高低电平阈值(V)', default_value=2.0, min_value=0.8, max_value=3.3)

    # 解析结果输出通道（Saleae界面分层展示）
    result_types = {
        'physical': {'format': '物理层: {data}'},
        'frame': {'format': '帧解析层: {data}'},
        'app': {'format': '应用层: {data}'},
        'business': {'format': '业务层: {data}'},
        'error': {'format': '【错误】: {data}'}
    }

    def __init__(self):
        # 初始化状态机
        self.state = ParseState.IDLE
        # 时序记录（单位：ms，Saleae采样点转换为时间）
        self.t1_start = None
        self.t2_start = None
        self.bit_start = None
        # 报文缓存
        self.frame_data = b''  # 主报文字节缓存
        self.current_byte = 0  # 正在解析的字节
        self.bit_count = 0     # 已解析的位数
        self.msg_id = None     # 报文ID
        self.msg_len = None    # 报文长度
        # 帧时间戳
        self.frame_start = None
        self.frame_end = None

    def _calc_physical_value(self, c, r, f):
        """物理值转换：P = C*R + F"""
        return round(c * r + f, 2)

    def _check_checksum(self, data, check_byte, start=0, end=None):
        """校验码验证：和的低8位"""
        if end is None:
            end = len(data)
        calc_sum = sum(data[start:end]) & ProtocolConst.CHECKSUM_MASK.value
        return calc_sum == check_byte

    def _parse_public_msg(self, data):
        """解析公有报文（ID=0x01，20字节）- 表A.2"""
        result = []
        # 协议版本（高4位主版本，低4位次版本）
        proto_ver = data[1]
        main_ver = (proto_ver & 0xF0) >> 4
        sub_ver = proto_ver & 0x0F
        result.append(f'协议版本: V{main_ver}.{sub_ver}')
        # 电池厂商代码
        vendor = data[2]
        result.append(f'电池厂商: {"星恒" if vendor == 0x01 else "无效(0xFF)" if vendor == 0xFF else f"未知(0x{vendor:02X})"}')
        # 电池型号
        model = data[3]
        result.append(f'电池型号: {model if model != 0xFF else "无效(0xFF)"}')
        # 电芯材料
        cell_mat = data[4]
        result.append(f'电芯材料: {CELL_MATERIAL.get(cell_mat, "保留/未知")}')
        # 额定电压（16bit，0.1V精度，偏移0）
        rated_volt = struct.unpack('<H', data[5:7])[0]
        result.append(f'额定电压: {self._calc_physical_value(rated_volt, 0.1, 0)}V' if rated_volt != 0xFFFF else '额定电压: 无效(0xFFFF)')
        # 额定容量（16bit，0.1AH精度，偏移0）
        rated_cap = struct.unpack('<H', data[7:9])[0]
        result.append(f'额定容量: {self._calc_physical_value(rated_cap, 0.1, 0)}AH' if rated_cap != 0xFFFF else '额定容量: 无效(0xFFFF)')
        # 剩余电量（8bit，0.5%精度，偏移0）
        soc = data[9]
        result.append(f'剩余电量: {self._calc_physical_value(soc, 0.5, 0)}%' if soc != 0xFF else '剩余电量: 无效(0xFF)')
        # 当前工作电压（16bit，0.1V精度，偏移0）
        curr_volt = struct.unpack('<H', data[10:12])[0]
        result.append(f'当前电压: {self._calc_physical_value(curr_volt, 0.1, 0)}V' if curr_volt != 0xFFFF else '当前电压: 无效(0xFFFF)')
        # 当前工作电流（16bit，0.1A精度，偏移-500）
        curr_curr = struct.unpack('<H', data[12:14])[0]
        result.append(f'当前电流: {self._calc_physical_value(curr_curr, 0.1, -500)}A' if curr_curr != 0xFFFF else '当前电流: 无效(0xFFFF)')
        # 温度（8bit，偏移-40℃）
        max_temp = data[14]
        min_temp = data[15]
        mos_temp = data[16]
        result.append(f'最高温度: {self._calc_physical_value(max_temp, 1, -40)}℃' if max_temp != 0xFF else '最高温度: 无效(0xFF)')
        result.append(f'最低温度: {self._calc_physical_value(min_temp, 1, -40)}℃' if min_temp != 0xFF else '最低温度: 无效(0xFF)')
        result.append(f'MOS温度: {self._calc_physical_value(mos_temp, 1, -40)}℃' if mos_temp != 0xFF else 'MOS温度: 无效(0xFF)')
        # 故障列表
        fault = data[17]
        result.append(f'故障码: 0x{fault:02X} ({FAULT_CODE.get(fault, "预留/未知")})')
        # 电池工作状态
        bat_status = data[18]
        result.append(f'工作状态: 0x{bat_status:02X} ({BATTERY_STATUS.get(bat_status, "预留/未知")})')
        # 校验码
        checksum = data[19]
        is_check_ok = self._check_checksum(data, checksum, 0, 19)
        result.append(f'校验码: 0x{checksum:02X} ({"通过" if is_check_ok else "失败"})')
        return ' | '.join(result), is_check_ok

    def _parse_bms_status(self, status_byte):
        """解析BMS当前状态位（表A.5）"""
        result = []
        for bit in range(8):
            val = (status_byte >> bit) & 0x01
            result.append(f'{BMS_STATUS_BIT[bit]}: {val}')
        return ' | '.join(result)

    def decode(self, frame: AnalyzerFrame):
        """核心解析方法：Saleae逐帧传入原始采样帧"""
        # 原始帧数据：frame.type（high/low）、frame.start_time、frame.end_time（秒）、frame.data
        current_type = frame.type
        current_start = frame.start_time.total_seconds() * 1000  # 转换为ms
        current_end = frame.end_time.total_seconds() * 1000
        pulse_width = current_end - current_start  # 脉宽ms

        # 状态机驱动
        if self.state == ParseState.IDLE:
            # 空闲状态：检测上升沿（high），开始同步信号T1
            if current_type == 'high':
                self.t1_start = current_start
                self.frame_start = current_start
                self.state = ParseState.SYNC
                return AnalyzerFrame('physical', frame.start_time, frame.end_time, {'data': f'检测到上升沿，进入同步信号解析'})

        elif self.state == ParseState.SYNC:
            # 同步信号解析：T1(high)≥10ms → T2(low)=1ms
            if current_type == 'low' and self.t1_start is not None:
                t1_width = current_start - self.t1_start
                # 校验T1脉宽
                if t1_width < ProtocolConst.SYNC_T1_MIN.value:
                    self.state = ParseState.IDLE
                    self.t1_start = None
                    return AnalyzerFrame('error', frame.start_time, frame.end_time, {'data': f'同步信号T1脉宽异常，实测{t1_width:.1f}ms < 最小10ms'})
                self.t2_start = current_start
                return AnalyzerFrame('physical', frame.start_time, frame.end_time, {'data': f'同步信号T1={t1_width:.1f}ms(合格)，开始T2'})
            if current_type == 'high' and self.t2_start is not None:
                t2_width = current_start - self.t2_start
                # 校验T2脉宽
                if abs(t2_width - ProtocolConst.SYNC_T2.value) > 0.2:  # 允许±0.2ms误差
                    self.state = ParseState.IDLE
                    self.t1_start = self.t2_start = None
                    return AnalyzerFrame('error', frame.start_time, frame.end_time, {'data': f'同步信号T2脉宽异常，实测{t2_width:.1f}ms ≠ 1ms'})
                # 同步信号合格，进入主报文解析
                self.state = ParseState.DATA
                self.bit_start = current_start
                self.current_byte = 0
                self.bit_count = 0
                self.frame_data = b''
                return AnalyzerFrame('frame', frame.start_time, frame.end_time, {'data': f'同步信号合格(T1={t1_width:.1f}ms,T2={t2_width:.1f}ms)，进入主报文解析'})

        elif self.state == ParseState.DATA:
            # 主报文解析：按位时序提取逻辑0/1，8位组成1字节
            if self.bit_start is None:
                self.bit_start = current_start
                return
            # 校验位周期（±0.2ms误差）
            if abs(pulse_width - ProtocolConst.BIT_PERIOD.value) > 0.2:
                self.state = ParseState.IDLE
                self.bit_start = None
                return AnalyzerFrame('error', frame.start_time, frame.end_time, {'data': f'位周期异常，实测{pulse_width:.1f}ms ≠ 2ms'})
            # 判断逻辑0/1（根据T1脉宽，high为T1）
            bit_val = 0
            if current_type == 'high':
                if abs(pulse_width - ProtocolConst.BIT1_T1.value) < 0.2:
                    bit_val = 1
                elif abs(pulse_width - ProtocolConst.BIT0_T1.value) < 0.2:
                    bit_val = 0
                else:
                    self.state = ParseState.IDLE
                    return AnalyzerFrame('error', frame.start_time, frame.end_time, {'data': f'位信号T1脉宽异常，实测{pulse_width:.1f}ms'})
            # 按LSB拼接字节（先低后高）
            self.current_byte |= (bit_val << self.bit_count)
            self.bit_count += 1
            self.bit_start = current_end
            # 8位拼接完成，存入字节缓存
            if self.bit_count == 8:
                self.frame_data += struct.pack('B', self.current_byte)
                self.current_byte = 0
                self.bit_count = 0
                # 提取报文ID和长度（第1字节为ID）
                if len(self.frame_data) == 1:
                    self.msg_id = self.frame_data[0]
                    if self.msg_id == ProtocolConst.PUBLIC_ID.value:
                        self.msg_len = ProtocolConst.PUBLIC_LEN.value
                        return AnalyzerFrame('app', frame.start_time, frame.end_time, {'data': f'识别公有报文ID=0x{self.msg_id:02X}，长度={self.msg_len}字节'})
                    elif self.msg_id == ProtocolConst.SINGLE_VOLT_ID.value:
                        self.msg_len = None  # 长度可变，后续解析data_len
                        return AnalyzerFrame('app', frame.start_time, frame.end_time, {'data': f'识别单串电压私有报文ID=0x{self.msg_id:02X}，长度可变'})
                    elif self.msg_id == ProtocolConst.UNIQUE_CODE_ID.value:
                        self.msg_len = None  # 长度可变
                        return AnalyzerFrame('app', frame.start_time, frame.end_time, {'data': f'识别电池唯一码私有报文ID=0x{self.msg_id:02X}，长度可变'})
                    else:
                        self.msg_len = None  # 自定义私有报文，长度可变
                        return AnalyzerFrame('app', frame.start_time, frame.end_time, {'data': f'识别自定义私有报文ID=0x{self.msg_id:02X}，长度可变'})
                # 公有报文长度校验
                if self.msg_id == ProtocolConst.PUBLIC_ID.value and len(self.frame_data) >= self.msg_len:
                    self.state = ParseState.STOP
                    self.t1_start = current_end
                    return AnalyzerFrame('frame', frame.start_time, frame.end_time, {'data': f'主报文解析完成，共{len(self.frame_data)}字节，进入停止信号解析'})

        elif self.state == ParseState.STOP:
            # 停止信号解析：T1(high)=5ms → T2(low)≥50ms
            if current_type == 'low' and self.t1_start is not None:
                t1_width = current_start - self.t1_start
                if abs(t1_width - ProtocolConst.STOP_T1.value) > 0.5:  # 允许±0.5ms误差
                    self.state = ParseState.IDLE
                    self.t1_start = None
                    return AnalyzerFrame('error', frame.start_time, frame.end_time, {'data': f'停止信号T1脉宽异常，实测{t1_width:.1f}ms ≠ 5ms'})
                self.t2_start = current_start
                return AnalyzerFrame('physical', frame.start_time, frame.end_time, {'data': f'停止信号T1={t1_width:.1f}ms(合格)，开始T2'})
            if current_type == 'high' and self.t2_start is not None:
                t2_width = current_start - self.t2_start
                if t2_width < ProtocolConst.STOP_T2_MIN.value:
                    self.state = ParseState.IDLE
                    self.t1_start = self.t2_start = None
                    return AnalyzerFrame('error', frame.start_time, frame.end_time, {'data': f'停止信号T2脉宽异常，实测{t2_width:.1f}ms < 最小50ms'})
                # 停止信号合格，进入校验阶段
                self.state = ParseState.CHECK
                self.frame_end = current_end
                frame_duration = self.frame_end - self.frame_start
                return AnalyzerFrame('frame', frame.start_time, frame.end_time, {'data': f'停止信号合格(T1={t1_width:.1f}ms,T2={t2_width:.1f}ms)，帧总时长={frame_duration:.1f}ms'})

        elif self.state == ParseState.CHECK:
            # 校验与业务层解析
            self.state = ParseState.IDLE  # 解析完成，返回空闲
            if self.msg_id == ProtocolConst.PUBLIC_ID.value:
                # 解析公有报文
                if len(self.frame_data) != ProtocolConst.PUBLIC_LEN.value:
                    return AnalyzerFrame('error', frame.start_time, frame.end_time, {'data': f'公有报文长度异常，实测{len(self.frame_data)}字节 ≠ 20字节'})
                busi_info, is_check_ok = self._parse_public_msg(self.frame_data)
                if not is_check_ok:
                    return AnalyzerFrame('error', frame.start_time, frame.end_time, {'data': f'公有报文校验码失败 | {busi_info}'})
                return AnalyzerFrame('business', frame.start_time, frame.end_time, {'data': busi_info})
            else:
                # 私有报文（基础解析，可根据客户需求扩展）
                checksum = self.frame_data[-1]
                is_check_ok = self._check_checksum(self.frame_data, checksum, 0, -1)
                base_info = f'私有报文ID=0x{self.msg_id:02X}，长度={len(self.frame_data)}字节，校验码=0x{checksum:02X}({"通过" if is_check_ok else "失败"})'
                if not is_check_ok:
                    return AnalyzerFrame('error', frame.start_time, frame.end_time, {'data': base_info})
                return AnalyzerFrame('business', frame.start_time, frame.end_time, {'data': base_info})

        # 无解析结果时返回None
        return None