import machine
from machine import Pin, I2C, UART, RTC
import struct
import math
import time
import ssd1306

# ==========================================================
# --- 1. CẤU HÌNH HỆ THỐNG ---
# ==========================================================
i2c = I2C(0, scl=Pin(22), sda=Pin(21))
oled = ssd1306.SSD1306_I2C(128, 32, i2c, addr=0x3C)
rtc = RTC()

uart = UART(2, baudrate=9600, bits=8, parity=None, stop=1, tx=17, rx=16, timeout=500)
rs485_en = Pin(18, Pin.OUT, value=0)

# Định nghĩa nút nhấn
BTN_K1 = Pin(27, Pin.IN, Pin.PULL_UP) # Thoát / Tăng
BTN_K2 = Pin(14, Pin.IN, Pin.PULL_UP) # Cài đặt / Giảm
BTN_K3 = Pin(26, Pin.IN, Pin.PULL_UP) # Lưu & Nhảy mét
BTN_K4 = Pin(13, Pin.IN, Pin.PULL_UP) # Đo / Xác nhận

# Biến dự án
project_name = "DUAN-01"
n_meters = 14        
current_m = 14       
save_count = 0       # Bắt đầu từ 0 lần lưu
chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ -"

# ==========================================================
# --- 2. HÀM TRỢ GIÚP ---
# ==========================================================
def crc16(data):
    crc = 0xFFFF
    for pos in data:
        crc ^= pos
        for i in range(8):
            if (crc & 1) != 0: crc >>= 1; crc ^= 0xA001
            else: crc >>= 1
    return crc

def read_sensor():
    try:
        msg = struct.pack('>BBHH', 1, 4, 0x0120, 6)
        msg += struct.pack('<H', crc16(msg))
        while uart.any(): uart.read()
        rs485_en.value(1)
        uart.write(msg)
        time.sleep_ms(15)
        rs485_en.value(0)
        time.sleep_ms(300)
        if uart.any():
            raw = uart.read()
            idx = raw.find(b'\x01\x04\x0c')
            if idx != -1 and len(raw) >= idx + 17:
                packet = raw[idx : idx + 17]
                if crc16(packet[:-2]) == struct.unpack('<H', packet[-2:])[0]:
                    regs = struct.unpack('>HHHHHH', packet[3:15])
                    rx = struct.unpack('>i', struct.pack('>HH', regs[0], regs[1]))[0]
                    ry = struct.unpack('>i', struct.pack('>HH', regs[2], regs[3]))[0]
                    x = math.degrees(math.asin(max(-1, min(1, rx / 1310720000.0))))
                    y = math.degrees(math.asin(max(-1, min(1, ry / 1310720000.0))))
                    return x, y
    except: pass
    return None

def show_oled(l1, l2="", l3=""):
    oled.fill(0)
    oled.text(l1, 0, 0)
    oled.text(l2, 0, 12)
    oled.text(l3, 0, 24)
    oled.show()

# Hàm khởi tạo file CSV riêng cho từng dự án
def init_project_file(name):
    filename = f"{name}.csv"
    try:
        with open(filename, "r") as f: pass
    except:
        try:
            with open(filename, "w") as f: 
                f.write("Project,Meter,X,Y\n")
        except:
            pass

# Khởi tạo file ban đầu cho dự án mặc định
init_project_file(project_name)

# ==========================================================
# --- 3. KIỂM TRA KẾT NỐI BAN ĐẦU ---
# ==========================================================
show_oled("DANG KIEM TRA CB..", "VUI LONG CHO")
while True:
    if read_sensor() is not None:
        break
    time.sleep(1)

# ==========================================================
# --- 4. VÒNG LẶP CHÍNH ---
# ==========================================================
state = "START_SCREEN" # Bắt đầu ở trang đầu tiên sau khi kết nối thành công
cur_x, cur_y = 0.0, 0.0

