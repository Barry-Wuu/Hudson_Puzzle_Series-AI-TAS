#!/usr/bin/env python3
"""RSP 中间人代理：让 gdb 15 能连 DeSmuME 0.9.11 老旧 stub。

拦截 gdb 的 vMustReplyEmpty 探测（stub 会回 'timeout' 字符串导致 gdb 退出），
由代理直接回 '+$#00'（ACK + 空响应）。其余包原样双向转发。
"""
import socket
import threading
import time

LISTEN = ("127.0.0.1", 1235)
UPSTREAM = ("127.0.0.1", 1234)


def find_packets(buf):
    """从字节流中切出完整 $...#xx 包，返回 (包列表, 剩余字节)。"""
    pkts = []
    while True:
        i = buf.find(b"$")
        if i < 0:
            return pkts, b""
        j = buf.find(b"#", i)
        if j < 0 or len(buf) < j + 3:
            return pkts, buf[i:]
        pkts.append(buf[i : j + 3 :])
        buf = buf[j + 3 :]


def pkt_data(p):
    """包 -> 数据部分（去 $ 和 #xx）。"""
    return p[1 : p.rfind(b"#")]


# 探测命令 -> 代理直接构造的响应（数据部分）
FAKE_RESP = {
    b"vMustReplyEmpty": b"",
    b"qTStatus": b"",
    b"qTStatusV": b"",
    b"qAttached": b"1",
    b"qOffsets": b"Text=0;Data=0;Bss=0",
    b"qC": b"QC0",
    b"qfThreadInfo": b"m0",
    b"qsThreadInfo": b"l",
    b"qSymbol::": b"OK",
    b"qXfer:features:read:": b"l<m>",
}


def fake_for(data):
    """若 data 是需要伪造响应的探测命令，返回响应数据；否则 None。"""
    for k, v in FAKE_RESP.items():
        if data.startswith(k):
            return v
    if data.startswith(b"qXfer:"):
        return b"l<m>"
    return None


class Pipe(threading.Thread):
    def __init__(self, src, dst, name, intercept=False):
        super().__init__(daemon=True)
        self.src, self.dst, self.name = src, dst, name
        self.intercept = intercept
        self.buf = b""

    def run(self):
        while True:
            try:
                d = self.src.recv(65536)
            except Exception:
                break
            if not d:
                break
            if self.intercept:
                # gdb -> stub 方向：拦截探测命令，其余原样
                self.buf += d
                pkts, rest = find_packets(self.buf)
                self.buf = rest
                for p in pkts:
                    data = pkt_data(p)
                    # 立即回 ACK（DeSmuME stub 不回 ACK，gdb 会干等）
                    self.src.sendall(b"+")
                    fake = fake_for(data)
                    if fake is not None:
                        cs = sum(fake) & 0xFF
                        resp = b"$" + fake + b"#" + ("%02x" % cs).encode()
                        self.dst.sendall(resp)
                    else:
                        self.dst.sendall(p)
            else:
                # stub -> gdb 方向：清洗非法 'timeout' 响应
                d2 = d.replace(b"$timeout#a6", b"$#00")
                self.dst.sendall(d2)


def handle(client):
    up = socket.create_connection(UPSTREAM, timeout=30)
    p1 = Pipe(client, up, "gdb->stub", intercept=True)
    p2 = Pipe(up, client, "stub->gdb")
    p1.start(); p2.start()
    p1.join(3600); p2.join(3600)


def main():
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(LISTEN)
    srv.listen(5)
    print("proxy 1235 -> 1234", flush=True)
    while True:
        c, _ = srv.accept()
        threading.Thread(target=handle, args=(c,), daemon=True).start()


if __name__ == "__main__":
    main()
