use anyhow::Result;
use log_ingestor::{config::Config, mcp_server};
use std::sync::Arc;

#[tokio::main]
async fn main() -> Result<()> {
    let _ = dotenvy::from_filename(".env").or_else(|_| dotenvy::from_filename("log_ingestor/.env"));
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or(
        if cfg!(debug_assertions) {
            "debug"
        } else {
            "info"
        },
    ))
    .init();
    mcp_server::serve(Arc::new(Config::from_env())).await
}
