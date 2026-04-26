use crate::errors::VaultError;
use std::ffi::c_void;
use std::thread;
use std::time::{Duration, Instant};
use windows::Win32::Foundation::{CloseHandle, HANDLE};
use windows::Win32::System::Diagnostics::Debug::{ReadProcessMemory, WriteProcessMemory};
use windows::Win32::System::Diagnostics::ToolHelp::{
    CreateToolhelp32Snapshot, Module32FirstW, Module32NextW, MODULEENTRY32W, TH32CS_SNAPMODULE,
};
use windows::Win32::System::Memory::{
    VirtualAllocEx, VirtualFreeEx, MEM_COMMIT, MEM_RELEASE, MEM_RESERVE,
    PAGE_EXECUTE_READWRITE, PAGE_READWRITE,
};
use windows::Win32::System::Threading::{
    OpenProcess, PROCESS_QUERY_INFORMATION, PROCESS_VM_OPERATION, PROCESS_VM_READ,
    PROCESS_VM_WRITE,
};
use windows::Win32::UI::WindowsAndMessaging::GetWindowThreadProcessId;

// Pattern to locate the game's internal command dispatcher.
// Matches: mov r9b,1 / xor r8d,r8d / lea rdx,[rbp-59h] / mov rcx,[rip+??]
const LOGIN_PATTERN: &[u8] = &[
    0x41, 0xB1, 0x01, 0x45, 0x33, 0xC0, 0x48, 0x8D, 0x55, 0xA7, 0x48, 0x8B, 0x0D,
];

// RootWindowHook injection-point pattern (wildcards = None).
// 7 ?? bytes | 48 8B 01 | 7 ?? bytes | FF 50 70 84
const HOOK_PATTERN: &[Option<u8>] = &[
    None, None, None, None, None, None, None,
    Some(0x48), Some(0x8B), Some(0x01),
    None, None, None, None, None, None, None,
    Some(0xFF), Some(0x50), Some(0x70), Some(0x84),
];
const HOOK_INSTR_LEN: usize = 7;

// ── Remote process helpers ─────────────────────────────────────────

struct RemoteProcess {
    handle: HANDLE,
}

impl RemoteProcess {
    fn open(pid: u32) -> Result<Self, VaultError> {
        let access = PROCESS_VM_OPERATION | PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_QUERY_INFORMATION;
        let handle = unsafe {
            OpenProcess(access, false, pid)
                .map_err(|e| VaultError::LoginFailed(format!("OpenProcess: {e}")))?
        };
        Ok(Self { handle })
    }

    fn read(&self, addr: u64, size: usize) -> Result<Vec<u8>, VaultError> {
        let mut buf = vec![0u8; size];
        unsafe {
            ReadProcessMemory(
                self.handle,
                addr as *const c_void,
                buf.as_mut_ptr() as *mut c_void,
                size,
                None,
            )
            .map_err(|e| VaultError::LoginFailed(format!("ReadProcessMemory @ {addr:#x}: {e}")))?;
        }
        Ok(buf)
    }

    fn write(&self, addr: u64, data: &[u8]) -> Result<(), VaultError> {
        unsafe {
            WriteProcessMemory(
                self.handle,
                addr as *const c_void,
                data.as_ptr() as *const c_void,
                data.len(),
                None,
            )
            .map_err(|e| VaultError::LoginFailed(format!("WriteProcessMemory @ {addr:#x}: {e}")))?;
        }
        Ok(())
    }

    fn alloc(&self, size: usize, executable: bool) -> Result<u64, VaultError> {
        let protect = if executable { PAGE_EXECUTE_READWRITE } else { PAGE_READWRITE };
        let ptr = unsafe {
            VirtualAllocEx(
                self.handle,
                None,
                size,
                MEM_COMMIT | MEM_RESERVE,
                protect,
            )
        };
        if ptr.is_null() {
            return Err(VaultError::LoginFailed("VirtualAllocEx returned NULL".into()));
        }
        Ok(ptr as u64)
    }

