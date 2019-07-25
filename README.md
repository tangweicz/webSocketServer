# webSocketServer
python3 webSocketServer

从websocket连接到服务器端相应的流程（遵从websocket的协议）\
收发数据，全都是用阻塞的模式，并且设置了超时时间，每有一个新连接进来都会对其余的连接进行广播告知目前有多少个新连接在线上\
普通文字接收，接收并拼接已经收到的数据，然后解析数据，当数据能被正常json.loads，并且解析到的status为1，证明数据接收完毕，这个规则需要自己定义并处理！\
大、小文件接收，已经实现。\

因为是使用的epoll方式，所以该程序只能使用在linux平台，不兼容windows、mac os！\

使用方法：
    服务器端运行：python webSocketServerUseEpoll.py即运行了本地的socket，等待连接\
    使用本地的index.html文件，进行交互\
