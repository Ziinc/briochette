//! Runs a briochette app in embedded CPython, driving levain's host through
//! its C ABI ([`levain_abi::HostApi`]).
//!
//! An app is a directory holding `app.json` (`{"app": "module:function", ...}`)
//! and its Python code, directly or in `site-packages/` (a site directory:
//! its `.pth` files are read). [`start`] runs the
//! app's function on a thread of its own; the built-in `_briochette` module
//! is its only way to the host.

use std::path::{Path, PathBuf};
use std::sync::mpsc::{self, Sender};
use std::sync::{Mutex, Once, OnceLock};

use levain_abi::{ABI_VERSION, EventSink, HostApi};
use pyo3::prelude::*;
use pyo3::types::PyList;

static HOST: OnceLock<&'static HostApi> = OnceLock::new();

/// Where an app may be, in order: `dev` (`BRIOCHETTE_APP`, for development),
/// `app/` beside the executable, then `app/` in the bundle's resources.
pub fn candidates(
    dev: Option<&Path>,
    exe: Option<&Path>,
    resources: Option<&Path>,
) -> Vec<PathBuf> {
    let beside_exe = exe.and_then(Path::parent).map(|dir| dir.join("app"));
    let in_resources = resources.map(|dir| dir.join("app"));
    dev.map(Path::to_path_buf)
        .into_iter()
        .chain(beside_exe)
        .chain(in_resources)
        .collect()
}

/// The first of `candidates` that holds an app (`app.json`).
pub fn find_app(candidates: &[PathBuf]) -> Option<PathBuf> {
    candidates
        .iter()
        .find(|dir| dir.join("app.json").is_file())
        .cloned()
}

/// The `module:function` the app's `app.json` names to start it.
pub fn entry_point(root: &Path) -> Result<(String, String), String> {
    let json = std::fs::read(root.join("app.json"))
        .map_err(|e| format!("cannot read {}: {e}", root.join("app.json").display()))?;
    let config: serde_json::Value =
        serde_json::from_slice(&json).map_err(|e| format!("app.json: {e}"))?;
    let app = config["app"]
        .as_str()
        .ok_or("app.json has no \"app\" (module:function)")?;
    match app.split_once(':') {
        Some((module, function)) if !module.is_empty() && !function.is_empty() => {
            Ok((module.to_owned(), function.to_owned()))
        }
        _ => Err(format!(
            "app.json: \"app\" must be module:function, not {app:?}"
        )),
    }
}

/// Starts the app at `root` on a new `python` thread. One app per process.
pub fn start(root: PathBuf, api: &'static HostApi) -> Result<(), String> {
    if api.abi_version != ABI_VERSION {
        return Err(format!(
            "the host speaks ABI {} and briochette ABI {ABI_VERSION}; rebuild the app",
            api.abi_version
        ));
    }
    let entry = entry_point(&root)?;
    HOST.set(api)
        .map_err(|_| "an app is already running in this process")?;
    std::thread::Builder::new()
        .name("python".into())
        .spawn(move || run(&root, entry))
        .map_err(|e| e.to_string())?;
    Ok(())
}

fn run(root: &Path, (module, function): (String, String)) {
    static INIT: Once = Once::new();
    INIT.call_once(|| {
        pyo3::append_to_inittab!(_briochette);
        Python::initialize();
    });
    Python::attach(|py| {
        let result = (|| -> PyResult<()> {
            // A site dir, so its `.pth` files (editable installs) count too.
            // Strings: the import system skips any other kind of entry.
            let site_packages = root.join("site-packages");
            py.import("site")?
                .call_method1("addsitedir", (site_packages.to_string_lossy(),))?;
            let path = py.import("sys")?.getattr("path")?.cast_into::<PyList>()?;
            path.insert(0, root.to_string_lossy())?;
            py.import(module.as_str())?
                .getattr(function.as_str())?
                .call0()?;
            Ok(())
        })();
        if let Err(err) = result {
            err.print(py);
            notice(&format!("The app stopped: {err}"));
        }
    });
}

/// Replaces window 0 with `text`, so a failed start is not a blank window.
fn notice(text: &str) {
    let frame = serde_json::json!({"root": {
        "t": "div",
        "a": {"class": "size-full flex items-center justify-center p-6 text-sm"},
        "c": [text],
    }});
    render_json(0, frame.to_string().as_bytes());
}