    /// Allocate memory within ±2 GB of `near` so a rel32 jump can reach it.
    fn alloc_near(&self, near: u64, size: usize) -> Result<u64, VaultError> {
        let granularity = 0x10000u64; // Windows allocation granularity
        let max_range = 0x7FFF_0000u64; // ~2 GB

        for offset in (granularity..max_range).step_by(granularity as usize) {
            for &dir in &[1i64, -1i64] {
                let candidate = (near as i64 + dir * offset as i64) as u64;
                let candidate = candidate & !(granularity - 1);
                let ptr = unsafe {
                    VirtualAllocEx(
                        self.handle,
                        Some(candidate as *const c_void),
                        size,
                        MEM_COMMIT | MEM_RESERVE,
                        PAGE_EXECUTE_READWRITE,
                    )
                };
                if !ptr.is_null() {
                    return Ok(ptr as u64);
                }
            }
        }
        Err(VaultError::LoginFailed(
            "Failed to allocate executable memory within jump range".into(),
        ))
    }

    fn free(&self, addr: u64) -> Result<(), VaultError> {
        unsafe {
            VirtualFreeEx(self.handle, addr as *mut c_void, 0, MEM_RELEASE)
                .map_err(|e| VaultError::LoginFailed(format!("VirtualFreeEx: {e}")))?;
        }
        Ok(())
    }
}

impl Drop for RemoteProcess {
    fn drop(&mut self) {
        unsafe { let _ = CloseHandle(self.handle); }
    }
}

// ── Module enumeration ─────────────────────────────────────────────

/// Returns (base_address, module_size) for the named module.
fn find_module(pid: u32, name: &str) -> Result<(u64, u32), VaultError> {
    let name_lower = name.to_lowercase();
    unsafe {
        let snap = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, pid)
            .map_err(|e| VaultError::LoginFailed(format!("CreateToolhelp32Snapshot: {e}")))?;

        let mut entry: MODULEENTRY32W = std::mem::zeroed();
        entry.dwSize = std::mem::size_of::<MODULEENTRY32W>() as u32;

        if Module32FirstW(snap, &mut entry).is_ok() {
            loop {
                let mod_name = String::from_utf16_lossy(
                    &entry.szModule[..entry.szModule.iter().position(|&c| c == 0).unwrap_or(256)],
                );
                if mod_name.to_lowercase() == name_lower {
                    let base = entry.modBaseAddr as u64;
                    let size = entry.modBaseSize;
                    let _ = CloseHandle(snap);
                    return Ok((base, size));
                }
                if Module32NextW(snap, &mut entry).is_err() {
                    break;
                }
            }
        }
        let _ = CloseHandle(snap);
    }
    Err(VaultError::LoginFailed(format!("Module '{name}' not found")))
}

// ── Pattern scanning ───────────────────────────────────────────────

/// Exact-byte pattern scan.  Returns offset within `data`.
fn scan_exact(data: &[u8], pattern: &[u8]) -> Option<usize> {
    data.windows(pattern.len())
        .position(|w| w == pattern)
}

/// Wildcard pattern scan (None = any byte).  Returns offset within `data`.
fn scan_wild(data: &[u8], pattern: &[Option<u8>]) -> Option<usize> {
    data.windows(pattern.len()).position(|window| {
        window.iter().zip(pattern.iter()).all(|(&b, pat)| match pat {
            Some(expected) => b == *expected,
            None => true,
        })
    })
}

// ── Bytecode builder ───────────────────────────────────────────────

