import ujson
from gpb import UART, delay
from machine import Pin
import time


class AIFML:
    AIFML_URL = "140.110.3.59"
    AIFML_SIGNIN_ENDPOINT = "/aifml/api/sign-in/"
    AIFML_REQUEST_GET_ENDPOINT = "/aifml/api/profile-get-fmldata/?access_token={}"
    TCPIP = "TCP"
    PORT = 80

    ZERO = ""
    ZERO_READ = None # define after initialization
    ZERO_MESSAGE = bytearray(ZERO)

    def __init__(self, wifiusn, wifipwd, usn, pwd, dataStages):
        self.username = usn
        self.password = pwd

        self.dataStages = dataStages

        self.uartdev = UART(0, 115200)
        self.ZERO_READ = self.uartdev.uart_read(6)

        self.connected = self.enableNetwork(wifiusn, wifipwd)
        delay(100)

        self.sendAT("AT+CIFSR")
        replymsg = self.getMessageAT_Byte2String()
        print("IP Address:", replymsg)

        if ((not self.connected) or ("OK" not in replymsg)): 
            print("reply: \"{}\", connected: {}".format(replymsg, self.connected))
            return

        print("Account Login Starts")
        self.accessToken = self.enableAIFML()
        print("Account Login Ends")

        if self.accessToken in ["busy", "404 not Found", "StatusFalse"]:  
            print("accessToken replied: \"{}\"".format(self.accessToken))
            return



    def getDataFromFML(self):
        # Every 3sec, send profile-get-fmldata command
        requestGetURL = self.AIFML_REQUEST_GET_ENDPOINT.format(self.accessToken)     
        replymsg = self.sendCommandGet(requestGetURL)
        self.processGetData(replymsg)



    def sendAT(self, cmd, delay1=100):
        #用來傳AT指令的function (包含傳送後的等待時間)
        self.uartdev.uart_write(str(cmd) + "\r\n")
        delay(delay1)



    def GetMessageAT(self, switch):
        readMessage = self.ZERO_MESSAGE
        receivedMessage = self.ZERO_MESSAGE
        while switch:
            readMessage = self.uartdev.uart_read(6)
            switch = readMessage==self.ZERO_READ
            receivedMessage = receivedMessage + readMessage
        return receivedMessage



    def sendCommandGet(self, requestcmd):    
        self.sendAT("AT+CIPSTART=\"{}\",\"{}\",{}".format(self.TCPIP, self.AIFML_URL, self.PORT), 1000)   #aifml學習平台位址
        self.GetMessageAT(1)

        getstr = "GET " + requestcmd + " HTTP/1.1\r\n" + "Host: " + self.AIFML_URL + "\r\n" + "Connection: close\r\n"   #資料拆解過濾
        command = "AT+CIPSEND=" + str(len(getstr) + 2)
        self.sendAT(command, 1000)    
        self.GetMessageAT(1)

        self.sendAT(getstr, 1000)
        replymsg = self.getMessageAT_Byte2String()
        return replymsg



    def analyzeGetFMLData(self, replymsg):
        json_msg = self.jsonDataParse(replymsg)
        if (json_msg == "JSONError"): return 0, "JSONError", ""

        jsondata = ujson.loads(json_msg)
        status = jsondata["status"]
        replymsg = ""
        if (status != True): return 0, "StatusFalse", ""
        print("analyzecmd_Get_fmldat(jsondata): ", jsondata)
        fmljsondata = ujson.loads(jsondata["data"]["fmldata"])
        
        type = fmljsondata["type"]
        inFV_n = fmljsondata["inFV_n"]           #input_name
        inFV_v = fmljsondata["inFV_v"]           #input_value
        inFV_s = fmljsondata["inFV_s"]           #input_result
        outFV_n = fmljsondata["outFV_n"]         #output_name
        outFV_v = fmljsondata["outFV_v"]         #output_value
        outFV_s = fmljsondata["outFV_s"]         #output_result
        replymsg = "IF "
        inFVcount = len(inFV_v)
        returnmsg = "Input:\n" + "["    #LCD顯示input_value

        for i in range(inFVcount - 1):
            replymsg = replymsg + "{}({}){} and ".format(inFV_n[i], inFV_v[i], inFV_s[i])
            #print("inFV_n: {}, inFV_v: {}, inFV_s: {}".format(inFV_n[i], inFV_v[i], inFV_s[i]))
            returnmsg = returnmsg + "{},".format(inFV_v[i])
        

        replymsg = replymsg + "{}({}){} ".format(inFV_n[inFVcount - 1], inFV_v[inFVcount - 1], inFV_s[inFVcount - 1])
        #print("inFV_n: {}, inFV_v: {}, inFV_s: {}".format(inFV_n[inFVcount - 1], inFV_v[inFVcount - 1], inFV_s[inFVcount - 1]))
        returnmsg = returnmsg + "{}".format(inFV_v[inFVcount - 1]) + "]" + "\n" + "\n" 

        #output fuzzy variable
        replymsg = replymsg + "THEN {}({}){}".format(outFV_n, outFV_v, outFV_s)
        #print("outFV_n: {}, outFV_v: {}, outFV_s: {}".format(outFV_n, outFV_v, outFV_s))
        print("reply: ", replymsg)
        returnmsg = returnmsg + "Output:\n {}".format(outFV_v)   #LCD顯示output_value
        delay(3000)

        return float(outFV_v), returnmsg, fmljsondata["datetimestamp"]
            


    def activateHardward(self, outv, receivedmsg):
        #outv: 解模糊化後的值
        #判斷解模糊化後的數值並做出對應動作
        for i in range(len(self.dataStages)):
            if self.dataStages[i][0][0] <= outv and outv < self.dataStages[i][0][1]:
                self.dataStages[i][1]()

        #顯示文字在LCD
        print(receivedmsg)



    def processGetData(self, replymsg):
        #處理API profile-get-fmldata回傳的資訊
        if ("ERROR" in replymsg):
            print ("Sending Get Command has error")
            datetimestamp = ""
        else:
            outv, receivedmsg, datetimestamp = self.analyzeGetFMLData(replymsg)
            if (receivedmsg == "StatusFalse"):
                print ("There does not exist fmldata")
            elif (receivedmsg == "JSONError"):
                print ("Received fmldata has no JSON data")
            else:
                self.activateHardward(outv, receivedmsg)
        return datetimestamp



    def jsonDataParse(self, replymsg):
        startIndex = replymsg.find("{")
        endIndex = replymsg.rfind("}")
        if ((startIndex == -1) or (endIndex == -1)): return "JSONError"
        json_msg = ""
        for i in range(startIndex, endIndex + 1, 1):
            json_msg = json_msg + replymsg[i]   
        return json_msg
            



    def enableAIFML(self):
        self.sendAT("AT+CIPSTART=\"{}\",\"{}\",{}".format(self.TCPIP, self.AIFML_URL, self.PORT), 1000)
        self.GetMessageAT(1)

        formdata = "account=" + self.username + "&password=" + self.password       #登入學習平台帳號密碼
        reqstr = "POST " + self.AIFML_SIGNIN_ENDPOINT + " HTTP/1.1\r\n" + "Authorization: Basic cGM6cGM= \r\n" + "Content-Type: application/x-www-form-urlencoded\r\n" +"Host: " + self.AIFML_URL + "\r\n" + "Content-Length: " + str(len(formdata)) + "\r\n" + "\r\n" + formdata + "\r\n"
        command = "AT+CIPSEND=" + str(len(reqstr) + 2)
        self.sendAT(command, 1000)    
        self.GetMessageAT(1)

        self.sendAT(reqstr, 1000)
        replymsg = self.getMessageAT_Byte2String()

        #處理post_signin回傳的資訊
        if ("busy" in replymsg): return "busy"
        if ("404 Not Found" in replymsg): return "404 Not Found"
        #read response   
        json_msg = self.jsonDataParse(replymsg)
        #print("analyzecmd_Post_signin(json_msg): ", json_msg)
        if (json_msg == "JSONError"): return "JSONError"
        jsondata = ujson.loads(json_msg)
        #print("analyzecmd_Post_signin(jsondata): ", jsondata)     
        #check status
        status = jsondata["status"]
        if (status != True): return "StatusFalse"
        return jsondata["data"]["access_token"]



    def enableNetwork(self, wifiusn, wifipwd):    
        self.sendAT("ATE0", 200) # Clear Mirror
        print("Read Version - AT+GMR ")
        self.sendAT("AT+GMR", 200) # Read Version
        self.getMessageAT_Byte2String()

        #sendAT("AT+RESTORE", 1000) # 恢復預設設定
        print("設為 station 模式 - AT+CWMODE=1 ")
        self.sendAT("AT+CWMODE=1", 200) # 設為 station 模式
        self.getMessageAT_Byte2String()

        # 連到 WiFi (建議等久一點)
        print("Connecting to WIFI.... Please wait")
        self.sendAT("AT+CWJAP=\"{}\",\"{}\"".format(wifiusn, wifipwd), 15000)
        replymsg = self.getMessageAT_Byte2String()
        return replymsg.find("WIFI CONNECTED") != -1



    def convertByte2String(self, readMessage):   
        # Convert bytearray to bytes
        byteObj = bytes(readMessage)
        return byteObj.decode("utf-8")



    def getMessageAT_Byte2String(self):   
        readMessage = self.ZERO_MESSAGE
        receivedMessage = self.ZERO_MESSAGE
        receivedMessage_String = ""
        while(True):
            readMessage = self.uartdev.uart_read(6)
            if readMessage == self.ZERO_READ:
                receivedMessage_String = self.convertByte2String(receivedMessage)
                print("Start receivedMessage_String(getMessageAT_Byte2String): ", receivedMessage_String)
                print("End receivedMessage_String(getMessageAT_Byte2String)")
                return receivedMessage_String
            receivedMessage = receivedMessage + readMessage








if __name__ == "__main__":
    AIFMLusername = "nutneleS010102"     # AIFML學習平台帳號
    AIFMLpassword = "nutneleS010102"     # AIFML學習平台密碼
    WIFIusername  = "LAB_I3302"          # 現場 WiFi 名稱
    WIFIpassword  = "Fj2D9dQHnr"         # 現場 WiFi 密碼

    def func1():
        print("Function 1 Executed")
    def func2():
        print("Function 2 Executed")
    def func3():
        print("Function 3 Executed")

    fml = AIFML(
        WIFIusername, WIFIpassword,
        AIFMLusername, AIFMLpassword,
        [
            [ [0 , 35 ], func1],
            [ [35, 65 ], func2],
            [ [65, 100], func3],
        ]
    )
    if(fml.connected and fml.accessToken):
        while(1):
            print("result: ", fml.getDataFromFML())
            delay(3000)
    else:
        print("Error while: \nConnecting to Wifi\nor\nLogin to AI-FML")