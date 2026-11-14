//! The runtime against a stand-in host: renders and calls are recorded, and
//! events go in through the sink the app installs, as levain's bridge does.

use std::ffi::c_void;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use levain_abi::{ABI_VERSION, EventSink, HostApi};

static RENDERS: Mutex<Vec<(u32, String)>> = Mutex::new(Vec::new());
static SINK: Mutex<Option<EventSink>> = Mutex::new(None);

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
extern "C" fn call(_: *mut c_void, _: *const u8, _: usize) {}

fn host(abi_version: u32) -> &'static HostApi {
    Box::leak(Box::new(HostApi {
        abi_version,
        ctx: std::ptr::null_mut(),
        render,
        set_event_sink,
        check_components,
        call,
    }))
}

fn send(event: &str) {
    let sink = SINK
        .lock()
        .unwrap()
        .expect("the app installed no event sink");
    (sink.call)(sink.ctx, event.as_ptr(), event.len());
}

/// The first render after `seen` renders matching `pred`, waiting up to 10 s.
fn wait_render(seen: usize, pred: impl Fn(&serde_json::Value) -> bool) -> serde_json::Value {
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

fn repo() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .unwrap()
}

/// The counter example laid out as a built app: `app.json` and `site-packages`.
fn counter_app() -> tempfile::TempDir {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(
        dir.path().join("app.json"),
        r#"{"app": "counter.app:main", "window": {"title": "Counter"}}"#,
    )
    .unwrap();
    let site = dir.path().join("site-packages");
    std::fs::create_dir(&site).unwrap();
    let repo = repo();
    link(&repo.join("src/briochette"), &site.join("briochette"));
    link(&repo.join("examples/counter/counter"), &site.join("counter"));
    dir
}

fn link(target: &Path, link: &Path) {
    #[cfg(unix)]
    std::os::unix::fs::symlink(target, link).unwrap();
    #[cfg(windows)]
    std::os::windows::fs::symlink_dir(target, link).unwrap();
}

#[test]
fn rejects_another_abi_version() {
    let app = counter_app();
    let err = briochette_cpython::start(app.path().to_owned(), host(ABI_VERSION - 1)).unwrap_err();
    assert!(err.contains("ABI"), "{err}");
}

#[test]
fn counter_renders_then_handles_a_click() {
    let app = counter_app();
    briochette_cpython::start(app.path().to_owned(), host(ABI_VERSION)).unwrap();

    let first = wait_render(0, |f| f.get("root").is_some());
    let root = &first["root"];
    assert_eq!(
        root["c"][0],
        serde_json::json!({"t": "text", "a": {}, "c": ["Count: 0"]})
    );
    assert_eq!(root["c"][1]["a"]["aria-label"], "Increment");
    let event = root["c"][1]["a"]["phx-click"].as_str().unwrap().to_owned();

    let seen = RENDERS.lock().unwrap().len();
    send(&format!(
        r#"{{"type":"click","window":0,"event":"{event}","values":{{}}}}"#
    ));
    let patch = wait_render(seen, |f| f.get("patch").is_some());
    assert_eq!(
        patch,
        serde_json::json!({"patch": [{"op": "replace", "at": [0, 0], "node": "Count: 1"}]})
    );
}