while True:
    header = f"P:{project_name[:7]} L:{save_count}"

    # --- TRANG ĐẦU: Cho phép bắt đầu đo hoặc vào cài đặt ---
    if state == "START_SCREEN":
        show_oled("HE THONG SAN SANG", "K1: BAT DAU DO", "K2: CAI DAT")
        if BTN_K1.value() == 0:
            state = "STANDBY"
            time.sleep_ms(300)
        if BTN_K2.value() == 0:
            state = "SET_NAME"
            edit_val = list((project_name + "        ")[:8])
            cursor = 0
            time.sleep_ms(300)

    # --- TRẠNG THÁI CHỜ ĐO: K2 đã bị khóa hoàn toàn ---
    elif state == "STANDBY":
        show_oled(header, f"MUC TIEU: {current_m}m", "K4:DO")
        if BTN_K4.value() == 0:
            state = "MEASURING"
            time.sleep_ms(200)

    elif state == "MEASURING":
        show_oled(header, "DANG DOC CB...", "VUI LONG DOI")
        data = read_sensor()
        if data:
            cur_x, cur_y = data
            state = "DISPLAY_VAL"
        else:
            show_oled("LOI KET NOI!", "K4: THU LAI", "K1: QUAY LAI")
            if BTN_K1.value() == 0: state = "STANDBY"
        time.sleep_ms(200)

    elif state == "DISPLAY_VAL":
        show_oled(header, f"X:{cur_x:.4f}", f"Y:{cur_y:.4f}  K3:LUU")
        if BTN_K4.value() == 0: 
            state = "MEASURING"
            time.sleep_ms(300)
        if BTN_K3.value() == 0: # LƯU VÀ NHẢY MÉT
            try:
                filename = f"{project_name}.csv"
                with open(filename, "a") as f:
                    f.write(f"{project_name},{current_m},{cur_x:.4f},{cur_y:.4f}\n")
                
                save_count += 1 
                
                if current_m > 0:
                    current_m -= 1
                    state = "STANDBY"
                else:
                    state = "FINISH"
            except Exception as e:
                show_oled("LOI GHI FILE!")
                time.sleep(1)
                state = "STANDBY"
            time.sleep_ms(300)
        if BTN_K1.value() == 0: 
            state = "STANDBY"
            time.sleep_ms(300)

    # --- KẾT THÚC DỰ ÁN: Cho phép quay về Trang đầu để cài đặt lại ---
    elif state == "FINISH":
        show_oled("DA XONG DU AN!", f"FILE: {project_name}.csv", "K1: THOAT")
        if BTN_K1.value() == 0: 
            current_m = n_meters
            save_count = 0 
            state = "START_SCREEN" # Quay lại trang đầu để có thể nhấn K2 cài đặt lại [1]
            time.sleep_ms(300)

    # --- CÁC GIAO DIỆN CÀI ĐẶT ---
    elif state == "SET_NAME":
        oled.fill(0)
        oled.text("TEN DU AN:", 0, 0)
        oled.text("".join(edit_val), 0, 12)
        oled.text("^", cursor * 8, 24)
        oled.show()
        if BTN_K1.value() == 0:
            idx = chars.find(edit_val[cursor])
            edit_val[cursor] = chars[(idx + 1) % len(chars)]
            time.sleep_ms(150)
        if BTN_K2.value() == 0:
            idx = chars.find(edit_val[cursor])
            edit_val[cursor] = chars[(idx - 1) % len(chars)]
            time.sleep_ms(150)
        if BTN_K3.value() == 0:
            cursor = (cursor + 1) % 8
            while BTN_K3.value() == 0: time.sleep_ms(10)
        if BTN_K4.value() == 0:
            project_name = "".join(edit_val).strip()
            state = "SET_DEPTH"
            while BTN_K4.value() == 0: time.sleep_ms(10)
            time.sleep_ms(200)

    elif state == "SET_DEPTH":
        show_oled(f"P:{project_name}", f"TONG MET N: {n_meters}", "K1:+ K2:- K4:OK")
        if BTN_K1.value() == 0: 
            n_meters += 1
            time.sleep_ms(150)
        if BTN_K2.value() == 0:
            if n_meters > 0: n_meters -= 1
            time.sleep_ms(150)
        if BTN_K4.value() == 0:
            current_m = n_meters
            save_count = 0 
            init_project_file(project_name)
            state = "STANDBY"
            while BTN_K4.value() == 0: time.sleep_ms(10)
            time.sleep_ms(200)

    time.sleep_ms(50)