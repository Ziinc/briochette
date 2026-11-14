//! The process ends when the app's main function does, with its exit code,
//! and the app sees the process's arguments. A process of its own: one
//! interpreter per process.

mod common;

use common::*;
use levain_abi::ABI_VERSION;

const APP: &str = r#"
import json, sys
import _briochette

def main():
    _briochette.render(0, json.dumps({"root": {"t": "text", "a": {}, "c": [json.dumps(sys.argv)]}}))
    sys.exit(3)
"#;

#[test]
fn sys_exit_becomes_app_exit_and_argv_is_the_process_args() {
    let dir = app(r#"{"app": "exiting:main"}"#, &[("exiting.py", APP)]);
    briochette_cpython::start(dir.path().to_owned(), host(ABI_VERSION)).unwrap();

    let frame = wait_render(0, |f| f.get("root").is_some());
    let argv: Vec<String> = serde_json::from_str(frame["root"]["c"][0].as_str().unwrap()).unwrap();
    assert_eq!(argv, std::env::args().collect::<Vec<_>>());

    assert_eq!(
        wait_call("app.exit")["args"],
        serde_json::json!({"code": 3})
    );
}
