import io
import zlib
import struct
import bpy
from PIL import Image


def bin2dds(binary, width=512, height=512, type="DXT5"):
    """
        Convert binary textures to DDS format.

        Decompiled from AO Texture Viewer.

        NOTE: It is not fully correct, but PIL library can handle it. 
    """
    with io.BytesIO(binary) as comp_stream, io.BytesIO(b'\x04\x00\x00\x12') as decomp_stream:
        comp_stream.read(2)
        decomp_stream.write(zlib.decompress(comp_stream.read(), -15))
        decomp_stream.seek(0)
        binary = decomp_stream.read()

    n7, n8 = struct.unpack('2i', binary[:8])
    iValue, iOffset, n10, n11 = 0, 0, 0, 0
    n7 += 1

    numArray, bufferArray = [0] * n7, [[0] * n8 * (4 ** (n7 - 1)) for _ in range(n7)]

    for j in range(n7 - 1, -1, -1):
        numArray[j] = n8
        for k in range(n8):
            bufferArray[j][k] = binary[8 + iOffset + k]
        iOffset += 8 + n8
        n8 *= 4

    length = len(bufferArray[0])
    buf1, buf5, buf6 = b'\xf3\x9c\xd3\x9c\xaa\xaa\xaa\xaa', b'\x49\x92\x24\x49\x92\x24', \
                       b'\xff\xff\xff\xff\xff\xff\xff\xff'
    buf3, buf4 = b'\x01\00\00\00\00\00\00\00', b'\x01\00\00\00\00\00\00\00'
    bufferArray2, bufferArray3 = [buf1, buf5, buf3, buf4], [buf6]
    n15, n16, n17, n18 = 0, 0, 0, 0

    while True:
        if n18 >= len(bufferArray):
            n10, n11 = width, height
            break
        n19 = 0
        while True:
            if (n19 >= len(bufferArray2)):
                n22 = 0
                while True:
                    if (n22 >= len(bufferArray3)):
                        n15 += numArray[n18] // 16
                        n18 += 1
                        break
                    n23 = 8 - len(bufferArray3[n22])
                    while True:
                        if n23 >= numArray[n18]:
                            n22 += 1
                            break
                        flag2 = True
                        n24 = 0
                        while True:
                            if n24 < len(bufferArray3[n22]):
                                if bufferArray[n18][n23 + n24] == bufferArray3[n22][n24]:
                                    n24 += 1
                                    continue
                                flag2 = False
                            if flag2:
                                n17 += 1
                            n23 += 16
                            break

                break

            n20 = 8 - len(bufferArray2[n19])
            while True:
                if n20 >= numArray[n18]:
                    n19 += 1
                    break
                flag = True
                n21 = 0
                while True:
                    if (n21 < len(bufferArray2[n19])):
                        if (bufferArray[n18][n20 + n21] == bufferArray2[n19][n21]):
                            n21 += 1
                            continue
                        flag = False
                    if flag:
                        n16 += 1
                    n20 += 16
                    break

    n32 = 128
    for k in range(n7):
        n32 += numArray[k]

    with io.BytesIO() as stream:
        stream.write(b'DDS |\x00\x00\x00')
        stream.write(b'\a\x10\n\x00')
        stream.write(struct.pack('3I', n11, n10, length))
        stream.write(b'\x00' * 4)
        stream.write(struct.pack('I', iValue))
        stream.write(b'Allods Blender Import ')
        stream.write(b'v0.1' + (b'\x00' * 6))
        stream.write(b'Elementarno' + (b'\x00' * 5))
        stream.write(b'\x04\x00\x00\x00' + bytes(type, 'utf-8') + (b'\x00' * 20) + b'\b\x10@\0')
        stream.write(b'\x00' * 16)

        for i in range(1):
            stream.write(bytes(bufferArray[i]))

        stream.seek(0)
        return stream.read()


class TextureData:
    def __init__(self, path, width=512, height=512, type="DXT5"):
        with open(path, 'rb') as reader:
            self.data = bin2dds(reader.read(), width=width, height=height, type=type)
        self.width = width
        self.height = height
        self.type = type

    def save_to(self, path):
        image = Image.open(io.BytesIO(self.data))
        image.save(path)
