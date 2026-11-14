//! The runtime against a stand-in host: renders and calls are recorded, and
//! events go in through the sink the app installs, as levain's bridge does.

mod common;

use common::*;
use levain_abi::ABI_VERSION;

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
    link(
        &repo.join("examples/counter/counter"),
        &site.join("counter"),
    );
    dir
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
