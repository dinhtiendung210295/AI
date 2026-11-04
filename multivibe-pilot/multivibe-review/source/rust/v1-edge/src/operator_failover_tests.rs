// Local acceptance tests: fake tokens, loopback upstreams, no user configuration.
use super::*;
use axum::routing::{get, post};
use axum::{Json, Router};
use std::sync::{Arc, Mutex};
use std::sync::atomic::{AtomicBool, Ordering};
use tokio::task::JoinHandle;

async fn serve(router: Router) -> (String, JoinHandle<()>) {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let task = tokio::spawn(async move { axum::serve(listener, router).await.unwrap() });
    (format!("http://{address}"), task)
}

#[tokio::test]
async fn websocket_delta_keeps_prior_conversation_context_acceptance() {
    use futures_util::{SinkExt, StreamExt};
    use tokio_tungstenite::tungstenite::client::IntoClientRequest;
    let seen = Arc::new(Mutex::new(Vec::<Value>::new()));
    let recorded = seen.clone();
    let mock = Router::new()
        .route("/backend-api/codex/models", get(|| async { Json(json!({"models":[{"slug":"gpt-5.6-sol"}]})) }))
        .route("/backend-api/codex/responses", post(move |Json(body): Json<Value>| {
            let recorded = recorded.clone();
            async move {
                recorded.lock().unwrap().push(body);
                let event = json!({"type":"response.completed","response":{"id":"resp-first","object":"response","status":"completed","model":"gpt-5.6-sol","output":[],"usage":{"input_tokens":1,"output_tokens":1,"total_tokens":2}}});
                Response::builder().header("content-type","text/event-stream").body(Body::from(format!("event: response.completed\ndata: {event}\n\ndata: [DONE]\n\n"))).unwrap()
            }
        }));
    let (upstream, upstream_task) = serve(mock).await;
    let root = std::env::temp_dir().join(format!("multivibe-ws-{}", uuid::Uuid::new_v4()));
    fs::create_dir_all(&root).await.unwrap();
    let account = Account { id:"fake".into(), provider:Some("openai".into()), access_token:"fake-token".into(), enabled:true, ..Default::default() };
    let store = root.join("accounts.json");
    fs::write(&store, serde_json::to_vec(&StoreFile { accounts:vec![account], ..Default::default() }).unwrap()).await.unwrap();
    let mut config = EdgeConfig::default();
    config.store_path = store; config.jobs_path = root.join("jobs.json");
    config.models_cache_path = Some(root.join("models.json")); config.chatgpt_base_url = upstream;
    config.configured_api_keys = vec![("ws-test".into(),"fake-local-key".into())];
    let state = EdgeState::new(config).await.unwrap();
    let (edge, edge_task) = serve(build_router(state)).await;
    let mut request = format!("{}/v1/responses",edge.replace("http://","ws://")).into_client_request().unwrap();
    request.headers_mut().insert("authorization", "Bearer fake-local-key".parse().unwrap());
    let (mut socket, _) = tokio_tungstenite::connect_async(request).await.unwrap();
    for frame in [
        json!({"type":"response.create","model":"gpt-5.6-sol","input":[{"role":"user","content":"remember NONCE-729"}]}),
        json!({"type":"response.create","model":"gpt-5.6-sol","previous_response_id":"resp-first","input":[{"role":"user","content":"what was the nonce?"}]}),
    ] {
        socket.send(tokio_tungstenite::tungstenite::Message::Text(frame.to_string().into())).await.unwrap();
        loop {
            let message = tokio::time::timeout(Duration::from_secs(5),socket.next()).await.unwrap().unwrap().unwrap();
            if let tokio_tungstenite::tungstenite::Message::Text(text) = message {
                let value: Value = serde_json::from_str(&text).unwrap();
                if value["type"] == "response.completed" { break; }
                assert_ne!(value["type"], "error", "websocket error: {value}");
            }
        }
    }
    let calls = seen.lock().unwrap().clone();
    socket.close(None).await.unwrap(); edge_task.abort(); upstream_task.abort();
    let _ = fs::remove_dir_all(root).await;
    assert_eq!(calls.len(),2);
    assert!(calls[1]["previous_response_id"] == "resp-first" || calls[1]["input"].to_string().contains("NONCE-729"),
        "prior response reference and prior history both missing in the second upstream request");
}

#[tokio::test]
async fn quota_failover_preserves_full_history_and_tool_output() {
    check_failover(false).await;
}

#[tokio::test]
async fn http_sse_quota_failover_preserves_history_and_delivers_completion() {
    check_failover(true).await;
}

