#!/Library/Frameworks/Python.framework/Versions/3.6/bin/python3.6
#! -*- coding:utf-8 -*-

import socket, select, struct, collections, hashlib, base64, json

class webSocketServer(object):
    dictSocketHandleSendContent = {} #这儿存放每一个socket需要发送数据，每次发送数据完毕，需要删除其中的内容
    dictSocketHandle = {} #这儿存放每一个socket的句柄
    dictSocketShakeHandStatus = {} #用于存放每一个socket的握手状态，没有握手或握手失败为False、握手成功为True
    dictSocketShakeHandKey = {} #用于存放每一个socket的握手需要的key值
    dictRoom = {}#用于存放连接上来的socket在哪个房间的字典。比如 "room1":[{"socketHandle":socket1,"prepareStatus":status}, {"socketHandle":socket2,"prepareStatus":status}]。每次有一个socket连接上来，第一时间将该信息发送给该连接。

    def __init__(self):#初始化一个socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(("0.0.0.0", 8089))
        self.sock.setblocking(False)
        self.sock.listen(100)
        self.acceptOne()

    def acceptOne(self):#允许一个socket连接上来
        self.epollHandle = select.epoll()
        self.epollHandle.register(self.sock.fileno(), select.EPOLLIN|select.EPOLLET)
        while True:
            allSocketHandle = self.epollHandle.poll(1)
            for sock, event in allSocketHandle:
                if sock == self.sock.fileno():
                    client, address = self.sock.accept()
                    client.setblocking(False)
                    self.dictSocketShakeHandStatus[client.fileno()] = False
                    self.dictSocketHandle[client.fileno()] = client
                    self.epollHandle.register(client.fileno(), select.EPOLLIN | select.EPOLLET)  # |select.EPOLLET
                else:
                    if event == select.EPOLLIN:  # 有可读事件
                        message = self.recvMessage(sock)
                        if not self.dictSocketShakeHandStatus[sock]:
                            # print("拿到的数据为", message.decode("utf-8"))
                            message = self.decodeToUtf8(message)
                            headerData = self.parseHeaderData(message)  # 解析header头数据
                            self.dictSocketShakeHandKey[sock] = headerData
                            self.epollHandle.modify(sock, select.EPOLLOUT | select.EPOLLET)  # |select.EPOLLET
                        else:
                            frameOpCode = self.parseFrameOpCode(message)#解析数据帧中的opcode，确定客户端的请求到底是啥
                            if frameOpCode == 0:
                                self.closeConnect(sock)
                            elif frameOpCode == 1:
                                message = self.parseWebSocketData(message)#拿到客户端输入的数据，每次都要解包
                                # print(message)
                                try:#这儿为什么要try下，因为，如果不是json格式的字符串，不能json.loads所以，要try下
                                    message = self.parseStrToJson(message)
                                    self.accordActionToSend(sock, message)#根据获取到的json数据，然后对应操作处理的逻辑
                                except Exception as err:
                                    self.dictSocketHandleSendContent[sock] = '{"status":"error", "message":"通讯数据格式错误"}'
                                # print(message)

                                self.epollHandle.modify(sock, select.EPOLLOUT | select.EPOLLET)  # |select.EPOLLET
                            elif frameOpCode == 3:
                                print("解析数据帧错误")
                            else:
                                print("解析数据帧暂时不用的状态")

                    elif event == select.EPOLLOUT:  # 可写事件
                        if not self.dictSocketShakeHandStatus[sock]:
                            self.sendMessage(sock, "shakeSuccess")
                        else:
                            self.sendMessage(sock, self.parseDictToJson(self.dictSocketHandleSendContent[sock]))
                            self.dictSocketHandleSendContent.pop(sock)
                        self.epollHandle.modify(sock, select.EPOLLIN | select.EPOLLET)  # |select.EPOLLET
                    elif event == select.EPOLLHUP:#客户端断开事件
                        print("socket is closed " + str(sock))
                        self.dictSocketHandle[sock].close()
                        self.epollHandle.unregister(sock)
                        self.dictSocketHandle.pop(sock)
                    else:
                        print("socket is closed " + str(sock))
                        self.dictSocketHandle[sock].close()
                        self.epollHandle.unregister(sock)
                        self.dictSocketHandle.pop(sock)


    def closeConnect(self, sock):#关闭一个socket连接
        print("socket is closed " + str(sock))
        self.dictSocketHandle[sock].close()
        self.epollHandle.unregister(sock)
        self.dictSocketHandle.pop(sock)

    def parseStrToJson(self, strData):#将json字符串转成dict
        return json.loads(strData)

    def parseDictToJson(self, dictData):#将dict解析成json格式
        return json.dumps(dictData)

    def sendMessage(self, sockHandle, message):#用户提交数据的数据
        # print("准备发送数据到客户端.....\n")
        client = self.dictSocketHandle[sockHandle];
        if not self.dictSocketShakeHandStatus[sockHandle]:
            # print("发送握手数据到客户端.....")
            dictData = self.dictSocketShakeHandKey[sockHandle]
            # print("key", dictData["Sec-WebSocket-Key"])
            key = dictData["Sec-WebSocket-Key"] + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
            # print("**********,", key)
            sha1 = hashlib.sha1()
            sha1.update(str.strip(key).encode("utf-8"))
            ser_key = sha1.digest()
            # print("sha1", ser_key)
            base64str = base64.b64encode(ser_key).decode("utf-8")
            # print("base64", base64str)
            strings = "HTTP/1.1 101 Switching Protocol\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept:%s\r\n\r\n" % (base64str)
            # print(strings)
            strings = strings.encode("utf-8")
            self.dictSocketShakeHandKey.pop(sockHandle)
        else:
            # print("已经握过手，直接发送数据......")
            strings = self.packWebSocketData(message.encode("utf-8"))  # 要发送的数据
        totalLen = len(strings)  # 要发送数据的总长度
        sendLen = 0  # 已发送数据总长度
        while sendLen < totalLen:  # 开始循环发送数据
            try:
                if not self.dictSocketShakeHandStatus[sockHandle]:
                    self.dictSocketShakeHandStatus[sockHandle] = True
                # print("要发送数据总长度：", totalLen)
                m = strings[sendLen:]
                # print("mmmmmmmmmmmm", m)
                le = client.send(m)
                sendLen = sendLen + le
                # print("已发送数据总长度：", sendLen)
            except IOError as err:
                if err.errno == 32:  # 如果对端关闭，还去发送会产生，"Broken pipe"的错误  错误码为32
                    # print("客户端已经关闭连接，服务端等待关闭......")
                    self.epollHandle.modify(sockHandle, select.EPOLLHUP | select.EPOLLET)
                    break
                else:
                    print("服务端发送数据未知错误")

    def recvMessage(self, sockHandle):#读取来自客户端的数据
        strings = b""
        getNullTime = 0
        client = self.dictSocketHandle[sockHandle]
        while True:
            try:
                data = client.recv(5)  # 这儿如果没有拿够1024个字节的数据，那么会循环回来拿，但是，如果发现没有数据能拿到，socket会自动中止，扔出一个异常，代码就结束执行，所以需要try一下。
                if len(data) == 0:  # 通道断开或者close之后，就会一直收到空字符串。 而不是所谓的-1 或者报异常。这个跟C 和java等其他语言很不一样。
                    self.epollHandle.modify(sockHandle, select.EPOLLHUP | select.EPOLLET)
                    break
                # print("本次接收到的数据........", data)
                strings = strings + data
                getNullTime = 0
            except IOError as err:
                if err.errno == 11:  # 发生 Resource temporarily unavailable 错误 错误码为11，意为：数据尚未准备好，需要等待
                    if getNullTime >= 3:
                        break
                    else:
                        getNullTime = getNullTime + 1
                        # print("第" + str(getNullTime) + "次获取到空数据，继续尝试中.......")
                else:
                    print("读取数据，未知IO错误")
                    self.epollHandle.modify(sockHandle, select.EPOLLHUP | select.EPOLLET)
                    break
            except:
                print("未知错误")
                self.epollHandle.modify(sockHandle, select.EPOLLHUP | select.EPOLLET)
                break
        return strings

    def parseHeaderData(self, headerData):  # 解析头数据，分析出sec-websocket-key字段，然后返回
        data = headerData.split("\r\n\r\n")
        data = data[0]
        allData = data.split("\r\n")
        result = collections.OrderedDict()
        for item in allData:
            res = item.split(":", 1)
            if res[0].startswith("GET"):
                result["HTTP"] = res[0]
            else:
                result[res[0]] = res[1]
        return result

    def parseFrameOpCode(self, frame):#解析每一次请求过来的数据帧中的opcode，确定客户端现在的要求，返回 0=客户端退出、1=接收到数据、3=错误、4=未知（暂时不用）
        print("数据为：", frame)
        if(frame == b""):#这儿是为了兼容safair浏览器
            print('Client closed connection.')
            return 0
        tmpData = frame[0]
        print("帧为：", tmpData)
        if not tmpData:
            print('Client closed connection.')
            return 3
        opcode = tmpData & 0x0f
        if opcode == 0x8:
            print('Client asked to close connection.')
            return 0
        if opcode == 0x0:
            print('Continuation frames are not supported.')
            return 4
        if opcode == 0x2:
            print('Binary frames are not supported.')
            return 4
        elif opcode == 0x1:
            print("message_received")
            return 1
        elif opcode == 0x9:
            print("ping received")
            return 4
        elif opcode == 0xa:
            print('pong frames are not supported.')
            return 4
        else:
            print("Unknown opcode %#x." + opcode)
            return 4


    def parseWebSocketData(self, info):#解析头部数据，值要我们的消息主体，剔除掉header头信息
        payload_len = info[1] & 127
        if payload_len == 126:
            # 数据头部延伸的长度
            extend_payload_len = info[2:4]
            # 加密的4个字节
            mask = info[4:8]
            decoded = info[8:]# 数据
        elif payload_len == 127:
            extend_payload_len = info[2:10]
            mask = info[10:14]
            decoded = info[14:]
        else:
            extend_payload_len = None
            mask = info[2:6]
            decoded = info[6:]
        bytes_list = bytearray()
        for i in range(len(decoded)):
            chunk = decoded[i] ^ mask[i % 4]
            bytes_list.append(chunk)
        body = str(bytes_list, encoding='utf-8')
        return body

    def packWebSocketData(self, msg_bytes):#打包即将发送的数据
        token = b"\x81"
        length = len(msg_bytes)
        # 打包规则
        if length < 126:
            token += struct.pack("B", length)
        elif length <= 0xFFFF:
            token += struct.pack("!BH", 126, length)
        else:
            token += struct.pack("!BQ", 127, length)
        msg = token + msg_bytes
        return msg

    def decodeToUtf8(self, message):
        try:
            return message.decode('utf-8')
        except UnicodeDecodeError:
            return False
        except Exception as e:
            raise (e)
            return False

    def encodeToUtf8(self, message):
        try:
            return message.encode('UTF-8')
        except UnicodeEncodeError as e:
            return False
        except Exception as e:
            raise (e)
            return False

if __name__ == "__main__":
    socketService = webSocketServer()

