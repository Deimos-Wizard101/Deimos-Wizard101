import json
import struct

from enum import IntEnum

import sys

if sys.platform == "win32":
    import win32pipe, win32file
else:
    import os
    import socket


discord_base_pipe_path = "\\\\?\\pipe\\discord-ipc-"
app_id = 1000159655357587566
rpc_version = 1


class Opcodes(IntEnum):
	Handshake = 0
	Frame = 1
	Close = 2
	Ping = 3
	Pong = 4


def _linux_ipc_dirs():
	# Discord's IPC socket lives in the runtime dir, with flatpak/snap variants.
	base = os.environ.get("XDG_RUNTIME_DIR") or os.environ.get("TMPDIR") or "/tmp"
	return [
		base,
		os.path.join(base, "app", "com.discordapp.Discord"),
		os.path.join(base, "snap.discord"),
	]


def connect():
	if sys.platform == "win32":
		handle = None
		for i in range(10):
			path = discord_base_pipe_path + str(i)
			try:
				handle = win32file.CreateFile(
					path,
					win32file.GENERIC_READ | win32file.GENERIC_WRITE,
					0,
					None,
					win32file.OPEN_EXISTING,
					0,
					None
				)
				win32pipe.SetNamedPipeHandleState(handle, win32pipe.PIPE_READMODE_BYTE, None, None)
				break
			except:
				pass
		return handle
	# Linux: AF_UNIX socket at <runtime>/discord-ipc-<i>
	for d in _linux_ipc_dirs():
		for i in range(10):
			path = os.path.join(d, f"discord-ipc-{i}")
			if not os.path.exists(path):
				continue
			try:
				sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
				sock.connect(path)
				return sock
			except OSError:
				pass
	return None

def close(handle):
	if sys.platform == "win32":
		win32file.CloseHandle(handle)
	else:
		handle.close()

def serialize_message(opcode, jsondata) -> bytearray:
	result = bytearray()
	data = json.dumps(jsondata).encode()

	result += struct.pack("<L", int(opcode))
	result += struct.pack("<L", len(data))
	result += data

	return result

def parse_message(msg):
	opcode = Opcodes(struct.unpack("<L", msg[0:4])[0])
	data_len = struct.unpack("<L", msg[4:8])[0]
	data = msg[8:8+data_len].decode()
	return json.loads(data)

def send(handle, data):
	if sys.platform == "win32":
		win32file.WriteFile(handle, data)
	else:
		handle.sendall(data)

def recv(handle):
	if sys.platform == "win32":
		data = win32file.ReadFile(handle, 65536)
		if data[0] == 0:
			return parse_message(data[1])
	else:
		raw = handle.recv(65536)
		if raw:
			return parse_message(raw)

shake = serialize_message(
	Opcodes.Handshake,
	{
		"v": rpc_version,
		"client_id": str(app_id)
	}
)


def get_discord_user():
	"""Return the logged-in Discord user dict (id, username, global_name, ...) read
	from the local Discord IPC pipe, or None if Discord isn't running / on any error.

	Blocking named-pipe I/O — call off the main thread (e.g. via asyncio.to_thread).
	"""
	handle = None
	try:
		handle = connect()
		if handle is None:
			return None
		send(handle, shake)
		resp = recv(handle)
		return resp["data"]["user"]
	except Exception:
		return None
	finally:
		if handle is not None:
			try:
				close(handle)
			except Exception:
				pass


_cached_username = None


def get_discord_username():
	"""Best-effort current Discord username (the unique handle, falling back to the
	display name), or None if it can't be determined.

	The first success is cached for the process lifetime: Discord throttles rapid
	back-to-back IPC handshakes, and the username is stable within a session.
	"""
	global _cached_username
	if _cached_username is not None:
		return _cached_username
	user = get_discord_user()
	if not user:
		return None
	_cached_username = user.get("username") or user.get("global_name")
	return _cached_username
