//! The briochette host: levain with CPython as its runtime.

use levain::{App, AppPaths, Runtime, WindowConfig, levain_abi::HostApi};

#[derive(Default)]
struct CPython {
    resources: std::sync::Mutex<Option<std::path::PathBuf>>,
}

impl Runtime for CPython {
    fn locate(&self, paths: &AppPaths) -> Result<App, String> {
        let root = find(paths)?;
        *self.resources.lock().unwrap() = paths.resources.clone();
        let json = std::fs::read(root.join("app.json")).unwrap_or_default();
        let name = briochette_cpython::entry_point(&root)?.0;
        Ok(App {
            root,
            name,
            window: WindowConfig::from_app_json(&json),
            cli: levain::cli_from_app_json(&json),
        })
    }

    fn start(&self, app: App, api: &'static HostApi) -> Result<(), String> {
        let resources = self.resources.lock().unwrap().clone();
        let exe = std::env::current_exe().ok();
        let beside_exe = exe.as_deref().and_then(std::path::Path::parent);
        let home = briochette_cpython::python_home(&app.root, &[resources.as_deref(), beside_exe]);
        briochette_cpython::start(app.root, home, api)
    }
}

/// On desktop: `BRIOCHETTE_APP`, beside the executable, or in the bundle.
#[cfg(not(mobile))]
fn find(paths: &AppPaths) -> Result<std::path::PathBuf, String> {
    let dev = std::env::var_os("BRIOCHETTE_APP").map(std::path::PathBuf::from);
    let candidates = briochette_cpython::candidates(
        dev.as_deref(),
        paths.exe.as_deref(),
        paths.resources.as_deref(),
    );
    briochette_cpython::find_app(&candidates)
        .ok_or_else(|| format!("no app.json in any of {candidates:?}"))
}

/// On phones: the app is embedded in the host library, and unpacked once
/// per build into the app's data directory.
#[cfg(mobile)]
fn find(paths: &AppPaths) -> Result<std::path::PathBuf, String> {
    let data = paths.data.as_ref().ok_or("no data directory")?;
    levain::mobile::unpack(data, |_| Ok(()))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    levain::run(CPython::default(), tauri::generate_context!());
}
