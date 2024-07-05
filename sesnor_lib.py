import time
import serial

class DFRobot_mmWave_Radar:
    def __init__(self, port, baudrate=115200):
        self._s = serial.Serial(port, baudrate, timeout=1)

    '''def readN(self):
        if self._s.in_waiting > 0:
                buf = self._s.readline().decode('utf-8').strip()
        return buf, len(buf)

    def readPresenceDetection(self):
        dat, len = self.readN();
        ret = False
        print(dat)
        
        if dat[7] == ord('1'):
                ret = True
        elif dat[7] == ord('0'):
                ret = False
        else:
            raise Exception("Failed to read presence detection data")
        return ret'''
        
    def readN(self, buf, length):
        offset = 0
        left = length
        timeout = 1.5  # 1500 ms
        buffer = buf
        start_time = time.time()
        
        while left:
            if self._s.in_waiting > 0:
                buffer[offset] = self._s.read(1)[0]
                offset += 1
                left -= 1
            if time.time() - start_time > timeout:
                break
        return offset

    def recdData(self, buf):
        timeout = 50  # 50000 ms
        start_time = time.time()
        ch = bytearray(1)
        ret = False

        while not ret:
            if time.time() - start_time > timeout:
                break
            if self.readN(ch, 1) == 1:
                if ch[0] == ord('$'):
                    buf[0] = ch[0]
                    if self.readN(ch, 1) == 1:
                        if ch[0] == ord('J'):
                            buf[1] = ch[0]
                            if self.readN(ch, 1) == 1:
                                if ch[0] == ord('Y'):
                                    buf[2] = ch[0]
                                    if self.readN(ch, 1) == 1:
                                        if ch[0] == ord('B'):
                                            buf[3] = ch[0]
                                            if self.readN(ch, 1) == 1:
                                                if ch[0] == ord('S'):
                                                    buf[4] = ch[0]
                                                    if self.readN(ch, 1) == 1:
                                                        if ch[0] == ord('S'):
                                                            buf[5] = ch[0]
                                                            '''if self.readN(ch, 1) == 1:
                                                                buf[6] = ch[0]
                                                                if self.readN(ch, 1) == 1:
                                                                        buf[7] = ch[0]
                                                            if self.readN(buf[8:], 7) == 7:
                                                                ret = True'''
                                                            for x in range(6, 15):
                                                                if self.readN(ch, 1) == 1:
                                                                        buf[x] = ch[0]
                                                            ret = True    
        return ret

    def readPresenceDetection(self):
        dat = bytearray(15)
        ret = False
        if self.recdData(dat):
            #print(dat)
            if dat[7] == ord('1'):
                ret = True
            elif dat[7] == ord('0'):
                ret = False
        else:
            raise Exception("Failed to read presence detection data")
        return ret

    def sendCommand(self, command):
        self._s.write(command.encode())
        time.sleep(1)

    def DetRangeCfg(self, parA_s, parA_e, parB_s=None, parB_e=None, parC_s=None, parC_e=None, parD_s=None, parD_e=None):
        comStop = "sensorStop"
        comSaveCfg = "saveCfg 0x45670123 0xCDEF89AB 0x956128C6 0xDF54AC89"
        comStart = "sensorStart"

        commands = [comStop]
        if parB_s is None:
            comDetRangeCfg = f"detRangeCfg -1 {int(parA_s / 0.15)} {int(parA_e / 0.15)}"
        elif parC_s is None:
            comDetRangeCfg = f"detRangeCfg -1 {int(parA_s / 0.15)} {int(parA_e / 0.15)} {int(parB_s / 0.15)} {int(parB_e / 0.15)}"
        elif parD_s is None:
            comDetRangeCfg = f"detRangeCfg -1 {int(parA_s / 0.15)} {int(parA_e / 0.15)} {int(parB_s / 0.15)} {int(parB_e / 0.15)} {int(parC_s / 0.15)} {int(parC_e / 0.15)}"
        else:
            comDetRangeCfg = f"detRangeCfg -1 {int(parA_s / 0.15)} {int(parA_e / 0.15)} {int(parB_s / 0.15)} {int(parB_e / 0.15)} {int(parC_s / 0.15)} {int(parC_e / 0.15)} {int(parD_s / 0.15)} {int(parD_e / 0.15)}"
        
        commands.append(comDetRangeCfg)
        commands.append(comSaveCfg)
        commands.append(comStart)

        for command in commands:
            self.sendCommand(command)

    def OutputLatency(self, par1, par2):
        comStop = "sensorStop"
        comSaveCfg = "saveCfg 0x45670123 0xCDEF89AB 0x956128C6 0xDF54AC89"
        comStart = "sensorStart"
        
        Par1 = int(par1 * 1000 / 25)
        Par2 = int(par2 * 1000 / 25)
        comOutputLatency = f"outputLatency -1 {Par1} {Par2}"
        
        commands = [comStop, comOutputLatency, comSaveCfg, comStart]
        
        for command in commands:
            self.sendCommand(command)

    def factoryReset(self):
        comStop = "sensorStop"
        comFactoryReset = "factoryReset 0x45670123 0xCDEF89AB 0x956128C6 0xDF54AC89"
        comSaveCfg = "saveCfg 0x45670123 0xCDEF89AB 0x956128C6 0xDF54AC89"
        comStart = "sensorStart"
        
        commands = [comStop, comFactoryReset, comSaveCfg, comStart]
        
        for command in commands:
            self.sendCommand(command)
            
    def setRange(self, par1, par2):
        self.sendCommand(f"setRange {par1} {par2}")
        
    def getRange(self):
        self.sendCommand("getRange")
        
    def setSensitivity(self, par1):
        self.sendCommand(f"setSensitivity {par1}")
        
    def getSensitivity(self):
        self.sendCommand("getSensitivity")   
        
    def setLatency(self, par1, par2):
        self.sendCommand(f"setLatency {par1} {par2}")
        
    def getLatency(self):
        self.sendCommand("getLatency") 
        
    ''' par2: 0(when working the LED flashes once per second, and stays on stopped)    
        par2: 1(when working the LED is off and it is always on when stopped)'''
    def setLedMode(self, par2):
        self.sendCommand(f"setLedMode 1 {par2}")
        
    def getLedMode(self):
        self.sendCommand("getLedMode 1")
        
    ''' par1: 0 Disable echo prompt "leapMMW:/>, par1: 1 Enable echo prompt(default)" '''    
    def setEcho(self, par1=1):
        self.sendCommand(f"setEcho {par1}")
        
    def getEcho(self):
        self.sendCommand("getEcho")
        
    ''' par1: 1(output $JYBSS message), 2(output $JYRPO message) 
        par2: 0(disable par1 messaging), 1(enable par1 messaging)  
        -when  0.025 < par4 < 1500- 
        par3: 0(output data according to cycle set by par4), 
        par3: 1(output data immediately when data changes, and accoridng to par4 when data doesnt change )
        -when  par4 > 1500-
        par3: 0(do not output data(must use getOutput to get data)) 
        par0: 1(output immedietly when data changes and dont output when data doesnt change)'''    
    def setUartOutput(self, par1, par2, par3="", par4=""):
        self.sendCommand(f"setUartOutput {par1} {par2} {par3} {par4}")
        
    def getUartOutput(self, par1):
        self.sendCommand(f"getUartOutput {par1}")
        
    def sensorStop(self):
        self.sendCommand("sensorStop")
        
    def sensorStart(self):
        self.sendCommand("sensorStart")
        
    def saveConfig(self):
        self.sendCommand("saveConfig")
        
    def resetCfg(self):
        self.sendCommand("resetCfg")
        
    ''' par1: 0 Normal software reset  
        par2: 1 Software reset and enter the bootloader'''  
    def resetSystem(self, par1):
        self.sendCommand(f"resetSystem {par1}")

# Example usage:
# radar = DFRobot_mmWave_Radar('/dev/ttyUSB0')  # Replace with your actual port
# if radar.readPresenceDetection():
#     print("Presence detected")
# else:
#     print("No presence detected")