async fn check_failover(sse: bool) {
    use axum::response::IntoResponse;
    let seen = Arc::new(Mutex::new(Vec::<(String, Value)>::new()));
    let recorded = seen.clone();
    let exhausted = Arc::new(AtomicBool::new(false));
    let upstream_exhausted = exhausted.clone();
    let mock = Router::new()
        .route("/backend-api/codex/models", get(|| async {
            Json(json!({"models":[{"slug":"gpt-5.6-sol","display_name":"Mock"}]}))
        }))
        .route("/backend-api/codex/responses", post(move |headers: HeaderMap, Json(body): Json<Value>| {
            let recorded = recorded.clone();
            let exhausted = upstream_exhausted.clone();
            async move {
                let token = headers.get("authorization").unwrap().to_str().unwrap().to_owned();
                recorded.lock().unwrap().push((token.clone(), body));
                if token == "Bearer fake-a" || exhausted.load(Ordering::SeqCst) {
                    return (StatusCode::TOO_MANY_REQUESTS, Json(json!({"error":{"type":"usage_limit_reached","message":"mock quota exhausted"}}))).into_response();
                }
                let result = json!({"id":"resp-mock","object":"response","model":"gpt-5.6-sol","status":"completed","output":[{"type":"message","role":"assistant","content":[{"type":"output_text","text":"mock-ok"}]}],"usage":{"input_tokens":1,"output_tokens":1,"total_tokens":2}});
                if sse {
                    let delta = json!({"type":"response.output_text.delta","delta":"mock-ok","output_index":0,"content_index":0});
                    let done = json!({"type":"response.completed","response":result});
                    Response::builder().header("content-type","text/event-stream").body(Body::from(format!("event: response.output_text.delta\ndata: {delta}\n\nevent: response.completed\ndata: {done}\n\ndata: [DONE]\n\n"))).unwrap()
                } else { (StatusCode::OK, Json(result)).into_response() }
            }
        }));
    let (upstream, upstream_task) = serve(mock).await;
    let root = std::env::temp_dir().join(format!("multivibe-operator-{}", uuid::Uuid::new_v4()));
    fs::create_dir_all(&root).await.unwrap();
    let accounts = vec![
        Account { id:"a".into(), provider:Some("openai".into()), access_token:"fake-a".into(), enabled:true, priority:Some(0), ..Default::default() },
        Account { id:"b".into(), provider:Some("openai".into()), access_token:"fake-b".into(), enabled:true, priority:Some(1), ..Default::default() },
    ];
    let store = root.join("accounts.json");
    fs::write(&store, serde_json::to_vec(&StoreFile { accounts, ..Default::default() }).unwrap()).await.unwrap();
    let mut config = EdgeConfig::default();
    config.store_path = store;
    config.jobs_path = root.join("jobs.json");
    config.models_cache_path = Some(root.join("models.json"));
    config.chatgpt_base_url = upstream;
    config.configured_api_keys = vec![("operator-test".into(),"fake-local-key".into())];
    config.upstream_timeout = Duration::from_secs(3);
    config.max_upstream_retries = 0;
    let state = EdgeState::new(config).await.unwrap();
    let (edge, edge_task) = serve(build_router(state)).await;
    let client = reqwest::Client::new();
    let first = json!({"model":"gpt-5.6-sol","stream":sse,"input":[{"role":"user","content":"remember NONCE-operator-729"}],"instructions":"Keep the nonce"});
    let response = client.post(format!("{edge}/v1/responses")).bearer_auth("fake-local-key").json(&first).send().await.unwrap();
    assert!(response.status().is_success(), "{}", response.text().await.unwrap());
    let reply = response.text().await.unwrap();
    assert!(reply.contains("mock-ok"));
    if sse { assert_eq!(reply.matches("event: response.completed").count(), 1); }
    let second = json!({"model":"gpt-5.6-sol","stream":sse,"instructions":"Keep the nonce","input":[{"role":"user","content":"remember NONCE-operator-729"},{"type":"function_call","call_id":"call-mock","name":"mock_read","arguments":"{}"},{"type":"function_call_output","call_id":"call-mock","output":"TOOL-RESULT-481"},{"role":"user","content":"continue"}]});
    let response = client.post(format!("{edge}/v1/responses")).bearer_auth("fake-local-key").json(&second).send().await.unwrap();
    assert!(response.status().is_success(), "{}", response.text().await.unwrap());
    let reply = response.text().await.unwrap();
    assert!(reply.contains("mock-ok"));
    if sse { assert_eq!(reply.matches("event: response.completed").count(), 1); }
    let before = seen.lock().unwrap().len();
    let unauthorized = client.post(format!("{edge}/v1/responses")).json(&first).send().await.unwrap();
    assert_eq!(unauthorized.status(), StatusCode::UNAUTHORIZED);
    let calls = seen.lock().unwrap().clone();
    assert_eq!(calls.len(), before, "unauthorized request reached upstream");
    assert_eq!(calls.len(), 3, "unexpected replay count: {calls:?}");
    assert_eq!(calls[0].0, "Bearer fake-a");
    assert_eq!(calls[1].0, "Bearer fake-b");
    assert_eq!(calls[0].1["input"], calls[1].1["input"]);
    assert_eq!(calls[2].0, "Bearer fake-b");
    assert_eq!(calls[2].1["input"], second["input"]);
    assert_eq!(calls[2].1["instructions"], second["instructions"]);
    exhausted.store(true, Ordering::SeqCst);
    let exhausted_response = client.post(format!("{edge}/v1/responses")).bearer_auth("fake-local-key").json(&second).send().await.unwrap();
    assert_eq!(exhausted_response.status(), StatusCode::TOO_MANY_REQUESTS);
    assert!(seen.lock().unwrap().len() <= 5, "quota exhaustion looped instead of stopping");
    edge_task.abort(); upstream_task.abort();
    let _ = fs::remove_dir_all(root).await;
}
