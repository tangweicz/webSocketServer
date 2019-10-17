#!/Library/Frameworks/Python.framework/Versions/3.6/bin/python3.6
#! -*- coding:utf-8 -*-

__author__ = "tangwei"

from selectors import DefaultSelector, EVENT_READ, EVENT_WRITE

import struct, collections, hashlib, base64, time, json

import socket

class webSocketServer(object):

    dictSocketHandleSendContent = {}  # 这儿存放每一个socket需要发送数据，每次发送数据完毕，需要删除其中的内容
    dictSocketHandle = {}  # 这儿存放每一个socket的句柄
    dictSocketShakeHandStatus = {}  # 用于存放每一个socket的握手状态，没有握手或握手失败为False、握手成功为True
    dictSocketShakeHandKey = {}  # 用于存放每一个socket的握手需要的key值
    dictRoom = {}  # 用于存放连接上来的socket在哪个房间的字典。比如 "room1":[{"socketHandle":socket1,"prepareStatus":status}, {"socketHandle":socket2,"prepareStatus":status}]。每次有一个socket连接上来，第一时间将该信息发送给该连接。
    dictSocketFrame = {}
    listClosingSocketHandle = []  # 正在关闭的socket句柄
    dictSocketContent = {}  # 存放需要切片的socket的数据
    dictSocketRecvFileExtension = {}  # 用来存放发送文件的时候 文件的后缀名是啥
    dictSocketSendHandle = {}  # 用来存放每个socket要发送的数据的总长度
    dictSocketSendedHandle = {}  # 用来存放每个socket已经发送数据的总长度
    dictSocketLeftHandle = {}  # 用来存放每个socket剩余发送数据量
    dictSocketRecvData = {}  # 用来存放每个socket接收到的数据
    resDict = {}

    def __init__(self, ipAddr, port):#初始化一个socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((ipAddr, port))
        self.sock.setblocking(False)
        self.sock.listen(100)
        self.acceptOne()

    def acceptOne(self):
        self.selector = DefaultSelector()
        self.selector.register(self.sock.fileno(), EVENT_READ, self.readable)

        while True:
            ready = self.selector.select(1)
            # print(ready)
            for key, event in ready:
                callbackFunc = key.data
                callbackFunc(key)

    def readable(self, key):
        if key.fd == self.sock.fileno():#如果是新的连接进来
            client, address = self.sock.accept()
            self.dictSocketHandle[client.fileno()] = client
            self.dictSocketShakeHandStatus[client.fileno()] = False
            self.selector.register(client.fileno(), EVENT_READ, self.readable)
        else:#如果是连接有数据可以读取
            #-------
            print("请求开始")
            strings = b""

            client = self.dictSocketHandle[key.fd]
            if not self.dictSocketShakeHandStatus[key.fd]:  # 如果没有握手完成，我用1024个字节去接收数据是完全够用的
                print("握手未完成，去握手")
                data = client.recv(1024)  # 这儿如果没有拿够1024个字节的数据，那么会循环回来拿，但是，如果发现没有数据能拿到，socket会自动中止，扔出一个异常，代码就结束执行，所以需要try一下。
                if len(data) == 0:  # 通道断开或者close之后，就会一直收到空字符串。 而不是所谓的-1 或者报异常。这个跟C 和java等其他语言很不一样。
                    pass
                strings = data
                opCode = -5
                print("新连接句柄，尚未握手完成", client.fileno())
                message = strings.decode('utf-8')

                data = message.split("\r\n\r\n")
                data = data[0]
                allData = data.split("\r\n")
                headerData = collections.OrderedDict()
                for item in allData:
                    res = item.split(":", 1)
                    if res[0].startswith("GET"):
                        headerData["HTTP"] = res[0]
                    else:
                        headerData[res[0]] = res[1]
                if headerData:
                    self.dictSocketShakeHandKey[key.fd] = headerData
                    self.selector.modify(key.fd, EVENT_WRITE, self.writeable)


            else:  # 如果已经握手完成了，那么先要去完成一次通讯由客户端告知服务端，下一次要发送的数据大小

                # if not client.fileno() in self.listClosingSocketHandle:#当前操作的socket不是处于正在关闭的状态，那么可以正常获取数据，如果处于正在关闭的状态，等待关闭

                print("*******************************************")
                everyRecvDataLen = 2048
                minExtendPayloadLen = 2
                maxExtendPayloadLen = 8
                maskRecvLength = 4
                print("句柄为", client.fileno())
                returnRes = False

                if not key.fd in self.resDict:
                    self.resDict[key.fd] = {}

                bytes_list = bytearray('', encoding='utf-8')
                if not key.fd in self.dictSocketRecvData:
                    self.dictSocketRecvData[key.fd] = {}

                if not "hasFirstByte" in self.dictSocketRecvData[key.fd] or self.dictSocketRecvData[key.fd]["hasFirstByte"] == False:
                    try:
                        data_head = client.recv(1)  # 获取一个字节的数据
                        if len(data_head) == 0:  # 如果在接收数据过程中，客户端突然关闭，那么就会接收到空数据，然后根据空数据去断开连接，这点至关重要
                            raise RuntimeError()
                        if len(data_head) == 1:
                            self.dictSocketRecvData[key.fd]["hasFirstByte"] = True

                            data_head = struct.unpack("B", data_head)[0]  # unpack这个字节的数据
                            self.dictSocketRecvData[key.fd]["firstByteFIN"] = data_head & 0x80
                            opCode = self.parseHeadData(data_head)
                            print("opCode", opCode)
                            if opCode == 8:  # 浏览器端主动关闭请求，这段必须写。因为客户端主动关闭之后，还会再次发送一个请求过来确认是否关闭
                                # self.listClosingSocketHandle.append(client.fileno())
                                self.resDict["type"] = 8
                                self.resDict["string"] = ""
                                self.selector.modify(key.fd, EVENT_WRITE, self.writeable)

                            self.dictSocketRecvData[key.fd]["opCode"] = opCode
                            if self.dictSocketRecvData[key.fd]["firstByteFIN"] == 0:
                                if self.dictSocketRecvData[key.fd]["opCode"] == 1:
                                    print("----------------------文本消息，传输尚未完成")
                                elif self.dictSocketRecvData[key.fd]["opCode"] == 2:
                                    print("----------------------二进制数据，传输尚未完成")
                                elif self.dictSocketRecvData[key.fd]["opCode"] == 0:
                                    print("----------------------数据分片，传输尚未完成")
                                else:
                                    print("----------------------数据尚未完成，opCode为：",
                                          self.dictSocketRecvData[key.fd]["opCode"])
                            else:
                                if self.dictSocketRecvData[key.fd]["opCode"] == 1:
                                    print("----------------------文本消息，传输已完成")
                                elif self.dictSocketRecvData[key.fd]["opCode"] == 2:
                                    print("----------------------二进制数据，传输已完成")
                                elif self.dictSocketRecvData[key.fd]["opCode"] == 0:
                                    print("----------------------数据分片，传输已完成")
                                else:
                                    print("----------------------传输已完成，opCode为：",
                                          self.dictSocketRecvData[key.fd]["opCode"])
                    except Exception as re:
                        pass

                if "firstByteFIN" in self.dictSocketRecvData[key.fd] and "opCode" in self.dictSocketRecvData[key.fd]:

                    if not "hasSecondByte" in self.dictSocketRecvData[key.fd] or self.dictSocketRecvData[key.fd]["hasSecondByte"] == False:
                        try:
                            byteData = client.recv(1)  # 再获取一个字节的数据
                            if len(byteData) == 0:
                                raise RuntimeError()
                            if len(byteData) == 1:
                                self.dictSocketRecvData[key.fd]["hasSecondByte"] = True

                                byteData = struct.unpack("B", byteData)[0]  # unpack这个字节的数据

                                self.dictSocketRecvData[key.fd][
                                    "payload_len"] = byteData & 127  # 根据这个字节的后7位，这个数字只可能 小于126 等于126 等于127 这三种情况。
                                # 小于126代表后面的数据长度为dataLength
                                # 等于126代表后面的2个字节（16位无符号整数的十进制的值为dataLength）
                                # 等于127代表后面的8个字节（64位无符号证书的十进制的值为dataLength）
                                # mask key 是固定的后四字节
                                print("payloadLen", self.dictSocketRecvData[key.fd]["payload_len"])

                        except Exception as re:
                            pass

                    if "payload_len" in self.dictSocketRecvData[key.fd]:

                        if self.dictSocketRecvData[key.fd]["payload_len"] == 126:
                            print("========", self.dictSocketRecvData[key.fd])
                            self.dictSocketRecvData[key.fd]["finish"] = False
                            if not "dataLength" in self.dictSocketRecvData[key.fd]:

                                if not "recvExtendMinPayloadLen" in self.dictSocketRecvData[key.fd]:
                                    self.dictSocketRecvData[key.fd]["recvExtendMinPayloadLen"] = 0
                                if not "tmpRecvMinExtendPayloadData" in self.dictSocketRecvData[key.fd]:
                                    self.dictSocketRecvData[key.fd]["tmpRecvMinExtendPayloadData"] = b""

                                if self.dictSocketRecvData[key.fd]["recvExtendMinPayloadLen"] < minExtendPayloadLen:
                                    try:
                                        extend_payload_len = client.recv(1)  # 数据头部延伸的长度,每次获取1个字节
                                        if len(extend_payload_len) == 0:
                                            raise RuntimeError()
                                        if len(extend_payload_len) == 1:
                                            self.dictSocketRecvData[key.fd]["recvExtendMinPayloadLen"] = \
                                            self.dictSocketRecvData[key.fd]["recvExtendMinPayloadLen"] + 1
                                            self.dictSocketRecvData[key.fd][
                                                "tmpRecvMinExtendPayloadData"] += extend_payload_len
                                            # self.dictSocketRecvData[key.fd]["dataLength"] = struct.unpack("!H", extend_payload_len)[0]  # 因为是2个字节 所以用H解码
                                    except RuntimeError as re:
                                        pass
                                else:
                                    self.dictSocketRecvData[key.fd]["dataLength"] = struct.unpack("!H", self.dictSocketRecvData[key.fd]["tmpRecvMinExtendPayloadData"])[
                                        0]  # 因为是2个字节 所以用H解码

                            if "dataLength" in self.dictSocketRecvData[key.fd]:
                                if not "mask" in self.dictSocketRecvData[key.fd]:

                                    if not "recvMaskLen" in self.dictSocketRecvData[key.fd]:
                                        self.dictSocketRecvData[key.fd]["recvMaskLen"] = 0
                                    if not "tmpRecvMaskData" in self.dictSocketRecvData[key.fd]:
                                        self.dictSocketRecvData[key.fd]["tmpRecvMaskData"] = b""

                                    if self.dictSocketRecvData[key.fd]["recvMaskLen"] < maskRecvLength:
                                        try:
                                            mask = client.recv(1)  # 加密的4个字节
                                            if len(mask) == 0:
                                                raise RuntimeError()
                                            if len(mask) == 1:
                                                self.dictSocketRecvData[key.fd]["recvMaskLen"] = \
                                                self.dictSocketRecvData[key.fd]["recvMaskLen"] + 1
                                                self.dictSocketRecvData[key.fd]["tmpRecvMaskData"] += mask
                                        except RuntimeError as re:
                                            pass
                                    else:
                                        self.dictSocketRecvData[key.fd]["mask"] = \
                                        self.dictSocketRecvData[key.fd]["tmpRecvMaskData"]

                                print("接收到的数据长度为：", self.dictSocketRecvData[key.fd]["dataLength"])

                                if "mask" in self.dictSocketRecvData[key.fd]:
                                    if not "recvDataLength" in self.dictSocketRecvData[key.fd]:
                                        self.dictSocketRecvData[key.fd]["recvDataLength"] = 0
                                    if not "leftRecvDataLength" in self.dictSocketRecvData[key.fd]:
                                        self.dictSocketRecvData[key.fd]["leftRecvDataLength"] = \
                                        self.dictSocketRecvData[key.fd]["dataLength"]
                                    if self.dictSocketRecvData[key.fd]["recvDataLength"] < \
                                            self.dictSocketRecvData[key.fd]["dataLength"]:
                                        if self.dictSocketRecvData[key.fd]["leftRecvDataLength"] < everyRecvDataLen:
                                            try:
                                                data = client.recv(
                                                    self.dictSocketRecvData[key.fd]["leftRecvDataLength"])
                                                if len(data) == 0:
                                                    raise RuntimeError()
                                                for i in range(len(data)):
                                                    chunk = data[i] ^ self.dictSocketRecvData[key.fd]["mask"][i % 4]
                                                    bytes_list.append(chunk)
                                                self.dictSocketRecvData[key.fd]["recvDataLength"] = \
                                                self.dictSocketRecvData[key.fd]["recvDataLength"] + len(data)
                                                self.dictSocketRecvData[key.fd]["leftRecvDataLength"] = \
                                                self.dictSocketRecvData[key.fd]["leftRecvDataLength"] - len(data)
                                            except RuntimeError as re:
                                                pass
                                        else:
                                            try:
                                                data = client.recv(everyRecvDataLen)
                                                if len(data) == 0:
                                                    raise RuntimeError()
                                                for i in range(len(data)):
                                                    chunk = data[i] ^ self.dictSocketRecvData[key.fd]["mask"][i % 4]
                                                    bytes_list.append(chunk)
                                                self.dictSocketRecvData[key.fd]["recvDataLength"] = \
                                                self.dictSocketRecvData[key.fd]["recvDataLength"] + len(data)
                                                self.dictSocketRecvData[key.fd]["leftRecvDataLength"] = \
                                                self.dictSocketRecvData[key.fd]["leftRecvDataLength"] - len(data)
                                            except RuntimeError as re:
                                                pass

                                    # self.dictSocketContent[client.fileno()] = bytes_list
                                    self.dictSocketRecvData[key.fd]["finish"] = True
                                    if self.dictSocketRecvData[key.fd]["firstByteFIN"] == 0:  # 如果数据接收尚未完成（数据切片的情况下）
                                        if client.fileno() in self.dictSocketContent:  # 如果socket字典中已经有该socket了
                                            self.dictSocketContent[client.fileno()] = self.dictSocketContent[
                                                                                          client.fileno()] + bytes_list
                                        else:
                                            self.dictSocketContent[client.fileno()] = bytes_list

                                    else:  # 如果已经接收完成了
                                        if client.fileno() in self.dictSocketContent:  # 如果socket字典中已经有该socket了
                                            self.dictSocketContent[client.fileno()] = self.dictSocketContent[
                                                                                          client.fileno()] + bytes_list
                                        else:
                                            self.dictSocketContent[client.fileno()] = bytes_list

                                    print("数据总大小", self.dictSocketRecvData[key.fd]["dataLength"], "获取数据长度",
                                          self.dictSocketRecvData[key.fd][
                                              "recvDataLength"])  # , "获取到数据：", bytes_list)


                        elif self.dictSocketRecvData[key.fd]["payload_len"] == 127:
                            print("========", self.dictSocketRecvData[key.fd])
                            self.dictSocketRecvData[key.fd]["finish"] = False
                            if not "dataLength" in self.dictSocketRecvData[key.fd]:

                                if not "recvExtendMaxPayloadLen" in self.dictSocketRecvData[key.fd]:
                                    self.dictSocketRecvData[key.fd]["recvExtendMaxPayloadLen"] = 0
                                if not "tmpRecvMaxExtendPayloadData" in self.dictSocketRecvData[key.fd]:
                                    self.dictSocketRecvData[key.fd]["tmpRecvMaxExtendPayloadData"] = b""

                                if self.dictSocketRecvData[key.fd]["recvExtendMaxPayloadLen"] < maxExtendPayloadLen:
                                    try:
                                        extend_payload_len = client.recv(1)
                                        if len(extend_payload_len) == 0:
                                            raise RuntimeError()
                                        if len(extend_payload_len) == 1:
                                            self.dictSocketRecvData[key.fd]["recvExtendMaxPayloadLen"] = \
                                            self.dictSocketRecvData[key.fd]["recvExtendMaxPayloadLen"] + 1
                                            self.dictSocketRecvData[key.fd][
                                                "tmpRecvMaxExtendPayloadData"] += extend_payload_len
                                    except RuntimeError as re:
                                        pass
                                else:
                                    self.dictSocketRecvData[key.fd]["dataLength"] = struct.unpack("!Q",
                                                                                                      self.dictSocketRecvData[
                                                                                                          key.fd][
                                                                                                          "tmpRecvMaxExtendPayloadData"])[
                                        0]
                                    print("接收到的数据长度为：", self.dictSocketRecvData[key.fd]["dataLength"])

                            if "dataLength" in self.dictSocketRecvData[key.fd]:

                                if not "mask" in self.dictSocketRecvData[key.fd]:

                                    if not "recvMaskLen" in self.dictSocketRecvData[key.fd]:
                                        self.dictSocketRecvData[key.fd]["recvMaskLen"] = 0
                                    if not "tmpRecvMaskData" in self.dictSocketRecvData[key.fd]:
                                        self.dictSocketRecvData[key.fd]["tmpRecvMaskData"] = b""

                                    if self.dictSocketRecvData[key.fd]["recvMaskLen"] < maskRecvLength:
                                        try:
                                            mask = client.recv(1)  # 加密的4个字节
                                            if len(mask) == 0:
                                                raise RuntimeError()
                                            if len(mask) == 1:
                                                self.dictSocketRecvData[key.fd]["recvMaskLen"] = \
                                                self.dictSocketRecvData[key.fd]["recvMaskLen"] + 1
                                                self.dictSocketRecvData[key.fd]["tmpRecvMaskData"] += mask
                                        except RuntimeError as re:
                                            pass
                                    else:
                                        self.dictSocketRecvData[key.fd]["mask"] = \
                                        self.dictSocketRecvData[key.fd]["tmpRecvMaskData"]

                                    # try:
                                    #     mask = client.recv(4)  # 加密的4个字节
                                    #     if len(mask) == 0:
                                    #         raise RuntimeError()
                                    #     if len(mask) >= 4:
                                    #         self.dictSocketRecvData[key.fd]["mask"] = mask
                                    # except RuntimeError as re:
                                    #     self.epollHandle.modify(client, select.EPOLLHUP)

                                if "mask" in self.dictSocketRecvData[key.fd]:
                                    if not "recvDataLength" in self.dictSocketRecvData[key.fd]:
                                        self.dictSocketRecvData[key.fd]["recvDataLength"] = 0

                                    if not "leftRecvDataLength" in self.dictSocketRecvData[key.fd]:
                                        self.dictSocketRecvData[key.fd]["leftRecvDataLength"] = \
                                        self.dictSocketRecvData[key.fd]["dataLength"]

                                    if self.dictSocketRecvData[key.fd]["recvDataLength"] < \
                                            self.dictSocketRecvData[key.fd]["dataLength"]:
                                        if self.dictSocketRecvData[key.fd]["leftRecvDataLength"] < everyRecvDataLen:
                                            try:
                                                data = client.recv(
                                                    self.dictSocketRecvData[key.fd]["leftRecvDataLength"])
                                                if len(data) == 0:
                                                    raise RuntimeError()
                                                for i in range(len(data)):
                                                    chunk = data[i] ^ self.dictSocketRecvData[key.fd]["mask"][i % 4]
                                                    bytes_list.append(chunk)
                                                self.dictSocketRecvData[key.fd]["recvDataLength"] = \
                                                self.dictSocketRecvData[key.fd]["recvDataLength"] + len(data)
                                                self.dictSocketRecvData[key.fd]["leftRecvDataLength"] = \
                                                self.dictSocketRecvData[key.fd]["leftRecvDataLength"] - len(data)
                                            except RuntimeError as re:
                                                pass
                                        else:
                                            try:
                                                data = client.recv(everyRecvDataLen)
                                                if len(data) == 0:
                                                    raise RuntimeError()
                                                for i in range(len(data)):
                                                    chunk = data[i] ^ self.dictSocketRecvData[key.fd]["mask"][i % 4]
                                                    bytes_list.append(chunk)
                                                self.dictSocketRecvData[key.fd]["recvDataLength"] = \
                                                self.dictSocketRecvData[key.fd]["recvDataLength"] + len(data)
                                                self.dictSocketRecvData[key.fd]["leftRecvDataLength"] = \
                                                self.dictSocketRecvData[key.fd]["leftRecvDataLength"] - len(data)
                                            except RuntimeError as re:
                                                pass

                                    # self.dictSocketContent[client.fileno()] = bytes_list
                                    self.dictSocketRecvData[key.fd]["finish"] = True
                                    if self.dictSocketRecvData[key.fd]["firstByteFIN"] == 0:  # 如果数据接收尚未完成（数据切片的情况下）
                                        if client.fileno() in self.dictSocketContent:  # 如果socket字典中已经有该socket了
                                            self.dictSocketContent[client.fileno()] = self.dictSocketContent[
                                                                                          client.fileno()] + bytes_list
                                        else:
                                            self.dictSocketContent[client.fileno()] = bytes_list
                                    else:  # 如果已经接收完成了
                                        if client.fileno() in self.dictSocketContent:  # 如果socket字典中已经有该socket了
                                            self.dictSocketContent[client.fileno()] = self.dictSocketContent[
                                                                                          client.fileno()] + bytes_list
                                        else:
                                            self.dictSocketContent[client.fileno()] = bytes_list

                                    print("数据总大小", self.dictSocketRecvData[key.fd]["dataLength"], "获取数据长度",
                                          self.dictSocketRecvData[key.fd][
                                              "recvDataLength"])  # , "获取到数据：", bytes_list)
                        else:
                            self.dictSocketRecvData[key.fd]["finish"] = False
                            self.dictSocketRecvData[key.fd]["dataLength"] = self.dictSocketRecvData[key.fd]["payload_len"]
                            if not "mask" in self.dictSocketRecvData[key.fd]:

                                if not "recvMaskLen" in self.dictSocketRecvData[key.fd]:
                                    self.dictSocketRecvData[key.fd]["recvMaskLen"] = 0
                                if not "tmpRecvMaskData" in self.dictSocketRecvData[key.fd]:
                                    self.dictSocketRecvData[key.fd]["tmpRecvMaskData"] = b""

                                if self.dictSocketRecvData[key.fd]["recvMaskLen"] < maskRecvLength:
                                    try:
                                        mask = client.recv(1)  # 加密的4个字节
                                        if len(mask) == 0:
                                            raise RuntimeError()
                                        if len(mask) == 1:
                                            self.dictSocketRecvData[key.fd]["recvMaskLen"] = self.dictSocketRecvData[key.fd]["recvMaskLen"] + 1
                                            self.dictSocketRecvData[key.fd]["tmpRecvMaskData"] += mask
                                    except RuntimeError as re:
                                        pass
                                else:
                                    self.dictSocketRecvData[key.fd]["mask"] = self.dictSocketRecvData[key.fd]["tmpRecvMaskData"]

                            print("接收到的数据长度为：", self.dictSocketRecvData[key.fd]["dataLength"])

                            print(self.dictSocketRecvData[key.fd])

                            if "mask" in self.dictSocketRecvData[key.fd]:

                                if not "recvDataLength" in self.dictSocketRecvData[key.fd]:
                                    self.dictSocketRecvData[key.fd]["recvDataLength"] = 0

                                if not "leftRecvDataLength" in self.dictSocketRecvData[key.fd]:
                                    self.dictSocketRecvData[key.fd]["leftRecvDataLength"] = self.dictSocketRecvData[key.fd]["dataLength"]

                                if self.dictSocketRecvData[key.fd]["recvDataLength"] < self.dictSocketRecvData[key.fd]["dataLength"]:
                                    if self.dictSocketRecvData[key.fd]["leftRecvDataLength"] < everyRecvDataLen:
                                        try:
                                            data = client.recv(self.dictSocketRecvData[key.fd]["leftRecvDataLength"])
                                            if len(data) == 0:
                                                raise RuntimeError()
                                            for i in range(len(data)):
                                                chunk = data[i] ^ self.dictSocketRecvData[key.fd]["mask"][i % 4]
                                                bytes_list.append(chunk)
                                            self.dictSocketRecvData[key.fd]["recvDataLength"] = self.dictSocketRecvData[key.fd]["recvDataLength"] + len(data)
                                            self.dictSocketRecvData[key.fd]["leftRecvDataLength"] = self.dictSocketRecvData[key.fd]["leftRecvDataLength"] - len(data)
                                        except RuntimeError as re:
                                            pass
                                    else:
                                        try:
                                            data = client.recv(everyRecvDataLen)
                                            if len(data) == 0:
                                                raise RuntimeError()
                                            for i in range(len(data)):
                                                chunk = data[i] ^ self.dictSocketRecvData[key.fd]["mask"][i % 4]
                                                bytes_list.append(chunk)
                                            self.dictSocketRecvData[key.fd]["recvDataLength"] = self.dictSocketRecvData[key.fd]["recvDataLength"] + len(data)
                                            self.dictSocketRecvData[key.fd]["leftRecvDataLength"] = self.dictSocketRecvData[key.fd]["leftRecvDataLength"] - len(data)
                                        except RuntimeError as re:
                                            pass
                                # self.dictSocketContent[client.fileno()] = bytes_list

                                if self.dictSocketRecvData[key.fd]["leftRecvDataLength"] == 0:

                                    self.dictSocketRecvData[key.fd]["finish"] = True

                                    if self.dictSocketRecvData[key.fd]["firstByteFIN"] == 0:  # 如果数据接收尚未完成（数据切片的情况下）

                                        if client.fileno() in self.dictSocketContent:  # 如果socket字典中已经有该socket了
                                            self.dictSocketContent[client.fileno()] = self.dictSocketContent[client.fileno()] + bytes_list
                                        else:
                                            self.dictSocketContent[client.fileno()] = bytes_list
                                    else:  # 如果已经接收完成了
                                        if client.fileno() in self.dictSocketContent:  # 如果socket字典中已经有该socket了
                                            self.dictSocketContent[client.fileno()] = self.dictSocketContent[client.fileno()] + bytes_list
                                        else:
                                            self.dictSocketContent[client.fileno()] = bytes_list
                                    print("内容是否接收完成的标志：", self.dictSocketRecvData[key.fd]["finish"])


                        if self.dictSocketRecvData[key.fd]["finish"]:
                            if self.dictSocketRecvData[key.fd]["firstByteFIN"] == 0:
                                if self.dictSocketRecvData[key.fd]["opCode"] == 1:
                                    if self.dictSocketRecvData[key.fd]["recvDataLength"] >= self.dictSocketRecvData[key.fd]["dataLength"]:
                                        self.dictSocketRecvData.pop(key.fd)
                                    print("----------------------文本消息，传输尚未完成")

                                elif self.dictSocketRecvData[key.fd]["opCode"] == 2:
                                    if self.dictSocketRecvData[key.fd]["recvDataLength"] >= self.dictSocketRecvData[key.fd]["dataLength"]:
                                        self.dictSocketRecvData.pop(key.fd)
                                    print("----------------------二进制数据，传输尚未完成")
                                elif self.dictSocketRecvData[key.fd]["opCode"] == 0:
                                    if self.dictSocketRecvData[key.fd]["recvDataLength"] >= self.dictSocketRecvData[key.fd]["dataLength"]:
                                        self.dictSocketRecvData.pop(key.fd)
                                    print("----------------------数据分片，传输尚未完成")
                                else:
                                    pass
                            else:
                                if self.dictSocketRecvData[key.fd]["opCode"] == 1:
                                    print("正在接收最后一帧文本消息数据")
                                    if self.dictSocketRecvData[key.fd]["recvDataLength"] >= self.dictSocketRecvData[key.fd]["dataLength"]:
                                        print(self.dictSocketRecvData[key.fd]["recvDataLength"], "=======", self.dictSocketRecvData[key.fd]["dataLength"])
                                        strings = self.dictSocketContent[client.fileno()]
                                        self.resDict[key.fd]["string"] = strings
                                        self.resDict[key.fd]["type"] = 1
                                        self.dictSocketRecvData.pop(key.fd)
                                        self.dictSocketContent.pop(key.fd)
                                        self.selector.modify(key.fd, EVENT_WRITE, self.writeable)

                                elif self.dictSocketRecvData[key.fd]["opCode"] == 2:
                                    print("正在接收一帧二进制数据")
                                    if self.dictSocketRecvData[key.fd]["recvDataLength"] >= self.dictSocketRecvData[key.fd]["dataLength"]:
                                        print(self.dictSocketRecvData[key.fd]["recvDataLength"], "=======", self.dictSocketRecvData[key.fd]["dataLength"])
                                        strings = self.dictSocketContent[client.fileno()]
                                        self.resDict[key.fd]["string"] = strings
                                        self.resDict[key.fd]["type"] = 2
                                        self.dictSocketRecvData.pop(key.fd)
                                        self.dictSocketContent.pop(key.fd)


                                        message = self.resDict[key.fd]
                                        if message:
                                            if not self.dictSocketShakeHandStatus[key.fd]:
                                                message = self.decodeToUtf8(message["string"])
                                                headerData = self.parseHeaderData(message)  # 解析header头数据
                                                if headerData:
                                                    self.dictSocketShakeHandKey[key.fd] = headerData
                                            else:
                                                if message["type"] == 1:
                                                    print("数据已传输完毕，纯文本消息")
                                                    try:  # 这儿为什么要try下，因为，如果不是json格式的字符串，不能json.loads所以，要try下
                                                        data = self.parseStrToJson(message["string"].decode("utf-8"))
                                                        if data["status"] == str(2):
                                                            print("确定为上传文件，文件后缀为", data["info"])
                                                            self.dictSocketRecvFileExtension[key.fd] = data["info"]

                                                            self.dictSocketHandleSendContent[key.fd] = '{"status":"success", "message":"信息接收成功"}'
                                                        else:
                                                            self.dictSocketHandleSendContent[key.fd] = '{"status":"success", "message":"信息接收成功"}'
                                                    except:
                                                        self.dictSocketHandleSendContent[key.fd] = '{"status":"error", "message":"通讯数据格式错误"}'
                                                elif message["type"] == 8:
                                                    print("接收到关闭信息，正在关闭" + str(key.fd))
                                                    self.dictSocketShakeHandStatus.pop(key.fd)
                                                    self.dictSocketHandle[key.fd].close()
                                                    self.epollHandle.unregister(key.fd)
                                                    self.dictSocketHandle.pop(key.fd)
                                                    self.dictSocketRecvData.pop(key.fd)
                                                    print("关闭操作完成")
                                                elif message["type"] == 2:
                                                    print("数据已传输完毕，二进制保存文件", len(message["string"]))
                                                    # ext = self.dictSocketRecvFileExtension[sock]
                                                    filename = str(int(time.time())) + "." + "jpeg"
                                                    with open(filename, "wb") as fd:
                                                        fd.write(message["string"])
                                                    if "jpeg" in ["png", "jpg", "jpeg", "gif"]:
                                                        self.dictSocketHandleSendContent[key.fd] = '{"status":"success", "message":"文件传输完成", "filename": "' + filename + '"}'
                                                    else:
                                                        self.dictSocketHandleSendContent[key.fd] = '{"status":"success", "message":"文件传输完成"}'

                                                    # self.dictSocketRecvFileExtension.pop(sock)

                                                    self.selector.modify(key.fd, EVENT_WRITE, self.writeable)

                                                else:
                                                    print("opCode为", message["type"], "不做任何处理")
                                                    pass
                                            self.selector.modify(key.fd, EVENT_WRITE, self.writeable)

                                elif self.dictSocketRecvData[key.fd]["opCode"] == 0:
                                    print("正在接收一帧二进制分片数据")
                                    if self.dictSocketRecvData[key.fd]["recvDataLength"] >= self.dictSocketRecvData[key.fd]["dataLength"]:
                                        print(self.dictSocketRecvData[key.fd]["recvDataLength"], "=======", self.dictSocketRecvData[key.fd]["dataLength"])
                                        strings = self.dictSocketContent[client.fileno()]
                                        self.resDict[key.fd]["string"] = strings
                                        self.resDict[key.fd]["type"] = 2
                                        self.dictSocketRecvData.pop(key.fd)
                                        self.dictSocketContent.pop(key.fd)



                                        message = self.resDict[key.fd]
                                        if message:
                                            if not self.dictSocketShakeHandStatus[key.fd]:
                                                message = self.decodeToUtf8(message["string"])
                                                headerData = self.parseHeaderData(message)  # 解析header头数据
                                                if headerData:
                                                    self.dictSocketShakeHandKey[key.fd] = headerData
                                            else:
                                                if message["type"] == 1:
                                                    try:  # 这儿为什么要try下，因为，如果不是json格式的字符串，不能json.loads所以，要try下
                                                        data = self.parseStrToJson(message["string"].decode("utf-8"))
                                                        if data["status"] == str(2):
                                                            print("确定为上传文件，文件后缀为", data["info"])
                                                            self.dictSocketRecvFileExtension[key.fd] = data["info"]

                                                            self.dictSocketHandleSendContent[
                                                                key.fd] = '{"status":"success", "message":"信息接收成功"}'
                                                        else:
                                                            self.dictSocketHandleSendContent[
                                                                key.fd] = '{"status":"success", "message":"信息接收成功"}'
                                                    except:
                                                        self.dictSocketHandleSendContent[
                                                            key.fd] = '{"status":"error", "message":"通讯数据格式错误"}'
                                                elif message["type"] == 8:
                                                    print("接收到关闭信息，正在关闭" + str(key.fd))
                                                    self.dictSocketShakeHandStatus.pop(key.fd)
                                                    self.dictSocketHandle[key.fd].close()
                                                    self.epollHandle.unregister(key.fd)
                                                    self.dictSocketHandle.pop(key.fd)
                                                    self.dictSocketRecvData.pop(key.fd)
                                                    print("关闭操作完成")
                                                elif message["type"] == 2:
                                                    print("数据已传输完毕，二进制保存文件", len(message["string"]))
                                                    # ext = self.dictSocketRecvFileExtension[sock]
                                                    filename = str(int(time.time())) + "." + "jpeg"
                                                    with open(filename, "wb") as fd:
                                                        fd.write(message["string"])
                                                    if "jpeg" in ["png", "jpg", "jpeg", "gif"]:
                                                        self.dictSocketHandleSendContent[
                                                            key.fd] = '{"status":"success", "message":"文件传输完成", "filename": "' + filename + '"}'
                                                    else:
                                                        self.dictSocketHandleSendContent[
                                                            key.fd] = '{"status":"success", "message":"文件传输完成"}'

                                                    # self.dictSocketRecvFileExtension.pop(sock)

                                                    self.selector.modify(key.fd, EVENT_WRITE, self.writeable)

                                                else:
                                                    print("opCode为", message["type"], "不做任何处理")
                                                    pass

                                            self.selector.modify(key.fd, EVENT_WRITE, self.writeable)
                                else:
                                    pass


    def writeable(self, key):

        # print("准备发送数据到客户端.....\n")
        client = self.dictSocketHandle[key.fd]
        strings = b""
        if not self.dictSocketShakeHandStatus[key.fd]:
            # print("发送握手数据到客户端.....")
            dictData = self.dictSocketShakeHandKey[key.fd]
            # print("key", dictData["Sec-WebSocket-Key"])
            keyStr = dictData["Sec-WebSocket-Key"] + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
            # print("**********,", key)
            sha1 = hashlib.sha1()
            sha1.update(str.strip(keyStr).encode("utf-8"))
            ser_key = sha1.digest()
            # print("sha1", ser_key)
            base64str = base64.b64encode(ser_key).decode("utf-8")
            # print("base64", base64str)
            strings = "HTTP/1.1 101 Switching Protocol\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept:%s\r\n\r\n" % (
                base64str)
            # print(strings)
            strings = strings.encode("utf-8")
            self.dictSocketShakeHandKey.pop(key.fd)
            if len(self.dictSocketHandle) >= 1:  # 一旦新的连接握手成功，这儿就发一个广播，告诉所有连接上来的用户，已经有多少用户在线上
                self.boardCast(key.fd)  # 发送广播对象，不包含刚刚连接上来的
        else:

            jsonData = json.loads(self.dictSocketHandleSendContent[key.fd])
            filename = ""
            if "filename" in jsonData:
                filename = jsonData["filename"]

            if not key.fd in self.dictSocketSendHandle:
                if filename == "":
                    strings = self.packWebSocketData('ceshi'.encode("utf-8"))  # 要发送的数据
                else:
                    data = b""
                    with open(filename, "rb") as fd:
                        data += fd.read()
                    print("要发送二进制文件总大小:", len(data))
                    strings = self.packWebSocketData(data)
                    print("要发送打包后的数据大小", len(strings))

        if not key.fd in self.dictSocketSendHandle:
            self.dictSocketSendHandle[key.fd] = len(strings)  # 要发送数据的总长度
        if not key.fd in self.dictSocketSendedHandle:
            self.dictSocketSendedHandle[key.fd] = 0  # 已发送数据总长度
        if not self.dictSocketShakeHandStatus[key.fd]:
            self.dictSocketShakeHandStatus[key.fd] = True
        # print("要发送数据总长度：", totalLen)
        print("yyyyy")

        while self.dictSocketSendedHandle[key.fd] < self.dictSocketSendHandle[key.fd]:
            try:
                m = strings[self.dictSocketSendedHandle[key.fd]:]
                le = client.send(m)
                print("本次发送数据量:", le)
                self.dictSocketSendedHandle[key.fd] = self.dictSocketSendedHandle[key.fd] + le
                print("已发送数据总量：", self.dictSocketSendedHandle[key.fd])

            except IOError as err:
                if err.errno == 32:  # 如果对端关闭，还去发送会产生，"Broken pipe"的错误  错误码为32
                    # print("客户端已经关闭连接，服务端等待关闭......")
                    pass
                if err.errno == 11:
                    print("写入缓冲区已满")
                    continue
                else:
                    print(err.errno)
                    print("服务端发送数据未知错误")
        # if self.dictSocketSendedHandle[sockHandle] < self.dictSocketSendHandle[sockHandle]:
        #     if self.dictSocketLeftHandle[sockHandle] < 512:
        #         try:
        #             print("开始位置：", self.dictSocketSendHandle[sockHandle])
        #             m = strings[self.dictSocketSendHandle[sockHandle]:]
        #             le = client.send(m)
        #             print("本次发送数据量:", le)
        #             self.dictSocketSendedHandle[sockHandle] = self.dictSocketSendedHandle[sockHandle] + le
        #             print("已发送数据总量：", self.dictSocketSendedHandle[sockHandle])
        #             self.dictSocketLeftHandle[sockHandle] = self.dictSocketLeftHandle[sockHandle] - le
        #             print("剩余发送数据总量：", self.dictSocketLeftHandle[sockHandle])
        #
        #         except IOError as err:
        #             if err.errno == 32:  # 如果对端关闭，还去发送会产生，"Broken pipe"的错误  错误码为32
        #                 # print("客户端已经关闭连接，服务端等待关闭......")
        #                 self.epollHandle.modify(sockHandle, select.EPOLLHUP)
        #             else:
        #                 print("服务端发送数据未知错误")
        #     else:
        #         try:
        #             m = strings[self.dictSocketSendHandle[sockHandle]:self.dictSocketSendHandle[sockHandle]+512]
        #             le = client.send(m)
        #             print("本次发送数据量:", le)
        #             self.dictSocketSendedHandle[sockHandle] = self.dictSocketSendedHandle[sockHandle] + le
        #             print("已发送数据总量：", self.dictSocketSendedHandle[sockHandle])
        #             self.dictSocketLeftHandle[sockHandle] = self.dictSocketLeftHandle[sockHandle] - le
        #             print("剩余发送数据总量：", self.dictSocketLeftHandle[sockHandle])
        #
        #         except IOError as err:
        #             if err.errno == 32:  # 如果对端关闭，还去发送会产生，"Broken pipe"的错误  错误码为32
        #                 # print("客户端已经关闭连接，服务端等待关闭......")
        #                 self.epollHandle.modify(sockHandle, select.EPOLLHUP)
        #             else:
        #                 print("服务端发送数据未知错误")

        else:
            self.selector.modify(key.fd, EVENT_READ, self.readable)
            self.dictSocketSendHandle.pop(key.fd)
            self.dictSocketSendedHandle.pop(key.fd)
            print("删掉之前用的socket")
        # if self.dictSocketSendHandle[sockHandle] == self.dictSocketSendedHandle[sockHandle]:#如果待发送数据总长度等于已发送数据总长度，那么就把socket改成读等待
        #     self.epollHandle.modify(sockHandle, select.EPOLLIN)
        #     self.dictSocketSendHandle.pop(sockHandle)
        #     self.dictSocketSendedHandle.pop(sockHandle)
        #     print("删掉之前用的socket")
        # else:
        #     m = strings[self.dictSocketSendedHandle[sockHandle]:]
        #     # print("mmmmmmmmmmmm", m)
        #     le = client.send(m)
        #     print("本次发送数据量:", le)
        #     self.dictSocketSendedHandle[sockHandle] = self.dictSocketSendedHandle[sockHandle] + le
        #     print("已发送数据总量：", self.dictSocketSendedHandle[sockHandle])
        #
        #     if self.dictSocketSendHandle[sockHandle] == self.dictSocketSendedHandle[sockHandle]:  # 如果待发送数据总长度等于已发送数据总长度，那么就把socket改成读等待
        #         self.epollHandle.modify(sockHandle, select.EPOLLIN)
        #         self.dictSocketSendHandle.pop(sockHandle)
        #         self.dictSocketSendedHandle.pop(sockHandle)
        #         print("删掉之前用的socket已经发送的句柄信息")
        # print("已发送数据总长度：", sendLen)

        # if not self.dictSocketShakeHandStatus[key.fd]:
        #     dictData = self.dictSocketShakeHandKey[key.fd]
        #     # print("key", dictData["Sec-WebSocket-Key"])
        #     keyStr = dictData["Sec-WebSocket-Key"] + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
        #     # print("**********,", key)
        #     sha1 = hashlib.sha1()
        #     sha1.update(str.strip(keyStr).encode("utf-8"))
        #     ser_key = sha1.digest()
        #     # print("sha1", ser_key)
        #     base64str = base64.b64encode(ser_key).decode("utf-8")
        #     # print("base64", base64str)
        #     strings = "HTTP/1.1 101 Switching Protocol\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept:%s\r\n\r\n" % (base64str)
        #     # print(strings)
        #     strings = strings.encode("utf-8")
        #     if not self.dictSocketShakeHandStatus[key.fd]:
        #         self.dictSocketShakeHandStatus[key.fd] = True
        #     self.selector.modify(key.fd, EVENT_READ, self.readable)
        # else:
        #     print(len(self.resDict[key.fd]["string"]))
        #     strings = '{"status":"success", "message":"信息接收成功"}'
        #     if not key.fd in self.dictSocketSendHandle:
        #         # if filename == "":
        #         strings = json.dumps(strings)
        #         strings = self.packWebSocketData(strings.encode("utf-8"))  # 要发送的数据
        #         # else:
        #         #     data = b""
        #         #     with open(filename, "rb") as fd:
        #         #         data += fd.read()
        #         #     print("要发送二进制文件总大小:", len(data))
        #         #     strings = self.packWebSocketData(data)
        #         #     print("要发送打包后的数据大小", len(strings))
        #
        # if not key.fd in self.dictSocketSendHandle:
        #     self.dictSocketSendHandle[key.fd] = len(strings)  # 要发送数据的总长度
        # if not key.fd in self.dictSocketSendedHandle:
        #     self.dictSocketSendedHandle[key.fd] = 0  # 已发送数据总长度
        # if not self.dictSocketShakeHandStatus[key.fd]:
        #     self.dictSocketShakeHandStatus[key.fd] = True
        # # print("要发送数据总长度：", totalLen)
        # print("要发送的数据为：", strings)
        # if not key.fd in self.dictSocketSendHandle:
        #     self.dictSocketSendHandle[key.fd] = len(strings)  # 要发送数据的总长度
        # if not key.fd in self.dictSocketSendedHandle:
        #     self.dictSocketSendedHandle[key.fd] = 0  # 已发送数据总长度
        #
        # while self.dictSocketSendedHandle[key.fd] < self.dictSocketSendHandle[key.fd]:
        #     try:
        #         m = strings[self.dictSocketSendedHandle[key.fd]:]
        #         le = self.dictSocketHandle[key.fd].send(m)
        #         print("本次发送数据量:", le)
        #         self.dictSocketSendedHandle[key.fd] = self.dictSocketSendedHandle[key.fd] + le
        #         print("已发送数据总量：", self.dictSocketSendedHandle[key.fd])
        #
        #     except IOError as err:
        #         if err.errno == 32:  # 如果对端关闭，还去发送会产生，"Broken pipe"的错误  错误码为32
        #             # print("客户端已经关闭连接，服务端等待关闭......")
        #             pass
        #         if err.errno == 11:
        #             print("写入缓冲区已满")
        #             continue
        #         else:
        #             print("服务端发送数据未知错误")
        # else:
        #     self.selector.modify(key.fd, EVENT_READ, self.readable)
        #     self.dictSocketSendHandle.pop(key.fd)
        #     self.dictSocketSendedHandle.pop(key.fd)
        #     print("删掉之前用的socket")



    def parseHeadData(self, head):
        opcode = head & 0x0f  # 与00001111进行与运算，其实就是取后四位的数据
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

    def boardCast(self, sock):#广播到所有的连接上
        for everySock in self.dictSocketHandle.values():
            if not sock == everySock:
                self.dictSocketHandleSendContent[everySock.fileno()] = '{"status":"success", "message":"have ' + str(len(self.dictSocketHandle)) + ' socket connect"}'
                self.selector.modify(sock, EVENT_WRITE, self.writeable)

if __name__ == "__main__":
    webSocketServer("0.0.0.0", 8089)