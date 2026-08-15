use async_net::TcpStream;
use smol::io::{AsyncReadExt, AsyncWriteExt};
use smol::unblock;
use std::time::Duration;

use crate::enums::{Country, Game, Platform};
use crate::errors::WizPatchError;

#[derive(Debug, Clone)]
pub struct PatchUrls {
    pub file_list_url: String,
    pub base_url: String,
}

/// Speaks the patch server's binary handshake and parses the two URLs out of
/// the second packet. Mirrors `wizdiff.webdriver.WebDriver.get_patch_urls`.
pub async fn get_patch_urls(
    game: Game,
    platform: Platform,
    country: Country,
) -> Result<PatchUrls, WizPatchError> {
    let addr = format!("{}:{}", game.host(country), platform.port());
    let mut stream = TcpStream::connect(&addr).await?;

    let mut request = [0u8; 40];
    request[..11].copy_from_slice(&[
        0x0D, 0xF0, 0x24, 0x00, 0x00, 0x00, 0x00, 0x00, 0x08, 0x01, 0x20,
    ]);
    stream.write_all(&request).await?;

    let mut discard = [0u8; 4096];
    let _ = stream.read(&mut discard).await?;

    let mut data = vec![0u8; 4096];
    let n = stream.read(&mut data).await?;
    data.truncate(n);

    let file_list_idx = find(&data, b"http")
        .ok_or_else(|| WizPatchError::Protocol("no http URL in response".into()))?;
    let base_idx = rfind(&data, b"http")
        .ok_or_else(|| WizPatchError::Protocol("no base http URL in response".into()))?;

    Ok(PatchUrls {
        file_list_url: read_pascal_url(&data, file_list_idx.saturating_sub(2))?,
        base_url: read_pascal_url(&data, base_idx.saturating_sub(2))?,
    })
}

fn find(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    haystack
        .windows(needle.len())
        .position(|w| w == needle)
}

fn rfind(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    haystack
        .windows(needle.len())
        .rposition(|w| w == needle)
}

fn read_pascal_url(data: &[u8], start: usize) -> Result<String, WizPatchError> {
    if start + 2 > data.len() {
        return Err(WizPatchError::Protocol("URL length out of bounds".into()));
    }
    let len = u16::from_le_bytes([data[start], data[start + 1]]) as usize;
    let str_start = start + 2;
    let str_end = str_start + len;
    if str_end > data.len() {
        return Err(WizPatchError::Protocol("URL string out of bounds".into()));
    }
    String::from_utf8(data[str_start..str_end].to_vec()).map_err(Into::into)
}

/// Builds a connection-pooling ureq agent. Share one across many downloads to
/// keep HTTP keep-alive sockets reusable.
///
/// The idle-connection caps are set high on purpose: with thousands of tiny
/// files the per-request TLS handshake dominates, so we want finished sockets
/// kept warm for reuse rather than torn down and re-dialed for the next file.
pub fn build_agent() -> ureq::Agent {
    ureq::AgentBuilder::new()
        .timeout_connect(Duration::from_secs(30))
        .timeout_read(Duration::from_secs(120))
        .max_idle_connections(256)
        .max_idle_connections_per_host(256)
        .user_agent(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) \
             Gecko/20100101 Firefox/91.0",
        )
        .build()
}

/// HTTP GET against the patch CDN with a shared agent. Optional byte range.
/// Buffers the response fully — use [`download_to_file`] for large files.
pub async fn get_url_data_with(
    agent: &ureq::Agent,
    url: &str,
    range: Option<(u64, u64)>,
) -> Result<Vec<u8>, WizPatchError> {
    let agent = agent.clone();
    let url = url.to_string();
    unblock(move || {
        let mut req = agent.get(&url);
        if let Some((start, end)) = range {
            req = req.set("Range", &format!("bytes={start}-{end}"));
        }
        let resp = req
            .call()
            .map_err(|e| WizPatchError::Http(e.to_string()))?;
        let mut buf = Vec::new();
        resp.into_reader()
            .read_to_end(&mut buf)
            .map_err(WizPatchError::Io)?;
        Ok(buf)
    })
    .await
}

/// Convenience: builds a one-shot agent. Prefer [`get_url_data_with`] for any
/// batch of requests.
pub async fn get_url_data(
    url: &str,
    range: Option<(u64, u64)>,
) -> Result<Vec<u8>, WizPatchError> {
    let agent = build_agent();
    get_url_data_with(&agent, url, range).await
}

/// Maximum number of attempts (initial try + resumes) for one file.
const DOWNLOAD_ATTEMPTS: u32 = 5;

