from saleae.analyzer import Analyzer, Device
from saleae.protocol_exporter import ProtocolExporter
import time

class XinghengOneWireAnalyzer(Analyzer):
    settings = {}

    def __init__(self, analyzer, settings):
        super().__init__(analyzer, settings)
        self.channel = int(settings.get('channel', 0))
        # 时间阈值 (单位: 秒)，根据文档 ms 转换
        self.T_SYNC_LOW_MIN = 0.010   # 10ms
        self.T_BIT_PERIOD = 0.002     # 2ms (0.5+1.5 or 1.5+0.5)
        self.T_STOP_LOW_MIN = 0.005   # 5ms
        self.T_STOP_HIGH_MIN = 0.050  # 50ms
        
        # 容差范围 (建议设为周期的 20%-30% 以适应噪声)
        self.TOLERANCE = 0.0004 

    def decode(self):
        samples_per_second = self.analyzer.sample_rate
        samples_sync_low_min = int(self.T_SYNC_LOW_MIN * samples_per_second)
        samples_bit_period = int(self.T_BIT_PERIOD * samples_per_second)
        samples_stop_low_min = int(self.T_STOP_LOW_MIN * samples_per_second)
        samples_stop_high_min = int(self.T_STOP_HIGH_MIN * samples_per_second)
        
        # 获取通道采样数据
        data = self.analyzer.get_sample_data(self.channel)
        
        # 状态机变量
        state = 'IDLE' 
        frame_bits = []
        current_time = 0
        
        # 遍历边沿 (Edge Detection)
        # 注意：实际实现需使用 analyzer.get_transitions() 或手动扫描电平变化
        transitions = self.analyzer.get_transitions(self.channel)
        
        for i in range(len(transitions) - 1):
            t_start, level_start = transitions[i]
            t_end, level_end = transitions[i+1]
            duration = t_end - t_start
            
            if state == 'IDLE':
                # 检测同步信号：低电平 >= 10ms
                if level_start == 0 and duration >= self.T_SYNC_LOW_MIN:
                    state = 'READING_BITS'
                    frame_bits = []
                    self.analyzer.mark_frame_start(t_start, "Sync")
            
            elif state == 'READING_BITS':
                # 检测停止信号：低电平 >= 5ms 且随后高电平 >= 50ms
                # 简化处理：如果低电平超过 5ms，检查后续是否长时间高电平
                if level_start == 0 and duration >= self.T_STOP_LOW_MIN:
                    # 预判断停止位，需查看下一个边沿
                    if i+1 < len(transitions):
                        next_t, next_lvl = transitions[i+1]
                        if next_lvl == 1 and (next_t - t_end) >= self.T_STOP_HIGH_MIN:
                            state = 'IDLE'
                            self.process_frame(frame_bits, t_start)
                            self.analyzer.mark_frame_end(t_end, "Stop")
                            continue
                
                # 解析数据位 (周期应接近 2ms)
                if abs(duration - self.T_BIT_PERIOD) < self.TOLERANCE:
                    # 判断是 0 还是 1
                    # 逻辑 1: Low 0.5, High 1.5 -> 低电平短
                    # 逻辑 0: Low 1.5, High 0.5 -> 低电平长
                    if level_start == 0: # 关注低电平宽度
                        if duration < 0.001: # 约 0.5ms
                            frame_bits.append(1)
                        else: # 约 1.5ms
                            frame_bits.append(0)
                    # 如果是高电平开始，逻辑相反，但通常从低电平边缘判断更稳
                    # 此处简化逻辑，实际需根据具体波形相位调整
                    
            # 异常处理：如果脉宽严重偏离，重置帧
            if duration > 0.010 and state == 'READING_BITS' and level_start == 0:
                 # 非停止位的长低电平，视为错误
                 state = 'IDLE'

    def process_frame(self, bits, timestamp):
        # 1. 将 bit 流转换为 Byte 流 (LSB First)
        if len(bits) % 8 != 0:
            return # 帧长度错误
            
        bytes_list = []
        for i in range(0, len(bits), 8):
            byte_bits = bits[i:i+8]
            # LSB First 重组
            byte_val = 0
            for j, bit in enumerate(byte_bits):
                byte_val |= (bit << j)
            bytes_list.append(byte_val)
            
        if len(bytes_list) < 4:
            return

        # 2. 解析报文头
        msg_id = bytes_list[0]
        version = bytes_list[1]
        
        frame_type = "Unknown"
        if msg_id == 0x01:
            frame_type = "Public (0x01)"
            self.parse_public_msg(bytes_list, timestamp)
        elif msg_id == 0x3A:
            frame_type = "Private Real-time (0x3A)"
            self.parse_private_realtime(bytes_list, timestamp)
        elif msg_id == 0x3B:
            frame_type = "Private Cell Voltage (0x3B)"
        elif msg_id == 0x3C:
            frame_type = "Private Unique ID (0x3C)"
            
        # 3. 校验和验证
        # SUM = ID + Ver + Data (不含SUM本身)
        # 文档规定：SUM = ID + 协议版本 + Byte0...Byte(Len-4)
        # 注意：文档中 Len 包含 ID, Ver, Data, Sum。
        # 公有报文 Len=20。私有报文 Len 可变。
        
        calculated_sum = sum(bytes_list[:-1]) & 0xFF
        received_sum = bytes_list[-1]
        
        status = "OK" if calculated_sum == received_sum else "CRC Error"
        
        # 在 Saleae 界面显示结果
        result_str = f"{frame_type} | SOC:{self.extract_soc(bytes_list)} | V:{self.extract_volts(bytes_list)} | {status}"
        self.analyzer.add_result(timestamp, result_str)

    def parse_public_msg(self, data, ts):
        # 根据表 A.2 解析
        # 示例：提取额定电压 (Index 5, 16bit, Little Endian)
        if len(data) >= 20:
            rated_volts_raw = data[5] | (data[6] << 8)
            rated_volts = rated_volts_raw * 0.1
            # 添加详细测量值到 Saleae 表格
            self.analyzer.add_measurement("Rated Voltage", f"{rated_volts:.1f}V", ts)

    def extract_soc(self, data):
        # 简单提取 SOC (公有报文 index 9, 私有 index 3)
        if data[0] == 0x01 and len(data) > 9:
            return data[9] * 0.5
        elif data[0] == 0x3A and len(data) > 3:
            return data[3] * 0.5
        return 0

    def extract_volts(self, data):
        # 简单提取工作电压
        if data[0] == 0x01 and len(data) > 11:
            raw = data[10] | (data[11] << 8)
            return raw * 0.1
        elif data[0] == 0x3A and len(data) > 5:
            raw = data[4] | (data[5] << 8)
            return raw * 0.1
        return 0

# Saleae 注册配置
settings = [
    {'id': 'channel', 'type': 'integer', 'min': 0, 'max': 15, 'default': 0, 'label': 'Input Channel'}
]

def setup(analyzer, settings):
    return XinghengOneWireAnalyzer(analyzer, settings)