/// Build the injected bytecode that:
///  1. Checks the flag — skips login if flag != 1
///  2. Saves registers, calls the game's command dispatcher
///  3. Clears flag
///  4. Restores registers
///  5. Executes the original hooked instruction
///  6. Jumps back
fn build_login_bytecode(
    block_addr: u64,
    flag_addr: u64,
    string_struct_addr: u64,
    dat_addr: u64,
    func_addr: u64,
    orig_instr: &[u8],
    ret_addr: u64,
) -> Vec<u8> {
    let mut bc = Vec::with_capacity(256);

    // ── Check flag ──
    // push rax
    bc.push(0x50);
    // mov rax, flag_addr
    bc.extend_from_slice(&[0x48, 0xB8]);
    bc.extend_from_slice(&flag_addr.to_le_bytes());
    // cmp byte [rax], 1
    bc.extend_from_slice(&[0x80, 0x38, 0x01]);
    // pop rax
    bc.push(0x58);
    // jne <skip past login code>
    bc.extend_from_slice(&[0x0F, 0x85]);
    let skip_fixup = bc.len();
    bc.extend_from_slice(&[0x00, 0x00, 0x00, 0x00]); // placeholder

    // ── Login code (only executes when flag == 1) ──
    // push rax, rcx, rdx, r8, r9, r10, r11
    bc.extend_from_slice(&[0x50, 0x51, 0x52, 0x41, 0x50, 0x41, 0x51, 0x41, 0x52, 0x41, 0x53]);
    // sub rsp, 0x28  (shadow space for x64 calling convention)
    bc.extend_from_slice(&[0x48, 0x83, 0xEC, 0x28]);
    // mov r9b, 1
    bc.extend_from_slice(&[0x41, 0xB1, 0x01]);
    // xor r8d, r8d
    bc.extend_from_slice(&[0x45, 0x33, 0xC0]);
    // mov rdx, string_struct_addr
    bc.extend_from_slice(&[0x48, 0xBA]);
    bc.extend_from_slice(&string_struct_addr.to_le_bytes());
    // mov rax, dat_addr
    bc.extend_from_slice(&[0x48, 0xB8]);
    bc.extend_from_slice(&dat_addr.to_le_bytes());
    // mov rcx, [rax]  (dereference to get game client pointer)
    bc.extend_from_slice(&[0x48, 0x8B, 0x08]);
    // mov rax, func_addr
    bc.extend_from_slice(&[0x48, 0xB8]);
    bc.extend_from_slice(&func_addr.to_le_bytes());
    // call rax
    bc.extend_from_slice(&[0xFF, 0xD0]);
    // mov rax, flag_addr
    bc.extend_from_slice(&[0x48, 0xB8]);
    bc.extend_from_slice(&flag_addr.to_le_bytes());
    // mov byte [rax], 0  (clear flag — signals completion)
    bc.extend_from_slice(&[0xC6, 0x00, 0x00]);
    // add rsp, 0x28
    bc.extend_from_slice(&[0x48, 0x83, 0xC4, 0x28]);
    // pop r11, r10, r9, r8, rdx, rcx, rax
    bc.extend_from_slice(&[0x41, 0x5B, 0x41, 0x5A, 0x41, 0x59, 0x41, 0x58, 0x5A, 0x59, 0x58]);

    // ── Fix up jne offset ──
    let skip_target = bc.len();
    let skip_offset = (skip_target as i32) - (skip_fixup as i32) - 4;
    bc[skip_fixup..skip_fixup + 4].copy_from_slice(&skip_offset.to_le_bytes());

    // ── Original instruction (always runs) ──
    bc.extend_from_slice(orig_instr);

    // ── Jump back to return address ──
    bc.push(0xE9);
    let jmp_from = block_addr + bc.len() as u64 + 4; // address after this E9 instruction
    let jmp_offset = (ret_addr as i64 - jmp_from as i64) as i32;
    bc.extend_from_slice(&jmp_offset.to_le_bytes());

    bc
}

/// Build the 32-byte game string struct in memory.
///   offset  0: u64 — pointer to char data
///   offset  8: u64 — 0
///   offset 16: u64 — string length (excl. null)
///   offset 24: u64 — string capacity (excl. null)
fn build_string_struct(data_addr: u64, len: usize) -> [u8; 32] {
    let mut ss = [0u8; 32];
    ss[0..8].copy_from_slice(&data_addr.to_le_bytes());
    // ss[8..16] stays 0
    ss[16..24].copy_from_slice(&(len as u64).to_le_bytes());
    ss[24..32].copy_from_slice(&(len as u64).to_le_bytes());
    ss
}

// ── Public API ─────────────────────────────────────────────────────

