use uuid::Uuid;
use crate::types::LogTemplate;

pub fn build_template(normalized: String) -> LogTemplate {
    LogTemplate {
        id: Uuid::new_v4(),
        template: normalized,
    }
}
