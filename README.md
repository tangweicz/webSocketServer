# webSocketServer
python3 webSocketServer

从websocket连接到服务器端相应的流程\
客户端需要连接到服务端，需要先发送握手信息(类似一个http头请求)，服务器端接收到头信息，解析头信息并得到一个Sec-WebSocket-Key，然后拿这个Sec-WebSocket-Key做数据处理之后返回给客户端，客户端接收到数据，握手成功\
收发数据，全都是用非阻塞的模式，每有一个新连接进来都会对其余的连接进行广播告知目前有多少个新连接在线上\


本计划写一个网页小游戏的，目前仅仅只实现了websocket的消息接收与发送，等有时间了再去调整代码，做成一个小游戏。\
因为是使用的epoll方式，所以该程序只能使用在linux平台，不兼容windows、mac os！\