fn render_json(window: u32, json: &[u8]) {
    if let Some(api) = HOST.get() {
        (api.render)(api.ctx, window, json.as_ptr(), json.len());
    }
}

/// Events from the host's UI thread, forwarded to Python on a thread of
/// their own, so the UI thread never waits for the interpreter.
static EVENTS: OnceLock<Mutex<Sender<Vec<u8>>>> = OnceLock::new();
static HANDLER: Mutex<Option<Py<PyAny>>> = Mutex::new(None);

extern "C" fn on_event(_ctx: *mut std::ffi::c_void, json: *const u8, len: usize) {
    // SAFETY: the host passes a buffer valid for `len` bytes for this call.
    let json = unsafe { std::slice::from_raw_parts(json, len) }.to_vec();
    if let Some(events) = EVENTS.get() {
        let _ = events.lock().unwrap().send(json);
    }
}

fn forward(events: mpsc::Receiver<Vec<u8>>) {
    for json in events {
        Python::attach(|py| {
            let handler = HANDLER.lock().unwrap().as_ref().map(|h| h.clone_ref(py));
            if let Some(handler) = handler
                && let Err(err) = handler.call1(py, (String::from_utf8_lossy(&json),))
            {
                err.print(py);
            }
        });
    }
}

/// The app's way to the host. Every function may be called from any thread.
#[pymodule]
mod _briochette {
    use super::*;

    /// Sends window `window` a frame: `{"root": ...}` or `{"patch": [...]}`, as JSON.
    #[pyfunction]
    fn render(window: u32, frame: &str) {
        render_json(window, frame.as_bytes());
    }

    /// A platform call, `{"call", "ref", "args"}` as JSON; its reply comes as an event.
    #[pyfunction]
    fn call(message: &str) {
        if let Some(api) = HOST.get() {
            (api.call)(api.ctx, message.as_ptr(), message.len());
        }
    }

    /// Calls `handler` with each host event's JSON, on a thread of its own.
    #[pyfunction]
    fn set_event_handler(handler: Py<PyAny>) -> PyResult<()> {
        *HANDLER.lock().unwrap() = Some(handler);
        let Some(api) = HOST.get() else {
            return Err(pyo3::exceptions::PyRuntimeError::new_err(
                "not running in a host",
            ));
        };
        if EVENTS.get().is_none() {
            let (tx, rx) = mpsc::channel();
            if EVENTS.set(Mutex::new(tx)).is_ok() {
                std::thread::Builder::new()
                    .name("python-events".into())
                    .spawn(move || forward(rx))?;
                let sink = EventSink {
                    ctx: std::ptr::null_mut(),
                    call: on_event,
                };
                (api.set_event_sink)(api.ctx, sink);
            }
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn app(json: &str) -> tempfile::TempDir {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("app.json"), json).unwrap();
        dir
    }

    #[test]
    fn candidates_in_order_dev_then_beside_exe_then_resources() {
        let found = candidates(
            Some(Path::new("/dev/app")),
            Some(Path::new("/opt/x/bin/host")),
            Some(Path::new("/opt/x/res")),
        );
        let expected: Vec<PathBuf> = vec![
            "/dev/app".into(),
            "/opt/x/bin/app".into(),
            "/opt/x/res/app".into(),
        ];
        assert_eq!(found, expected);
        assert_eq!(candidates(None, None, None), Vec::<PathBuf>::new());
    }

    #[test]
    fn finds_the_first_dir_with_an_app() {
        let empty = tempfile::tempdir().unwrap();
        let a = app("{}");
        let b = app("{}");
        let found = find_app(&[empty.path().into(), a.path().into(), b.path().into()]);
        assert_eq!(found.as_deref(), Some(a.path()));
        assert_eq!(find_app(&[empty.path().into()]), None);
    }

    #[test]
    fn entry_point_from_app_json() {
        let dir = app(r#"{"app": "counter.app:main"}"#);
        assert_eq!(
            entry_point(dir.path()),
            Ok(("counter.app".into(), "main".into()))
        );
    }

    #[test]
    fn entry_point_errors_name_the_problem() {
        assert!(
            entry_point(app("{}").path())
                .unwrap_err()
                .contains("module:function")
        );
        assert!(
            entry_point(app(r#"{"app": "main"}"#).path())
                .unwrap_err()
                .contains("\"main\"")
        );
        assert!(
            entry_point(tempfile::tempdir().unwrap().path())
                .unwrap_err()
                .contains("app.json")
        );
    }
}
