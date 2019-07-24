#!/Library/Frameworks/Python.framework/Versions/3.6/bin/python3.6
#! -*- coding:utf-8 -*-

import socket, select, struct, collections, hashlib, base64, json, time

class webSocketServer(object):
    dictSocketHandleSendContent = {} #这儿存放每一个socket需要发送数据，每次发送数据完毕，需要删除其中的内容
    dictSocketHandle = {} #这儿存放每一个socket的句柄
    dictSocketShakeHandStatus = {} #用于存放每一个socket的握手状态，没有握手或握手失败为False、握手成功为True
    dictSocketShakeHandKey = {} #用于存放每一个socket的握手需要的key值
    dictRoom = {}#用于存放连接上来的socket在哪个房间的字典。比如 "room1":[{"socketHandle":socket1,"prepareStatus":status}, {"socketHandle":socket2,"prepareStatus":status}]。每次有一个socket连接上来，第一时间将该信息发送给该连接。
    dictSocketFrame = {}
    listClosingSocketHandle = [] #正在关闭的socket句柄
    dictSocketContent = {}#存放需要切片的socket的数据

    def __init__(self, ipAddr, port):#初始化一个socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((ipAddr, port))
        self.sock.setblocking(False)
        self.sock.listen(100)
        self.acceptOne()

    def acceptOne(self):#允许一个socket连接上来
        self.epollHandle = select.epoll()
        self.epollHandle.register(self.sock.fileno(), select.EPOLLIN|select.EPOLLET)
        while True:
            allSocketHandle = self.epollHandle.poll(1)
            for sock, event in allSocketHandle:
                if event == select.EPOLLIN:  # 有可读事件
                    if sock == self.sock.fileno():
                        client, address = self.sock.accept()
                        client.setblocking(False)
                        # client.settimeout(0.1)
                        self.dictSocketShakeHandStatus[client.fileno()] = False
                        self.dictSocketHandle[client.fileno()] = client
                        self.epollHandle.register(client.fileno(), select.EPOLLIN |select.EPOLLET)  # |select.EPOLLET
                    else:
                        message = self.recvMessage(sock)
                        # print("接收到的数据：", message)
                        if message:
                            if not self.dictSocketShakeHandStatus[sock]:
                                message = self.decodeToUtf8(message["string"])
                                headerData = self.parseHeaderData(message)  # 解析header头数据
                                if headerData:
                                    self.dictSocketShakeHandKey[sock] = headerData
                                    self.epollHandle.modify(sock, select.EPOLLOUT | select.EPOLLET)  # |select.EPOLLET
                            else:
                                if message["type"] == 1:
                                    try:  # 这儿为什么要try下，因为，如果不是json格式的字符串，不能json.loads所以，要try下
                                        data = self.parseStrToJson(message["string"].decode("utf-8"))
                                        self.accordActionToSend(sock, data)  # 根据获取到的json数据，然后对应操作处理的逻辑
                                    except:
                                        self.dictSocketHandleSendContent[sock] = '{"status":"error", "message":"通讯数据格式错误"}'

                                    self.epollHandle.modify(sock, select.EPOLLOUT | select.EPOLLET)  # |select.EPOLLET
                                elif message["type"] == 8:
                                    self.epollHandle.modify(sock, select.EPOLLHUP | select.EPOLLET)  # |select.EPOLLET
                                elif message["type"] == -10:
                                    pass
                                elif message["type"] == -11:
                                    print("数据未传输完毕，分片接收完毕，不作处理")
                                    # self.epollHandle.modify(sock, select.EPOLLIN | select.EPOLLET)  # |select.EPOLLET
                                    self.dictSocketHandleSendContent[sock] = '{"status":"success", "message":"数据分片接收完毕", "dataLen":"'+str(len(self.dictSocketContent[sock]))+'"}'
                                    self.epollHandle.modify(sock, select.EPOLLOUT | select.EPOLLET)  # |select.EPOLLET
                                elif message["type"] == 2:
                                    print("数据已传输完毕，保存文件")
                                    ext = "jpeg"
                                    with open(str(int(time.time())) + "." + ext, "wb") as fd:
                                        fd.write(message["string"])
                                    self.dictSocketHandleSendContent[sock] = '{"status":"success", "message":"文件传输完成", "dataLen":"'+str(len(self.dictSocketContent[sock]))+'"}'
                                    self.dictSocketContent.pop(sock)
                                    self.epollHandle.modify(sock, select.EPOLLOUT | select.EPOLLET)  # |select.EPOLLET
                                else:
                                    print("opCode为", message["type"], "不做任何处理")
                                    pass
                elif event == select.EPOLLOUT:  # 可写事件
                    if not self.dictSocketShakeHandStatus[sock]:
                        self.sendMessage(sock, "shakeSuccess")
                    else:
                        self.sendMessage(sock, self.parseDictToJson(self.dictSocketHandleSendContent[sock]))
                        self.dictSocketHandleSendContent.pop(sock)
                    self.epollHandle.modify(sock, select.EPOLLIN | select.EPOLLET)  # |select.EPOLLET
                elif event == select.EPOLLHUP:#客户端断开事件
                    print("socket is closed " + str(sock))
                    sock.close()
                    self.dictSocketShakeHandStatus.pop(sock)
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
        client = self.dictSocketHandle[sockHandle]
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
            if len(self.dictSocketHandle) >= 1:  # 一旦新的连接握手成功，这儿就发一个广播，告诉所有连接上来的用户，已经有多少用户在线上
                self.boardCast(sockHandle)  # 发送广播对象，不包含刚刚连接上来的
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
        print("请求开始")
        strings = b""
        resDict = {}
        client = self.dictSocketHandle[sockHandle]
        if not self.dictSocketShakeHandStatus[sockHandle]:#如果没有握手完成，我用1024个字节去接收数据是完全够用的
            print("握手未完成，去握手")
            data = client.recv(1024)  # 这儿如果没有拿够1024个字节的数据，那么会循环回来拿，但是，如果发现没有数据能拿到，socket会自动中止，扔出一个异常，代码就结束执行，所以需要try一下。
            if len(data) == 0:  # 通道断开或者close之后，就会一直收到空字符串。 而不是所谓的-1 或者报异常。这个跟C 和java等其他语言很不一样。
                self.epollHandle.modify(sockHandle, select.EPOLLHUP | select.EPOLLET)
            strings = data
            optCode = -5
            print("新连接句柄", client.fileno())
        else: #如果已经握手完成了，那么先要去完成一次通讯由客户端告知服务端，下一次要发送的数据大小

            if not client.fileno() in self.listClosingSocketHandle:#当前操作的socket不是处于正在关闭的状态，那么可以正常获取数据，如果处于正在关闭的状态，等待关闭

                print("句柄为", client.fileno())
                bytes_list = bytearray('', encoding='utf-8')

                data_head = client.recv(1)#获取一个字节的数据
                data_head = struct.unpack("B", data_head)[0]#unpack这个字节的数据

                FIN = data_head & 0x80

                opCode = self.parseHeadData(data_head)
                if opCode == 8:
                    self.listClosingSocketHandle.append(client.fileno())
                    return {"type": 8, "string": ""}

                if FIN == 0:
                    if opCode == 1:
                        print("----------------------文本消息，传输尚未完成")
                    elif opCode == 2:
                        print("----------------------二进制数据，传输尚未完成")
                    elif opCode == 0:
                        print("----------------------数据分片，传输尚未完成")
                    else:
                        print("----------------------数据尚未完成，opCode为：", opCode)
                else:
                    if opCode == 1:
                        print("----------------------文本消息，传输已完成")
                    elif opCode == 2:
                        print("----------------------二进制数据，传输已完成")
                    elif opCode == 0:
                        print("----------------------数据分片，传输已完成")
                    else:
                        print("----------------------传输已完成，opCode为：", opCode)

                byteData = client.recv(1)#再获取一个字节的数据
                byteData = struct.unpack("B", byteData)[0]#unpack这个字节的数据
                payload_len = byteData & 127#根据这个字节的后7位，这个数字只可能 小于126 等于126 等于127 这三种情况。
                                            # 小于126代表后面的数据长度为dataLength
                                            # 等于126代表后面的2个字节（16位无符号整数的十进制的值为dataLength）
                                            # 等于127代表后面的8个字节（64位无符号证书的十进制的值为dataLength）
                                            # mask key 是固定的后四字节
                print("payloadLen", payload_len)

                if payload_len == 126:
                    extend_payload_len = client.recv(2)  # 数据头部延伸的长度
                    dataLength = struct.unpack("!H", extend_payload_len)[0]#因为是2个字节 所以用H解码
                    mask = client.recv(4)  # 加密的4个字节

                    recvLen = 0
                    print("接收到的数据长度为：", dataLength)
                    while recvLen < dataLength:
                        try:
                            data = client.recv(1024)
                            for i in range(len(data)):
                                chunk = data[i] ^ mask[i % 4]
                                bytes_list.append(chunk)
                            recvLen = recvLen + len(data)
                        except IOError as e:
                            if e.errno == 11:
                                print("yyyyyyyyyyy")
                                time.sleep(1)
                                pass

                    if FIN == 0:#如果数据接收尚未完成（数据切片的情况下）
                        if client.fileno() in self.dictSocketContent:#如果socket字典中已经有该socket了
                            self.dictSocketContent[client.fileno()] = self.dictSocketContent[client.fileno()] + bytes_list
                        else:
                            self.dictSocketContent[client.fileno()] = bytes_list

                    else:#如果已经接收完成了
                        if client.fileno() in self.dictSocketContent:#如果socket字典中已经有该socket了
                            self.dictSocketContent[client.fileno()] = self.dictSocketContent[client.fileno()] + bytes_list
                        else:
                            self.dictSocketContent[client.fileno()] = bytes_list


                    print("数据总大小", dataLength, "获取数据长度", recvLen)#, "获取到数据：", bytes_list)
                elif payload_len == 127:
                    extend_payload_len = client.recv(8)
                    dataLength = struct.unpack("!Q", extend_payload_len)[0]#因为是8个字节 所以用Q解码
                    mask = client.recv(4)

                    recvLen = 0
                    print("接收到的数据长度为：", dataLength)
                    while recvLen < dataLength:
                        try:
                            data = client.recv(1024)
                            for i in range(len(data)):
                                chunk = data[i] ^ mask[i % 4]
                                bytes_list.append(chunk)
                            recvLen = recvLen + len(data)
                        except IOError as e:
                            if e.errno == 11:
                                print("xxxxxxxxxxx")
                                time.sleep(1)
                                continue

                    if FIN == 0:#如果数据接收尚未完成（数据切片的情况下）
                        if client.fileno() in self.dictSocketContent:#如果socket字典中已经有该socket了
                            self.dictSocketContent[client.fileno()] = self.dictSocketContent[client.fileno()] + bytes_list
                        else:
                            self.dictSocketContent[client.fileno()] = bytes_list
                    else:#如果已经接收完成了
                        if client.fileno() in self.dictSocketContent:#如果socket字典中已经有该socket了
                            self.dictSocketContent[client.fileno()] = self.dictSocketContent[client.fileno()] + bytes_list
                        else:
                            self.dictSocketContent[client.fileno()] = bytes_list

                    print("数据总大小", dataLength, "获取数据长度", recvLen)#, "获取到数据：", bytes_list)
                else:
                    dataLength = payload_len
                    mask = client.recv(4)

                    recvLen = 0
                    print("接收到的数据长度为：", dataLength)
                    while recvLen < dataLength:
                        try:
                            data = client.recv(1024)
                            for i in range(len(data)):
                                chunk = data[i] ^ mask[i % 4]
                                bytes_list.append(chunk)
                            recvLen = recvLen + len(data)
                        except IOError as e:
                            if e.errno == 11:
                                print("xxxxxxxxxxx")
                                time.sleep(1)
                                continue

                    self.dictSocketContent[client.fileno()] = bytes_list

                if FIN == 0:
                    strings = ""
                    optCode = -11
                else:
                    strings = self.dictSocketContent[client.fileno()]
                    optCode = 2


            else:
                print(client.fileno(), "正在关闭")
                time.sleep(0.1)
                self.listClosingSocketHandle.remove(client.fileno())
                optCode = -10
                strings = ""

        resDict["string"] = strings
        resDict["type"] = optCode
        return resDict

    def parseHeaderData(self, headerData):  # 解析头数据，分析出sec-websocket-key字段，然后返回
        try:
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
        except Exception as err:
            print("解析握手数据失败，不能建立连接")
            return False

    def boardCast(self, sock):#广播到所有的连接上
        for everySock in self.dictSocketHandle.values():
            if not sock == everySock:
                self.dictSocketHandleSendContent[everySock.fileno()] = '{"status":"success", "message":"have ' + str(len(self.dictSocketHandle)) + ' socket connect"}'
                self.epollHandle.modify(everySock, select.EPOLLOUT | select.EPOLLET)

    def parseHeadData(self, head):
        opcode = head & 0x0f #与00001111进行与运算，其实就是取后四位的数据
        if opcode == 0x0:
            print('数据请求被切片，目前只接收到一个数据分片')
            return 0
        if opcode == 0x1:
            print("文本消息")
            return 1
        if opcode == 0x2:
            print('二进制帧上传文件')
            return 2
        if opcode == 0x8:
            print('连接请求断开')
            return 8
        if opcode == 0x9:
            print("ping操作")
            return 9
        if opcode == 0xa:
            print('pong操作')
            return 10
        return -1

    def packWebSocketData(self, msg_bytes):#打包即将发送的数据
        token = b"\x81"
        length = len(msg_bytes)
        # 打包规则
        if length < 126:
            token += struct.pack("B", length)
        elif length <= 0xFFFF:
            token += struct.pack("B", 126)
            token += struct.pack("!H", length)
        else:
            token += struct.pack("B", 127)
            token += struct.pack("!Q", length)
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