/// True for transient HTTP statuses worth retrying. A plain `404`/`410` (KI
/// lists a file it doesn't actually host) is *not* retryable and surfaces as a
/// failure immediately.
fn is_retryable_status(code: u16) -> bool {
    code == 408 || code == 429 || (500..600).contains(&code)
}

/// Streams an HTTP GET directly into a file on disk in fixed-size chunks.
/// Constant memory regardless of file size. Creates parent directories.
///
/// KI's CDN frequently cuts off long-running transfers mid-body (the largest
/// `.wad`s fail with "response body closed before all bytes were read"). To
/// survive that, a truncated or dropped transfer is retried with a
/// `Range: bytes=<written>-` header so we resume from the partial file instead
/// of refetching the whole thing. Permanent HTTP errors (e.g. 404) are not
/// retried.
///
/// If `expected_size` is given, a transfer that ends cleanly but short of that
/// many bytes is treated as a failed attempt (and retried), so a truncated
/// CDN object can never be mistaken for a complete file.
///
/// If `progress` is provided, each chunk's byte count is added to it as it's
/// written, so a sampler can observe live throughput rather than waiting for
/// the whole file to land.
pub async fn download_to_file(
    agent: &ureq::Agent,
    url: &str,
    dest: std::path::PathBuf,
    expected_size: Option<u64>,
    progress: Option<std::sync::Arc<std::sync::atomic::AtomicU64>>,
) -> Result<u64, WizPatchError> {
    use std::io::{Read, Write};
    use std::sync::atomic::Ordering;

    let agent = agent.clone();
    let url = url.to_string();
    unblock(move || -> Result<u64, WizPatchError> {
        if let Some(parent) = dest.parent() {
            std::fs::create_dir_all(parent)?;
        }

        // Bytes already on disk and counted in `progress`. Carried across
        // attempts so a resume picks up where the last one was cut off.
        let mut written: u64 = 0;
        let mut last_err: Option<WizPatchError> = None;

        for attempt in 0..DOWNLOAD_ATTEMPTS {
            if attempt > 0 {
                // Linear backoff; these stalls are server-side, so a short
                // pause before resuming is plenty.
                std::thread::sleep(Duration::from_millis(300 * attempt as u64));
            }

            let mut req = agent.get(&url);
            if written > 0 {
                req = req.set("Range", &format!("bytes={written}-"));
            }

            let resp = match req.call() {
                Ok(r) => r,
                // We already hold every byte the server has.
                Err(ureq::Error::Status(416, _)) => return Ok(written),
                // Permanent failure (404/403/…): don't waste retries on it.
                Err(ureq::Error::Status(code, _)) if !is_retryable_status(code) => {
                    return Err(WizPatchError::Http(format!("HTTP {code}")));
                }
                Err(e) => {
                    last_err = Some(WizPatchError::Http(e.to_string()));
                    continue;
                }
            };

            // A resume is only valid if the server honored the range with a
            // 206. If it answered 200 it's resending from the top, so discard
            // the partial file (and its already-counted bytes) and restart.
            let resuming = written > 0 && resp.status() == 206;
            let mut file = if resuming {
                std::fs::OpenOptions::new().append(true).open(&dest)?
            } else {
                if written > 0 {
                    if let Some(p) = &progress {
                        p.fetch_sub(written, Ordering::Relaxed);
                    }
                    written = 0;
                }
                std::fs::File::create(&dest)?
            };

            let mut reader = resp.into_reader();
            let mut buf = vec![0u8; 64 * 1024];
            let mut stream_err: Option<std::io::Error> = None;
            loop {
                match reader.read(&mut buf) {
                    Ok(0) => break,
                    Ok(n) => {
                        // A local write failure is not the server's fault and
                        // won't be cured by retrying — fail hard.
                        file.write_all(&buf[..n])?;
                        written += n as u64;
                        if let Some(p) = &progress {
                            p.fetch_add(n as u64, Ordering::Relaxed);
                        }
                    }
                    Err(e) => {
                        stream_err = Some(e);
                        break;
                    }
                }
            }

            if let Some(e) = stream_err {
                // Truncated mid-body. Keep what landed and resume next attempt.
                let _ = file.flush();
                last_err = Some(WizPatchError::Io(e));
                continue;
            }

            // The body ended without a transport error. If it stopped short of
            // the manifest size (e.g. an edge object served with chunked
            // encoding and no Content-Length to trip ureq's own check), don't
            // accept the partial file — resume on the next attempt.
            if let Some(exp) = expected_size {
                if written < exp {
                    let _ = file.flush();
                    last_err = Some(WizPatchError::Http(format!(
                        "short download: {written} of {exp} bytes"
                    )));
                    continue;
                }
            }

            file.flush()?;
            return Ok(written);
        }

        Err(last_err
            .unwrap_or_else(|| WizPatchError::Http("download failed after retries".into())))
    })
    .await
}
