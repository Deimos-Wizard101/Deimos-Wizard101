import asyncio
import functools
import regex
import struct
import sys
from typing import Any, Union

import pefile
import pymem
import pymem.exception
import pymem.process
import pymem.ressources.structure

from wizwalker import (
    AddressOutOfRange,
    ClientClosedError,
    MemoryReadError,
    MemoryWriteError,
    PatternFailed,
    PatternMultipleResults,
    Primitive,
    utils,
)


class MemoryReader:
    """
    Represents anything that needs to read/write from/to memory
    """

    def __init__(self, process: pymem.Pymem):
        self.process = process

        self._symbol_table = {}

    # TODO: 2.0 make this a property
    def is_running(self) -> bool:
        """
        If the process we're reading/writing to/from is running
        """
        return utils.check_if_process_running(self.process.process_handle)

    @staticmethod
    async def run_in_executor(func, *args, **kwargs):
        """
        Run a function within an executor

        Args:
            func: The function to run
            args: Args to pass to the function
            kwargs: Kwargs to pass to the function
        """
        loop = asyncio.get_event_loop()
        function = functools.partial(func, *args, **kwargs)

        return await loop.run_in_executor(None, function)

    def _get_symbols(self, file_path: str, *, force_reload: bool = False):
        if (dll_table := self._symbol_table.get(file_path)) and not force_reload:
            return dll_table

        # exe_path = utils.get_wiz_install() / "Bin" / "WizardGraphicalClient.exe"
        pe = pefile.PE(file_path)

        symbols = {}

        for exp in pe.DIRECTORY_ENTRY_EXPORT.symbols:
            if exp.name:
                symbols[exp.name.decode()] = exp.address

            else:
                symbols[f"Ordinal {exp.ordinal}"] = exp.address

        self._symbol_table[file_path] = symbols
        return symbols

    @staticmethod
    def _scan_page_return_all(handle, address, pattern):
        mbi = pymem.memory.virtual_query(handle, address)
        next_region = mbi.BaseAddress + mbi.RegionSize
        allowed_protections = [
            pymem.ressources.structure.MEMORY_PROTECTION.PAGE_EXECUTE_READ,
            pymem.ressources.structure.MEMORY_PROTECTION.PAGE_EXECUTE_READWRITE,
            pymem.ressources.structure.MEMORY_PROTECTION.PAGE_READWRITE,
            pymem.ressources.structure.MEMORY_PROTECTION.PAGE_READONLY,
        ]
        if (
            mbi.state != pymem.ressources.structure.MEMORY_STATE.MEM_COMMIT
            or mbi.protect not in allowed_protections
        ):
            return next_region, None

        page_bytes = pymem.memory.read_bytes(handle, address, mbi.RegionSize)

        found = []

        for match in regex.finditer(pattern, page_bytes, regex.DOTALL):
            found_address = address + match.span()[0]
            found.append(found_address)

        return next_region, found

    def _scan_all(
        self,
        handle: int,
        pattern: bytes,
        return_multiple: bool = False,
    ):
        next_region = 0

        found = []
        while next_region < 0x7FFFFFFF0000:
            next_region, page_found = self._scan_page_return_all(
                handle, next_region, pattern
            )
            if page_found:
                found += page_found

            if not return_multiple and found:
                break

        return found

    def _scan_entire_module(self, handle, module, pattern):
        base_address = module.lpBaseOfDll
        max_address = module.lpBaseOfDll + module.SizeOfImage
        page_address = base_address

        found = []
        while page_address < max_address:
            page_address, page_found = self._scan_page_return_all(
                handle, page_address, pattern
            )
            if page_found:
                found += page_found

        return found

    async def pattern_scan(
        self, pattern: bytes, *, module: str = None, return_multiple: bool = False
    ) -> Union[list, int]:
        """
        Scan for a pattern

        Args:
            pattern: The byte pattern to search for
            module: What module to search or None to search all
            return_multiple: If multiple results should be returned

        Raises:
            PatternFailed: If the pattern returned no results
            PatternMultipleResults: If the pattern returned multiple results and return_multple is False

        Returns:
            A list of results if return_multple is True otherwise one result
        """
        if module:
            module_object = pymem.process.module_from_name(self.process.process_handle, module)

            if module_object is None:
                raise ValueError(f"{module} module not found.")

            # this can take a long time to run when collecting multiple results
            # so must be run in an executor
            found_addresses = await self.run_in_executor(
                self._scan_entire_module,
                self.process.process_handle,
                module_object,
                pattern,
            )

        else:
            found_addresses = await self.run_in_executor(
                self._scan_all,
                self.process.process_handle,
                pattern,
                return_multiple,
            )

        if (found_length := len(found_addresses)) == 0:
            raise PatternFailed(pattern)
        elif found_length > 1 and not return_multiple:
            raise PatternMultipleResults(f"Got {found_length} results for {pattern}")
        elif return_multiple:
            return found_addresses
        else:
            return found_addresses[0]

    async def get_address_from_symbol(
        self,
        module_name: str,
        symbol_name: str,
        *,
        module_dir: str = None,
        force_reload: bool = False,
    ) -> int:
        """
        Get an address from a module using its symbol

        Args:
            module_name: Name of the module
            symbol_name: Name of the symbol
            module_dir: Dir the module is within
            force_reload: Force export table reload

        Returns:
            The address of the symbol in memory

        Raises:
            ValueError: No symbol/module with that name
        """
        module = pymem.process.module_from_name(
            self.process.process_handle, module_name
        )
        if module is None:
            raise ValueError(f"No module named {module_name}")

        if sys.platform != "win32" and module_dir is None:
            # On Linux the DLL is a Wine PE loaded from the Proton tree, not a
            # Windows system dir (get_system_directory is a stub here). Resolve
            # symbols from the exact file backing the loaded mapping so the
            # export RVAs match what is actually in memory.
            file_path = self._backing_file_for(module.lpBaseOfDll)
            if file_path is None:
                raise ValueError(f"No backing file for module {module_name}")
        else:
            if not module_dir:
                module_dir = utils.get_system_directory()
            file_path = module_dir / module_name
            if not file_path.exists():
                raise ValueError(f"No module named {module_name}")

        symbols = await self.run_in_executor(
            self._get_symbols, file_path, force_reload=force_reload
        )

        if not (symbol := symbols.get(symbol_name)):
            raise ValueError(f"No symbol named {symbol_name} in module {module_name}")

        return module.lpBaseOfDll + symbol

    def _backing_file_for(self, address: int):
        """The on-disk file backing the mapping containing `address` in the
        target, from /proc/<pid>/maps — lets Linux resolve a Wine DLL's symbols
        from the exact PE image the process loaded."""
        pid = self.process.process_id
        try:
            with open(f"/proc/{pid}/maps") as f:
                for line in f:
                    parts = line.split(maxsplit=5)
                    if len(parts) < 6:
                        continue
                    lo, _, hi = parts[0].partition("-")
                    if int(lo, 16) <= address < int(hi, 16):
                        path = parts[5].strip()
                        return path if path.startswith("/") else None
        except OSError:
            pass
        return None

    async def allocate(self, size: int) -> int:
        """
        Allocate some bytes

        Args:
            size: The number of bytes to allocate

        Returns:
            The allocated address
        """
        return self.process.allocate(size)

    async def free(self, address: int):
        """
        Free some bytes

        Args:
             address: The address to free
        """
        self.process.free(address)

    # TODO: figure out how params works
    async def start_thread(self, address: int):
        """
        Start a thread at an address

        Args:
            address: The address to start the thread at
        """
        await self.run_in_executor(self.process.start_thread, address)

    async def read_bytes(self, address: int, size: int) -> bytes:
        """
        Read some bytes from memory

        Args:
            address: The address to read from
            size: The number of bytes to read

        Raises:
            ClientClosedError: If the client is closed
            MemoryReadError: If there was an error reading memory
            AddressOutOfRange: If the addrress is out of bounds
        """
        if not 0 < address <= 0x7FFFFFFFFFFFFFFF:
            raise AddressOutOfRange(address)

        try:
            return self.process.read_bytes(address, size)
        except pymem.exception.MemoryReadError:
            # we don't want to run is running for every read
            # so we just check after we error
            if not self.is_running():
                raise ClientClosedError()
            else:
                raise MemoryReadError(address)

    async def write_bytes(self, address: int, value: bytes):
        """
        Write bytes to memory

        Args:
            address: The address to write to
            value: The bytes to write
        """
        size = len(value)

        try:
            self.process.write_bytes(address, value, size)
        except pymem.exception.MemoryWriteError:
            # see read_bytes
            if not self.is_running():
                raise ClientClosedError()
            else:
                raise MemoryWriteError(address)

    async def write_code(self, address: int, value: bytes):
        """
        Write bytes into EXECUTABLE memory so the patch takes effect.

        On macOS an inline patch must be applied as a guest W^X write — Rosetta
        ignores an external write to already-translated code, so a plain write_bytes
        to a hook site never fires. zhol.write_code performs the
        VirtualProtect(RW) -> write -> VirtualProtect(RX) -> FlushInstructionCache
        sequence as guest code via the one-shot RPC. On Windows/Linux this is an
        ordinary memory write.
        """
        if sys.platform == "darwin":
            await self.run_in_executor(
                self.process.process_handle.write_code, address, value
            )
        else:
            await self.write_bytes(address, value)

    async def allocate_near(self, size: int, near: int) -> int:
        """
        Allocate executable memory reachable by a 5-byte E9 rel32 jump from ``near``
        (a hook's patch site). On macOS the cave is placed within ±2 GiB of ``near``
        so the jump reaches; elsewhere ``near`` is advisory.
        """
        if sys.platform == "darwin":
            return self.process.process_handle.allocate_near(size, near)
        return await self.allocate(size)

    async def read_typed(self, address: int, data_type: Primitive) -> Any:
        """
        Read typed bytes from memory

        Args:
            address: The address to read from
            data_type: The type to read (defined in constants)

        Returns:
            The converted data type
        """
        data = await self.read_bytes(address, data_type.value.size)
        return data_type.value.unpack(data)[0]

    async def write_typed(self, address: int, value: Any, data_type: Primitive):
        """
        Write typed bytes to memory

        Args:
            address: The address to write to
            value: The value to convert and then write
            data_type: The data type to convert to
        """
        packed_data = data_type.value.pack(value)
        await self.write_bytes(address, packed_data)
