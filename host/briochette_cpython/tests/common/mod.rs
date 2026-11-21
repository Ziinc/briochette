//! A stand-in for levain's host: renders and platform calls are recorded,
//! and events go in through the sink the app installs, as levain's bridge does.
#![allow(dead_code)]

use std::ffi::c_void;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use levain_abi::{EventSink, HostApi};

pub static RENDERS: Mutex<Vec<(u32, String)>> = Mutex::new(Vec::new());
pub static CALLS: Mutex<Vec<serde_json::Value>> = Mutex::new(Vec::new());
pub static SINK: Mutex<Option<EventSink>> = Mutex::new(None);

extern "C" fn render(_: *mut c_void, window: u32, json: *const u8, len: usize) {
    let json = unsafe { std::slice::from_raw_parts(json, len) };
    RENDERS
        .lock()
        .unwrap()
        .push((window, String::from_utf8(json.to_vec()).unwrap()));
}
extern "C" fn set_event_sink(_: *mut c_void, sink: EventSink) {
    *SINK.lock().unwrap() = Some(sink);
}
extern "C" fn check_components(_: *mut c_void, _: *const u8, _: usize) -> bool {
    true
}
extern "C" fn call(_: *mut c_void, json: *const u8, len: usize) {
    let json = unsafe { std::slice::from_raw_parts(json, len) };
    CALLS
        .lock()
        .unwrap()
        .push(serde_json::from_slice(json).unwrap());
}

pub fn host(abi_version: u32) -> &'static HostApi {
    Box::leak(Box::new(HostApi {
        abi_version,
        ctx: std::ptr::null_mut(),
        render,
        set_event_sink,
        check_components,
        call,
    }))
}

pub fn send(event: &str) {
    let sink = SINK
        .lock()
        .unwrap()
        .expect("the app installed no event sink");
    (sink.call)(sink.ctx, event.as_ptr(), event.len());
}

/// The first render after `seen` renders matching `pred`, waiting up to 10 s.
pub fn wait_render(seen: usize, pred: impl Fn(&serde_json::Value) -> bool) -> serde_json::Value {
    let deadline = Instant::now() + Duration::from_secs(10);
    loop {
        if let Some(frame) = RENDERS
            .lock()
            .unwrap()
            .iter()
            .skip(seen)
            .map(|(_, json)| serde_json::from_str(json).unwrap())
            .find(|frame| pred(frame))
        {
            return frame;
        }
        assert!(
            Instant::now() < deadline,
            "no such render: {:?}",
            RENDERS.lock().unwrap()
        );
        std::thread::sleep(Duration::from_millis(20));
    }
}

pub fn repo() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap()
}

/// The first platform call named `name`, waiting up to 10 s.
pub fn wait_call(name: &str) -> serde_json::Value {
    let deadline = Instant::now() + Duration::from_secs(10);
    loop {
        if let Some(call) = CALLS.lock().unwrap().iter().find(|c| c["call"] == name) {
            return call.clone();
        }
        assert!(
            Instant::now() < deadline,
            "no {name} call: {:?}",
            CALLS.lock().unwrap()
        );
        std::thread::sleep(Duration::from_millis(20));
    }
}

/// An app directory: `app.json` and the given files under `site-packages/`,
/// with briochette linked in.
pub fn app(app_json: &str, files: &[(&str, &str)]) -> tempfile::TempDir {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("app.json"), app_json).unwrap();
    let site = dir.path().join("site-packages");
    std::fs::create_dir(&site).unwrap();
    link(&repo().join("src/briochette"), &site.join("briochette"));
    for (name, text) in files {
        std::fs::write(site.join(name), text).unwrap();
    }
    dir
}

pub fn link(target: &Path, link: &Path) {
    #[cfg(unix)]
    std::os::unix::fs::symlink(target, link).unwrap();
    #[cfg(windows)]
    std::os::windows::fs::symlink_dir(target, link).unwrap();
}