/// Log in to a Wizard101 instance using buffer-write injection.
///
/// Credentials are written directly into the game process memory and dispatched
/// through the game's own command handler.  They never appear in any Python-
/// accessible location.
pub fn login_to_instance(hwnd: isize, username: &str, password: &str) -> Result<(), VaultError> {
    // 1. Get PID from window handle
    let mut pid: u32 = 0;
    unsafe {
        GetWindowThreadProcessId(
            windows::Win32::Foundation::HWND(hwnd as *mut c_void),
            Some(&mut pid),
        );
    }
    if pid == 0 {
        return Err(VaultError::LoginFailed("Could not get PID from window handle".into()));
    }

    // 2. Open the game process
    let proc = RemoteProcess::open(pid)?;

    // 3. Find WizardGraphicalClient.exe module
    let (mod_base, mod_size) = find_module(pid, "WizardGraphicalClient.exe")?;

    // 4. Read module memory for pattern scanning
    let module_mem = proc.read(mod_base, mod_size as usize)?;

    // 5. Find the login function via LOGIN_PATTERN
    let login_offset = scan_exact(&module_mem, LOGIN_PATTERN)
        .ok_or_else(|| VaultError::LoginFailed("LOGIN_PATTERN not found".into()))?;
    let login_addr = mod_base + login_offset as u64;

    // Resolve dat (game-client pointer) and func (command dispatcher) via RIP-relative offsets
    //   m+13: 4-byte disp for `mov rcx,[rip+disp]`  →  dat = m+17 + disp
    //   m+18: 4-byte disp for `call rip+disp`        →  func = m+22 + disp
    let t = proc.read(login_addr + 13, 9)?;
    let dat_disp = i32::from_le_bytes(t[0..4].try_into().unwrap());
    let func_disp = i32::from_le_bytes(t[5..9].try_into().unwrap());
    let dat_addr = (login_addr as i64 + 17 + dat_disp as i64) as u64;
    let func_addr = (login_addr as i64 + 22 + func_disp as i64) as u64;

    // 6. Find the hook injection point via HOOK_PATTERN
    let hook_offset = scan_wild(&module_mem, HOOK_PATTERN)
        .ok_or_else(|| VaultError::LoginFailed("HOOK_PATTERN not found".into()))?;
    let hook_addr = mod_base + hook_offset as u64;
    let ret_addr = hook_addr + HOOK_INSTR_LEN as u64;

    // 7. Save original bytes at hook site
    let orig_instr = proc.read(hook_addr, HOOK_INSTR_LEN)?;

    // 8. Build the login command string
    let cmd = format!("login {} {}", username, password);
    let cmd_bytes: Vec<u8> = cmd.bytes().chain(std::iter::once(0)).collect();
    let cmd_len = cmd.len(); // length without null

    // 9. Allocate remote memory
    let str_data_addr = proc.alloc(cmd_bytes.len(), false)?;
    let str_struct_addr = proc.alloc(32, false)?;
    let flag_addr = proc.alloc(8, false)?;
    let block_addr = proc.alloc_near(hook_addr, 512)?;

    // Track allocations for cleanup
    let allocs = [str_data_addr, str_struct_addr, flag_addr, block_addr];
    let cleanup = |proc: &RemoteProcess, restore: bool| {
        if restore {
            let _ = proc.write(hook_addr, &orig_instr);
        }
        for &a in &allocs {
            let _ = proc.free(a);
        }
    };

    // 10. Write string data + struct + flag
    if let Err(e) = proc.write(str_data_addr, &cmd_bytes) {
        cleanup(&proc, false);
        return Err(e);
    }
    let ss = build_string_struct(str_data_addr, cmd_len);
    if let Err(e) = proc.write(str_struct_addr, &ss) {
        cleanup(&proc, false);
        return Err(e);
    }
    if let Err(e) = proc.write(flag_addr, &[0u8; 8]) {
        cleanup(&proc, false);
        return Err(e);
    }

    // 11. Build and write bytecode
    let bytecode = build_login_bytecode(
        block_addr,
        flag_addr,
        str_struct_addr,
        dat_addr,
        func_addr,
        &orig_instr,
        ret_addr,
    );
    if let Err(e) = proc.write(block_addr, &bytecode) {
        cleanup(&proc, false);
        return Err(e);
    }

    // 12. Set the flag to arm the login
    if let Err(e) = proc.write(flag_addr, &[0x01]) {
        cleanup(&proc, false);
        return Err(e);
    }

    // 13. Patch the hook site: E9 <rel32 to block> + 2 NOOPs
    let jmp_offset = (block_addr as i64 - (hook_addr as i64 + 5)) as i32;
    let mut jmp_bytes = vec![0xE9];
    jmp_bytes.extend_from_slice(&jmp_offset.to_le_bytes());
    jmp_bytes.extend_from_slice(&[0x90, 0x90]); // 2 NOOPs to fill 7 bytes
    if let Err(e) = proc.write(hook_addr, &jmp_bytes) {
        cleanup(&proc, false);
        return Err(e);
    }

    // 14. Poll until the flag is cleared (bytecode sets it to 0 after login call)
    let deadline = Instant::now() + Duration::from_secs(10);
    loop {
        thread::sleep(Duration::from_millis(50));

        match proc.read(flag_addr, 1) {
            Ok(data) if data[0] == 0x00 => break,
            Ok(_) => {}
            Err(e) => {
                cleanup(&proc, true);
                return Err(e);
            }
        }

        if Instant::now() > deadline {
            cleanup(&proc, true);
            return Err(VaultError::LoginFailed(
                "Timed out waiting for login bytecode to execute".into(),
            ));
        }
    }

    // 15. Restore original bytes and free allocations
    cleanup(&proc, true);

    Ok(())
}
