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
    dictSocketRecvFileExtension = {} #用来存放发送文件的时候 文件的后缀名是啥

    resDict = {}

    dictSocketRecvData = {}  # 用来存放每个socket接收到的数据

    def __init__(self, ipAddr, port):#初始化一个socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((ipAddr, port))
        self.sock.setblocking(False)
        self.sock.listen(100)
        self.acceptOne()

    def acceptOne(self):#允许一个socket连接上来
        self.epollHandle = select.epoll()
        self.epollHandle.register(self.sock.fileno(), select.EPOLLIN)
        while True:
            allSocketHandle = self.epollHandle.poll(1)
            for sock, event in allSocketHandle:
                if event == select.EPOLLIN:  # 有可读事件
                    if sock == self.sock.fileno():
                        client, address = self.sock.accept()
                        client.setblocking(False)
                        # client.settimeout(1)
                        self.dictSocketShakeHandStatus[client.fileno()] = False
                        self.dictSocketHandle[client.fileno()] = client
                        self.epollHandle.register(client.fileno(), select.EPOLLIN|select.EPOLLET)  # |select.EPOLLET
                    else:
                        message = self.recvMessage(sock)
                        # print("接收到的数据：", message)
                        if message:
                            if not self.dictSocketShakeHandStatus[sock]:
                                message = self.decodeToUtf8(message["string"])
                                headerData = self.parseHeaderData(message)  # 解析header头数据
                                if headerData:
                                    self.dictSocketShakeHandKey[sock] = headerData
                                    self.epollHandle.modify(sock, select.EPOLLOUT|select.EPOLLET)  # |select.EPOLLET
                            else:
                                if message["type"] == 1:
                                    print("数据已传输完毕，纯文本消息")
                                    try:  # 这儿为什么要try下，因为，如果不是json格式的字符串，不能json.loads所以，要try下
                                        data = self.parseStrToJson(message["string"].decode("utf-8"))
                                        if data["status"] == str(2):
                                            print("确定为上传文件，文件后缀为", data["info"])
                                            self.dictSocketRecvFileExtension[sock] = data["info"]

                                            self.dictSocketContent.pop(sock)
                                            self.dictSocketHandleSendContent[sock] = '{"status":"success", "message":"信息接收成功"}'
                                        else:
                                            self.dictSocketHandleSendContent[sock] = '{"status":"success", "message":"信息接收成功"}'
                                    except:
                                        self.dictSocketHandleSendContent[sock] = '{"status":"error", "message":"通讯数据格式错误"}'

                                    self.epollHandle.modify(sock, select.EPOLLOUT|select.EPOLLET)  # |select.EPOLLET
                                elif message["type"] == 8:
                                    print("接收到关闭信息，正在关闭" + str(sock))
                                    self.dictSocketShakeHandStatus.pop(sock)
                                    self.dictSocketHandle[sock].close()
                                    self.epollHandle.unregister(sock)
                                    self.dictSocketHandle.pop(sock)
                                    print("关闭操作完成")
                                elif message["type"] == 2:
                                    print("数据已传输完毕，二进制保存文件", len(message["string"]))
                                    # ext = self.dictSocketRecvFileExtension[sock]
                                    filename = str(int(time.time())) + "." + "jpeg"
                                    with open(filename, "wb") as fd:
                                        fd.write(message["string"])
                                    if "jpeg" in ["png", "jpg", "jpeg", "gif"]:
                                        self.dictSocketHandleSendContent[sock] = '{"status":"success", "message":"文件传输完成", "filename": "'+filename+'"}'
                                    else:
                                        self.dictSocketHandleSendContent[sock] = '{"status":"success", "message":"文件传输完成"}'
                                    # self.dictSocketRecvFileExtension.pop(sock)
                                    self.epollHandle.modify(sock, select.EPOLLOUT|select.EPOLLET)  # |select.EPOLLET

                                else:
                                    print("opCode为", message["type"], "不做任何处理")
                                    pass
                elif event == select.EPOLLOUT:  # 可写事件
                    if not self.dictSocketShakeHandStatus[sock]:
                        self.sendMessage(sock, "shakeSuccess")
                    else:

                        jsonData = json.loads(self.dictSocketHandleSendContent[sock])
                        if "filename" in jsonData:
                            self.sendMessage(sock, self.dictSocketHandleSendContent[sock], jsonData["filename"])
                        else:
                            print("准备发送数据的类型", type(self.dictSocketHandleSendContent[sock]))
                            print("准备发送文字消息：", self.dictSocketHandleSendContent[sock])
                            self.sendMessage(sock, self.parseDictToJson(self.dictSocketHandleSendContent[sock]), "")
                        self.dictSocketHandleSendContent.pop(sock)
                    self.epollHandle.modify(sock, select.EPOLLIN|select.EPOLLET)  # |select.EPOLLET
                elif event == select.EPOLLHUP:#客户端断开事件
                    print("socket is closed " + str(sock))
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

    def sendMessage(self, sockHandle, message, filename = ""):#用户提交数据的数据，目前发送数据到网页端没有完善，只能发送简短的数据，不支持大文件
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
            if filename == "":
                strings = self.packWebSocketData(message.encode("utf-8"))  # 要发送的数据
            else:
                data = b""
                with open(filename, "rb") as fd:
                    data += fd.read()
                print("要发送二进制文件总大小:", len(data))
                strings = self.packWebSocketData(data)
                print("要发送打包后的数据大小", len(strings))
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
                print("本次发送数据量:", le)
                sendLen = sendLen + le
                print("已发送数据总量：", sendLen)
                # print("已发送数据总长度：", sendLen)
            except IOError as err:
                if err.errno == 11:
                    continue
                elif err.errno == 32:  # 如果对端关闭，还去发送会产生，"Broken pipe"的错误  错误码为32
                    # print("客户端已经关闭连接，服务端等待关闭......")
                    self.epollHandle.modify(sockHandle, select.EPOLLHUP)
                    break
                else:
                    print("服务端发送数据未知错误")

    def recvMessage(self, sockHandle):#读取来自客户端的数据
        print("请求开始")

        strings = b""
        globalOptCode = -1
        client = self.dictSocketHandle[sockHandle]
        if not self.dictSocketShakeHandStatus[sockHandle]:#如果没有握手完成，我用1024个字节去接收数据是完全够用的
            resDict = {}
            print("握手未完成，去握手")
            data = client.recv(1024)  # 这儿如果没有拿够1024个字节的数据，那么会循环回来拿，但是，如果发现没有数据能拿到，socket会自动中止，扔出一个异常，代码就结束执行，所以需要try一下。
            if len(data) == 0:  # 通道断开或者close之后，就会一直收到空字符串。 而不是所谓的-1 或者报异常。这个跟C 和java等其他语言很不一样。
                self.epollHandle.modify(sockHandle, select.EPOLLHUP)
            strings = data
            opCode = -5
            print("新连接句柄", client.fileno())
            resDict["string"] = strings
            resDict["type"] = opCode
            return resDict
        else: #如果已经握手完成了，那么先要去完成一次通讯由客户端告知服务端，下一次要发送的数据大小

            # if not client.fileno() in self.listClosingSocketHandle:#当前操作的socket不是处于正在关闭的状态，那么可以正常获取数据，如果处于正在关闭的状态，等待关闭

            everyRecvDataLen = 512
            minExtendPayloadLen = 2
            maxExtendPayloadLen = 8
            maskRecvLength = 4
            print("句柄为", client.fileno())

            returnRes = False
            while True:
                bytes_list = bytearray('', encoding='utf-8')
                if not sockHandle in self.dictSocketRecvData:
                    self.dictSocketRecvData[sockHandle] = {}

                self.dictSocketRecvData[sockHandle]["totalFinish"] = False

                if not "hasFirstByte" in self.dictSocketRecvData[sockHandle] or self.dictSocketRecvData[sockHandle]["hasFirstByte"] == False:
                    if not "firstByteLength" in self.dictSocketRecvData[sockHandle]:
                        self.dictSocketRecvData[sockHandle]["firstByteLength"] = 0
                    while self.dictSocketRecvData[sockHandle]["firstByteLength"] < 1:
                        try:
                            data_head = client.recv(1)#获取一个字节的数据
                            if len(data_head) == 0:#如果在接收数据过程中，客户端突然关闭，那么就会接收到空数据，然后根据空数据去断开连接，这点至关重要
                                raise RuntimeError()
                            if len(data_head) == 1:

                                self.dictSocketRecvData[sockHandle]["firstByteLength"] += 1
                                self.dictSocketRecvData[sockHandle]["hasFirstByte"] = True

                                data_head = struct.unpack("B", data_head)[0]  # unpack这个字节的数据

                                self.dictSocketRecvData[sockHandle]["firstByteFIN"] = data_head & 0x80

                                opCode = self.parseHeadData(data_head)
                                if opCode == 8:  # 浏览器端主动关闭请求，这段必须写。因为客户端主动关闭之后，还会再次发送一个请求过来确认是否关闭
                                    # self.listClosingSocketHandle.append(client.fileno())
                                    return {"type": 8, "string": ""}

                                self.dictSocketRecvData[sockHandle]["opCode"] = opCode
                                if self.dictSocketRecvData[sockHandle]["firstByteFIN"] == 0:
                                    if self.dictSocketRecvData[sockHandle]["opCode"] == 1:
                                        print("************************文本消息，传输尚未完成")
                                    elif self.dictSocketRecvData[sockHandle]["opCode"] == 2:
                                        print("************************二进制数据，传输尚未完成")
                                    elif self.dictSocketRecvData[sockHandle]["opCode"] == 0:
                                        print("************************数据分片，传输尚未完成")
                                    else:
                                        print("************************数据尚未完成，opCode为：",
                                              self.dictSocketRecvData[sockHandle]["opCode"])
                                else:
                                    if self.dictSocketRecvData[sockHandle]["opCode"] == 1:
                                        print("************************文本消息，传输已完成")
                                    elif self.dictSocketRecvData[sockHandle]["opCode"] == 2:
                                        print("************************二进制数据，传输已完成")
                                    elif self.dictSocketRecvData[sockHandle]["opCode"] == 0:
                                        print("************************数据分片，传输已完成")
                                    else:
                                        print("************************传输已完成，opCode为：",
                                              self.dictSocketRecvData[sockHandle]["opCode"])

                        except IOError as e:
                            if e.errno == 11:
                                break
                        except RuntimeError as re:
                            break
                if "firstByteFIN" in self.dictSocketRecvData[sockHandle]:

                    if not "hasSecondByte" in self.dictSocketRecvData[sockHandle] or self.dictSocketRecvData[sockHandle]["hasSecondByte"] == False:
                        if not "secondByteLength" in self.dictSocketRecvData[sockHandle]:
                            self.dictSocketRecvData[sockHandle]["secondByteLength"] = 0
                        while self.dictSocketRecvData[sockHandle]["secondByteLength"] < 1:
                            try:
                                byteData = client.recv(1)#再获取一个字节的数据
                                if len(byteData) == 0:
                                    raise RuntimeError()
                                if len(byteData) == 1:
                                    self.dictSocketRecvData[sockHandle]["secondByteLength"] += 1
                                    self.dictSocketRecvData[sockHandle]["hasSecondByte"] = True
                                    byteData = struct.unpack("B", byteData)[0]  # unpack这个字节的数据
                                    self.dictSocketRecvData[sockHandle]["payload_len"] = byteData & 127  # 根据这个字节的后7位，这个数字只可能 小于126 等于126 等于127 这三种情况。
                                    # 小于126代表后面的数据长度为dataLength
                                    # 等于126代表后面的2个字节（16位无符号整数的十进制的值为dataLength）
                                    # 等于127代表后面的8个字节（64位无符号证书的十进制的值为dataLength）
                                    # mask key 是固定的后四字节
                                    print("payloadLen", self.dictSocketRecvData[sockHandle]["payload_len"])
                            except IOError as e:
                                if e.errno == 11:
                                    break
                            except RuntimeError as re:
                                break

                    if "payload_len" in self.dictSocketRecvData[sockHandle]:
                        if self.dictSocketRecvData[sockHandle]["payload_len"]  == 126:

                            self.dictSocketRecvData[sockHandle]["finish"] = False
                            if not "dataLength" in self.dictSocketRecvData[sockHandle]:

                                if not "recvExtendMinPayloadLen" in self.dictSocketRecvData[sockHandle]:
                                    self.dictSocketRecvData[sockHandle]["recvExtendMinPayloadLen"] = 0
                                if not "tmpRecvMinExtendPayloadData" in self.dictSocketRecvData[sockHandle]:
                                    self.dictSocketRecvData[sockHandle]["tmpRecvMinExtendPayloadData"] = b""

                                while self.dictSocketRecvData[sockHandle]["recvExtendMinPayloadLen"] < minExtendPayloadLen:
                                    try:
                                        extend_payload_len = client.recv(1)  # 数据头部延伸的长度
                                        if len(extend_payload_len) == 0:
                                            raise RuntimeError()
                                        if len(extend_payload_len) == 1:
                                            self.dictSocketRecvData[sockHandle]["recvExtendMinPayloadLen"] = self.dictSocketRecvData[sockHandle]["recvExtendMinPayloadLen"] + 1
                                            self.dictSocketRecvData[sockHandle][ "tmpRecvMinExtendPayloadData"] += extend_payload_len
                                    except IOError as e:
                                        if e.errno == 11:
                                            break
                                    except RuntimeError as re:
                                        break

                                else:
                                    self.dictSocketRecvData[sockHandle]["dataLength"] = struct.unpack("!H", self.dictSocketRecvData[sockHandle]["tmpRecvMinExtendPayloadData"])[0]  # 因为是2个字节 所以用H解码

                            if "dataLength" in self.dictSocketRecvData[sockHandle]:

                                if not "mask" in self.dictSocketRecvData[sockHandle]:

                                    if not "recvMaskLen" in self.dictSocketRecvData[sockHandle]:
                                        self.dictSocketRecvData[sockHandle]["recvMaskLen"] = 0
                                    if not "tmpRecvMaskData" in self.dictSocketRecvData[sockHandle]:
                                        self.dictSocketRecvData[sockHandle]["tmpRecvMaskData"] = b""

                                    while self.dictSocketRecvData[sockHandle]["recvMaskLen"] < maskRecvLength:
                                        try:
                                            mask = client.recv(1)  # 加密的4个字节
                                            if len(mask) == 0:
                                                raise RuntimeError()
                                            if len(mask) == 1:
                                                self.dictSocketRecvData[sockHandle]["recvMaskLen"] = self.dictSocketRecvData[sockHandle]["recvMaskLen"] + 1
                                                self.dictSocketRecvData[sockHandle]["tmpRecvMaskData"] += mask

                                        except IOError as e:
                                            if e.errno == 11:
                                                break
                                        except RuntimeError as re:
                                            break
                                    else:
                                        self.dictSocketRecvData[sockHandle]["mask"] = self.dictSocketRecvData[sockHandle]["tmpRecvMaskData"]


                                    print("接收到的数据长度为：", self.dictSocketRecvData[sockHandle]["dataLength"])

                            if "mask" in self.dictSocketRecvData[sockHandle]:
                                if not "recvDataLength" in self.dictSocketRecvData[sockHandle]:
                                    self.dictSocketRecvData[sockHandle]["recvDataLength"] = 0
                                if not "leftRecvDataLength" in self.dictSocketRecvData[sockHandle]:
                                    self.dictSocketRecvData[sockHandle]["leftRecvDataLength"] = self.dictSocketRecvData[sockHandle]["dataLength"]

                                while self.dictSocketRecvData[sockHandle]["recvDataLength"] < self.dictSocketRecvData[sockHandle]["dataLength"]:
                                    if self.dictSocketRecvData[sockHandle]["leftRecvDataLength"] < everyRecvDataLen:
                                        try:
                                            data = client.recv(self.dictSocketRecvData[sockHandle]["leftRecvDataLength"])
                                            if len(data) == 0:
                                                raise RuntimeError()
                                            for i in range(len(data)):
                                                chunk = data[i] ^ self.dictSocketRecvData[sockHandle]["mask"][i % 4]
                                                bytes_list.append(chunk)
                                            self.dictSocketRecvData[sockHandle]["recvDataLength"] = self.dictSocketRecvData[sockHandle]["recvDataLength"] + len(data)
                                            self.dictSocketRecvData[sockHandle]["leftRecvDataLength"] = self.dictSocketRecvData[sockHandle]["leftRecvDataLength"] - len(data)
                                        except IOError as e:
                                            if e.errno == 11:
                                                break
                                        except RuntimeError as re:
                                            self.epollHandle.modify(client, select.EPOLLHUP)
                                    else:
                                        try:
                                            data = client.recv(everyRecvDataLen)
                                            if len(data) ==0:
                                                raise RuntimeError()
                                            for i in range(len(data)):
                                                chunk = data[i] ^ self.dictSocketRecvData[sockHandle]["mask"][i % 4]
                                                bytes_list.append(chunk)
                                            self.dictSocketRecvData[sockHandle]["recvDataLength"] = self.dictSocketRecvData[sockHandle]["recvDataLength"] + len(data)
                                            self.dictSocketRecvData[sockHandle]["leftRecvDataLength"] = self.dictSocketRecvData[sockHandle]["leftRecvDataLength"] - len(data)
                                        except IOError as e:
                                            if e.errno == 11:
                                                break
                                        except RuntimeError as re:
                                            break
                                self.dictSocketRecvData[sockHandle]["finish"] = True
                                if self.dictSocketRecvData[sockHandle]["firstByteFIN"] == 0:#如果数据接收尚未完成（数据切片的情况下）
                                    if client.fileno() in self.dictSocketContent:#如果socket字典中已经有该socket了
                                        self.dictSocketContent[client.fileno()] = self.dictSocketContent[client.fileno()] + bytes_list
                                    else:
                                        self.dictSocketContent[client.fileno()] = bytes_list

                                else:#如果已经接收完成了
                                    if client.fileno() in self.dictSocketContent:#如果socket字典中已经有该socket了
                                        self.dictSocketContent[client.fileno()] = self.dictSocketContent[client.fileno()] + bytes_list
                                    else:
                                        self.dictSocketContent[client.fileno()] = bytes_list
                                print("数据总大小", self.dictSocketRecvData[sockHandle]["dataLength"], "获取数据长度", self.dictSocketRecvData[sockHandle]["recvDataLength"])#, "获取到数据：", bytes_list)


                        elif self.dictSocketRecvData[sockHandle]["payload_len"]  == 127:
                            self.dictSocketRecvData[sockHandle]["finish"] = False
                            if not "dataLength" in self.dictSocketRecvData[sockHandle]:

                                if not "recvExtendMaxPayloadLen" in self.dictSocketRecvData[sockHandle]:
                                    self.dictSocketRecvData[sockHandle]["recvExtendMaxPayloadLen"] = 0
                                if not "tmpRecvMaxExtendPayloadData" in self.dictSocketRecvData[sockHandle]:
                                    self.dictSocketRecvData[sockHandle]["tmpRecvMaxExtendPayloadData"] = b""

                                while self.dictSocketRecvData[sockHandle]["recvExtendMaxPayloadLen"] < maxExtendPayloadLen:
                                    try:
                                        extend_payload_len = client.recv(1)
                                        if len(extend_payload_len) == 0:
                                            raise RuntimeError()
                                        if len(extend_payload_len) == 1:
                                            self.dictSocketRecvData[sockHandle]["recvExtendMaxPayloadLen"] = self.dictSocketRecvData[sockHandle]["recvExtendMaxPayloadLen"] + 1
                                            self.dictSocketRecvData[sockHandle]["tmpRecvMaxExtendPayloadData"] += extend_payload_len
                                    except IOError as e:
                                        if e.errno == 11:
                                            break
                                    except RuntimeError as re:
                                        break
                                else:
                                    self.dictSocketRecvData[sockHandle]["dataLength"] = struct.unpack("!Q", self.dictSocketRecvData[sockHandle]["tmpRecvMaxExtendPayloadData"])[0]
                                    print("接收到的数据长度为：", self.dictSocketRecvData[sockHandle]["dataLength"])

                            if "dataLength" in self.dictSocketRecvData[sockHandle]:
                                if not "recvMaskLen" in self.dictSocketRecvData[sockHandle]:
                                    self.dictSocketRecvData[sockHandle]["recvMaskLen"] = 0
                                if not "tmpRecvMaskData" in self.dictSocketRecvData[sockHandle]:
                                    self.dictSocketRecvData[sockHandle]["tmpRecvMaskData"] = b""

                                if not "mask" in self.dictSocketRecvData[sockHandle]:
                                    while self.dictSocketRecvData[sockHandle]["recvMaskLen"] < maskRecvLength:
                                        try:
                                            mask = client.recv(1)  # 加密的4个字节
                                            if len(mask) == 0:
                                                raise RuntimeError()
                                            if len(mask) == 1:
                                                self.dictSocketRecvData[sockHandle]["recvMaskLen"] = self.dictSocketRecvData[sockHandle]["recvMaskLen"] + 1
                                                self.dictSocketRecvData[sockHandle]["tmpRecvMaskData"] += mask

                                        except IOError as e:
                                            if e.errno == 11:
                                                break
                                        except RuntimeError as re:
                                            self.epollHandle.modify(client, select.EPOLLHUP)
                                    else:
                                        self.dictSocketRecvData[sockHandle]["mask"] = self.dictSocketRecvData[sockHandle]["tmpRecvMaskData"]

                                print("需要接收的数据长度为：", self.dictSocketRecvData[sockHandle]["dataLength"])

                            if "mask" in self.dictSocketRecvData[sockHandle]:
                                if not "recvDataLength" in self.dictSocketRecvData[sockHandle]:
                                    self.dictSocketRecvData[sockHandle]["recvDataLength"] = 0

                                if not "leftRecvDataLength" in self.dictSocketRecvData[sockHandle]:
                                    self.dictSocketRecvData[sockHandle]["leftRecvDataLength"] = self.dictSocketRecvData[sockHandle]["dataLength"]


                                while self.dictSocketRecvData[sockHandle]["recvDataLength"] < self.dictSocketRecvData[sockHandle]["dataLength"]:
                                    if self.dictSocketRecvData[sockHandle]["leftRecvDataLength"] < everyRecvDataLen:
                                        try:
                                            data = client.recv(self.dictSocketRecvData[sockHandle]["leftRecvDataLength"])
                                            if len(data) == 0:
                                                raise RuntimeError()
                                            for i in range(len(data)):
                                                chunk = data[i] ^ self.dictSocketRecvData[sockHandle]["mask"][i % 4]
                                                bytes_list.append(chunk)
                                            self.dictSocketRecvData[sockHandle]["recvDataLength"] = self.dictSocketRecvData[sockHandle]["recvDataLength"] + len(data)
                                            self.dictSocketRecvData[sockHandle]["leftRecvDataLength"] = self.dictSocketRecvData[sockHandle]["leftRecvDataLength"] - len(data)
                                        except IOError as e:
                                            print("错误码：", e.errno)
                                            if e.errno == 11:
                                                break
                                        except RuntimeError as re:
                                            self.epollHandle.modify(client, select.EPOLLHUP)
                                    else:
                                        try:
                                            data = client.recv(everyRecvDataLen)
                                            if len(data) == 0:
                                                raise RuntimeError()
                                            for i in range(len(data)):
                                                chunk = data[i] ^ self.dictSocketRecvData[sockHandle]["mask"][i % 4]
                                                bytes_list.append(chunk)
                                            self.dictSocketRecvData[sockHandle]["recvDataLength"] = self.dictSocketRecvData[sockHandle]["recvDataLength"] + len(data)
                                            self.dictSocketRecvData[sockHandle]["leftRecvDataLength"] = self.dictSocketRecvData[sockHandle]["leftRecvDataLength"] - len(data)
                                        except IOError as e:
                                            print("错误码：", e.errno)
                                            if e.errno == 11:
                                                break
                                        except RuntimeError as re:
                                            self.epollHandle.modify(client, select.EPOLLHUP)

                                self.dictSocketRecvData[sockHandle]["finish"] = True
                                if self.dictSocketRecvData[sockHandle]["firstByteFIN"] == 0:#如果数据接收尚未完成（数据切片的情况下）
                                    print("获取到的长度为：", len(bytes_list))
                                    if client.fileno() in self.dictSocketContent:#如果socket字典中已经有该socket了
                                        self.dictSocketContent[client.fileno()] = self.dictSocketContent[client.fileno()] + bytes_list
                                    else:
                                        print("获取到的长度为：", len(bytes_list))
                                        self.dictSocketContent[client.fileno()] = bytes_list
                                else:#如果已经接收完成了
                                    if client.fileno() in self.dictSocketContent:#如果socket字典中已经有该socket了
                                        print("获取到的长度为：", len(bytes_list))
                                        self.dictSocketContent[client.fileno()] = self.dictSocketContent[client.fileno()] + bytes_list
                                    else:
                                        print("获取到的长度为：", len(bytes_list))
                                        self.dictSocketContent[client.fileno()] = bytes_list

                                print("数据总大小", self.dictSocketRecvData[sockHandle]["dataLength"], "获取数据长度", self.dictSocketRecvData[sockHandle]["recvDataLength"])#, "获取到数据：", bytes_list)
                        else:
                            self.dictSocketRecvData[sockHandle]["finish"] = False
                            self.dictSocketRecvData[sockHandle]["dataLength"] = self.dictSocketRecvData[sockHandle]["payload_len"]
                            if not "mask" in self.dictSocketRecvData[sockHandle]:
                                if not "recvMaskLen" in self.dictSocketRecvData[sockHandle]:
                                    self.dictSocketRecvData[sockHandle]["recvMaskLen"] = 0
                                if not "tmpRecvMaskData" in self.dictSocketRecvData[sockHandle]:
                                    self.dictSocketRecvData[sockHandle]["tmpRecvMaskData"] = b""

                                while self.dictSocketRecvData[sockHandle]["recvMaskLen"] < maskRecvLength:
                                    try:
                                        mask = client.recv(1)  # 加密的4个字节
                                        if len(mask) == 0:
                                            raise RuntimeError()
                                        if len(mask) == 1:
                                            self.dictSocketRecvData[sockHandle]["recvMaskLen"] = self.dictSocketRecvData[sockHandle]["recvMaskLen"] + 1
                                            self.dictSocketRecvData[sockHandle]["tmpRecvMaskData"] += mask

                                    except IOError as e:
                                        if e.errno == 11:
                                            break
                                    except RuntimeError as re:
                                        break
                                else:
                                    self.dictSocketRecvData[sockHandle]["mask"] = self.dictSocketRecvData[sockHandle]["tmpRecvMaskData"]

                                print("接收到的数据长度为：", self.dictSocketRecvData[sockHandle]["dataLength"])

                            if "mask" in self.dictSocketRecvData[sockHandle]:
                                if not "recvDataLength" in self.dictSocketRecvData[sockHandle]:
                                    self.dictSocketRecvData[sockHandle]["recvDataLength"] = 0

                                if not "leftRecvDataLength" in self.dictSocketRecvData[sockHandle]:
                                    self.dictSocketRecvData[sockHandle]["leftRecvDataLength"] = self.dictSocketRecvData[sockHandle]["dataLength"]
                                    while self.dictSocketRecvData[sockHandle]["recvDataLength"] < self.dictSocketRecvData[sockHandle]["dataLength"]:
                                        if self.dictSocketRecvData[sockHandle]["leftRecvDataLength"] < everyRecvDataLen:
                                            try:
                                                data = client.recv(self.dictSocketRecvData[sockHandle]["leftRecvDataLength"])
                                                if len(data) == 0:
                                                    raise RuntimeError()
                                                for i in range(len(data)):
                                                    chunk = data[i] ^ self.dictSocketRecvData[sockHandle]["mask"][i % 4]
                                                    bytes_list.append(chunk)
                                                self.dictSocketRecvData[sockHandle]["recvDataLength"] = self.dictSocketRecvData[sockHandle]["recvDataLength"] + len(data)
                                                self.dictSocketRecvData[sockHandle]["leftRecvDataLength"] = self.dictSocketRecvData[sockHandle]["leftRecvDataLength"] - len(data)
                                            except IOError as e:
                                                if e.errno == 11:
                                                    break
                                            except RuntimeError as re:
                                                self.epollHandle.modify(client, select.EPOLLHUP)
                                        else:
                                            try:
                                                data = client.recv(everyRecvDataLen)
                                                if len(data) == 0:
                                                    raise RuntimeError()
                                                for i in range(len(data)):
                                                    chunk = data[i] ^ self.dictSocketRecvData[sockHandle]["mask"][i % 4]
                                                    bytes_list.append(chunk)
                                                self.dictSocketRecvData[sockHandle]["recvDataLength"] = self.dictSocketRecvData[sockHandle]["recvDataLength"] + len(data)
                                                self.dictSocketRecvData[sockHandle]["leftRecvDataLength"] = self.dictSocketRecvData[sockHandle]["leftRecvDataLength"] - len(data)
                                            except RuntimeError as re:
                                                self.epollHandle.modify(client, select.EPOLLHUP)


                                    self.dictSocketRecvData[sockHandle]["finish"] = True
                                    if self.dictSocketRecvData[sockHandle]["firstByteFIN"] == 0:#如果数据接收尚未完成（数据切片的情况下）
                                        if client.fileno() in self.dictSocketContent:#如果socket字典中已经有该socket了
                                            self.dictSocketContent[client.fileno()] = self.dictSocketContent[client.fileno()] + bytes_list
                                        else:
                                            self.dictSocketContent[client.fileno()] = bytes_list
                                    else:#如果已经接收完成了
                                        if client.fileno() in self.dictSocketContent:#如果socket字典中已经有该socket了
                                            self.dictSocketContent[client.fileno()] = self.dictSocketContent[client.fileno()] + bytes_list
                                        else:
                                            self.dictSocketContent[client.fileno()] = bytes_list

                        if self.dictSocketRecvData[sockHandle]["finish"]:
                            if self.dictSocketRecvData[sockHandle]["firstByteFIN"] == 0:
                                if self.dictSocketRecvData[sockHandle]["opCode"] == 1:
                                    if self.dictSocketRecvData[sockHandle]["recvDataLength"] >= self.dictSocketRecvData[sockHandle]["dataLength"]:
                                        self.dictSocketRecvData[sockHandle]["totalFinish"] = "xxxx"
                                    print("----------------------文本消息，传输尚未完成")

                                elif self.dictSocketRecvData[sockHandle]["opCode"] == 2:
                                    # self.dictSocketRecvData[sockHandle]["totalFinish"] = "xxxx"
                                    if self.dictSocketRecvData[sockHandle]["recvDataLength"] >= self.dictSocketRecvData[sockHandle]["dataLength"]:
                                        self.dictSocketRecvData[sockHandle]["totalFinish"] = "xxxx"
                                        #     self.dictSocketRecvData.pop(sockHandle)
                                    print("----------------------二进制数据，传输尚未完成")
                                elif self.dictSocketRecvData[sockHandle]["opCode"] == 0:


                                    if self.dictSocketRecvData[sockHandle]["recvDataLength"] >= self.dictSocketRecvData[sockHandle]["dataLength"]:
                                        self.dictSocketRecvData[sockHandle]["totalFinish"] = "xxxx"
                                        #     self.dictSocketRecvData.pop(sockHandle)
                                    print("----------------------数据分片，传输尚未完成")
                                else:
                                    pass
                            else:
                                if self.dictSocketRecvData[sockHandle]["opCode"] == 1:
                                    print("正在接收最后一帧文本消息数据")
                                    if self.dictSocketRecvData[sockHandle]["recvDataLength"] >= self.dictSocketRecvData[sockHandle]["dataLength"]:
                                        print(self.dictSocketRecvData[sockHandle]["recvDataLength"], "=======", self.dictSocketRecvData[sockHandle]["dataLength"])
                                        self.dictSocketRecvData[sockHandle]["totalFinish"] = True
                                        returnRes = True
                                        strings = self.dictSocketContent[client.fileno()]
                                        self.resDict["string"] = strings
                                        self.resDict["type"] = 1


                                elif self.dictSocketRecvData[sockHandle]["opCode"] == 2:
                                    print("正在接收一帧二进制数据")
                                    if self.dictSocketRecvData[sockHandle]["recvDataLength"] >= self.dictSocketRecvData[sockHandle]["dataLength"]:
                                        print(self.dictSocketRecvData[sockHandle]["recvDataLength"], "=======", self.dictSocketRecvData[sockHandle]["dataLength"])
                                        self.dictSocketRecvData[sockHandle]["totalFinish"] = True
                                        returnRes = True
                                        strings = self.dictSocketContent[client.fileno()]
                                        print("数据总大小：", len(strings))
                                        self.resDict["string"] = strings
                                        self.resDict["type"] = 2

                                elif self.dictSocketRecvData[sockHandle]["opCode"] == 0:
                                    print("正在接收一帧二进制分片数据")
                                    if self.dictSocketRecvData[sockHandle]["recvDataLength"] >= self.dictSocketRecvData[sockHandle]["dataLength"]:
                                        print(self.dictSocketRecvData[sockHandle]["recvDataLength"], "=======", self.dictSocketRecvData[sockHandle]["dataLength"])
                                        self.dictSocketRecvData[sockHandle]["totalFinish"] = True
                                        returnRes = True
                                        strings = self.dictSocketContent[client.fileno()]
                                        print("数据总大小：", len(strings))
                                        self.resDict["string"] = strings
                                        self.resDict["type"] = 2

                                else:
                                    pass
                if self.dictSocketRecvData[sockHandle]["totalFinish"] == True:
                    print("true")
                    self.dictSocketRecvData.pop(sockHandle)
                    self.dictSocketContent.pop(sockHandle)
                elif self.dictSocketRecvData[sockHandle]["totalFinish"] == "xxxx":
                    print("xxxxx")
                    self.dictSocketRecvData.pop(sockHandle)
                elif self.dictSocketRecvData[sockHandle]["totalFinish"] == False:
                    print("false")
                    break
            if returnRes == True:
                return self.resDict

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
                self.epollHandle.modify(everySock, select.EPOLLOUT|select.EPOLLET)

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

        length = len(msg_bytes)
        # 打包规则
        if length < 126:
            token = struct.pack("B", 129)
            token += struct.pack("B", length)
        elif length <= 0xFFFF:
            token = struct.pack("B", 129)
            token += struct.pack("B", 126)
            token += struct.pack("!H", length)
        else:
            token = struct.pack("B", 130)
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
    socketService = webSocketServer("0.0.0.0", 8089)

