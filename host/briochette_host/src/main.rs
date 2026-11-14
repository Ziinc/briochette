//! The briochette host: levain with CPython as its runtime.

use levain::{App, AppPaths, Runtime, WindowConfig, levain_abi::HostApi};

struct CPython;

impl Runtime for CPython {
    fn locate(&self, paths: &AppPaths) -> Result<App, String> {
        let dev = std::env::var_os("BRIOCHETTE_APP").map(std::path::PathBuf::from);
        let candidates = briochette_cpython::candidates(
            dev.as_deref(),
            paths.exe.as_deref(),
            paths.resources.as_deref(),
        );
        let root = briochette_cpython::find_app(&candidates)
            .ok_or_else(|| format!("no app.json in any of {candidates:?}"))?;
        let json = std::fs::read(root.join("app.json")).unwrap_or_default();
        let name = briochette_cpython::entry_point(&root)?.0;
        Ok(App {
            root,
            name,
            window: WindowConfig::from_app_json(&json),
        })
    }

    fn start(&self, app: App, api: &'static HostApi) -> Result<(), String> {
        briochette_cpython::start(app.root, api)
    }
}

fn main() {
    levain::run(CPython, tauri::generate_context!());
}
