#!/Library/Frameworks/Python.framework/Versions/3.6/bin/python3.6
#! -*- coding:utf-8 -*-

import socket,json
# def parseWebSocketData(info):  # 解析头部数据，值要我们的消息主体，剔除掉header头信息
#     payload_len = info[1] & 127
#     if payload_len == 126:
#         # 数据头部延伸的长度
#         extend_payload_len = info[2:4]
#         # 加密的4个字节
#         mask = info[4:8]
#         decoded = info[8:]  # 数据
#     elif payload_len == 127:
#         extend_payload_len = info[2:10]
#         mask = info[10:14]
#         decoded = info[14:]
#     else:
#         extend_payload_len = None
#         mask = info[2:6]
#         decoded = info[6:]
#     bytes_list = bytearray()
#     for i in range(len(decoded)):
#         chunk = decoded[i] ^ mask[i % 4]
#         bytes_list.append(chunk)
#
#     print(bytes_list)
#     body = str(bytes_list, encoding='utf-8')
#     return body

if __name__ == "__main__":
    # strs = ''
    # print(json.loads(strs))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    bufsize = sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
    print(bufsize)
