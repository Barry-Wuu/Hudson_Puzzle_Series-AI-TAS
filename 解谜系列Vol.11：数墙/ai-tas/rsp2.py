#!/usr/bin/env python3
"""DeSmuME arm9gdb 简化客户端：stalled=1（停止）状态下读内存。

重启 DeSmuME --arm9gdb=PORT 后 stub 初始 stalled=1，'?' -> S02，'m' 服务。
"""
import socket
import time


class G:
    def __init__(self, port=1234, host="127.0.0.1", timeout=15.0):
        self.s = socket.create_connection((host, port), timeout=timeout)
        self.s.settimeout(timeout)
        self.buf = b""
        time.sleep(0.2)
        # 确认停止状态
        r = self.cmd(b"?")
        if b"S02" not in r and b"S05" not in r:
            raise RuntimeError("stub not stalled: " + r.decode(errors="replace"))

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
            d = self.s.recv(65536)
            if not d:
                raise EOFError
            self.buf = d

    def _recv_pkt(self):
        while True:
            c = self._recv1()
            if c == b"$":
                break
        data = b""
        while True:
            c = self._recv1()
            if c == b"#":
                break
            data += c
        self._recv1(); self._recv1()  # checksum
        return data

    def cmd(self, data, timeout=15.0):
        self.s.settimeout(timeout)
        cs = sum(data) & 0xFF
        pkt = b"$" + data + b"#" + ("%02x" % cs).encode()
        self.s.sendall(pkt)
        # ACK（ stall 状态 stub 会 ACK）
        while True:
            c = self._recv1()
            if c == b"+":
                break
        return self._recv_pkt()

    def read(self, addr, length, chunk=2048):
        out = bytearray()
        while length > 0:
            n = min(chunk, length)
            r = self.cmd(("m%x,%x" % (addr, n)).encode())
            if r.startswith(b"E"):
                raise RuntimeError("read err " + r.decode())
            out += _unhex(r.decode())
            addr += n
            length -= n
        return bytes(out)

    def write(self, addr, data: bytes):
        r = self.cmd(("M%x,%x:" % (addr, len(data))).encode() + data.hex().encode())
        if r.startswith(b"E"):
            raise RuntimeError("write err " + r.decode())
        return r


def _unhex(s):
    out = bytearray()
    i = 0
    while i < len(s):
        c = s[i]
        if c == "*" and out:
            out += bytes([out[-1]]) * (int(s[i + 1], 16) - 1)
            i += 2
        else:
            out.append(int(s[i : i + 2], 16))
            i += 2
    return bytes(out)


if __name__ == "__main__":
    g = G()
    print("VCOUNT:", g.read(0x04000006, 1).hex())
    print("IPC80:", g.read(0x027FFC80, 16).hex())
    g.close()
