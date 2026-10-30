#!/usr/bin/env python3
"""GDB Remote Serial Protocol 最小客户端（DeSmuME arm9gdb stub）。"""
import socket
import time


class RSP:
    def __init__(self, host="127.0.0.1", port=1234, timeout=10.0):
        self.s = socket.create_connection((host, port), timeout=timeout)
        self.s.settimeout(timeout)
        self.buf = b""

    def close(self):
        try:
            self.s.close()
        except Exception:
            pass

    def _recv1(self):
        while True:
            if self.buf:
                c = self.buf[:1]
                self.buf = self.buf[1:]
                return c
            d = self.s.recv(4096)
            if not d:
                raise EOFError("rsp closed")
            self.buf = d

    def _recv_pkt(self):
        # 跳过 + - 和 $ 外的输出，读一个完整 $...#xx 包
        while True:
            c = self._recv1()
            if c == b"$":
                break
        data = b""
        while True:
            c = self._recv1()
            if c == b"#":
                break
            if c == b"}":  # 转义
                c2 = self._recv1()
                data += bytes([c2[0] ^ 0x20])
            else:
                data += c
        cs = self._recv1() + self._recv1()
        self.s.sendall(b"+")
        return data

    def cmd(self, data, timeout=10.0):
        """发命令收一个响应包。data: bytes。"""
        self.s.settimeout(timeout)
        cs = sum(data) & 0xFF
        pkt = b"$" + data + b"#" + ("%02x" % cs).encode()
        self.s.sendall(pkt)
        # ACK
        while True:
            c = self._recv1()
            if c == b"+":
                break
            if c == b"-":
                self.s.sendall(pkt)
        return self._recv_pkt()

    def read_mem(self, addr, length):
        r = self.cmd(("m%x,%x" % (addr, length)).encode())
        if r.startswith(b"E"):
            raise RuntimeError("read_mem error: " + r.decode())
        return _unhex_rle(r.decode())

    def write_mem(self, addr, data: bytes):
        h = data.hex().encode()
        r = self.cmd(("M%x,%x:" % (addr, len(data))).encode() + h)
        if r.startswith(b"E"):
            raise RuntimeError("write_mem error: " + r.decode())
        return r

    def cont(self):
        # 'c' 无响应回来（CPU 跑），后续命令需先 Ctrl-C 打断
        cs = 0x63
        self.s.sendall(b"$c#63")
        while True:
            c = self._recv1()
            if c == b"+":
                break
        time.sleep(0.02)

    def stop(self):
        self.s.sendall(b"\x03")
        return self._recv_pkt()

    def halt_cmd(self, data, timeout=10.0):
        """停 CPU -> 发命令 -> 继续。用于运行中读写内存。"""
        self.stop()
        return self.cmd(data, timeout=timeout)

    def rd(self, addr, length):
        return self.halt_cmd(("m%x,%x" % (addr, length)).encode())

    def wr(self, addr, data: bytes):
        h = data.hex().encode()
        r = self.halt_cmd(("M%x,%x:" % (addr, len(data))).encode() + h)
        if r.startswith(b"E"):
            raise RuntimeError("write error: " + r.decode())
        return r


def _unhex_rle(s):
    """解 RSP hex（含 '*' RLE）。"""
    out = bytearray()
    i = 0
    while i < len(s):
        c = s[i]
        if c == "*" and out and i + 1 < len(s):
            rep = int(s[i + 1], 16) - 1
            out += bytes([out[-1]]) * rep
            i += 2
        else:
            out.append(int(s[i : i + 2], 16))
            i += 2
    return bytes(out)


if __name__ == "__main__":
    r = RSP()
    print("connected")
    print("stop reason:", r.stop())
    # 读 ARM9 PC 验证（寄存器 15 = PC，g 命令全寄存器；简化读 0x04000006 VCOUNT 验证可读）
    v = r.cmd(b"m4000006,1")
    print("VCOUNT raw:", v)
    print("VCOUNT:", r.read_mem(0x04000006, 1)[0])
    r.close()
