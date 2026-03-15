import struct

from io import BytesIO


# Made using Niftools's nif reference: https://github.com/niftools/nifxml


# TODO: finish
class NifMap:
    def __init__(self, data):
        """
        doc
        """
        self._bytes = BytesIO(data)
        self._read_header()

    @staticmethod
    def _read_file_bytes(path) -> BytesIO:
        with open(path, "rb") as fp:
            return BytesIO(fp.read())

    def _read_sized_string(self):
        length = struct.unpack("<I", self._bytes.read(4))[0]
        value = self._bytes.read(length).decode("UTF-8")
        return value

    # This is probably fast enough to not be async
    def _read_header(self):
        # Header string should be within the first 100 bytes
        tmp_find_bytes = self._bytes.read(100)
        self._bytes.seek(0)
        # end of header string "\n"; +1 so it's included
        end_header_string_pos = tmp_find_bytes.find(b"\x0A") + 1
        self.header_string = self._bytes.read(end_header_string_pos).decode("UTF-8")[
            :-1
        ]

        self.format_version = self.header_string.split(" ")[-1]

        # no idea what these 4 bytes are
        self._bytes.seek(self._bytes.tell() + 4)
        self.is_little_endian = struct.unpack("<?", self._bytes.read(1))[0]
        self.user_version = struct.unpack("<I", self._bytes.read(4))[0]
        self.block_number = struct.unpack("<I", self._bytes.read(4))[0]
        self.block_type_number = struct.unpack("<H", self._bytes.read(2))[0]

        self.types = []
        for idx in range(self.block_type_number):
            self.types.append(self._read_sized_string())

        self.type_indexs = []
        for idx in range(self.block_number):
            type_num = struct.unpack("<h", self._bytes.read(2))[0]
            self.type_indexs.append(self.types[type_num])

        self.size_map = []
        for idx in range(self.block_number):
            self.size_map.append(struct.unpack("<I", self._bytes.read(4))[0])

        self.string_num = struct.unpack("<I", self._bytes.read(4))[0]

        self.max_string_length = struct.unpack("<I", self._bytes.read(4))[0]

        self.strings = []
        for idx in range(self.string_num):
            self.strings.append(self._read_sized_string())

        self.group_num = struct.unpack("<I", self._bytes.read(4))[0]

        if self.group_num != 0:
            raise RuntimeError("Group num is not zero; please report error")

        self.header_end_pos = self._bytes.tell()
