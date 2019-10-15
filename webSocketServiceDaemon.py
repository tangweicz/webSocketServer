#!/Library/Frameworks/Python.framework/Versions/3.6/bin/python3.6
#! -*- coding:utf-8 -*-

from websocketServer.webSocketServerUseEpollET import webSocketServer # webSocketServerUseEpollET 和webSocketServerUseEpollLT自己选择使用

class webSocketServiceDaemon(webSocketServer):
    def __init__(self, ipAddr, port):
        super().__init__(ipAddr, port)

    #通讯格式为：{"status":"ok", "message":"xxxx"}。
    def accordActionToSend(self, sock, message):
        print(message)
        if "action" in message and "info" in message:
            if message["action"] == "getRoomInfo":  # websocket连接（握手）完成，客户端会直接发送这个数据到这儿
                self.dictSocketHandleSendContent[sock] = '{"status":"ok", "message":' + str(self.dictRoom) + '}'
            else:
                self.dictSocketHandleSendContent[sock] = '{"status":"ok", "message":"未知操作类型"}'
        else:
            self.dictSocketHandleSendContent[sock] = '{"status":"error", "message":"通讯数据格式错误"}'

if __name__ == "__main__":
    ipAddr = "0.0.0.0"
    port = 8089
    webSocketServiceDaemon(ipAddr, port)